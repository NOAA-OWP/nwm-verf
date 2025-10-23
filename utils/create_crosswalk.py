# Create crosswalk table between USGS gage IDs and NWM/NGENCERF reach/link/feature IDs and save in parquet files
# Use this script to create crosswalk for NWMv3.0 and NGENCERF simulations/forecasts
from pathlib import Path

import geopandas as gpd
import netCDF4 as nc
import numpy as np
import pandas as pd

# all four NWM domains
domains = ["CONUS", "AK", "HI", "Puerto_Rico"]
domains_long = ["CONUS", "Alaska", "Hawaii", "Puerto_Rico"]

# folder where NWMv30 route_link files are stored
dir1 = Path("~/work/data/NWMv3/Domain").expanduser()

# folder to store the crosswalk parquet files created
dir2 = Path("~/repos/nwm-verf/data/inputs/gage_files").expanduser()
dir2.mkdir(parents=True, exist_ok=True)

# loop through the domains
df_cwt = pd.DataFrame()
for d1, d1_long in zip(domains, domains_long):
    # read the route link file for each domain
    file1 = dir1 / d1_long / f"RouteLink_{d1}_NWMv3.0.nc"
    ncvar = nc.Dataset(file1, "r")

    # gages are two dimentional, first convert each row to list, then convert each value in the row from byte to str,
    # remove whitespace and then combine all items in the row into a gage ID
    gages = [
        "".join([s1.decode("utf-8").strip() for s1 in g1])
        for g1 in ncvar["gages"][:].tolist()
    ]
    links = ncvar["link"][:].tolist()

    # combine gages and links into a DataFrame, removing gages with blank IDs
    df = pd.DataFrame(
        [
            ("usgs-" + gage, "nwm30-" + str(link))
            for gage, link in zip(gages, links)
            if gage != ""
        ],
        columns=["primary_location_id", "secondary_location_id"],
    )

    # add domain info
    df["domain"] = d1
    df = df[["domain"] + [c1 for c1 in df.columns if c1 != "domain"]]

    # add the dataframe for all domains
    df_cwt = pd.concat([df_cwt, df], ignore_index=True)

# add geometry column based on lat/lon from gages_metadata_all_domains.csv
# first load metadata
meta_file = Path(
    "~/repos/nwm-verf/data/inputs/gage_files/gages_metadata_all_domains.csv"
).expanduser()
df_meta = pd.read_csv(meta_file, sep="\t")

# create primary_location_id
df_meta["primary_location_id"] = (
    df_meta["agency"].astype(str).str.lower() + "-" + df_meta["gage"].astype(str)
)

# keep only lat/lon and remove missing
df_meta = df_meta[["primary_location_id", "lat", "lon"]]
df_meta = df_meta[df_meta["lat"].notna() & df_meta["lon"].notna()]

# merge with df_cwt
df_cwt = df_cwt.merge(df_meta, on="primary_location_id", how="inner")

# convert to GeoDataFrame
gdf_cwt = gpd.GeoDataFrame(
    df_cwt, geometry=gpd.points_from_xy(df_cwt.lon, df_cwt.lat), crs="EPSG:4326"
)
gdf_cwt.drop(["lat", "lon"], axis=1, inplace=True)

# Ensure geometry is a proper GeometryArray
gdf_cwt["geometry"] = gpd.GeoSeries(gdf_cwt.geometry).values

# save to parquet files
gdf_cwt.to_parquet(dir2 / "usgs_nwm30_crosswalk_all_domains.parquet", index=False)

# create cwt for ngenCERF, deriving secondary_location_id from primary_location_id by replacing "usgs-" with "ngen-"
gdf_cwt_ngen = gdf_cwt.copy()
gdf_cwt_ngen["secondary_location_id"] = gdf_cwt_ngen["primary_location_id"].str.replace(
    "usgs-", "ngen-", regex=False
)

gdf_cwt_ngen.to_parquet(
    Path(dir2, "usgs_ngen_crosswalk_all_domains.parquet"), index=False
)
