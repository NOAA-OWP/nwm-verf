"""Create NGEN crosswalk for all gages for evaluation and plot a gage map."""

import argparse
from pathlib import Path

import contextily as cx
import fiona
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

from nwm.verf.settings import conus_vpu_list, default_txdot_gage_list

ALL_VPUS = {
    "conus": conus_vpu_list,
    "prvi": ["prvi"],
    "hi": ["hi"],
    "ak": ["ak"],
}


def create_crosswalk(domain: str, vpu: str, out_dir: str | Path) -> gpd.GeoDataFrame:
    """Create crosswalk for a specific VPU."""
    print(f"Creating crosswalk for VPU {vpu}...")

    if vpu in ["prvi", "hi", "ak"]:
        gpkg_file = Path(
            f"~/data/hydrofabric/gpkg_nhf/{vpu}_nhf_1.1.3.gpkg"
        ).expanduser()
    else:
        gpkg_file = Path(f"~/data/hydrofabric/gpkg_nhf/vpu_{vpu}.gpkg").expanduser()

    if not gpkg_file.exists():
        print(f"Error: GeoPackage file {gpkg_file} does not exist.")
        return gpd.GeoDataFrame()

    # get gages layer in the GeoPackage
    layers = fiona.listlayers(gpkg_file)
    if "gages" not in layers:
        print(
            f"Error: GeoPackage file {gpkg_file} does not contain required layer 'gages'."
        )
        return gpd.GeoDataFrame()

    # read gages layer
    gdf_gages = gpd.read_file(gpkg_file, layer="gages")
    gdf_gages = gdf_gages[
        ["site_no", "fp_id", "USGS_basin_km2", "status", "geometry"]
    ].copy()

    # add vpu_id  and domain columns
    gdf_gages["vpu_id"] = vpu
    gdf_gages["domain"] = domain.upper()

    # identify area column
    area_col = (
        "USGS_basin_km2"
        if "USGS_basin_km2" in gdf_gages.columns
        else "area_sqkm"
        if "area_sqkm" in gdf_gages.columns
        else None
    )
    # round basin area to 2 decimal places
    if area_col:
        gdf_gages[area_col] = pd.to_numeric(gdf_gages[area_col], errors="coerce")
        gdf_gages[area_col] = gdf_gages[area_col].round(2)

    # rename columns to match crosswalk format
    gdf_gages.rename(
        columns={
            "site_no": "primary_location_id",
            "fp_id": "secondary_location_id",
            "USGS_basin_km2": "basin_area_km2",
            "area_sqkm": "basin_area_km2",
        },
        inplace=True,
    )

    # reorder columns
    gdf_gages = gdf_gages[
        [
            "domain",
            "vpu_id",
            "primary_location_id",
            "secondary_location_id",
            "basin_area_km2",
            "status",
            "geometry",
        ]
    ]

    return gdf_gages


def plot_gages(gage_file: str | Path, domain: str = "conus"):
    """Plot gages in the crosswalk file for a specific domain."""
    # Read the GeoDataFrame
    gage_file = Path(gage_file).expanduser()
    gdf_gages = gpd.read_parquet(gage_file)

    # Reproject to web mercator (required for contextily basemap)
    gdf_gages = gdf_gages.to_crs(epsg=3857)

    # Desired status order
    status_order = [
        "USGS-discontinued",
        "USGS-active",
        "CADWR_ENVCA",
        "TXDOT",
        "routelink",
        "-",
    ]

    # Filter to statyus_order to only includes those statuses that are actually present in the data
    status_order = [
        status for status in status_order if status in gdf_gages["status"].unique()
    ]

    # Compute counts
    status_counts = gdf_gages["status"].value_counts()

    # Map statuses to include counts
    status_map = {
        status: f"{status} ({status_counts.get(status, 0)})" for status in status_order
    }
    gdf_gages["status_labeled"] = gdf_gages["status"].map(status_map)

    # Make 'status_labeled' categorical so plotting order is respected
    gdf_gages["status_labeled"] = pd.Categorical(
        gdf_gages["status_labeled"],
        categories=[status_map[s] for s in status_order],
        ordered=True,
    )

    # Sort by this categorical column to control plotting order (first plotted below)
    gdf_gages_sorted = gdf_gages.sort_values("status_labeled")

    # Plot
    fig, ax = plt.subplots(figsize=(12, 8))

    gdf_gages_sorted.plot(
        ax=ax,
        column="status_labeled",
        categorical=True,
        markersize=8,
        marker="o",
        legend=True,
    )

    # Move legend outside the plot
    leg = ax.get_legend()
    if leg is not None:
        leg.set_bbox_to_anchor((1.0, 1.0))
        leg.set_loc("upper left")
        leg.set_title("Status")
    fig.subplots_adjust(right=0.75)  # leave space for legend

    # Remove axis ticks and labels
    ax.set_xticks([])
    ax.set_yticks([])

    # Add title
    ax.set_title(f"NHF Gages by Status in {domain.upper()}", fontsize=16)

    # Add basemap
    cx.add_basemap(ax, source=cx.providers.CartoDB.Positron)

    plt.tight_layout()
    plt.show()


