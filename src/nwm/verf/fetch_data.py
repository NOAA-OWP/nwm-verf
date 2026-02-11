import gc
import glob
import os
import sys
import warnings
from pathlib import Path

import pandas as pd
import teehr.loading.nwm.nwm_points as tlp
import xarray as xr
from aiohttp.client_exceptions import ClientOSError, ServerDisconnectedError
from dask.distributed import (  # install with 'pip install dask[complete]'
    Client,
    LocalCluster,
)
from teehr.loading.usgs.usgs import usgs_to_parquet

from .nwm_configs import ForecastConfig
from .utils import create_time_sequence, get_n_workers, read_data, save_data

warnings.filterwarnings("ignore", message="Compute Engine Metadata server unavailable")

import logging

logger = logging.getLogger(__name__)


def get_fcst_info(conf: dict) -> tuple[int, int, pd.Timestamp]:
    """Get the forecast window size, time step, and reference time for a given NWM configuration."""
    # validate forecast cycle
    nwm_config = conf["general"]["nwm_configuration"]
    fc = ForecastConfig(conf["file_paths"]["fcst_config_file"])
    fc.validate_cycle_info(nwm_config)

    # define reference time
    reference_time = pd.to_datetime(conf["general"]["forecast_start_date"][0])

    if reference_time.hour not in fc.get_valid_cycles(nwm_config):
        msg = f"Invalid hour/cycle ({reference_time.hour}) for forecast_start_date. "
        msg += f"Valid cycles are: {fc.get_valid_cycles(nwm_config)}"
        logger.error(msg)
        raise ValueError(msg)

    # get time step and forecast window for the configuration and cycle
    win_size, time_step = fc.get_fcst_window_timestep(
        nwm_config, int(reference_time.hour)
    )

    return win_size, time_step, reference_time


def check_existing_obs_data(obs_dir: str | Path) -> list:
    """Check existing parquet files of usgs obs and get the dates for previously downloaded data."""
    dates0 = list()
    parquet_files = glob.glob(str(obs_dir) + "/*.parquet")
    if len(parquet_files):
        periods = sorted(
            [os.path.basename(x).split(".")[0].split("_") for x in parquet_files]
        )
        for p1 in periods:
            if len(p1) == 1:
                p1 = [p1[0], p1[0]]
            dates0 = dates0 + create_time_sequence(
                p1[0], p1[1], freq_hour=24, start_hour=0, end_hour=23
            )
        dates0 = sorted(list(set(dates0)))

    return dates0


