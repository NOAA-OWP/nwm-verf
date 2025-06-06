import pandas as pd
import os
import glob
from pathlib import Path
import gc
from dask.distributed import Client, LocalCluster  #install with 'pip install dask[complete]'
import teehr.loading.nwm.nwm_points as tlp
from teehr.loading.usgs.usgs import usgs_to_parquet
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from aiohttp.client_exceptions import ServerDisconnectedError, ClientOSError
from .utils import create_hour_sequence, get_n_workers
from .nwm_configs import get_nwm_fcst_window, get_nwm_cycle_config

import warnings
warnings.filterwarnings("ignore", message="Compute Engine Metadata server unavailable")

import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Mute Dask logs
logging.getLogger("distributed").setLevel(logging.WARNING)
logging.getLogger("dask").setLevel(logging.WARNING)
logging.getLogger("tornado.application").setLevel(logging.ERROR)


# Retry on network/server disconnection-related errors
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=1, max=30),  # exponential backoff
    retry=retry_if_exception_type((ServerDisconnectedError, ClientOSError)),
    reraise=True
)
def safe_fetch_usgs(site_codes:list, dates:list, conf:dict, out_dir: str):

    usgs_to_parquet(
        sites = site_codes,
        start_date = min(dates),
        end_date = max(dates),
        output_parquet_dir = out_dir,
        chunk_by = conf['chunk_by'],
        overwrite_output = conf['overwrite_output']
    )


def retrieve_usgs_obs(locations:dict, conf: dict, output_dir:Path):

    """
    Retrieve USGS streamflow observations given configuration and a list of gage IDs

    locations: dictionary containing USGS gage IDs for which observations are to be retrieved
    conf: dictionary defining the configurations (e.g., config.yaml)

    Data retrieved will be saved in parquet files by chunk (e.g., month) in the data directory defined in conf

    """

    # get the list of unique USGS gage IDs
    list_usgs = list({item for subdict in locations.values() for item in subdict['primary']})

    # get some general information
    conf1 = conf['general']
    conf2 = conf['flow_observation']['usgs']
    config = conf1['nwm_configuration']

    # check existing parquet files of usgs obs and get the dates for previously downloaded data
    dates0 = list()
    parquet_files = glob.glob(str(output_dir) +'/*.parquet')
    if len(parquet_files)>0 and not conf2['overwrite_output']:        
        periods = sorted([os.path.basename(x).split('.')[0].split('_') for x in parquet_files])
        for p1 in periods:
            if len(p1) == 1:
                p1 = [p1[0], p1[0]]
            dates0 = dates0 + create_hour_sequence(p1[0], p1[1], start_hour=0, end_hour=23, freq_hour=24)
        dates0 = sorted(list(set(dates0)))
        dates0 = [x.strftime('%Y-%m-%d') for x in dates0]  
        logger.info(f'  Existing USGS parquet files for {min(dates0)} to {max(dates0)} will be used')   

    # identify start and end dates of observations required by all NWM forecasts datasets
    dates = list()
    for i1 in range(len(conf1['forecast_start_date'])):
        start_date = conf1['forecast_start_date'][i1]
        end_date = conf1['forecast_end_date'][i1]
        win1 = get_nwm_fcst_window(config)
        end_date = pd.Timestamp(end_date) + pd.Timedelta(win1, unit="hours")
        dates = dates + create_hour_sequence(start_date, end_date, start_hour=0, end_hour=23, freq_hour=24)

    dates = sorted(list(set(dates)))
    dates = [x.strftime('%Y-%m-%d') for x in dates]     

    # dates that require data downloading
    dates1 = [d1 for d1 in dates if d1 not in dates0]

    if len(dates1) == 0:
        logger.info(f'  USGS data for all required dates already exist')
    else:

        # create data path
        output_dir.mkdir(parents=True, exist_ok=True)

        # break the list of dates into consecutive chunks
        dates2 = sorted([pd.Timestamp(d1) for d1 in dates1])
        dates2 = [pd.Timestamp(d1) for d1 in dates2]
        date_list = list()
        for i1 in range(len(dates2)):
            if i1==0:
                list1 = [dates2[i1]]
            else:
                if (dates2[i1]-dates2[i1-1]).days == 1:
                    list1 = list1 + [dates2[i1]]
                else:
                    date_list.append(list1)
                    list1 = [dates2[i1]]
        date_list.append(list1)    

        #determine n_workers dynamically
        #n_workers = max(os.cpu_count() - 2, 1)
        mem_limit = conf2['memory_per_worker_gb']
        n_workers = get_n_workers(mem_limit)

        # loop through the date chunks to download USGS data
        for d1 in date_list:

            logger.info(f'  Downloading USGS data for {min(d1)} to {max(d1)} ...')

            # use a local dask cluster to fetch the data 
            with LocalCluster(n_workers=n_workers,
                        processes=True, memory_limit=f"{mem_limit}GB", dashboard_address=None,
            ) as cluster, Client(cluster) as client:

                try:
                    safe_fetch_usgs(list_usgs, d1, conf2, str(output_dir))
                except (ServerDisconnectedError, ClientOSError) as e:
                    logger.warning(f"Failed to fetch USGS data after retries: {e}")
          
                # usgs_to_parquet(
                #     sites = list_usgs,
                #     start_date = min(d1),
                #     end_date = max(d1),
                #     output_parquet_dir = str(output_dir),
                #     chunk_by = conf2['chunk_by'],
                #     overwrite_output = conf2['overwrite_output']
                # )

            # clean up memory
            gc.collect()

        logger.info(f'  USGS observation data are saved in parquet files at: {output_dir}')


