import yaml
import argparse
from pathlib import Path
from ngen.verf.identify_location_ids import get_nwm_link_ids, get_usgs_gage_ids
from ngen.verf import fetch_data, pair_data, settings, calc_metrics, create_plots
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Create the parser
parser = argparse.ArgumentParser()

# Add arguments
parser.add_argument('config_file', type=str, help='Path to the config yaml file for verification')

# Parse the arguments
args = parser.parse_args()
logger.info(f"Config file to use: {args.config_file}")

# read in configuration
yaml_file = Path(args.config_file).resolve(strict=True)
with open(yaml_file) as file:
    conf = yaml.safe_load(file)

# get paths for storing the datasets
data_paths = settings.data_paths(conf)

# steps to run
steps = conf['general']['steps']

# fetch NWM forecast data
if steps['fetch_fcst_data']:
    
    # get NWM link ID for verification locations
    locations = get_nwm_link_ids(conf)

    # fetch NWM forecasts
    fetch_data.retrieve_nwm_fcsts(conf, locations,data_paths.get('fcst'), data_paths.get('fcst_json'), data_paths.get('fcst_link'))

# fetch flow observation data
if steps['fetch_obs_data']:

    # get USGS gage ID for verification locations
    gages = get_usgs_gage_ids(conf) 
    
    # fetch USGS obs data
    fetch_data.retrieve_usgs_obs(conf, gages, data_paths.get('obs'))

# loop through datasets to join the time series of forecasts and observations
if steps['pair_data']:
    for dataset in conf['general']['dataset_name']:
        pairs = pair_data.create_pairs(data_paths, dataset, conf['pair_data']['overwrite'])

# compute metrics
if steps['compute_metrics']:
   for dataset in conf['general']['dataset_name']:
      df_metrics = calc_metrics.calc_metrics(conf['metrics'], data_paths, dataset, conf['metrics']['overwrite'])      

# plot metrics
if steps['plot_metrics']:
    # spatial maps
    if conf['plots']['spatial_map']['plot']:
        create_plots.create_spatial_maps(conf, data_paths)

    # histograms
    if conf['plots']['histogram']['plot']:
        print('plot histograms')
        create_plots.create_histograms(conf, data_paths)

    # boxplots
    if conf['plots']['boxplot']['plot']:
        create_plots.create_boxplots(conf, data_paths)