def check_missing_obs_data(obs_dir: str | Path, conf: dict, gages: list):
    """Check for missing observation data in the specified directory."""
    # Get existing observation dates
    df = pd.DataFrame()
    parquet_files = glob.glob(str(obs_dir) + "/*.parquet")
    for p in parquet_files:
        df = pd.concat([df, pd.read_parquet(p)], ignore_index=True)

    # If no observation data is found, log warning and exit
    if df.empty:
        max_show = 5
        gages_list = list(gages)
        if len(gages_list) > max_show:
            shown = gages_list[:max_show]
            msg = (
                f"No observation data is available for gages {shown} "
                f"(showing first {max_show} of {len(gages_list)})."
                " Verification cannot proceed. Exit."
            )
        else:
            msg = (
                f"No observation data is available for gages {gages_list}."
                " Verification cannot proceed. Exit."
            )

        logger.warning(msg)
        sys.exit(0)

    if "value_time" not in df.columns:
        msg = f"'value_time' column not found in observation data in {obs_dir}."
        logger.error(msg)
        raise ValueError(msg)

    df["value_time"] = pd.to_datetime(df["value_time"])
    existing_dates = df["value_time"].unique().tolist()

    # Get required observation dates
    time_step = 1
    if conf["general"]["nwm_configuration"] != "ngen_simulation":
        fcst_win, time_step, _ = get_fcst_info(conf)
    conf1 = conf["general"]
    for i1, dataset in enumerate(conf1["dataset_name"]):
        if conf1["nwm_configuration"] == "ngen_simulation":
            start_date = pd.to_datetime(conf1["eval_start_date"][i1])
            end_date = pd.to_datetime(conf1["eval_end_date"][i1])
        else:
            start_date = pd.to_datetime(
                conf1["forecast_start_date"][i1]
            ) + pd.Timedelta(hours=time_step)
            end_date = pd.to_datetime(conf1["forecast_end_date"][i1]) + pd.Timedelta(
                hours=fcst_win
            )
        required_dates = create_time_sequence(start_date, end_date, freq_hour=time_step)

        # Check for missing data. For ngenCERF (single gage), check by dates; otherwise, check by gages
        if conf["nwm_forecast"]["data_source"] == "ngenCERF":
            # Check for missing dates
            missing_dates = [d for d in required_dates if d not in existing_dates]
            if missing_dates:
                formatted = ", ".join(
                    [d.strftime("%Y-%m-%d %H:%M:%S") for d in missing_dates]
                )
                logger.warning(
                    f"{dataset} - Missing observation data for dates: {formatted}"
                )
        else:
            # first filter data with dates within required dates range
            df_required = df[
                (df["value_time"] >= min(required_dates))
                & (df["value_time"] <= max(required_dates))
            ]

            # then check for missing gages
            existing_gages = df_required["location_id"].unique().tolist()
            logger.info(
                f"{dataset} - Number of gages with observation data available: {len(existing_gages)}"
            )
            missing_gages = [g for g in gages if f"usgs-{g}" not in existing_gages]
            if missing_gages:
                logger.warning(
                    f"{dataset} - Missing observation data for {len(missing_gages)} gages."
                )
                logger.debug(f"{dataset} - Missing gages: {missing_gages}")


def safe_fetch_usgs(
    site_codes: list, dates: list, conf: dict, out_dir: str, hourly: bool = True
):
    usgs_to_parquet(
        sites=site_codes,
        start_date=min(dates),
        end_date=max(dates) + pd.Timedelta(hours=23),
        output_parquet_dir=out_dir,
        chunk_by=conf["chunk_by"],
        filter_to_hourly=hourly,
        overwrite_output=conf["overwrite_output"],
    )


