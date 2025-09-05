import argparse
import logging

from nwm.verf import calc_metrics, create_plots, fetch_data, pair_data, settings
from nwm.verf.configuration import load_and_validate_yaml
from nwm.verf.identify_location_ids import identify_locations

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
logging.getLogger("google.auth.compute_engine._metadata").setLevel(logging.ERROR)
logging.getLogger("fsspec.reference").setLevel(logging.WARNING)

from contextlib import contextmanager
from time import time


# function to timing the execution of various steps
@contextmanager
def timing_block(step_str: str):
    start = time()
    yield
    end = time()
    logger.info(f"  Execution time for {step_str}: {end - start} seconds")


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

    # read and validate configurations
    conf = load_and_validate_yaml(args.config_file)

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
            fetch_data.retrieve_nwm_fcsts(locations, conf, data_paths)

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
