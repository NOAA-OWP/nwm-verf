import logging
import math
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from teehr.classes.duckdb_database import DuckDBDatabase

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def join_time_series(data_paths: dict, dataset: str, nwm_version: str) -> Path:
    output_dir = data_paths.get("obs").parent.resolve(strict=True)
    primary_data_files = f"{str(data_paths.get('obs'))}/*.parquet"
    secondary_data_files = f"{str(data_paths.get('fcst_link')[dataset])}/*.parquet"
    crosswalk_file = f"{str(data_paths.get('crosswalk')[nwm_version])}"

    # make sure input files exist
    primary_files = list(Path(data_paths.get("obs")).glob("*.parquet"))
    if len(primary_files) == 0:
        msg = f"No observation data files found in {data_paths.get('obs')}. Verification cannot proceed. Exit."
        logger.error(msg)
        raise Exception(msg)
    secondary_files = list(Path(data_paths.get("fcst_link")[dataset]).glob("*.parquet"))
    if len(secondary_files) == 0:
        msg = f"No forecast data files found in {data_paths.get('fcst_link')[dataset]}. Verification cannot proceed. Exit."
        logger.error(msg)
        raise Exception(msg)

    # If there is an existing database, delete it and create a new one.
    db_filepath = Path(output_dir, "teehr.db")
    if db_filepath.is_file():
        db_filepath.unlink()

    ddb = DuckDBDatabase(db_filepath)

    # Join and insert the timeseries data to the temporary database.
    logger.info(
        f"  Joining time series for dataset {dataset} in DuckDBDatabase: {db_filepath}"
    )
    ddb.insert_joined_timeseries(
        primary_filepath=primary_data_files,
        secondary_filepath=secondary_data_files,
        crosswalk_filepath=crosswalk_file,
        drop_added_fields=True,
    )

    return db_filepath


def replace_values_with_nan(
    df,
    colnames: list[str] | str,
    replace_values: list[float],
    tol: float = 1e-12,
):
    """Replace specified values in DataFrame with NaN.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame.
    colnames : list of str or str
        List of column names to check for replacement.
    replace_values : list of float
        List of values to be replaced with NaN.

    Returns
    -------
    pd.DataFrame
        DataFrame with specified values replaced by NaN.

    """
    if isinstance(colnames, str):
        colnames = [colnames]

    for val in replace_values:
        df[colnames] = df[colnames].where(
            ~np.isclose(df[colnames], val, atol=tol), np.nan
        )

    return df


def export_location_groups_with_lead_time(
    db_path: Path,
    output_path: Path,
    table_name: str = "joined_timeseries",
    group_size: int = 200,
    start_time: str = None,
    end_time: str = None,
):
    # Get sorted list of unique primary_location_id values
    con = duckdb.connect(str(db_path))
    location_ids = con.execute(f"""
        SELECT DISTINCT primary_location_id FROM {table_name}
        ORDER BY primary_location_id
    """).fetchall()
    location_ids = [loc[0] for loc in location_ids]

    if len(location_ids) == 0:
        raise Exception(
            "ERROR: no primary_location_id found in the joined_timeseries database"
        )

    n_groups = math.ceil(len(location_ids) / group_size)

    # define time bounds for filtering reference_time
    min_ref_time = (
        datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S") if start_time else None
    )
    max_ref_time = (
        datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S") if end_time else None
    )

    # Convert datetime to string in SQL format
    min_ref_str = f"'{min_ref_time}'" if min_ref_time else "NULL"
    max_ref_str = f"'{max_ref_time}'" if max_ref_time else "NULL"

    # Split the list into n groups and process each group separately
    for i in range(n_groups):
        group_ids = location_ids[i * group_size : (i + 1) * group_size]

        if n_groups > 1:
            group_file = output_path.with_name(output_path.stem + f".group{i}.parquet")
            logger.info(
                f"  Exporting paired data for group {i} locations to {group_file} ..."
            )
        else:
            group_file = output_path.with_name(output_path.stem + ".parquet")
            logger.info(f"  Exporting paired data to {group_file} ...")

        # Ensure group_file is a Path and convert to absolute string
        group_file_path = str(Path(group_file).resolve())

        # Convert IDs list to a comma-separated string
        formatted_ids = ", ".join(f"'{loc}'" for loc in group_ids)

        query = f"""
        COPY (
            SELECT
                primary_location_id,
                primary_value,
                secondary_location_id,
                secondary_value,
                value_time,
                configuration,
                measurement_unit,
                variable_name,
                reference_time,
                (EXTRACT(EPOCH FROM value_time) - EXTRACT(EPOCH FROM reference_time)) / 3600.0 AS lead_time
            FROM {table_name}
            WHERE primary_location_id IN ({formatted_ids})
            {f"AND reference_time >= {min_ref_str}" if min_ref_time else ""}
            {f"AND reference_time <= {max_ref_str}" if max_ref_time else ""}
        )
        TO '{group_file_path}' (FORMAT PARQUET)
        """
        con.execute(query)

        # replace specified values with NaN in the exported parquet file
        replace_values_with_nan(
            df=pd.read_parquet(group_file_path),
            colnames=["primary_value", "secondary_value"],
            replace_values=[
                -9999.0,
                -99999.0,
                -999999.0,
                -28316.818359375,
            ],  # -28316.818359375 is -999999.0 in cfs
        ).to_parquet(group_file_path, index=False)

    con.close()


def create_pairs(
    data_paths: dict,
    dataset: str,
    nwm_version: str,
    group_size=200,
    start_time: str = None,
    end_time: str = None,
    overwrite: bool = False,
) -> Path:
    # check if paired data already exist; if not, create it
    pair_file = data_paths.get("joined")[dataset]
    existing_pair_files = list(
        pair_file.parent.glob(f"{pair_file.stem}.group*.parquet")
    )
    if len(existing_pair_files) > 0 and (not overwrite):
        logger.info(
            f"  Paired data for {dataset} already exist at {existing_pair_files}. Skip pairing"
        )
    else:
        pair_file.parent.mkdir(exist_ok=True, parents=True)

        # remove existing pair files if any
        for file in existing_pair_files:
            if file.is_file():
                file.unlink()

        # first create joined time series in (temporary) DuckDBDatabse
        db_path = join_time_series(data_paths, dataset, nwm_version)

        # then calculate lead times and export paired data by group (to avoid potential memory issues)
        export_location_groups_with_lead_time(
            db_path,
            pair_file,
            table_name="joined_timeseries",
            group_size=group_size,
            start_time=start_time,
            end_time=end_time,
        )

        # remove the temporay database
        if Path(db_path).exists():
            db_path.unlink()

    return pair_file
