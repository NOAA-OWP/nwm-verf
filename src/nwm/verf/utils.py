"""Utility functions for the NGEN verification package."""

import logging
import os
from enum import Enum
from itertools import product
from pathlib import Path
from typing import Any, Set, Union

import geopandas as gpd
import numpy as np
import pandas as pd
import psutil
import pyarrow.parquet as pq
import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

__all__ = [
    "create_time_sequence",
    "get_key_from_value",
    "get_n_workers",
    "clean_data",
    "expand_with_lists",
    "recursive_substitute",
    "flatten_dict",
    "check_columns_dataframe",
]


# function to remove rows with NaN and infinite values for a given column from a pandas dataframe or geo-dataframe
# this is useful for cleaning the data before plotting
# or performing calculations to avoid errors due to NaN or infinite values
def clean_data(
    df: pd.DataFrame | gpd.GeoDataFrame, column: str
) -> pd.DataFrame | gpd.GeoDataFrame:
    df[column] = df[column].replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=[column])
    return df


def create_time_sequence(
    start_date: str | pd.Timestamp,
    end_date: str | pd.Timestamp,
    freq_hour: float = 1,
    start_hour: float = 0,
    end_hour: float = 0,
) -> list[pd.Timestamp]:
    start_dt = pd.to_datetime(start_date) + pd.Timedelta(hours=start_hour)
    end_dt = pd.to_datetime(end_date) + pd.Timedelta(hours=end_hour)

    return pd.date_range(start=start_dt, end=end_dt, freq=f"{freq_hour}H").to_list()


# get key from dictionary given value
def get_key_from_value(d, value):
    return next((key for key, val in d.items() if val == value), None)


# determine number of workers to use for parallel jobs dynamically based on system resources available
def get_n_workers(memory_per_worker_gb: int) -> int:
    # System resources
    total_cores = os.cpu_count()
    total_memory_gb = psutil.virtual_memory().total // (1024**3)

    # Determine number of workers
    max_workers_by_memory = total_memory_gb // memory_per_worker_gb
    n_workers = min(total_cores - 1, max_workers_by_memory)  # leave one core free

    # Safety check
    n_workers = max(n_workers, 1)

    # logger.info(
    #     f"  Using {n_workers} workers, with ~{memory_per_worker_gb} GB per worker."
    # )

    return n_workers


def expand_with_lists(template_str: str, context: dict) -> dict | str:
    """Expand a string with list placeholders using Cartesian product.

    Always returns a dict if any list placeholders are involved — even if only one result.
    Otherwise, returns a plain substituted string.
    """
    # Find all list-type keys in context used in the string
    list_keys = [
        k
        for k in context
        if isinstance(context[k], list) and f"{{{k}}}" in template_str
    ]

    if not list_keys:
        # No list placeholders → do a simple substitution
        return template_str.format(**context)

    # Get all combinations of list values
    combinations = list(product(*[context[k] for k in list_keys]))

    result = {}
    for combo in combinations:
        sub_context = context.copy()
        sub_context.update(dict(zip(list_keys, combo)))
        key = "_".join(str(v) for v in combo)
        result[key] = template_str.format(**sub_context)

    return result


def recursive_substitute(obj: Any, context: dict) -> Any:
    """Recursively substitute placeholders in nested structures."""
    if isinstance(obj, BaseModel):
        data = obj.model_dump()
        substituted = recursive_substitute(data, context)
        return obj.__class__(**substituted)

    elif isinstance(obj, dict):
        return {k: recursive_substitute(v, context) for k, v in obj.items()}

    elif isinstance(obj, str):
        try:
            return expand_with_lists(obj, context)
        except KeyError:
            return obj  # leave unchanged if substitution fails

    else:
        return obj


def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Flatten a nested dictionary.

    Args:
        d (dict): The dictionary to flatten.
        parent_key (str): The base key to prepend to the flattened keys.
        sep (str): The separator to use between keys.

    Returns:
        dict: A flattened dictionary with concatenated keys.

    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def check_columns_dataframe(file: Path | str, columns: Set[str]):
    """Check if the required columns are present in the file.

    Args:
        file: Path to the CSV or Parquet file.
        columns: Set of required column names.

    Raises:
        ValueError: If any of the required columns are missing in the file.

    """
    if isinstance(file, str):
        file = Path(file)

    if not file.exists():
        msg = f"File not found: {file}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    suffix = file.suffix.lower()
    if suffix == ".csv":
        # Read full DataFrame with minimal memory usage
        df = pd.read_csv(file, sep=None, engine="python")  # auto-detect separator
        df.columns = df.columns.str.strip().str.lower()
        columns_present = list(df.columns)
        is_empty = df.empty

    elif suffix == ".parquet":
        pf = pq.ParquetFile(file)
        columns_present = [col.strip().lower() for col in pf.schema.names]
        is_empty = pf.metadata.num_rows == 0  # More efficient than loading into pandas

    else:
        msg = f"Unsupported file format: {suffix}. Supported formats are .csv and .parquet."
        logger.error(msg)
        raise ValueError(msg)

    # raise error if the file is empty
    if is_empty:
        msg = f"The file {file} is empty. Please provide a file with data."
        logger.error(msg)
        raise ValueError(msg)

    # Check for missing columns (case insensitive)
    missing_cols = {col.lower() for col in columns} - {
        col.lower() for col in columns_present
    }
    if missing_cols:
        msg = f"Missing columns (case insensitive) in {file}: {missing_cols}. Available columns: {columns_present}"
        logger.error(msg)
        raise ValueError(msg)


