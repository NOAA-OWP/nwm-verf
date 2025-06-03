from pathlib import Path
import math
import duckdb
from teehr.classes.duckdb_database import DuckDBDatabase

import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def join_time_series(data_paths: dict, dataset: str, nwm_version:str) -> Path:
        
    output_dir = data_paths.get('obs').parent.resolve(strict=True)
    primary_data_files = f'{str(data_paths.get("obs"))}/*.parquet'
    secondary_data_files =f'{str(data_paths.get("fcst_link")[dataset])}/*.parquet'
    crosswalk_file = f'{str(data_paths.get("crosswalk")[nwm_version])}'

    # If there is an existing database, delete it and create a new one.
    db_filepath = Path(output_dir, 'teehr.db')
    if db_filepath.is_file():
        db_filepath.unlink()

    ddb = DuckDBDatabase(db_filepath)

    # Join and insert the timeseries data to the temporary database.
    logger.info(f'  Joining time series for dataset {dataset} in DuckDBDatabase: {db_filepath}')
    ddb.insert_joined_timeseries(
        primary_filepath = primary_data_files,
        secondary_filepath = secondary_data_files,
        crosswalk_filepath = crosswalk_file,
        drop_added_fields = True,
    )

    return db_filepath


def export_location_groups_with_lead_time(
    db_path: Path,
    output_path: Path,
    table_name: str = "joined_timeseries",
    group_size: int = 200
):
    # Get sorted list of unique primary_location_id values
    con = duckdb.connect(str(db_path))
    location_ids = con.execute(f"""
        SELECT DISTINCT primary_location_id FROM {table_name}
        ORDER BY primary_location_id
    """).fetchall()
    location_ids = [loc[0] for loc in location_ids]
    n_groups = math.ceil(len(location_ids) / group_size)

    # Split the list into n groups and process each group separately
    for i in range(n_groups):
        
        group_ids = location_ids[i * group_size:(i + 1) * group_size]
        group_file = output_path.with_name(output_path.stem + f".group{i}.parquet")
        logger.info(f'Exporting paired data for group {i} locations to {group_file} ...')

        formatted_ids = ', '.join(f"'{loc}'" for loc in group_ids)
        
        # Query with lead_time calculation and drop reference_time
        con.execute(f"""
            COPY (
                SELECT
                    primary_location_id,
                    primary_value,
                    secondary_location_id,
                    secondary_value,
                    value_time,
                    DATEDIFF('hour', reference_time, value_time) AS lead_time
                FROM {table_name}
                WHERE primary_location_id IN ({formatted_ids})
            )
            TO '{group_file}' (FORMAT PARQUET)
        """)

    con.close()


def create_pairs(data_paths: dict, dataset: str, nwm_version:str, group_size=200, overwrite: bool=False) -> Path:

    # check if paired data already exist; if not, create it
    pair_file = data_paths.get('joined')[dataset]
    existing_pair_files = list(pair_file.parent.glob(f'{pair_file.stem}.group*.parquet'))
    if (len(existing_pair_files)>0 and (not overwrite)):
        logger.info(f'  Paired data for {dataset} already exist at {existing_pair_files}. Skip pairing')
    else:
        pair_file.parent.mkdir(exist_ok=True, parents=True)

        # remove existing pair files if any
        for file in existing_pair_files:
            if file.is_file():
                file.unlink()        

        # first create joined time series in (temporary) DuckDBDatabse
        db_path = join_time_series(data_paths, dataset, nwm_version)

        # then calculate lead times and export paired data by group (to avoid potential memory issues)
        export_location_groups_with_lead_time(db_path, pair_file, table_name="joined_timeseries", group_size=group_size)

    return pair_file   