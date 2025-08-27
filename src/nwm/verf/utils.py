"""Utility functions for the NGEN verification package."""

import logging
import os
from datetime import timedelta

import geopandas as gpd
import numpy as np
import pandas as pd
import psutil

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

__all__ = [
    "create_hour_sequence",
    "get_key_from_value",
    "get_n_workers",
    "clean_data",
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


# create datetime sequence given start date, end date, and frequency
def create_hour_sequence(
    start_date: str,
    end_date: str,
    start_hour: int,
    end_hour: int,
    freq_hour: int,
) -> list:
    start_dt = pd.to_datetime(start_date).normalize() + timedelta(hours=start_hour)
    end_dt = pd.to_datetime(end_date).normalize() + timedelta(hours=end_hour)

    hours = []
    while start_dt <= end_dt:
        hours.append(start_dt)
        start_dt += timedelta(hours=freq_hour)

    return hours


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

    logger.info(
        f"  Using {n_workers} workers, with ~{memory_per_worker_gb} GB per worker."
    )

    return n_workers
