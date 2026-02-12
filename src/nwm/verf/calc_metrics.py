import gc
import warnings
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from teehr.classes.duckdb_joined_parquet import DuckDBJoinedParquet

import nwm.eval.metric_functions as mf

from .nwm_configs import ForecastConfig
from .settings import dict_nwm_eval_metrics, dict_teehr_metrics

warnings.filterwarnings("ignore")

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Suppress specific logging messages from the metric functions library
logging.getLogger("nwm.eval.metric_functions").setLevel(logging.ERROR)


def check_metrics(metrics: list, mapping: dict, mode: str = "nwm.eval"):
    """Validate a list of metric names against a known mapping (here a metrics library).

    Args:
        metrics: List of metric names to validate.
        mapping: A dictionary mapping known metric keys to values.
        mode: Either "teehr" or "nwm.eval", determining how to map supported metrics.

    Returns:
        A filtered and mapped list of supported metrics.

    """
    mode = mode.lower()  # Make mode case-insensitive
    if mode not in ["teehr", "nwm.eval"]:
        raise ValueError(
            f"Unsupported mode: {mode}. Supported modes are 'nwm.eval' and 'teehr'."
        )

    mapped_metrics = []
    unsupported_metrics = []

    for m in metrics:
        if m in mapping.values():
            if mode == "teehr":
                mapped_metrics.append(m)
            elif mode == "nwm.eval":
                # Get key from value (reverse lookup)
                key = next((k for k, v in mapping.items() if v == m), None)
                if key is not None:
                    mapped_metrics.append(key)
        elif m in mapping.keys():
            mapped_metrics.append(mapping[m] if mode == "teehr" else m)
        else:
            unsupported_metrics.append(m)

    if unsupported_metrics:
        logger.warning(
            f"The following metrics are not supported by {mode}: {unsupported_metrics}. Skipping them."
        )

    return mapped_metrics


# function to calculate TEEHR metrics
def calc_teehr_metrics(
    pairs: Path,
    geometry: Path,
    metrics: list[str],
) -> pd.DataFrame:
    # paired data parquet
    joined_data = DuckDBJoinedParquet(
        joined_parquet_filepath=pairs, geometry_filepath=geometry
    )

    # compute metrics
    gdf_all = joined_data.get_metrics(
        group_by=["primary_location_id", "lead_group"],
        order_by=["primary_location_id", "lead_group"],
        include_metrics=metrics,
        include_geometry=False,
    )

    return gdf_all


# function to calculate nwm.eval metrics (i.e, metrics used by nwm-cal)
def func_calc_metrics(
    df: pd.DataFrame, metrics: list[str], lead_time: int, thresholds: list = [0.9, 0.9]
) -> pd.DataFrame:
    if len(df) < 2:  # personr calculation requires data length of at least 2
        logger.warning(
            f"Insufficient data for metric calculation, lead time: {lead_time}, "
            f"location: {df['primary_location_id'].unique()[0]} (data length: {len(df)})"
        )
        return pd.DataFrame()
    else:
        df1 = df.copy(deep=True)
        df1 = df1.set_index("value_time", inplace=False)
        values = mf.calculate_metrics(
            pd.Series(df1["primary_value"]),
            pd.Series(df1["secondary_value"]),
            metrics,
            thresholds[0],
            thresholds[1],
        )
        values["lead_group"] = df1["lead_group"].unique()[0]
        values["primary_location_id"] = df1["primary_location_id"].unique()[0]

        return pd.DataFrame([values])


def calc_nwm_eval_metrics(
    pairs: Path,
    metrics: list[str],
    thresholds: Optional[list] = [0.9, 0.9],
) -> pd.DataFrame:
    # read in paired data parquet
    df_pairs = pd.read_parquet(pairs)

    # get all the lead times
    lead_times = df_pairs["lead_group"].unique()

    # get all locations
    locations = df_pairs["primary_location_id"].unique()

    # drop unneeded columns
    df_pairs = df_pairs[
        [
            "primary_location_id",
            "lead_group",
            "value_time",
            "primary_value",
            "secondary_value",
        ]
    ]

    # sort by location then lead time
    df_pairs = df_pairs.sort_values(["primary_location_id", "lead_group"])

    # use multiprocessing to compute metrics
    with Pool(cpu_count() - 1) as pool:
        results = []
        for l1 in locations:
            df1 = df_pairs[df_pairs["primary_location_id"] == l1]
            for l2 in lead_times:
                df2 = df1[df1["lead_group"] == l2]
                results.append(
                    pool.apply_async(
                        func_calc_metrics, args=(df2, metrics, l2, thresholds)
                    )
                )

        new_dfs = [result.get() for result in results]
        df_metrics = pd.concat(new_dfs, ignore_index=True)

    return df_metrics


