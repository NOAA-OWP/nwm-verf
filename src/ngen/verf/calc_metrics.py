import pandas as pd
import numpy as np
from pathlib import Path
import gc
from teehr.classes.duckdb_joined_parquet import DuckDBJoinedParquet
from multiprocessing import Pool, cpu_count
from typing import Optional, Union
import ngen.eval.metric_functions as mf
from .settings import dict_teehr_metrics, dict_ngen_eval_metrics
from .utils import get_key_from_value
import warnings
warnings.filterwarnings('ignore') 

import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# check if metrics are supported for teehr
def check_metrics_teehr(metrics: list, dict1: dict):
    metrics1 = []
    for m in metrics:
        if m in dict1.values():
            metrics1 = metrics1 + [m]
        elif m in dict1.keys():
            metrics1 = metrics1 + [dict1.get(m)]
        else:
            raise Exception(f'{m} is not one of the supported metrics')

    return(metrics1)

# check if metrics are supported for ngen.eval
def check_metrics_ngen_eval(metrics: list, dict1: dict):
    metrics1 = []
    for m in metrics:
        if m in dict1.values():
            metrics1 = metrics1 + [get_key_from_value(m)]
        elif m in dict1.keys():
            metrics1 = metrics1 + [m]
        else:
            raise Exception(f'{m} is not one of the supported metrics')

    return(metrics1)

# function to calculate TEEHR metrics
def calc_teehr_metrics(pairs:Path, geometry: Path, 
                       metrics: list[str],
) -> pd.DataFrame:

    # make sure all metrics requested are supported
    metrics = check_metrics_teehr(metrics, dict_teehr_metrics)

    # paired data parquet
    joined_data = DuckDBJoinedParquet(
        joined_parquet_filepath = pairs,
        geometry_filepath = geometry
    )

    # compute metrics
    gdf_all = joined_data.get_metrics(
        group_by=["primary_location_id", 'lead_group'],
        order_by=["primary_location_id", 'lead_group'],
        include_metrics=metrics,
        include_geometry=False,
    )

    return gdf_all

# function to calculate ngen.eval metrics (i.e, metrics used by ngen-cal)
def func_calc_metrics(
        df:pd.DataFrame, 
        metrics: list[str], 
        thresholds: list=[0.9, 0.9]
) -> pd.DataFrame:

    # make sure all metrics requested are supported
    metrics = check_metrics_ngen_eval(metrics, dict_ngen_eval_metrics)

    #if len(df)==0:
    if len(df) < 2: #personr calculation requires data length of at least 2
        return pd.DataFrame()
    else:
        df1 = df.copy(deep=True)
        df1 = df1.set_index('value_time',inplace=False)
        values = mf.calculate_metrics(pd.Series(df1['primary_value']),pd.Series(df1['secondary_value']),metrics,thresholds[0], thresholds[1])
        values['lead_group'] = df1['lead_group'].unique()[0]
        values['primary_location_id'] = df1['primary_location_id'].unique()[0]

        return pd.DataFrame([values])


def calc_ngen_eval_metrics(
        pairs:Path, 
        metrics: list[str],
        #metrics: Optional[Union[str,list]]="all", 
        thresholds: Optional[list]=[0.9,0.9]
) -> pd.DataFrame:

    # read in paired data parquet
    df_pairs = pd.read_parquet(pairs)

    # get all the lead times
    lead_times = df_pairs['lead_group'].unique()

    # get all locations
    locations = df_pairs['primary_location_id'].unique()
    
    # drop unneeded columns
    df_pairs = df_pairs[['primary_location_id','lead_group','value_time','primary_value','secondary_value']]

    # sort by location then lead time
    df_pairs = df_pairs.sort_values(['primary_location_id','lead_group'])

    # use multiprocessing to compute metrics
    with Pool(cpu_count()-1) as pool: 
        results = []
        for l1 in locations:
            df1 = df_pairs[df_pairs['primary_location_id']==l1]
            for l2 in lead_times:
                df2 = df1[df1['lead_group']==l2]
                results.append(pool.apply_async(func_calc_metrics, args=(df2, metrics, thresholds)))
            
        new_dfs = [result.get() for result in results]
        df_metrics = pd.concat(new_dfs, ignore_index=True)

    return df_metrics

