# Create geopandas parquet files for all usgs gages

from pathlib import Path

import geopandas as gpd
import pandas as pd

# root dir for all data
root_dir = Path("~/repos/nwm-verf/data/inputs/gage_files").expanduser()

# get gage IDs from crosswalk parquet
# cwt = pd.read_parquet(Path(root_dir, "usgs_nwm30_crosswalk_all_domains.parquet"))
# cwt.columns = ["domain", "gage", "link"]

# read gage metadata
f1 = Path(root_dir, "gages_metadata_all_domains.csv").resolve(strict=True)
df = pd.read_csv(f1, sep="\t")

# align with gage ids used in crosswalk
# df["gage"] = "usgs-" + df["gage"]
df["primary_location_id"] = (
    df["agency"].astype(str).str.lower() + "-" + df["gage"].astype(str)
)

# filter with gages in crosswalk
# df = pd.merge(df, cwt, on="gage", how="inner")
# remove rows with lat or lon being NaN or
df = df[df["lat"].notna() & df["lon"].notna()]

# create geopandas dataframe with lat/lon coordinates
gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326")
gdf.drop(["lat", "lon", "gage"], axis=1, inplace=True)

# rename column
# gdf.rename(columns={"gage": "id"}, inplace=True)

# make sure primary_location_id is the first column
gdf = gdf[
    ["primary_location_id"] + [c1 for c1 in gdf.columns if c1 != "primary_location_id"]
]

# sort by primary_location_id
gdf.sort_values("primary_location_id", inplace=True)

# save to parquet file
gdf.to_parquet(Path(root_dir, "gage_hydrofabric_all_domains.parquet"), index=False)
