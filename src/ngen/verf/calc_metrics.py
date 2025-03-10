import pandas as pd
import numpy as np
from pathlib import Path
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
def calc_teehr_metrics(pairs:Path, geometry: Path, metrics: Union[str,list]='all') -> pd.DataFrame:

    # determine the list of metrics to compute
    if not metrics:
        metrics = 'all'
    else:
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
        metrics: Optional[Union[str,list]]='all', 
        thresholds: list=[0.9, 0.9]
) -> pd.DataFrame:

    # detemine the list of metrics to compute
    if not metrics:
        metrics = 'all'
    if metrics == 'all':
        metrics = dict_ngen_eval_metrics.keys()
    metrics = check_metrics_ngen_eval(metrics, dict_ngen_eval_metrics)

    if len(df)==0:
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
        metrics: Optional[Union[str,list]]="all", 
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
                results.append(pool.apply_async(func_calc_metrics, args=(df2,metrics,thresholds)))
            
        new_dfs = [result.get() for result in results]
        df_metrics = pd.concat(new_dfs, ignore_index=True)

    return df_metrics

def calc_metrics(conf:dict, data_paths:dict, dataset: str, overwrite:bool) -> pd.DataFrame:
   
    # check if metric file already exists
    metric_file = data_paths['metrics'][dataset]
    metric_file.parent.mkdir(exist_ok=True, parents=True)
    if (metric_file.is_file() and (not overwrite)):
        logger.info(f'  Metric file {metric_file} already exist; remove the file or change "overwrite" to False to recalcualte metrics')
    else:      
        # metrics to be calculated 
        metrics = conf['metric_subset']
        if not isinstance(metrics,list):
            if metrics != 'all':
                raise Exception(f'metric_subset can only be a list or "all"')

        # get all data pairs and raw lead times
        pairs = data_paths['joined'][dataset]
        df0 = pd.read_parquet(pairs)
        leads0 = df0['lead_time'].unique()
        leads0.sort()
        lead_step = leads0[0]

        # lead times to calculate metrics for (can be grouped lead times e.g., 1-3 hours)
        if 'lead_times' in conf.keys() and conf['lead_times'] is not None:
            lead_times = [str(x) for x in conf['lead_times']]
        else:
            lead_times = ['all']

        # removed repetitive lead times covered by "all" raw lead times
        if 'all' in lead_times:
            lead_times = [x for x in lead_times if x != str(lead_step)]
        lead_times = list(set(lead_times))

        # get all lead times (groups) and all lead time intervals (in hours)
        lead_ints = []
        lead_times_all = []
        for s1 in lead_times:
            if s1=='all':
                int1 = [lead_step] * len(leads0)
                lead_ints = lead_ints + int1
                lead_times_all = lead_times_all + list(map(str, leads0))
            else:
                range1 = [int(x) for x in s1.split('-')]
                if len(range1) == 1:
                    range1 = [range1[0]-lead_step] + range1
                int1 = range1[1] - range1[0]
                int1 = int1 if int1 == lead_step else int1 + 1
                lead_times_all = lead_times_all + [s1]
                lead_ints = lead_ints + [int1]     

        assert len(lead_times_all) == len(lead_ints), \
            f'lead_times_all (len={len(lead_times_all)}) and lead_ints (len={len(lead_ints)}) must have the same length'

        # loop through all lead time intervals to calculate metrics
        lead_ints_unique = list(set(lead_ints))
        df_metrics = pd.DataFrame()
        for l1 in lead_ints_unique:

            # add a column of lead time group (string) to the paired data
            if l1 == lead_step:
                lead_grps = [str(x) for x in leads0]
                df0['lead_group'] = df0['lead_time'].map(str)
            else:
                bins = list(range(0, max(leads0)+1, l1))
                cuts = pd.cut(leads0, bins, right=True, include_lowest=False)
                lead_grps = [x.replace('(','').replace(']','').replace(', ','-') for x in cuts.astype(str)]
                lead_grps = [str(int(x.split('-')[0])+1) + '-' + x.split('-')[1] if x!='nan' else x for x in lead_grps]
                df0['lead_group'] = df0['lead_time'].map(dict(zip(leads0, lead_grps)))

            # gather lead time groups (to be computed) that are corresponding to the current lead time interval
            leads = [x for x,y in zip(lead_times_all, lead_ints) if y==l1]

            # filter paired data based on lead times
            lead_groups0 = df0['lead_group'].unique()
            leads1 = [l1 for l1 in leads if l1 not in lead_groups0]
            if len(leads1) > 0:
                raise Exception(f'  lead group {leads1} not found in paired data')
            df0 = df0[df0['lead_group'].isin(leads)]

            # save filtered data to new parquet file
            pairs1 = Path(str(pairs).replace('joined.parquet','joined_new.parquet'))
            df0.to_parquet(pairs1)
          
            if conf['library'] == 'teehr':
                logger.info(f'  Calculating metrics using teehr library')
                df_metrics = pd.concat([df_metrics, calc_teehr_metrics(pairs1, data_paths['geofile'], metrics)], ignore_index=True)

            elif conf['library'] == 'ngen.eval':
                thresholds = [conf['flow_threshold_categorical'], conf['flow_threshold_event']]
                logger.info(f'  Calculating metrics using ngen.eval library')
                df_metrics = pd.concat([df_metrics, calc_ngen_eval_metrics(pairs1, metrics, thresholds)], ignore_index=True)

            else:
                raise Exception(f'Metric library {conf["library"]} not supported')
   
        # save metrics to parquet file
        df_metrics.to_parquet(metric_file)
        logger.info(f'  Metrics for dataset {dataset} are save at {metric_file}')

    return df_metrics