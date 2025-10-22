import argparse
import copy
import logging
from contextlib import contextmanager
from pathlib import Path
from time import time

import pandas as pd

import nwm.verf.process_config as pc
from nwm.verf import calc_metrics, create_plots, fetch_data, pair_data, settings
from nwm.verf.identify_location_ids import identify_locations

logger = logging.getLogger(__name__)


@contextmanager
def timing_block(step_str: str):
    """Context manager to time a block of code."""
    start = time()
    yield
    end = time()
    logger.info(f"  Execution time for {step_str}: {end - start} seconds")


def run_verification(conf: dict):
    """Run the verification steps based on configuration."""
    # define paths for storing the datasets
    data_paths = settings.data_paths(conf)

    # steps to run verification
    steps = conf["general"]["steps"]

    # fetch NWM forecast data
    step1 = "fetch_fcst_data"
    if steps[step1]:
        # identify locations to run verification for
        locations = identify_locations(conf)
        with timing_block(step1):
            fetch_data.retrieve_fcsts(locations, conf, data_paths)

    # fetch flow observation data
    step1 = "fetch_obs_data"
    if steps[step1]:
        try:
            locations
        except NameError:
            locations = identify_locations(conf)

        with timing_block(step1):
            fetch_data.retrieve_usgs_obs(locations, conf, data_paths.get("obs"))

    # join the time series of forecasts and observations for each dataset
    step1 = "pair_data"
    if steps[step1]:
        with timing_block(step1):
            for dataset_idx, dataset in enumerate(conf["general"]["dataset_name"]):
                nwm_version = conf["general"]["nwm_version"][dataset_idx]
                pairs = pair_data.create_pairs(
                    data_paths,
                    dataset,
                    nwm_version,
                    conf["pair_data"]["group_size"],
                    conf["pair_data"]["overwrite"],
                )

    # compute metrics for each dataset
    step1 = "compute_metrics"
    if steps[step1]:
        with timing_block(step1):
            calc_metrics.calc_metrics(conf, data_paths)

    # plot metrics
    step1 = "plot_metrics"
    if steps[step1]:
        with timing_block(step1):
            create_plots.create_all_plots(conf, data_paths)


def _assemble_domain_metrics(conf: dict):
    """Assemble metrics from different VPUs across a domain."""
    # get list of VPUs for the domain
    vpus = []
    if conf["general"]["domain"].lower() == "conus":
        vpus = settings.conus_vpu_list
    else:
        logger.error(
            "Assemble domain metrics is only supported for 'conus' domain currently."
        )
        return

    if not vpus:
        logger.error("No VPUs found for the specified domain.")
        return

    # save the original conf
    conf1 = copy.deepcopy(conf)

    for dataset in conf1["general"]["dataset_name"]:
        df_metric = pd.DataFrame()
        for vpu in vpus:
            out_dir = conf1["file_paths"]["output_dir"]
            conf1["file_paths"]["output_dir"] = Path(out_dir).parent / f"vpu_{vpu}"
            metric_file = settings.data_paths(conf1)["metrics"][dataset]

            if not metric_file.exists():
                logger.warning(
                    f"Metric file for dataset {dataset} and VPU {vpu} does not exist at {metric_file}. Skipping."
                )
                continue
            else:
                logger.info(
                    f"Found metric file for dataset {dataset} and VPU {vpu} at {metric_file}."
                )
            df_vpu_metric = pd.read_parquet(metric_file)
            df_vpu_metric["vpu"] = vpu
            df_metric = pd.concat([df_metric, df_vpu_metric], ignore_index=True)

        # save the assembled metric file for the domain
        output_metric_file = settings.data_paths(conf)["metrics"][dataset]
        logger.info(
            f"Saving assembled metric file for dataset {dataset} across domain {conf['general']['domain']} "
            f"at {output_metric_file}"
        )
        Path(output_metric_file).parent.mkdir(parents=True, exist_ok=True)
        df_metric.to_parquet(output_metric_file, index=False)


def assemble_domain_results(conf: dict):
    """Assemble results from different VPUs across domains if applicable."""
    # currently only support 'conus' domain
    if conf["general"]["domain"].lower() != "conus":
        logger.error(
            "Assemble domain results is only supported for 'conus' domain currently."
        )
        return

    # define paths for storing the datasets
    data_paths = settings.data_paths(conf)

    # steps to run verification
    steps = conf["general"]["steps"]

    # assemble metrics from various VPUs for each dataset
    step1 = "compute_metrics"
    if steps[step1]:
        with timing_block(step1):
            _assemble_domain_metrics(conf)

    # plot metrics
    step1 = "plot_metrics"
    if steps[step1]:
        with timing_block(step1):
            create_plots.create_all_plots(conf, data_paths)


def main(config_file: str | Path):
    """Run verification or assemble domain results based on the provided config file."""
    # read and validate configurations
    pc1 = pc.ProcessConfig(config_path=config_file)
    conf = pc1.load_and_validate_yaml()

    if conf["general"]["assemble_domain"]:
        # assemble results from different VPUs across a domain
        assemble_domain_results(conf)
        return
    else:
        # run verification steps
        run_verification(conf)


if __name__ == "__main__":
    # Create the parser
    parser = argparse.ArgumentParser()

    # Add arguments
    parser.add_argument(
        "config_file", type=str, help="Path to the config yaml file for verification"
    )

    # Parse the arguments
    args = parser.parse_args()
    logger.info(f"  Config file to use: {args.config_file}")

    main(args.config_file)
