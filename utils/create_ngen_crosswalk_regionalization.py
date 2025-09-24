"""Retrieve VPU gpkg from conus.gpkg file"""

import argparse
from pathlib import Path

import geopandas as gpd


def main(domain: str = "conus", out_dir: str | Path = "."):
    """Create ngen divide crosswalk for all gages for regionalization evaluation."""
    # conus gpkg file
    conus_in = Path(
        f"~/s3/hydrofabric-data/patch/7_30_25/nwm_patch_{domain}_nextgen.gpkg"
    ).expanduser()

    # Read in conus geopackage hydrolocations layer
    gdf = gpd.read_file(conus_in, layer="hydrolocations")

    # get required columns (id: feature id, hl_uri: gage id, vpuid: vpu id)
    df_cwt = gdf[["id", "hl_uri", "vpuid"]].copy()

    # keep only rows with hl_uri starting with 'gages-'
    df_cwt = df_cwt[df_cwt["hl_uri"].str.startswith("gages-")].copy()

    # replace "wb-" with "ngen-" in id columns to create secondary_location_id
    df_cwt["secondary_location_id"] = df_cwt["id"].str.replace(
        "wb-", "ngen-", regex=False
    )

    # replace "gages-" with "usgs-" in hl_uri column to create primary_location_id
    df_cwt["primary_location_id"] = df_cwt["hl_uri"].str.replace(
        "gages-", "usgs-", regex=False
    )

    # add domain column
    df_cwt["domain"] = domain.upper()

    # reorder columns
    df_cwt = df_cwt[["domain", "primary_location_id", "secondary_location_id", "vpuid"]]

    # Save the crosswalk table to a parquet file
    cwt_file = Path(out_dir) / f"usgs_ngen_crosswalk_{domain}.parquet"
    cwt_file.parent.mkdir(parents=True, exist_ok=True)
    df_cwt.to_parquet(cwt_file, index=False)
    print(f"Crosswalk table saved to {cwt_file} with {len(df_cwt)} entries.")

    # loop through unique VPUs to create a gage list file for each VPU
    for vpu in df_cwt["vpuid"].dropna().unique():
        df_vpu = df_cwt.loc[df_cwt["vpuid"] == vpu, ["primary_location_id"]].copy()
        df_vpu.rename(columns={"primary_location_id": "gage"}, inplace=True)

        # remove "gages-" prefix
        df_vpu["gage"] = df_vpu["gage"].str.replace("usgs-", "", regex=False)

        gage_file = Path(out_dir) / f"gage_list_{domain}_vpu_{vpu}.txt"
        df_vpu = df_vpu.sort_values(by="gage").reset_index(drop=True)

        df_vpu.to_csv(gage_file, index=False, header=True)
        print(f"Gage list for VPU {vpu} saved to {gage_file} with {len(df_vpu)} gages.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create crosswalk for all gages.")
    parser.add_argument(
        "--out_dir", required=True, help="Output directory for the crosswalk files"
    )
    parser.add_argument(
        "--domain",
        type=str,
        default="conus",
        help="Domain name (default: conus)",
    )
    args = parser.parse_args()
    main(args.domain, args.out_dir)