def retrieve_usgs_obs(locations: dict, conf: dict, output_dir: Path):
    """Retrieve USGS streamflow observations given configuration and a list of gage IDs.

    Args:
        locations: dictionary containing USGS gage IDs for which observations are to be retrieved
        conf: dictionary defining the configurations (e.g., config.yaml)
        output_dir: path to store the observation data

    Data retrieved will be saved in parquet files by chunk (e.g., month) in the data directory defined in conf

    """
    # get the list of unique USGS gage IDs
    list_usgs = list(
        {item for subdict in locations.values() for item in subdict["primary"]}
    )

    # get some general information
    conf1 = conf["general"]
    conf2 = conf["flow_observation"]["usgs"]

    # check existing parquet files of usgs obs and get the dates for previously downloaded data
    dates0 = list()
    if not conf2["overwrite_output"]:
        dates0 = check_existing_obs_data(str(output_dir))
        dates0 = [x.strftime("%Y-%m-%d") for x in dates0]
        if len(dates0) > 0:
            logger.info(
                f"  Existing USGS parquet files for {min(dates0)} to {max(dates0)} will be used"
            )

    # identify start and end dates of observations required by all NWM forecasts datasets
    dates = list()
    for i1 in range(len(conf1["forecast_start_date"])):
        start_date = conf1["forecast_start_date"][i1]
        end_date = conf1["forecast_end_date"][i1]
        if conf1["nwm_configuration"] == "ngen_simulation":
            fcst_win1 = 0
            timestep1 = 1
        else:
            fcst_win1, timestep1, reference_time = get_fcst_info(conf)

        # adjust start/end date based on forecast window
        if fcst_win1 < 0:
            start_date = pd.Timestamp(start_date) + pd.Timedelta(
                fcst_win1, unit="hours"
            )
            start_date = start_date.strftime("%Y-%m-%d %H:%M:%S")
        else:
            end_date = pd.Timestamp(end_date) + pd.Timedelta(
                fcst_win1 + 24, unit="hours"
            )
            end_date = end_date.strftime("%Y-%m-%d %H:%M:%S")

        # create the list of dates required
        dates = dates + create_time_sequence(
            start_date, end_date, freq_hour=24, start_hour=0, end_hour=23
        )

    dates = sorted(list(set(dates)))
    dates = [x.strftime("%Y-%m-%d") for x in dates]

    # dates that require data downloading
    dates1 = [d1 for d1 in dates if d1 not in dates0]

    if len(dates1) == 0:
        logger.info("  USGS data for all required dates already exist")
    else:
        # create data path
        output_dir.mkdir(parents=True, exist_ok=True)

        # break the list of dates into consecutive chunks
        dates2 = sorted([pd.Timestamp(d1) for d1 in dates1])
        dates2 = [pd.Timestamp(d1) for d1 in dates2]
        date_list = list()
        for i1 in range(len(dates2)):
            if i1 == 0:
                list1 = [dates2[i1]]
            else:
                if (dates2[i1] - dates2[i1 - 1]).days == 1:
                    list1 = list1 + [dates2[i1]]
                else:
                    date_list.append(list1)
                    list1 = [dates2[i1]]
        date_list.append(list1)

        # determine n_workers dynamically
        mem_limit = conf2["memory_per_worker_gb"]
        n_workers = get_n_workers(mem_limit)

        # loop through the date chunks to download USGS data
        hourly = False if timestep1 < 1 else True
        for d1 in date_list:
            logger.info(f"  Downloading USGS data for {min(d1)} to {max(d1)} ...")

            # use a local dask cluster to fetch the data
            with (
                LocalCluster(
                    n_workers=n_workers,
                    processes=True,
                    memory_limit=f"{mem_limit}GB",
                    dashboard_address=None,
                ) as cluster,
                Client(cluster) as client,
            ):
                try:
                    safe_fetch_usgs(list_usgs, d1, conf2, str(output_dir), hourly)
                except (ServerDisconnectedError, ClientOSError) as e:
                    logger.warning(f"Failed to fetch USGS data after retries: {e}")

            # clean up memory
            gc.collect()

        # if output_dir is empty after retrieval, give warning
        if not any(output_dir.iterdir()):
            msg = "No USGS observation data retrieved for the specified gage IDs and date range. Verification cannot proceed. Exit."
            logger.error(msg)
            raise Exception(msg)

        logger.info(
            f"  USGS observation data are saved in parquet files at: {output_dir}"
        )

    # Check for missing observation data after retrieval
    check_missing_obs_data(output_dir, conf, list_usgs)