def retrieve_nwm_fcsts(locations:dict, conf: dict, data_paths:dict):

    """
    Retrieve NMW forecasts given the configrations and list of locations

    locations: dictionary containing secondary ID (NWM link IDs) for which forecasts are to be retrieved
    conf: dictionary defining the configurations (e.g., config.yaml)
    data_paths: dictionary containing paths to store the data

    Data retrieved will be saved in parquet files by forecast cycle in the data directory defined in conf

    """
    output_dir = data_paths.get('fcst')
    json_dir = data_paths.get('fcst_json')
    data_link_dir = data_paths.get('fcst_link')

    # get some general information
    conf1 = conf['general']
    conf2 = conf['nwm_forecast']
    config = conf1['nwm_configuration']

    # determine n_workers dynamically
    #n_workers = max(os.cpu_count() - 2, 1)
    mem_limit = conf2['memory_per_worker_gb']
    n_workers = get_n_workers(mem_limit)

    # loop through datasets
    for i1, dataset in enumerate(conf1['dataset_name']):
        
        locations_nwm = locations[dataset]['secondary']

        fetch = conf2['fetch_fcst'][i1]
        if fetch:

            version = conf1['nwm_version'][i1]
            start_date = conf1['forecast_start_date'][i1]
            end_date = conf1['forecast_end_date'][i1]

            # get forecast configuration and cycle frequency
            cycle_config = get_nwm_cycle_config(config)

            logger.info(f'  ======== Fetch data for NWM dataset {dataset}: {version} {config} {start_date} to {end_date} ==========')

            # check existing parquet files for NWM forecasts
            parquet_files = glob.glob(str(output_dir[dataset]) +'/*.parquet')
            hours = sorted([os.path.basename(x).split('.')[0] for x in parquet_files])
            cycles0 = [pd.Timestamp(h1) for h1 in hours]

            # determine all cycles needed
            cycles = create_hour_sequence(start_date, end_date, cycle_config['start_hr'], cycle_config['end_hr'], cycle_config['freq_hr'])

            # cycles not in existing parquet files 
            cycles1 = [c1 for c1 in cycles if c1 not in cycles0]
        
            if len(cycles1)==0:
                logger.info(f'  All parquet files already exist at: {output_dir[dataset]}')
            else: 
                if len(cycles1) < len(cycles):
                    logger.info(f'  Some parquet files already exist at: {output_dir[dataset]}')

                # create the data paths
                output_dir[dataset].mkdir(parents=True, exist_ok=True)
                json_dir[dataset].mkdir(parents=True, exist_ok=True)

                # determine the dates
                dates1 = sorted(list(set([c1.strftime('%Y-%m-%d') for c1 in cycles1])))
                        
                for d1 in dates1:

                    logger.info(f'  Retriving NWM forecast data for {d1} ...')

                    # use a local dask cluster to fetch the data
                    with LocalCluster(n_workers=n_workers,
                                processes=True, memory_limit=f"{mem_limit}GB", dashboard_address=None,
                    ) as cluster, Client(cluster) as client:
                        
                        # fectch NWM forecasts data (1-month short-range took around 1.5 hours)
                        tlp.nwm_to_parquet(
                            configuration = config,
                            output_type = conf2['output_type'],
                            variable_name = conf1['variable_name'],
                            start_date = d1, 
                            ingest_days = 1, 
                            location_ids = locations_nwm,
                            json_dir = str(json_dir[dataset]),
                            output_parquet_dir = str(output_dir[dataset]),
                            nwm_version = version,
                            data_source = conf2['data_source'],
                            kerchunk_method = conf2['kerchunk_method'],
                            t_minus_hours = conf2['t_minus'],
                            process_by_z_hour = conf2['process_by_z_hour'],
                            stepsize = conf2['stepsize'],
                            ignore_missing_file = conf2['ignore_missing_file'],
                            overwrite_output = conf2['overwrite_output'],

                        )

                    # clean up memory
                    gc.collect() 

                logger.info(f'  NWM forecast data are saved in parquet files at: {output_dir[dataset]}')

            for c1 in cycles:
                c1_str = c1.strftime('%Y%m%dT%H')
                link1 = Path(data_link_dir[dataset], c1_str + '.parquet')
                if not link1.parent.exists():
                    link1.parent.mkdir(parents=True)
                if link1.is_symlink():
                    link1.unlink()
                target1 = Path(output_dir[dataset], c1_str + '.parquet')
                link1.symlink_to(target1)