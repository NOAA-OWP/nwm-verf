
import pandas as pd
from pathlib import Path
from typing import Union, Optional, Dict, List
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

__all__ = [
    "get_link_by_gage",
    "get_link_id_from_file",
    "get_locations_from_config_list",
    "get_nwm_link_ids",
    "get_gage_by_link",
    "get_gage_id_from_file",
    "get_usgs_gage_ids",    
]


# get location link ID based on gage ID and crosswalk 
def get_link_by_gage(gages: List[str], crosswalk_file: str):

    cwt = pd.read_parquet(crosswalk_file)
    cwt.rename(columns={'primary_location_id':'gage'}, inplace=True)
    
    df = pd.DataFrame(list(map('usgs-'.__add__,gages)), columns=['gage'])
    df1 = df.merge(cwt,on='gage',how='inner')
    miss_ids = []
    if len(df1) < len(df):
        miss_ids = [x for x in df['gage'].tolist() if x not in df1['gage'].tolist()]
        logger.info(f'  Link ID for gages {miss_ids} are not found in crosswalk file {crosswalk_file}')
    
    gages1 = [x[1] for x in df1['gage'].str.split('-')]
    links1 = [int(x[1]) for x in df1['secondary_location_id'].str.split('-')]  

    return gages1, links1 

# get location link IDs (NWM feature or reach id) from locations in a file
def get_link_id_from_file(
    id_file: str, 
    nwm_ver: str,
    crosswalk_file: Optional[str] = None,
) -> list:
    
    f1 = Path(id_file).absolute()
    if not f1.exists():
        raise FileNotFoundError(f1)
    df = pd.read_csv(f1, sep=None,comment='#',engine='python')
    df.columns = [x.lower() for x in df.columns]
    locations = []
    link1 = nwm_ver + '_link'
    if link1 in df.columns:
        locations = df[link1].tolist()
    elif 'gage' in df.columns:
        crosswalk_file = Path(crosswalk_file).absolute()
        if not crosswalk_file.exists():
            raise FileNotFoundError(crosswalk_file)
        locations = get_link_by_gage(df['gage'].tolist(), crosswalk_file)
    else:
        raise Exception(f'No "gage" or "{link1}" column found in {id_file}')
    
    return locations

# get list of locations as either "gage" or "link" based on location_list provided in config file,
# i.e., not via a location_list_file
def get_locations_from_config_list(conf:dict, id_type:str, nwm_ver: Optional[str]=None) -> list:

    locations = []
    loc_list = conf['general']['location_list']
    loc_type = conf['general']['location_type']
    crosswalk_file = conf['file_paths']['crosswalk_file']
    if loc_list is not None and loc_type is None:
        raise ValueError(f'config general section: location_type must be provided when location_list is not empty')
    else:
        if (loc_type in [x + '_link' for x in list(set(conf['general']['nwm_version']))]):
            ver1 = loc_type.split('_')[0]
            if ver1 not in crosswalk_file.keys():
                raise ValueError(f'Crosswalk file is not found for {ver1}')
            else:
                if id_type == 'gage':
                    locations = get_gage_by_link(loc_list, crosswalk_file[ver1])
                elif id_type == 'link':
                    locations = loc_list.copy()
                else:
                    raise ValueError(f'location type {id_type} not supported')
        elif (loc_type == "usgs_gage"):
            if id_type == 'gage':
                locations = loc_list.copy()
            elif id_type == 'link':
                locations = get_link_by_gage(loc_list, crosswalk_file[nwm_ver])
            else:
                raise ValueError(f'location type {id_type} not supported')
        else:
            raise ValueError(f'location_type must be either "usgs_gage" or "nwm30_link" or "nwm22_link')

    return locations