def retrieve_fcsts_ngencerf(conf: dict, data_paths: dict):
    """Retrieve NWM forecasts given the configurations and list of locations from the NGENCERF data source.

    The forecast files are generated by ngenCERF on the server.
    """
    # get time step and forecast window for the configuration and cycle
    win_size, time_step, reference_time = get_fcst_info(conf)

    # Define time window for forecasts
    if win_size >= 0:
        start_time = reference_time + pd.Timedelta(hours=time_step)
        end_time = start_time + pd.Timedelta(hours=win_size - time_step).round("s")
    else:
        start_time = reference_time + pd.Timedelta(hours=win_size + time_step)
        end_time = reference_time

    # read forecast data from file for each dataset
    for dataset in conf["general"]["dataset_name"]:
        logger.info(f"  Retrieving forecast data for dataset {dataset} ...")

        fcst_file = conf["file_paths"]["fcst_data_file"][dataset]
        df_fcst = read_data(fcst_file, dtype={"sim_flow": float}, parse_dates=["Time"])

        if df_fcst.empty:
            logger.warning(f"No forecast data found for {fcst_file}")
            return

        # order the dataframe by time
        df_fcst = df_fcst.sort_values("Time")

        # make sure the time period covers the forecast window
        if df_fcst["Time"].min() > start_time or df_fcst["Time"].max() < end_time:
            msg = (
                f"Forecast time period {start_time} to {end_time} is not covered by data. "
                f"Available data time period is {df_fcst['Time'].min()} to {df_fcst['Time'].max()}"
            )
            logger.warning(msg)

        # if extra data is found, give warning too
        if df_fcst["Time"].max() > end_time or df_fcst["Time"].min() < start_time:
            msg = (
                f"Extra forecast data found beyond the expected time period: "
                f"Available data time period is {df_fcst['Time'].min()} to {df_fcst['Time'].max()}. "
                f"Expected time period is {start_time} to {end_time}."
            )
            logger.warning(msg)

        # filter data by the overlapping period
        df_fcst = df_fcst[
            (df_fcst["Time"] >= start_time) & (df_fcst["Time"] <= end_time)
        ]

        # make sure every time step is covered
        all_times = pd.date_range(start=start_time, end=end_time, freq=f"{time_step}H")
        missing_times = all_times[~all_times.isin(df_fcst["Time"])]
        if not missing_times.empty:
            msg = f"Missing forecast data for time steps: {missing_times.min()} to {missing_times.max()}"
            logger.warning(msg)

        # rename columns to match the format expected by teehr
        df_fcst = df_fcst.rename(columns={"sim_flow": "value", "Time": "value_time"})

        # add additional columns to match the format expected by teehr
        df_fcst["reference_time"] = reference_time
        df_fcst["location_id"] = (
            conf["general"]["nwm_version"][0]
            + "-"
            + conf["general"]["location_list"][0]
        )
        df_fcst["configuration"] = conf["general"]["nwm_configuration"]
        df_fcst["variable_name"] = conf["general"]["variable_name"]
        df_fcst["measurement_unit"] = "m3/s"

        # save forecast data to parquet files
        output_file = Path(
            data_paths.get("fcst_link").get(dataset)
        ) / start_time.strftime("%Y%m%dT%H.parquet")
        save_data(df_fcst, output_file)
        logger.info(f"  Forecast data saved to {output_file}")


