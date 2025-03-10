import argparse
from ngen.verf.configuration import load_and_validate_yaml
from ngen.verf import fetch_data, pair_data, settings, calc_metrics, create_plots

import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

from time import time
from contextlib import contextmanager

# function to timing the execution of various steps
@contextmanager
def timing_block(step_str:str):
    start = time()
    yield
    end = time()
    logger.info(f"Execution time for {step_str}: {end - start} seconds")

# Create the parser
parser = argparse.ArgumentParser()

# Add arguments
parser.add_argument('config_file', type=str, help='Path to the config yaml file for verification')

# Parse the arguments
args = parser.parse_args()
logger.info(f"Config file to use: {args.config_file}")

# read and validate configurations
conf = load_and_validate_yaml(args.config_file)

# define paths for storing the datasets
data_paths = settings.data_paths(conf)

# steps to run verification
steps = conf['general']['steps']

# fetch NWM forecast data
step1 = 'fetch_fcst_data'
if steps[step1]:    
    with timing_block(step1):
        fetch_data.retrieve_nwm_fcsts(conf, data_paths.get('fcst'), data_paths.get('fcst_json'), data_paths.get('fcst_link'))

# fetch flow observation data
step1 = 'fetch_obs_data'
if steps[step1]:
    with timing_block(step1):
        fetch_data.retrieve_usgs_obs(conf, data_paths.get('obs'))

# join the time series of forecasts and observations for each dataset
step1 = 'pair_data'
if steps[step1]:
    with timing_block(step1):
        for dataset_idx, dataset in enumerate(conf['general']['dataset_name']):
            nwm_version = conf['general']['nwm_version'][dataset_idx]
            pairs = pair_data.create_pairs(data_paths, dataset, nwm_version, conf['pair_data']['overwrite'])

# compute metrics for each dataset
step1 = 'compute_metrics'
if steps[step1]:
    with timing_block(step1):
        for dataset in conf['general']['dataset_name']:
            df_metrics = calc_metrics.calc_metrics(conf['metrics'], data_paths, dataset, conf['metrics']['overwrite'])      

# plot metrics
step1 = 'plot_metrics'
if steps[step1]:
    with timing_block(step1):
        # spatial maps
        if conf['plots']['spatial_map']['plot']:
            create_plots.create_spatial_maps(conf, data_paths)

        # histograms
        if conf['plots']['histogram']['plot']:
            create_plots.create_histograms(conf, data_paths)

        # boxplots
        if conf['plots']['boxplot']['plot']:
            create_plots.create_boxplots(conf, data_paths)

