# Create crosswalk table between USGS gage IDs and NWM reach/link/feature IDs and save in parquet files

import netCDF4 as nc
import pandas as pd
import os
import numpy as np

# all four NWM domains
domains = ['CONUS', 'AK', 'HI', 'PR']

# folder where NWMv30 route_link files are stored 
dir1 = '/home/yuqiong.liu/work/data/NWMv3/Domain'

# folder to store the crosswalk parquet files created
dir2 = '/home/yuqiong.liu/work/data/ngen-verf/crosswalks'
if not os.path.isdir(dir2):
    os.makedirs(dir2)

# loop through the domains
for d1 in domains:
    file1 = os.path.join(dir1,d1 + '/RouteLink_' + d1 + '_NWMv3.0.nc')
    ncvar = nc.Dataset(file1, "r")
    # gages are two dimentional, first convert each row to list, then convert each value in the row from byte to str, 
    # remove whitespace and then combine all items in the row into a gage ID
    gages = [''.join([s1.decode("utf-8").strip() for s1 in g1]) for g1 in ncvar['gages'][:].tolist()]
    links = ncvar['link'][:].tolist()

    # combine gages and links into a DataFrame, removing gages with blank IDs
    df = pd.DataFrame([('usgs-'+gage,'nwm30-'+str(link)) for gage,link in zip(gages,links) if gage!=''],
                  columns=['primary_location_id','secondary_location_id'])
    
    # save to parquet files
    df.to_parquet(os.path.join(dir2, 'usgs_nwm30_crosswalk_' + d1 + '.parquet'))