# get nwm link ids for the locations for retrieveing the forecasts
def get_nwm_link_ids(conf: dict, nwm_ver: str) -> list:

    location_list = conf['general']['location_list']
    location_type = conf['general']['location_type']
    location_list_file = conf['file_paths']['location_list_file']
    crosswalk_file = conf['file_paths']['crosswalk_file']

    locations = []
    if (location_list is not None):
        locations = get_locations_from_config_list(conf, 'link', nwm_ver)
    elif (location_list_file is not None):
        location_list_file = Path(location_list_file).absolute()
        if not location_list_file.exists():
            raise FileNotFoundError(location_list_file)
        if nwm_ver in crosswalk_file.keys() and crosswalk_file[nwm_ver] is not None:
            cwf = Path(crosswalk_file[nwm_ver]).absolute()
            if not cwf.exists():
                raise FileNotFoundError(cwf)
            locations = get_link_id_from_file(location_list_file, nwm_ver, cwf)
        else:
            raise ValueError(f'Crosswalk file for {nwm_ver} is not provided')
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

# get USGS gage ID for locations from the location_list_file
def get_gage_id_from_file(
    id_file: str, 
    crosswalk_file: Optional[dict] = None,
) -> list:
    
    f1 = Path(id_file).absolute()
    if not f1.exists():
        raise FileNotFoundError(f1)
    df = pd.read_csv(f1, sep=None,comment='#', dtype={'gage': str}, engine='python')
    df.columns = [x.lower() for x in df.columns]
    locations = []
    if 'gage' in df.columns:
        locations = df['gage'].tolist()    
    else:
        # check for link columns
        cols = [c1 for c1 in df.columns if 'link' in c1]
        if len(cols)>0:
            for c1 in cols:
                ver1 = c1.split('_')[0]
                if ver1 in crosswalk_file.keys() and crosswalk_file[ver1] is not None:
                    cwf = Path(crosswalk_file[ver1])
                    if cwf.exists():
                        locations = get_gage_by_link(df[c1].tolist(), cwf)
                        break
                    else:
                        logger.info(f'crosswalk file not found: {cwf}')
        else:
            raise ValueError(f'No gage or NWM link column (e.g., nwmv30_link) is not found in location file')
    
    return locations

# get USGS ID for the locations from config.yaml or a separate file
def get_usgs_gage_ids(conf:dict) -> list:

    location_list = conf['general']['location_list']
    location_list_file = conf['file_paths']['location_list_file']
    crosswalk_file = conf['file_paths']['crosswalk_file']
    gage_meta_file = conf['file_paths']['gage_meta_file'] 

    locations = []
    if (location_list is not None):
        locations = get_locations_from_config_list(conf,'gage')
    elif (location_list_file is not None):
        location_list_file = Path(location_list_file).absolute()
        locations = get_gage_id_from_file(location_list_file, crosswalk_file)
    else:
        raise ValueError(f'Either location_list or location_list_file must be provided in configuration yaml file')

    # only accept usgs locations for now
    gage_meta_file = Path(gage_meta_file).absolute()
    if not gage_meta_file.exists():
        raise FileNotFoundError(gage_meta_file)
    df = pd.read_csv(gage_meta_file,sep=None,comment='#',engine='python')
    #gages = [x for x in locations if df[df['gage']==x]['agency'].iloc[0] == 'USGS']
    gages = [x for x in locations if not df[df['gage'] == x].empty and df[df['gage'] == x]['agency'].iloc[0] == 'USGS']

    missed = [x for x in locations if x not in gages]
    if len(missed)>0:
        logger.info(f'  The following non-usgs locations will be dropped {missed}')
    
    return gages 

def identify_locations(conf:dict) -> dict:

    # get USGS gage ID for verification locations
    locations_usgs = get_usgs_gage_ids(conf) 

    locations = {}
    for dataset_idx, dataset in enumerate(conf['general']['dataset_name']):

        # get NWM link ID based on USGS gage ID
        nwm_version = conf['general']['nwm_version'][dataset_idx]
        locations_usgs1, locations_nwm1 = get_link_by_gage(locations_usgs, conf['file_paths']['crosswalk_file'][nwm_version])
        logger.info(f'  Total number of locations for dataset {dataset}: {len(locations_nwm1)}')
        locations[dataset] = {'primary': locations_usgs1, 'secondary': locations_nwm1}

    return locations