
import pandas as pd
from pathlib import Path
from typing import Union, Optional, Dict
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

__all__ = [
    "get_link_by_gage",
    "get_link_id_from_file",
    "get_nwm_link_ids",
    "get_gage_by_link",
    "get_gage_id_from_file",
    "get_usgs_gage_ids",    
]


# get location link ID based on gage ID and crosswalk 
def get_link_by_gage(gages: str, crosswalk_file: str):

    cwt = pd.read_parquet(crosswalk_file)
    cwt.rename(columns={'primary_location_id':'gage'}, inplace=True)
    
    df = pd.DataFrame(list(map('usgs-'.__add__,gages)), columns=['gage'])
    df1 = df.merge(cwt,on='gage',how='inner')
    if len(df1) < len(df):
        miss_ids = [x for x in df['gage'].tolist() if x not in df1['gage'].tolist()]
        logger.info(f'  Link ID for gages {miss_ids} are not found in crosswalk file {crosswalk_file}')
    locations = [int(x[1]) for x in df1['secondary_location_id'].str.split('-')]  

    return locations 

# get location link IDs (NWM feature or reach id)
def get_link_id_from_file(
    id_file: str, 
    crosswalk_file: Optional[str] = None,
) -> list:
    
    f1 = Path(id_file).resolve(strict=True)
    df = pd.read_csv(f1, sep='\t')
    df.columns = [x.lower() for x in df.columns]
    locations = []
    if 'link' in df.columns:
        locations = df['link'].tolist()
    elif 'gage' in df.columns:
        crosswalk_file = Path(crosswalk_file).resolve(strict=True)
        locations = get_link_by_gage(df['gage'].tolist(), crosswalk_file)
    
    return locations

def get_nwm_link_ids(conf: dict) -> list:

    location_list = conf['general']['location_list']
    location_type = conf['general']['location_type']
    location_list_file = conf['file_paths']['location_list_file']
    crosswalk_file = conf['file_paths']['crosswalk_file']

    locations = []
    if (location_list is not None):
        if location_type is None:
            raise ValueError(f'config general section: location_type must be provided when location_list is not empty')
        else:
            if (location_type == 'nwm_link'):
                pass
            elif (location_type == "usgs_gage"):
                locations = get_link_by_gage(locations, 'crosswalk_file')
            else:
                raise ValueError(f'location_type must be either "usgs_gage" or "nwm_link"')
    elif (location_list_file is not None):
        location_list_file = Path(location_list_file).resolve(strict=True)
        locations = get_link_id_from_file(location_list_file, crosswalk_file)
    else:
        raise ValueError(f'Either location_list or location_list_file must be provided in configuration yaml file')

    logger.info(f'  Total number of nwm locations: {len(locations)}')

    return locations 

# get location gage ID based on link ID and crosswalk 
def get_gage_by_link(links: int, crosswalk_file: str):

    cwt = pd.read_parquet(crosswalk_file)
    cwt.rename(columns={'primary_location_id':'gage'}, inplace=True)
    cwt.rename(columns={'secondary_location_id':'link'}, inplace=True)
    
    df = pd.DataFrame(list(map('nwm30-'.__add__,str(links))), columns=['link'])
    df1 = df.merge(cwt,on='link',how='inner')
    if len(df1) < len(df):
        miss_ids = [x for x in df['link'].tolist() if x not in df1['link'].tolist()]
        logger.info(f'  Gage ID for links {miss_ids} are not found in crosswalk file {crosswalk_file}')
    locations = [int(x[1]) for x in df1['gage'].str.split('-')]  

    return locations 

# get USGS gage ID for locations from file
def get_gage_id_from_file(
    id_file: str, 
    crosswalk_file: Optional[str] = None,
) -> list:
    
    f1 = Path(id_file).resolve(strict=True)
    df = pd.read_csv(f1, sep='\t')
    df.columns = [x.lower() for x in df.columns]
    locations = []
    if 'gage' in df.columns:
        locations = df['gage'].tolist()    
    elif 'link' in df.columns:
        crosswalk_file = Path(crosswalk_file).resolve(strict=True)
        locations = get_gage_by_link(df['link'].tolist(), crosswalk_file)
    
    return locations

# get USGS ID for the locations from config.yaml or a separate file
def get_usgs_gage_ids(conf:dict) -> list:

    location_list = conf['general']['location_list']
    location_type = conf['general']['location_type']
    location_list_file = conf['file_paths']['location_list_file']
    crosswalk_file = conf['file_paths']['crosswalk_file']
    gage_meta_file = conf['file_paths']['gage_meta_file'] 

    locations = []
    if (location_list is not None):
        if location_type is None:
            raise ValueError(f'config general section: location_type must be provided when location_list is not empty')
        else:
            if (location_type == 'nwm_link'):
                locations = get_gage_by_link(locations, 'crosswalk_file')
            elif (location_type == "usgs_gage"):
                pass               
            else:
                raise ValueError(f'location_type must be either "usgs_gage" or "nwm_link"')
    elif (location_list_file is not None):
        location_list_file = Path(location_list_file).resolve(strict=True)
        locations = get_gage_id_from_file(location_list_file, crosswalk_file)
    else:
        raise ValueError(f'Either location_list or location_list_file must be provided in configuration yaml file')

    # only accept usgs locations for now
    df = pd.read_csv(gage_meta_file,sep='\t')
    gages = [x for x in locations if df[df['gage']==x]['agency'].iloc[0] == 'USGS']
    missed = [x for x in locations if x not in gages]
    if len(missed)>0:
        logger.info(f'  The following non-usgs locations will be dropped {missed}')

    logger.info(f'  Total number of USGS locations: {len(gages)}')
    
    return gages 
