# Create geopandas parquet files for all usgs gages

import geopandas as gpd
import pandas as pd
from pathlib import Path

# all four NWM domains
domains = ['CONUS', 'AK', 'HI', 'PR']

# root dir for all data
root_dir = Path('/home/yuqiong.liu/work/data/ngen-verf').resolve()

# folder where the crosswalk parquet files are stored
dir1 = Path(root_dir,'crosswalks').resolve()

# folder to store the geometry parquet files
dir2 = Path(root_dir,'geometry').resolve()

# loop through the four domains
for d1 in domains:

    # get gage IDs from crosswalk parquet
    cwt = pd.read_parquet(Path(dir1, 'usgs_nwm30_crosswalk_' + d1 + '.parquet'))
    cwt.columns = ['gage','link']

    # read gage metadata
    f1 = Path(root_dir,"gages_metadata_all_domains.csv").resolve(strict=True)
    df = pd.read_csv(f1,sep='\t')

    # align with gage ids used in crosswalk
    df['gage'] = 'usgs-' + df['gage']

    # filter with gages in crosswalk
    df = pd.merge(df,cwt,on='gage',how='inner')
    print(len(df))
    #df = df.loc[df['id'].isin(gages)]

    # create geopandas dataframe with coordinates
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326")
    gdf.drop(['lat','lon'], axis=1, inplace=True)

    # save to parquet files
    gdf.rename(columns={"gage":"id"},inplace=True)
    print(gdf.columns)
    gdf.to_parquet(Path(dir2, 'usgs_point_geometry_' + d1 + '.parquet'))

    # for conus domain, sample 100 calibration basins for testing verification capability
    # if d1=='CONUS':
    #     gdf1 = gdf.loc[gdf['calibration']]
    #     gdf1 = gdf1.iloc[random.sample(list(range(len(gdf1))),100),]
    #     gdf1.to_parquet(Path(dir2, 'usgs_point_geometry_' + d1 + '_calib100.parquet'))
    #     gdf1.plot()

    #     df1 = gdf1[['gage','link','name']].copy(deep=True)
    #     df1['gage'] = df1['gage'].str.replace("usgs-","")
    #     df1['link'] = df1['link'].str.replace("nwm30-","").astype(int)
    #     df1.to_csv(Path(Path(dir2).parent, 'usgs_gages_link_' + d1 + '_calib100.csv'), sep='\t', index=False)        


# save list of gages to txt for each domain (to provide to hydrofabric team to create gpkg files)
# for d1 in domains:
#     f1 = Path(dir2, 'usgs_point_geometry_' + d1 + '.parquet')
#     df1 = pd.read_parquet(f1)
#     gages = df1.loc[df1['calibration']]['gage'].str.replace("usgs-","").tolist()
#     print(list(set(df1['agency'].to_list())))

#     with open(Path('/home/yuqiong.liu/work/data/NWMv3', 'nwm_calib_gages_' + d1 + '.txt'),'w') as f:
#         for g1 in gages:
#             f.writelines(f'{g1}\n')