def calc_metrics_group(conf:dict, pair_file:Path, geofile: Path) -> pd.DataFrame:
   
    # metrics to be calculated 
    metrics = conf['metric_subset']
    if not metrics or metrics == ['all'] or metrics == 'all':               
        metrics = list(dict_teehr_metrics.keys()) if conf['library'] == 'teehr' else list(dict_ngen_eval_metrics.keys())
                         
    # exclude metrics as requested
    metrics_exclude = conf['metric_exclude']
    if metrics_exclude and len(metrics_exclude) > 0:
        metrics = [m1 for m1 in metrics if m1 not in metrics_exclude]

    # get all data pairs and raw lead times
    df0 = pd.read_parquet(pair_file)
    leads0 = df0['lead_time'].unique()
    leads0.sort()
    lead_step = leads0[0]

    # lead times to calculate metrics for (can be grouped lead times e.g., 1-3 hours)
    if 'lead_times' in conf.keys() and conf['lead_times'] is not None:
        lead_times = [str(x) for x in conf['lead_times']]
    else:
        lead_times = ['all']

    # interpret 'all' as calculating all native lead times (leads0)        
    if 'all' in lead_times:
        lead_times = list(map(str, leads0)) + [x for x in lead_times if x != 'all']
    
    # removed repetitive lead times if any
    lead_times = sorted(list(set(lead_times)))

    # loop through all lead times (including grouped lead times)
    df_metrics = pd.DataFrame()
    for l1 in lead_times:

        leads1 = l1.split('-')
        if len(leads1)==1:
            leads1 = leads1 + leads1
        leads1 = list(range(int(leads1[0]), int(leads1[1]) + lead_step, lead_step))

        # get paired data for the current lead time
        df1 = df0[df0['lead_time'].isin(leads1)]
        df1['lead_group'] = l1

        # save filtered data to new (temporary) parquet file
        pair_file1 = pair_file.with_name(pair_file.stem + ".new.parquet")
        df1.to_parquet(pair_file1)
          
        if conf['library'] == 'teehr':
            df_metrics = pd.concat([df_metrics, calc_teehr_metrics(pair_file1, geofile, metrics)], ignore_index=True)                

        elif conf['library'] == 'ngen.eval':
            thresholds = [conf['flow_threshold_categorical'], conf['flow_threshold_event']]
            df_metrics = pd.concat([df_metrics, calc_ngen_eval_metrics(pair_file1, metrics, thresholds)], ignore_index=True)

        else:
            raise Exception(f'Metric library {conf["library"]} not supported')
        
        # remove the temporary new parquet file
        pair_file1.unlink(missing_ok=True)
        del df1
        gc.collect()

    # If using teehr library, remap long name to short name for metrics
    if conf['library'] == 'teehr':
        df_metrics = df_metrics.rename(columns={v: k for k, v in dict_teehr_metrics.items()})

    return df_metrics

def calc_metrics(conf: dict, data_paths: dict):

    # library for calculating metrics
    supported_libraries = {'teehr', 'ngen.eval'}
    if 'library' not in conf['metrics']:
        raise KeyError("Missing required key: 'library' in metric configuration.")
    library = conf['metrics']['library']

    if library not in supported_libraries:
        raise ValueError(
            f"Unsupported metric library: '{library}'. "
            f"Supported libraries are: {', '.join(sorted(supported_libraries))}."
        ) 
    logger.info(f'  Metrics will be calculated using {library} library')

    # loop through dataset to calculate metrics
    for dataset in conf['general']['dataset_name']:
        
        # check if metric file already exists
        metric_file = data_paths['metrics'][dataset]
        metric_file.parent.mkdir(exist_ok=True, parents=True)
        if (metric_file.is_file() and (not conf['metrics']['overwrite'])):
            logger.info(f'  Metric file {metric_file} already exist; remove the file or change "overwrite" to False to recalcualte metrics')
        else:    

            # calculate metrics for each group of paired data and append to a single parquet file
            pair_path = data_paths['joined'][dataset]
            pair_files = list(pair_path.parent.glob(f'{pair_path.stem}.group*.parquet'))
            for i1, pair_file in enumerate(pair_files):
                logger.info(f'  Calculating metrics for {dataset} group {i1} ...')            
                df_metrics = calc_metrics_group(conf['metrics'], pair_file, data_paths['geofile']) 
                if i1 == 0:
                    df_metrics.to_parquet(metric_file, engine="fastparquet", index=False)
                else:
                    df_metrics.to_parquet(metric_file, engine="fastparquet", index=False, append=True) 
