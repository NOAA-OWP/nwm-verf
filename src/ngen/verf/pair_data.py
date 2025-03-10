from pathlib import Path
from teehr.classes.duckdb_database import DuckDBDatabase
from .calc_lead_times import insert_lead_time

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
    logger.info(f'  Joining time series for dataset in DuckDBDatabase: {db_filepath}')
    ddb.insert_joined_timeseries(
        primary_filepath = primary_data_files,
        secondary_filepath = secondary_data_files,
        crosswalk_filepath = crosswalk_file,
        drop_added_fields = True,
    )

    return db_filepath

def export_paired_data(db_path:Path, paired_data: Path):

    # export paired data from database
    ddb = DuckDBDatabase(db_path)
    ddb.query(f"""
        COPY (
            SELECT *
            FROM joined_timeseries
            ORDER BY configuration, primary_location_id, value_time
        )
    TO '{paired_data}' (FORMAT PARQUET)
    """)


def create_pairs(data_paths: dict, dataset: str, nwm_version:str, overwrite: bool) -> Path:

    # check if paired data already exist; if not, create it
    paired_data = data_paths.get('joined')[dataset]
    if (paired_data.is_file() and (not overwrite)):
        logger.info(f'  Paired data for {dataset} already exist at {paired_data}. Skip pairing')
    else:
        paired_data.parent.mkdir(exist_ok=True, parents=True)

        # first create joined time series in (temporary) DuckDBDatabse
        db_path = join_time_series(data_paths, dataset, nwm_version)

        # then calculate lead times
        logger.info(f'  Calculate native lead times for dataset {dataset}...')
        insert_lead_time(db_path)

        # then export the paired data to parquet files    
        export_paired_data(db_path, paired_data)
        logger.info(f'  Paired data for dataset {dataset} exported to parquet file at: {paired_data}')

        # The temprary database is not needed any longer.  Delete it.
        if db_path.is_file():            
            db_path.unlink() 

    return paired_data   