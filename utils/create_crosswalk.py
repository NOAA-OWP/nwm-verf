# Create crosswalk table between USGS gage IDs and NWM reach/link/feature IDs and save in parquet files

import os

import netCDF4 as nc
import numpy as np
import pandas as pd

# all four NWM domains
domains = ["CONUS", "AK", "HI", "Puerto_Rico"]
domains_long = ["CONUS", "Alaska", "Hawaii", "Puerto_Rico"]

# folder where NWMv30 route_link files are stored
dir1 = os.path.expanduser("~/work/data/NWMv3/Domain")

# folder to store the crosswalk parquet files created
dir2 = os.path.expanduser("~/repos/nwm-verf/data/inputs/gage_files")
if not os.path.isdir(dir2):
    os.makedirs(dir2)

# loop through the domains
df_cwt = pd.DataFrame()
for d1, d1_long in zip(domains, domains_long):
    # read the route link file for each domain
    file1 = os.path.join(dir1, d1_long + "/RouteLink_" + d1 + "_NWMv3.0.nc")
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

# save to parquet files
df_cwt.to_parquet(os.path.join(dir2, "usgs_nwm30_crosswalk_all_domains.parquet"))

# create cwt for ngen, deriving secondary_location_id from primary_location_id by replacing "usgs-" with "ngen-"
df_cwt_ngen = df_cwt.copy()
df_cwt_ngen["secondary_location_id"] = df_cwt_ngen["primary_location_id"].str.replace(
    "usgs-", "ngen-", regex=False
)

df_cwt_ngen.to_parquet(os.path.join(dir2, "usgs_ngen_crosswalk_all_domains.parquet"))
