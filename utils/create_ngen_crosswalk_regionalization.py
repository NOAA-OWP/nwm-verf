"""Create NGEN crosswalk for all gages for regionalization evaluation."""

import argparse
from pathlib import Path

import geopandas as gpd


def main(domain: str = "conus", out_dir: str | Path = "."):
    """Create ngen divide crosswalk for all gages for regionalization evaluation."""
    if domain.lower() == "conus":
        # Input GeoPackage (mount the s3 bucket with: s3fs hydrofabric-data ~/s3/hydrofabric-data)
        gpkg_file = Path(
            f"~/s3/hydrofabric-data/patch/7_30_25/nwm_patch_{domain}_nextgen.gpkg"
        ).expanduser()
    elif domain.lower() in ["prvi", "hi", "ak"]:
        gpkg_file = Path(
            f"~/repos/nwm-region-mgr/data/inputs/region/hydrofabric/gpkg_vpu/vpu_{domain.lower()}.gpkg"
        ).expanduser()
    else:
        print(
            f"Unsupported domain: {domain}. Supported domains are: conus, prvi, hi, ak."
        )
        exit(1)

    print(f"Reading hydrolocations from {gpkg_file}...")
    gdf = gpd.read_file(gpkg_file, layer="hydrolocations")

    # Select required columns
    df_cwt = gdf[["id", "hl_uri", "vpuid"]].copy()

    # first remove rows with hl_uri being NaN or empty string
    df_cwt = df_cwt[df_cwt["hl_uri"].notna() & (df_cwt["hl_uri"] != "")].copy()

    # Keep only rows with hl_uri starting with 'gages-' or "Gages-"
    df_cwt = df_cwt[df_cwt["hl_uri"].str.startswith(("gages-", "Gages-"))].copy()

    # convert Gages to gages in hl_uri
    df_cwt["hl_uri"] = df_cwt["hl_uri"].str.replace("Gages-", "gages-", regex=False)

    print(f"Reading divides from {gpkg_file}...")
    gdf_divides = gpd.read_file(gpkg_file, layer="divides")[["id", "geometry"]]

    print("Merging crosswalk with divide geometries...")
    df_cwt = df_cwt.merge(gdf_divides, on="id", how="left")
    gdf_cwt = gpd.GeoDataFrame(df_cwt, geometry="geometry", crs=gdf_divides.crs)

    print("Converting divide polygons to points with centroids...")

    # Reproject to projected CRS
    gdf_proj = gdf_cwt.to_crs("EPSG:5070")

    # Compute centroid in meters
    gdf_cwt["centroid"] = gdf_proj.geometry.centroid

    # Reproject centroids to WGS84 lat/lon and create point geometries
    gdf_cwt["centroid"] = gpd.GeoSeries(gdf_cwt["centroid"], crs="EPSG:5070").to_crs(
        epsg=4326
    )
    gdf_cwt["geometry"] = gpd.points_from_xy(
        gdf_cwt["centroid"].x, gdf_cwt["centroid"].y, crs=gdf_cwt.crs
    )
    gdf_cwt = gdf_cwt.drop(columns=["centroid"])

    # Replace prefixes to make location IDs
    gdf_cwt["secondary_location_id"] = gdf_cwt["id"].str.replace(
        "wb-", "ngen-", regex=False
    )
    gdf_cwt["primary_location_id"] = gdf_cwt["hl_uri"].str.replace(
        "gages-", "usgs-", regex=False
    )

    # Add domain column
    gdf_cwt["domain"] = domain.upper()

    # Reorder columns
    gdf_cwt = gdf_cwt[
        ["domain", "primary_location_id", "secondary_location_id", "vpuid", "geometry"]
    ]

    # Save the crosswalk GeoDataFrame to Parquet
    cwt_file = Path(out_dir) / f"usgs_ngen_crosswalk_{domain}.parquet"
    print(f"Saving Crosswalk GeoDataFrame to {cwt_file} with {len(gdf_cwt)} entries...")

    cwt_file.parent.mkdir(parents=True, exist_ok=True)
    gdf_cwt.to_parquet(cwt_file, index=False)

    # loop through unique VPUs to create a gage list file for each VPU
    for vpu in gdf_cwt["vpuid"].dropna().unique():
        df_vpu = gdf_cwt.loc[gdf_cwt["vpuid"] == vpu, ["primary_location_id"]].copy()
        df_vpu.rename(columns={"primary_location_id": "gage"}, inplace=True)

        # remove "gages-" prefix
        df_vpu["gage"] = df_vpu["gage"].str.replace("usgs-", "", regex=False)

        gage_file = Path(out_dir) / f"gage_list_{domain}_vpu_{vpu}.csv"
        df_vpu = df_vpu.sort_values(by="gage").reset_index(drop=True)

        df_vpu.to_csv(gage_file, index=False, header=True)
        print(f"Gage list for VPU {vpu} saved to {gage_file} with {len(df_vpu)} gages.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create crosswalk for all gages.")
    parser.add_argument(
        "--out_dir",
        default=Path("~/repos/nwm-verf/data/inputs/regionalization").expanduser(),
        help="Output directory for the crosswalk files",
    )
    parser.add_argument(
        "--domain",
        type=str,
        default="conus",
        help="Domain name (default: conus)",
    )
    args = parser.parse_args()
    main(args.domain, args.out_dir)