def create_gage_list(gdf_cwt: gpd.GeoDataFrame, out_dir: str | Path, domain: str):
    """Create gage list each VPU for a specific domain based on the crosswalk file."""
    for vpu in gdf_cwt["vpu_id"].dropna().unique():
        df_vpu = gdf_cwt.loc[gdf_cwt["vpu_id"] == vpu, ["primary_location_id"]].copy()
        df_vpu.rename(columns={"primary_location_id": "gage"}, inplace=True)

        # remove "gages-" prefix
        df_vpu["gage"] = df_vpu["gage"].str.replace("usgs-", "", regex=False)

        gage_file = Path(out_dir) / f"gage_list_{domain}_vpu_{vpu}.csv"
        df_vpu = df_vpu.sort_values(by="gage").reset_index(drop=True)

        df_vpu.to_csv(gage_file, index=False, header=True)
        print(f"Gage list for VPU {vpu} saved to {gage_file} with {len(df_vpu)} gages.")


def _format_primary_location_id(value):
    """Safely format primary_location_id with the appropriate prefix.

    Handles non-string types and missing values before applying length-based logic.
    """
    # Handle missing values explicitly
    if pd.isna(value):
        return value

    # Coerce to string
    s = str(value).strip()

    # Normalize common float representations like '123.0' to '123'
    if s.endswith(".0"):
        s = s[:-2]

    # Apply existing length-based prefix logic
    if len(s) == 3:
        return f"cadwr-{s}"
    elif len(s) == 7:
        return f"envca-{s}"
    else:
        return f"usgs-{s}"


def main(domain: str = "conus", out_dir: str | Path = ".") -> Path:
    """Create ngen divide crosswalk for all gages for regionalization evaluation."""
    if domain.lower() not in ALL_VPUS.keys():
        print(
            f"Unsupported domain: {domain}. Supported domains are: {', '.join(ALL_VPUS.keys())}."
        )
        exit(1)

    # loop through unique VPUs to create a crosswalk for each VPU in the domain
    gdfs = [create_crosswalk(domain, vpu, out_dir) for vpu in ALL_VPUS[domain.lower()]]
    gdfs = [gdf for gdf in gdfs if not gdf.empty]

    if not gdfs:
        raise ValueError(
            f"No non-empty crosswalk GeoDataFrames were created for domain '{domain}'. "
            "Check that the expected NHF GeoPackages exist and contain a 'gages' layer."
        )

    # concatenate all gage crosswalks into one GeoDataFrame
    gdf_cwt = gpd.GeoDataFrame(
        pd.concat(gdfs, ignore_index=True), geometry="geometry", crs=gdfs[0].crs
    )

    # add prefix to primary_location_id
    gdf_cwt["primary_location_id"] = gdf_cwt["primary_location_id"].apply(
        _format_primary_location_id
    )

    # add prefix "ngen-" to secondary_location_id
    gdf_cwt["secondary_location_id"] = gdf_cwt["secondary_location_id"].apply(
        lambda x: f"ngen-{int(x)}" if pd.notna(x) else None
    )

    # remove rows where primary_location_id or secondary_location_id is missing or empty after formatting
    gdf_cwt = gdf_cwt.dropna(subset=["primary_location_id", "secondary_location_id"])
    gdf_cwt = gdf_cwt[
        (gdf_cwt["primary_location_id"] != "")
        & (gdf_cwt["secondary_location_id"] != "")
    ]

    # Save the crosswalk GeoDataFrame to Parquet
    cwt_file = Path(out_dir) / f"usgs_ngen_crosswalk_{domain}.parquet"
    print(f"Saving Crosswalk GeoDataFrame to {cwt_file} with {len(gdf_cwt)} entries...")

    cwt_file.parent.mkdir(parents=True, exist_ok=True)
    gdf_cwt.to_parquet(cwt_file, index=False)

    return cwt_file


def check_gages_in_crosswalk(
    cwt_file: str | Path, gage_list: list, gage_list_name: str, domain: str = "conus"
):
    """Check how many gages in the provided gage list are included in the crosswalk file."""
    gdf_cwt = gpd.read_parquet(cwt_file)
    all_gages = set(
        gdf_cwt[gdf_cwt["domain"].str.lower() == domain.lower()]["primary_location_id"]
    )
    all_gages = set([gage.split("-")[-1] for gage in all_gages])  # remove prefix
    gages_in_cwt = set([gage for gage in gage_list if gage in all_gages])

    # gages that are not included in the crosswalk file
    missed_gages = set(gage_list) - gages_in_cwt
    if missed_gages:
        print(
            f"Warning: The following {gage_list_name} gages are not included in the crosswalk file: {', '.join(missed_gages)}"
        )
    else:
        print(f"All {gage_list_name} gages are included in the crosswalk file.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create crosswalk for all gages.")
    parser.add_argument(
        "--out_dir",
        default=Path("~/repos/nwm-verf/data/inputs/nhf").expanduser(),
        help="Output directory for the crosswalk files",
    )
    parser.add_argument(
        "--domain",
        type=str,
        default="conus",
        help="Domain name (default: conus)",
    )
    args = parser.parse_args()

    # create crosswalk file for all gages and save to output directory
    cwt_file = main(args.domain, args.out_dir)

    if args.domain.lower() == "conus":
        print("Checking if all TxDOT gages are included in the crosswalk file...")
        check_gages_in_crosswalk(
            cwt_file, default_txdot_gage_list, "TxDOT", args.domain
        )

    print(
        "Checking if all calibratable headwater gages are included in the crosswalk file..."
    )
    df_calib = pd.read_csv("../data/inputs/gages_nwm4_calib_all.csv")
    nwm4_calib = set(
        df_calib[df_calib["domain"].str.lower() == args.domain.lower()][
            "gage_id"
        ].astype(str)
    )
    check_gages_in_crosswalk(
        cwt_file, nwm4_calib, "calibratable headwater", args.domain
    )

    print("Plotting gages in the crosswalk file on spatial map...")
    plot_gages(cwt_file, args.domain)