def retrieve_fcsts_gcs(locations: dict, conf: dict, data_paths: dict):
    """Retrieve NWM forecasts given the configurations and list of locations from Google Cloud Storage.

    locations: dictionary containing secondary ID (NWM link IDs) for which forecasts are to be retrieved
    conf: dictionary defining the configurations (e.g., config.yaml)
    data_paths: dictionary containing paths to store the data

    Data retrieved will be saved in parquet files by forecast cycle in the data directory defined in conf

    """
    output_dir = data_paths.get("fcst")
    json_dir = data_paths.get("fcst_json")
    data_link_dir = data_paths.get("fcst_link")

    # get some general information
    conf1 = conf["general"]
    conf2 = conf["nwm_forecast"]
    config = conf1["nwm_configuration"]

    # determine n_workers dynamically
    mem_limit = conf2["memory_per_worker_gb"]
    n_workers = get_n_workers(mem_limit)

    # loop through datasets
    for i1, dataset in enumerate(conf1["dataset_name"]):
        locations_nwm = locations[dataset]["secondary"]

        fetch = conf2["fetch_fcst"][i1]
        if fetch:
            version = conf1["nwm_version"][i1]
            start_date = conf1["forecast_start_date"][i1]
            end_date = conf1["forecast_end_date"][i1]

            # get forecast configuration and cycle frequency
            fc = ForecastConfig(conf["file_paths"]["fcst_config_file"])
            fc.validate_cycle_info(config)
            cycle_config = fc.get_cycle_info(config)

            logger.info(
                f"  ======== Fetch data for NWM dataset {dataset}: {version} {config} {start_date} to {end_date} =========="
            )

            # check existing parquet files for NWM forecasts
            parquet_files = glob.glob(str(output_dir[dataset]) + "/*.parquet")
            hours = sorted([os.path.basename(x).split(".")[0] for x in parquet_files])
            cycles0 = [pd.Timestamp(h1) for h1 in hours]

            # determine all cycles needed
            cycles = []
            for c1 in cycle_config:
                cycle_start, cycle_end, cycle_freq, fcst_win, fcst_timestep = c1
                cycles.extend(
                    create_time_sequence(
                        start_date,
                        end_date,
                        cycle_freq,
                    )
                )

            # cycles not in existing parquet files
            cycles1 = [c1 for c1 in cycles if c1 not in cycles0]

            if len(cycles1) == 0:
                logger.info(
                    f"  All parquet files already exist at: {output_dir[dataset]}"
                )
            else:
                if len(cycles1) < len(cycles):
                    logger.info(
                        f"  Some parquet files already exist at: {output_dir[dataset]}"
                    )

                # create the data paths
                output_dir[dataset].mkdir(parents=True, exist_ok=True)
                json_dir[dataset].mkdir(parents=True, exist_ok=True)

                # determine the dates
                dates1 = sorted(list(set([c1.strftime("%Y-%m-%d") for c1 in cycles1])))

                for d1 in dates1:
                    logger.info(f"  Retriving NWM forecast data for {d1} ...")

                    # use a local dask cluster to fetch the data
                    with (
                        LocalCluster(
                            n_workers=n_workers,
                            processes=True,
                            memory_limit=f"{mem_limit}GB",
                            dashboard_address=None,
                        ) as cluster,
                        Client(cluster) as client,
                    ):
                        # fectch NWM forecasts data (1-month short-range took around 1.5 hours)
                        tlp.nwm_to_parquet(
                            configuration=config,
                            output_type=conf2["output_type"],
                            variable_name=conf1["variable_name"],
                            start_date=d1,
                            ingest_days=1,
                            location_ids=locations_nwm,
                            json_dir=str(json_dir[dataset]),
                            output_parquet_dir=str(output_dir[dataset]),
                            nwm_version=version,
                            data_source=conf2["data_source"],
                            kerchunk_method=conf2["kerchunk_method"],
                            t_minus_hours=conf2["t_minus"],
                            process_by_z_hour=conf2["process_by_z_hour"],
                            stepsize=conf2["stepsize"],
                            ignore_missing_file=conf2["ignore_missing_file"],
                            overwrite_output=conf2["overwrite_output"],
                        )

                    # clean up memory
                    gc.collect()

                logger.info(
                    f"  NWM forecast data are saved in parquet files at: {output_dir[dataset]}"
                )

            for c1 in cycles:
                c1_str = c1.strftime("%Y%m%dT%H")
                link1 = Path(data_link_dir[dataset], c1_str + ".parquet")
                if not link1.parent.exists():
                    link1.parent.mkdir(parents=True)
                if link1.is_symlink():
                    link1.unlink()
                target1 = Path(output_dir[dataset], c1_str + ".parquet")
                link1.symlink_to(target1)


def extract_flow_for_gages(
    nc_file: Path,
    crosswalk_file: Path,
    gage_file: Path,
    start_time: pd.Timestamp = None,
    end_time: pd.Timestamp = None,
    flow_var: str = "flow",
    feature_id_var: str = "feature_id",
    time_var: str = "time",
) -> pd.DataFrame:
    """Extract time and flow for specific gages from a NetCDF file using a crosswalk.

    Args:
        nc_file: Path to NetCDF file.
        crosswalk_file: Path to parquet crosswalk file with columns ['primary_location_id', 'secondary_location_id'].
        gage_file: Path to CSV file with gage IDs (primary_location_id) to include.
        start_time: Start time for filtering (optional).
        end_time: End time for filtering (optional).
        flow_var: Name of flow variable in NetCDF.
        feature_id_var: Name of feature_id variable in NetCDF.
        time_var: Name of time variable in NetCDF.

    Returns:
        pd.DataFrame with columns ['time', 'primary_location_id', 'flow'].

    """
    # Read crosswalk
    cwt_df = read_data(crosswalk_file)

    # Read list of gages to include
    gages_df = pd.read_csv(gage_file, dtype=str, header=0, names=["gage"])
    gage_list = set(gages_df["gage"])

    # Filter crosswalk to only gages in the gage list
    cwt_df["primary_location_id"] = cwt_df["primary_location_id"].str.replace(
        "^usgs-", "", regex=True
    )
    cwt_df["secondary_location_id"] = cwt_df["secondary_location_id"].str.replace(
        "^ngen-", "", regex=True
    )
    cwt_df = cwt_df[cwt_df["primary_location_id"].isin(gage_list)]

    # convert secondary_location_id to integer (feature_id in NetCDF is integer)
    cwt_df["secondary_location_id"] = cwt_df["secondary_location_id"].astype(int)

    # Map secondary_location_id to primary_location_id
    feature_to_gage = dict(
        zip(cwt_df["secondary_location_id"], cwt_df["primary_location_id"])
    )

    # Open NetCDF
    ds = xr.open_dataset(nc_file)

    # Select only the feature_ids in the crosswalk
    feature_ids = list(feature_to_gage.keys())

    # Flow is [time, feature_id]
    flow_data = ds[flow_var].sel({feature_id_var: feature_ids})

    # Convert to DataFrame
    df = flow_data.to_dataframe().reset_index()

    # create location_id by adding 'ngen-' prefix to feature_id
    df["location_id"] = "ngen-" + df[feature_id_var].astype(str)

    # Keep only relevant columns
    df = df[[time_var, "location_id", flow_var]]

    # filter by time if specified
    if start_time is not None:
        df = df[df[time_var] >= start_time]
    if end_time is not None:
        df = df[df[time_var] <= end_time]

    # rename columns into teehr format
    df.rename(
        columns={
            time_var: "value_time",
            flow_var: "value",
        },
        inplace=True,
    )

    return df