def remove_nulls(d: dict | list) -> dict | list:
    """Remove nulls.

    Recursively remove None values from a dictionary or list.
    This function traverses the input data structure and removes any keys with None values
    or any elements that are None in lists. It also removes empty dictionaries.

    Parameters
    ----------
    d : dict or list
        The input data structure to clean. It can be a dictionary or a list.

    Returns
    -------
    dict or list
        The cleaned data structure with None values and empty dictionaries removed.

    """
    if isinstance(d, dict):
        return {
            k: remove_nulls(v)
            for k, v in d.items()
            if v is not None and remove_nulls(v) != {}
        }
    elif isinstance(d, list):
        return [remove_nulls(v) for v in d if v is not None]
    else:
        return d


def convert_enum_to_value(obj: Any) -> Any:
    """Recursively convert Enum values to their `.value` (string) for YAML serialization.

    Args:
        obj: The object to convert, which can be a dictionary, list, or an Enum instance.

    Returns:
        The converted object with Enum values replaced by their string representations.

    """
    if isinstance(obj, dict):
        return {k: convert_enum_to_value(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_enum_to_value(item) for item in obj]
    elif isinstance(obj, Enum):
        return obj.value
    else:
        return obj


def convert_paths_to_str(obj):
    """Recursively convert Path objects to strings in dicts/lists."""
    if isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: convert_paths_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_paths_to_str(v) for v in obj]
    return obj


def save_data(
    data: Union[pd.DataFrame, BaseModel],
    file_path: Union[str, Path],
    index: bool = False,
) -> None:
    """Save data to disk in an appropriate format based on its type and file extension.

    Args:
        data : Union[pandas.DataFrame, pydantic.BaseModel]
            The data object to save. Must be either a pandas DataFrame or a Pydantic BaseModel.

            - If `data` is a pandas DataFrame:
                - Supported file formats: `.csv`, `.parquet`.

            - If `data` is a Pydantic BaseModel:
                - Supported file format: `.yaml`.

        file_path : Union[str, pathlib.Path]
            The target file path where the data will be saved. The file extension determines the format.
        index : bool
            Whether to write row indices in the DataFrame (default: False).

    Raises:
        Exception
            If the file extension is not supported for the given data type.

        ValueError
            If `data` is neither a pandas DataFrame nor a Pydantic BaseModel.

    Notes:
        - If the directory for the specified file path does not exist, it will be created.
        - YAML files for Pydantic models are written with custom inline list formatting (if configured).

    """

    class InlineListDumper(yaml.Dumper):
        pass

    def represent_inline_list(dumper, data):
        return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)

    file_path = Path(file_path)
    if not file_path.parent.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(data, pd.DataFrame):
        if file_path.suffix == ".csv":
            data.to_csv(file_path, index=index)
        elif file_path.suffix == ".parquet":
            data.to_parquet(file_path, index=index)
        else:
            raise Exception(
                "Only csv and parquet formats are supported for saving DataFrame"
            )

    elif isinstance(data, BaseModel):
        if file_path.suffix != ".yaml":
            raise Exception(f"Only yaml format is supported for saving {type(data)}")

        with open(file_path, "w") as f:
            InlineListDumper.add_representer(list, represent_inline_list)
            InlineListDumper.add_representer(
                Enum, lambda dumper, data: dumper.represent_scalar("!enum", data.value)
            )

            # Convert Enum + Path + drop None
            data_dict = data.model_dump()
            data_dict = convert_enum_to_value(data_dict)
            data_dict = convert_paths_to_str(data_dict)
            data_dict = remove_nulls(data_dict)

            # Dump the data to YAML file with inline list formatting
            # and without sorting keys to preserve the order of fields
            yaml.dump(
                data_dict,
                f,
                Dumper=InlineListDumper,
                sort_keys=False,
            )

    else:
        raise ValueError(
            "Unsupported data type: must be a pandas DataFrame or Pydantic BaseModel"
        )


def read_data(
    file_path: Path | str,
    dtype: dict[str, str] | None = None,
    parse_dates: list[str] | None = None,
) -> pd.DataFrame:
    """Read data from a csv or parquet file.

    Args:
        file_path (Path | str): Path to the file to read, with file format determined by the file extension
        (.csv or .parquet).
        dtype (dict[str, str] | None): Optional dictionary specifying the data types for specific columns.
        parse_dates (list[str] | None): Optional list of columns to parse as dates.

    Returns:
        pd.DataFrame: DataFrame containing the data from the file.

    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"{file_path} does not exist")

    suffix = file_path.suffix.lower()
    if suffix in [".csv", ".tsv"]:
        try:
            # Try automatic separator detection
            df = pd.read_csv(file_path, dtype=dtype, parse_dates=parse_dates)
        except pd.errors.ParserError:
            # Fallback to tab-delimited
            df = pd.read_csv(file_path, sep="\t", dtype=dtype, parse_dates=parse_dates)
    elif suffix == ".parquet":
        df = pd.read_parquet(file_path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    # remove leading/trailing whitespace from column names
    df.columns = df.columns.str.strip()

    return df
