from pathlib import Path

import pandas as pd

# from teehr.classes.duckdb_joined_parquet import DuckDBJoinedParquet
from teehr.classes.duckdb_database import DuckDBDatabase


# define function to calculate lead time
def calc_lead_time_field(arg1: pd.Timestamp, arg2: pd.Timestamp) -> int:
    return int(pd.Timedelta(arg1 - arg2).seconds / 3600)


# insert lead time field into the database
def insert_lead_time(db_path: Path):
    ddb = DuckDBDatabase(db_path)
    ddb.insert_calculated_field(
        new_field_name="lead_time",
        new_field_type="INTEGER",
        parameter_names=["value_time", "reference_time"],
        user_defined_function=calc_lead_time_field,
    )
