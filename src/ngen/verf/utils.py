from datetime import datetime, timedelta
import pandas as pd
from typing import Optional

__all__ = [
    "create_hour_sequence",
    "get_key_from_value",
]

def create_hour_sequence(
        start_date: str, 
        end_date: str, 
        by_hours: Optional[int] = 1,
) -> list:

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date) + timedelta(hours=23)

    hours = []
    while start_dt <= end_dt:
        hours.append(start_dt)
        start_dt += timedelta(hours=by_hours)

    return hours

# get key from dictionary given value
def get_key_from_value(d, value):
    return next((key for key, val in d.items() if val == value), None)