def retrieve_ngen_simulation(conf: dict, data_paths: dict):
    """Retrieve NGEN simulation data for the specified configuration.

    Based on the data source specified in the configuration, the appropriate retrieval function is called.
    """
    # read forecast data from file for each dataset
    for idx, (dataset, nwm_ver) in enumerate(
        zip(conf["general"]["dataset_name"], conf["general"]["nwm_version"])
    ):
        logger.info(f"  Retrieving forecast data for dataset {dataset} ...")

        fcst_file = conf["file_paths"]["fcst_data_file"][dataset]
        df_sim = extract_flow_for_gages(
            nc_file=Path(fcst_file),
            crosswalk_file=Path(conf["file_paths"]["crosswalk_file"][nwm_ver]),
            gage_file=Path(conf["file_paths"]["location_list_file"]),
            start_time=pd.to_datetime(conf["general"]["eval_start_date"][idx]),
            end_time=pd.to_datetime(conf["general"]["eval_end_date"][idx]),
            flow_var="flow",
            feature_id_var="feature_id",
            time_var="time",
        )

        # add additional columns to match the format expected by teehr
        df_sim["reference_time"] = df_sim["value_time"]
        df_sim["configuration"] = conf["general"]["nwm_configuration"]
        df_sim["variable_name"] = conf["general"]["variable_name"]
        df_sim["measurement_unit"] = "m3/s"

        # save forecast data to parquet files
        start_time = df_sim["value_time"].min()
        end_time = df_sim["value_time"].max()
        output_file = Path(
            data_paths.get("fcst_link").get(dataset)
        ) / start_time.strftime(
            "%Y%m%dT%H" + "-" + end_time.strftime("%Y%m%dT%H") + ".parquet"
        )
        save_data(df_sim, output_file)
        logger.info(f"  NGEN simulation data saved to {output_file}")


def retrieve_fcsts(locations: dict, conf: dict, data_paths: dict):
    """Retrieve NWM forecast data for the specified locations and configuration.

    Based on the data source specified in the configuration, the appropriate retrieval function is called.
    """
    if conf["nwm_forecast"]["data_source"].upper() in ["GCS", "NOMADS", "DSTOR"]:
        retrieve_fcsts_gcs(locations, conf, data_paths)
    elif conf["nwm_forecast"]["data_source"].upper() == "NGENCERF":
        retrieve_fcsts_ngencerf(conf, data_paths)
    elif conf["nwm_forecast"]["data_source"].upper() == "NGENSIM":
        retrieve_ngen_simulation(conf, data_paths)
    else:
        msg = (
            f"Data source {conf['nwm_forecast']['data_source']} not recognized. "
            f"Supported data sources are 'GCS', 'NOMADS', 'DSTOR', 'NGENCERF', and 'NGENSIM'."
        )
        logger.error(msg)
        raise ValueError(msg)
