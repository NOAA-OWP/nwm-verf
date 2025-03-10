import pandas as pd
import os
import glob
from pathlib import Path
from dask.distributed import Client, LocalCluster  #install with 'pip install dask[complete]'
import teehr.loading.nwm.nwm_points as tlp
from teehr.loading.usgs.usgs import usgs_to_parquet
from .utils import create_hour_sequence
from .nwm_configs import get_nwm_fcst_window, get_nwm_cycle_frequency
from .identify_location_ids import get_nwm_link_ids, get_usgs_gage_ids

import warnings
warnings.filterwarnings("ignore", message="Compute Engine Metadata server unavailable")

import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def retrieve_usgs_obs(conf: dict, output_dir:Path):

    """
    Retrieve USGS streamflow observations given configuration and a list of gage IDs

    conf: dictionary defining the configurations (e.g., config.yaml)

    Data retrieved will be saved in parquet files by chunk (e.g., month) in the data directory defined in conf

    """

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
            dates0 = dates0 + create_hour_sequence(p1[0], p1[1], by_hours=24)
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
        dates = dates + create_hour_sequence(start_date, end_date, by_hours=24)

    dates = sorted(list(set(dates)))
    dates = [x.strftime('%Y-%m-%d') for x in dates]     

    # dates that require data downloading
    dates1 = [d1 for d1 in dates if d1 not in dates0]

    if len(dates1) == 0:
        logger.info(f'  USGS data for all required dates already exist')
    else:

        # get USGS gage ID for verification locations
        locations = get_usgs_gage_ids(conf) 

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

        # loop through the date chunks to download USGS data
        for d1 in date_list:
            logger.info(f'  Downloading USGS data for {min(d1)} to {max(d1)} ...')

            # use a local dask cluster to fetch the data
            n_workers = max(os.cpu_count() - 2, 1)
            with LocalCluster(n_workers=n_workers,
                              processes=False, memory_limit="2GB",
            ) as cluster, Client(cluster) as client:
                
                usgs_to_parquet(
                    sites = locations,
                    start_date = min(d1),
                    end_date = max(d1),
                    output_parquet_dir = str(output_dir),
                    chunk_by = conf2['chunk_by'],
                    overwrite_output = conf2['overwrite_output']
                )

        logger.info(f'  USGS observation data are saved in parquet files at: {output_dir}')


def retrieve_nwm_fcsts(conf: dict, output_dir:dict, json_dir:dict, data_link_dir:dict):

    """
    Retrieve NMW forecasts given the configrations and list of locations

    conf: dictionary defining the configurations (e.g., config.yaml)

    Data retrieved will be saved in parquet files by forecast cycle in the data directory defined in conf

    """
    # get some general information
    conf1 = conf['general']
    conf2 = conf['nwm_forecast']
    config = conf1['nwm_configuration']

    # loop through datasets
    for i1, dataset in enumerate(conf1['dataset_name']):
        
        #i1 = conf1['dataset_name'].index(dataset)
        fetch = conf2['fetch_fcst'][i1]

        if fetch:

            version = conf1['nwm_version'][i1]
            start_date = conf1['forecast_start_date'][i1]
            end_date = conf1['forecast_end_date'][i1]

            # get NWM link ID for verification locations
            locations = get_nwm_link_ids(conf, version)

            # get forecast configuration and cycle frequency
            fcst_freq = get_nwm_cycle_frequency(config)

            logger.info(f'  ======== Fetch data for NWM dataset {dataset}: {version} {start_date} to {end_date} ==========')

            # check existing parquet files for NWM forecasts
            parquet_files = glob.glob(str(output_dir[dataset]) +'/*.parquet')
            hours = sorted([os.path.basename(x).split('.')[0] for x in parquet_files])
            cycles0 = [pd.Timestamp(h1) for h1 in hours]

            # determine all cycles needed
            cycles = create_hour_sequence(start_date, end_date, by_hours = fcst_freq)

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
                    n_workers = max(os.cpu_count() - 2, 1)
                    with LocalCluster(n_workers=n_workers,
                                processes=False, memory_limit="3GB",
                    ) as cluster, Client(cluster) as client:
                        
                        # fectch NWM forecasts data (1-month short-range took around 1.5 hours)
                        tlp.nwm_to_parquet(
                            configuration = config,
                            output_type = conf2['output_type'],
                            variable_name = conf1['variable_name'],
                            start_date = d1, 
                            ingest_days = 1, 
                            location_ids = locations,
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