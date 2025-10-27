# Create geopandas parquet files for all usgs gages

from pathlib import Path

import geopandas as gpd
import pandas as pd

# root dir for all data
root_dir = Path("~/repos/nwm-verf/data/inputs/").expanduser()

# get gage IDs from crosswalk parquet
cwt = pd.read_parquet(
    Path(root_dir, "regionalization", "usgs_ngen_crosswalk_conus.parquet")
)

# read gage metadata
f1 = Path(root_dir, "gage_files", "gages_metadata_all_domains.csv").resolve(strict=True)
df = pd.read_csv(f1, sep="\t")

# align with gage ids used in crosswalk
df["primary_location_id"] = (
    df["agency"].astype(str).str.lower() + "-" + df["gage"].astype(str)
)

# filter with gages in crosswalk
df = pd.merge(df, cwt, on="primary_location_id", how="outer")

# remove rows with lat or lon being NaN or
df = df[df["lat"].notna() & df["lon"].notna()]

# create geopandas dataframe with lat/lon coordinates
gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326")
gdf.drop(["lat", "lon", "gage"], axis=1, inplace=True)

# make sure primary_location_id is the first column
gdf = gdf[
    ["primary_location_id"] + [c1 for c1 in gdf.columns if c1 != "primary_location_id"]
]

# sort by primary_location_id
gdf.sort_values("primary_location_id", inplace=True)

# save to parquet file
gdf.to_parquet(Path(root_dir, "gage_hydrofabric_all_domains.parquet"), index=False)
print(gdf.head())