def calc_metrics_group(conf: dict, pair_file: Path, geofile: Path) -> pd.DataFrame:
    # metrics to be calculated
    conf_met = conf["metrics"]
    metrics = conf_met["metric_subset"]
    if not metrics or metrics == ["all"] or metrics == "all":
        metrics = (
            list(dict_teehr_metrics.keys())
            if conf_met["library"] == "teehr"
            else list(dict_nwm_eval_metrics.keys())
        )

    # exclude metrics as requested
    metrics_exclude = conf_met["metric_exclude"] or []
    if metrics_exclude:
        metrics = [m1 for m1 in metrics if m1 not in metrics_exclude]

    # check if metrics are supported by the library
    dict_metrics = (
        dict_teehr_metrics if conf_met["library"] == "teehr" else dict_nwm_eval_metrics
    )
    metrics = check_metrics(metrics, dict_metrics, mode=conf_met["library"])

    # get all data pairs and raw lead times
    df0 = pd.read_parquet(pair_file)
    leads0 = df0["lead_time"].unique()
    leads0.sort()

    nwm_config = conf["general"]["nwm_configuration"]
    fc = ForecastConfig(conf["file_paths"]["fcst_config_file"])
    lead_times, missed_leads, lead_step = fc.interpret_lead_times(
        conf_met["lead_times"], nwm_config, leads0
    )
    if missed_leads:
        if len(missed_leads) > 10:
            logger.warning(
                f"Many lead times specified for metric calculation are not present in the data: {missed_leads[:10]}... (total {len(missed_leads)})"
            )
        else:
            logger.warning(f"Missing lead times: {missed_leads}")
    logger.debug(f"Lead times to calculate metrics for: {lead_times}")

    # removed repetitive lead times if any
    lead_times = sorted(list(set(lead_times)))

    # loop through all lead times (including grouped lead times)
    df_metrics = pd.DataFrame()
    for l1 in lead_times:
        leads1 = l1.split("-")
        if len(leads1) == 1:
            leads1 = leads1 + leads1

        start = float(leads1[0]) if leads1[0][0] != "m" else -float(leads1[0][1:])
        end = float(leads1[1]) if leads1[1][0] != "m" else -float(leads1[1][1:])
        step = float(lead_step)

        if step == 0:  # for simulation, start and end are both 0
            leads1 = [start]
        else:
            leads1 = list(np.arange(start, end + step, step))

        # get paired data for the current lead time
        df1 = df0[df0["lead_time"].isin(leads1)]
        df1["lead_group"] = l1

        # save filtered data to a new (temporary) parquet file
        pair_file1 = pair_file.with_name(pair_file.stem + ".temp.parquet")
        df1.to_parquet(pair_file1)

        if conf_met["library"] == "teehr":
            df_metrics = pd.concat(
                [df_metrics, calc_teehr_metrics(pair_file1, geofile, metrics)],
                ignore_index=True,
            )

        elif conf_met["library"] == "nwm.eval":
            thresholds = [
                conf_met["flow_threshold_categorical"],
                conf_met["flow_threshold_event"],
            ]
            df_metrics = pd.concat(
                [df_metrics, calc_nwm_eval_metrics(pair_file1, metrics, thresholds)],
                ignore_index=True,
            )

        else:
            raise Exception(f"Metric library {conf_met['library']} not supported")

        # remove the temporary new parquet file
        pair_file1.unlink(missing_ok=True)
        del df1
        gc.collect()

    # If using teehr library, remap long name to short name for metrics
    if conf_met["library"] == "teehr":
        df_metrics = df_metrics.rename(
            columns={v: k for k, v in dict_teehr_metrics.items()}
        )

    return df_metrics


def calc_metrics(conf: dict, data_paths: dict):
    # library for calculating metrics
    supported_libraries = {"teehr", "nwm.eval"}
    if "library" not in conf["metrics"]:
        raise KeyError("Missing required key: 'library' in metric configuration.")
    library = conf["metrics"]["library"]

    if library not in supported_libraries:
        raise ValueError(
            f"Unsupported metric library: '{library}'. "
            f"Supported libraries are: {', '.join(sorted(supported_libraries))}."
        )
    logger.info(f"  Metrics will be calculated using {library} library")

    # loop through dataset to calculate metrics
    for dataset in conf["general"]["dataset_name"]:
        # check if metric file already exists
        metric_file = data_paths["metrics"][dataset]
        metric_file.parent.mkdir(exist_ok=True, parents=True)
        if metric_file.is_file() and (not conf["metrics"]["overwrite"]):
            logger.info(
                f'  Metric file {metric_file} already exist; remove the file or change "overwrite" to False to recalcualte metrics'
            )
        else:
            # calculate metrics for each group of paired data and append to a single parquet file
            pair_path = data_paths["joined"][dataset]
            pair_files = list(pair_path.parent.glob(f"{pair_path.stem}*.parquet"))
            # remove pair_files containing 'temp' in the name
            pair_files = [pf for pf in pair_files if "temp" not in pf.name]
            if len(pair_files) == 0:
                logger.warning(
                    f"  No paired data files found for dataset {dataset} at {pair_path.parent}. Skipping metric calculation."
                )

            for i1, pair_file in enumerate(pair_files):
                if len(pair_files) > 1:
                    logger.info(f"  Calculating metrics for {dataset} group {i1} ...")
                else:
                    logger.info(f"  Calculating metrics for {dataset} ...")

                # df_metrics = calc_metrics_group(conf, pair_file, data_paths["geofile"])
                df_metrics = calc_metrics_group(
                    conf,
                    pair_file,
                    data_paths["crosswalk"][list(data_paths["crosswalk"].keys())[0]],
                )

                # write metrics to file
                metric_path = Path(metric_file)

                if metric_path.suffix.lower() == ".parquet":
                    if i1 == 0:
                        df_metrics.to_parquet(
                            metric_file, engine="fastparquet", index=False
                        )
                    else:
                        df_metrics.to_parquet(
                            metric_file, engine="fastparquet", index=False, append=True
                        )

                elif metric_path.suffix.lower() == ".csv":
                    if i1 == 0:
                        df_metrics.to_csv(metric_file, index=False)
                    else:
                        # Append without writing the header
                        df_metrics.to_csv(
                            metric_file, mode="a", index=False, header=False
                        )

                else:
                    raise ValueError(f"Unsupported file type: {metric_path.suffix}")
