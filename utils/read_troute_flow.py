from pathlib import Path

import pandas as pd
import xarray as xr


def extract_flow_for_gages(
    nc_file: Path,
    crosswalk_file: Path,
    gage_file: Path,
    flow_var: str = "flow",
    feature_id_var: str = "feature_id",
    time_var: str = "time",
) -> pd.DataFrame:
    """Extract time and flow for specific gages from a NetCDF file using a crosswalk.

    Args:
        nc_file: Path to NetCDF file.
        crosswalk_file: Path to parquet crosswalk file with columns ['primary_location_id', 'secondary_location_id'].
        gage_file: Path to CSV file with gage IDs (primary_location_id) to include.
        flow_var: Name of flow variable in NetCDF.
        feature_id_var: Name of feature_id variable in NetCDF.
        time_var: Name of time variable in NetCDF.

    Returns:
        pd.DataFrame with columns ['time', 'primary_location_id', 'flow'].

    """
    # Read crosswalk
    cwt_df = pd.read_parquet(crosswalk_file)

    # Read list of gages to include
    gages_df = pd.read_csv(gage_file, dtype=str, header=0, names=["gage"])
    gage_list = set(gages_df["gage"])

    # Filter crosswalk to only gages in the gage list
    cwt_df["primary_location_id"] = cwt_df["primary_location_id"].str.replace(
        "^usgs-", "", regex=True
    )
    cwt_df["secondary_location_id"] = cwt_df["secondary_location_id"].str.replace(
        "^ngen-", "", regex=True
    )
    cwt_df = cwt_df[cwt_df["primary_location_id"].isin(gage_list)]

    # convert secondary_location_id to integer (feature_id in NetCDF is integer)
    cwt_df["secondary_location_id"] = cwt_df["secondary_location_id"].astype(int)

    # Map secondary_location_id to primary_location_id
    feature_to_gage = dict(
        zip(cwt_df["secondary_location_id"], cwt_df["primary_location_id"])
    )

    # Open NetCDF
    ds = xr.open_dataset(nc_file)

    # Select only the feature_ids in the crosswalk
    feature_ids = list(feature_to_gage.keys())

    # Flow is [time, feature_id]
    flow_data = ds[flow_var].sel({feature_id_var: feature_ids})

    # Convert to DataFrame
    df = flow_data.to_dataframe().reset_index()

    # Map feature_id to primary_location_id
    df["primary_location_id"] = df[feature_id_var].map(feature_to_gage)

    # Keep only relevant columns
    df = df[[time_var, "primary_location_id", flow_var]]
    df.rename(columns={time_var: "Time", flow_var: "value"}, inplace=True)

    return df


if __name__ == "__main__":
    nc_file = Path(
        "~/repos/nwm-region-mgr/data/regionalization/test3/vpu_09/Output/troute_output_202210010000.nc"
    ).expanduser()
    crosswalk_file = Path(
        "~/repos/nwm-verf/data/inputs/regionalization/usgs_ngen_crosswalk_conus.parquet"
    ).expanduser()
    gage_file = Path(
        "~/repos/nwm-verf/data/inputs/regionalization/gage_list_conus_vpu_09.txt"
    ).expanduser()

    df_flow = extract_flow_for_gages(
        nc_file=nc_file,
        crosswalk_file=crosswalk_file,
        gage_file=gage_file,
    )

    print(df_flow.head(11))
