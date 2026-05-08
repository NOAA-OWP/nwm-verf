import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - [%(levelname)s] - %(message)s"
)


class LocationFilter(BaseModel):
    """Data model for filtering locations based on column values in the crosswalk file."""

    columns: str | List[str]
    values: str | List[str]

    @model_validator(mode="before")
    @classmethod
    def normalize_and_validate(cls, data):
        """Normalize columns/values to lists and ensure they have matching lengths.

        This allows configs to specify either a single string or a list for each field,
        while guaranteeing that downstream code always receives lists of equal length.
        """
        if data is None:
            return data

        # If another validator has already constructed a LocationFilter instance, just return it unchanged.
        if isinstance(data, cls):
            return data

        if not isinstance(data, dict):
            return data

        columns = data.get("columns")
        values = data.get("values")

        # If either field is missing, let Pydantic's own validation handle it.
        if columns is None or values is None:
            return data

        # Normalize columns to a list of strings.
        if isinstance(columns, str):
            columns_list = [columns]
        else:
            columns_list = list(columns)

        # Normalize values to a list of strings.
        if isinstance(values, str):
            values_list = [values]
        else:
            values_list = list(values)

        # Ensure columns and values lists have the same length.
        if len(columns_list) != len(values_list):
            raise ValueError(
                "LocationFilter configuration error: 'columns' and 'values' must have the same length."
            )

        data["columns"] = columns_list
        data["values"] = values_list

        return data


class GeneralConfig(BaseModel):
    """Data model for the 'general' section of the config file."""

    steps: Dict[str, bool]
    domain: Optional[str] = None
    assemble_domain: Optional[bool] = False
    location_set_name: str
    location_list: Optional[List[Union[str, int]]] = None
    location_type: Optional[str] = None
    location_filter: Optional[LocationFilter] = None
    location_group_size: Optional[int] = 500
    variable_name: str
    nwm_configuration: str
    dataset_name: List[str]
    nwm_version: List[str]
    forecast_start_date: List[str]
    forecast_end_date: List[str]
    eval_start_date: Optional[List[str]] = None
    eval_end_date: Optional[List[str]] = None
    separate_calibrated: Optional[bool] = Field(
        default=False,
        description="Whether to distinguish calibrated and regionalized locations in the evaluation",
    )


class FilePathsConfig(BaseModel):
    """Data model for the 'file_paths' section of the config file"""

    base_dir: Path
    location_list_file: Optional[Path | str] = None
    crosswalk_file: Optional[Path | str | Dict[str, Path] | Dict[str, str]] = None
    fcst_config_file: Optional[str | Path] = None
    fcst_data_file: Optional[Path | str | Dict[str, Path] | Dict[str, str]] = None
    fcst_data_dir: Optional[Path | str | Dict[str, Path] | Dict[str, str]] = None
    calib_param_file: Optional[Path | str] = None
    txdot_gage_file: Optional[Path | str] = None
    output_dir: str | Path


class NWMForecastConfig(BaseModel):
    """Data model for the 'nwm_forecast' section of the config file"""

    data_source: str
    fetch_fcst: Optional[List[bool]] = None
    output_type: Optional[str] = None
    t_minus: Optional[List[int]] = None
    kerchunk_method: Optional[str] = None
    process_by_z_hour: Optional[bool] = None
    stepsize: Optional[int] = 100
    ignore_missing_file: Optional[bool] = True
    overwrite_output: Optional[bool] = False
    memory_per_worker_gb: Optional[int] = (
        3  # configurable memory (in GB) assigned to each worker
    )


class FlowObservationConfig(BaseModel):
    """Data model for the 'flow_observation' section of the config file"""

    usgs: Dict[str, Union[str, int, bool]]


class PairDataConfig(BaseModel):
    """Data model for the 'pair_data' section of the config file"""

    overwrite: bool
    group_size: Optional[int] = 200


class LeadTimesMixin(BaseModel):
    lead_times: Optional[List[str]] = None

    @field_validator("lead_times", mode="before")
    @classmethod
    def normalize_lead_times(cls, v):
        if v is None:
            return []
        if not isinstance(v, list):
            v = [v]
        return [str(lt) for lt in v]


class ReferenceTimesMixin(BaseModel):
    reference_times: Optional[List[datetime]] = None

    @field_validator("reference_times", mode="before")
    @classmethod
    def normalize_reference_times(cls, v):
        if v is None:
            return []
        if not isinstance(v, list):
            v = [v]
        return [pd.to_datetime(rt).to_pydatetime() for rt in v]


class MetricsConfig(LeadTimesMixin):
    """Data model for the 'metrics' section of the config file"""

    overwrite: bool
    library: str
    metric_subset: Union[str, List[str]]
    metric_exclude: Optional[List[str]] = None
    flow_threshold_categorical: Optional[float] = 0.9
    flow_threshold_event: Optional[float] = 0.9
    file_format: Optional[str] = "parquet"


Number = Union[int, float]


class BasePlotConfig(LeadTimesMixin):
    """Common fields for all plot configs"""

    plot: Optional[bool] = False
    metric_subset: Optional[List[str]] = []
    tag: Optional[str] = None


class HistogramConfig(BasePlotConfig):
    """Config for histogram plots"""

    binning: Optional[Dict[str, List[Number]]] = None


class BoxPlotConfig(BasePlotConfig):
    """Config for box plots"""

    show_outliers: Optional[bool] = False


class SpatialMapConfig(BasePlotConfig):
    """Config for spatial maps"""

    scaling: Optional[Dict[str, List[Number]]] = None


class TimeSeriesConfig(BasePlotConfig, ReferenceTimesMixin):
    """Config for time series plots."""

    lead_times: Optional[List[int]] = None

    @field_validator("lead_times", mode="before")
    @classmethod
    def validate_lead_times(cls, v):
        """Validate that lead_times is a list of integers or numeric strings, and convert to integers."""
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("lead_times must be a list")

        cleaned = []
        for item in v:
            # Accept int directly
            if isinstance(item, int):
                cleaned.append(item)

            # Accept numeric strings like "6"
            elif isinstance(item, str):
                if item.isdigit():
                    cleaned.append(int(item))
                else:
                    logger.info(
                        f"Invalid lead_time '{item}'. Must be integer-like (e.g., '6'), not ranges like '1-5'. Skip this lead time."
                    )
            else:
                logger.info(
                    f"Invalid type {type(item)} in lead_times. Must be int or numeric string. Skip this lead time."
                )

        return cleaned or None


class TablePlotConfig(BasePlotConfig):
    """Config for table plots displaying metric values"""

    pass


class BarChartConfig(BasePlotConfig):
    """Config for bar charts"""

    pass


class PlotsConfig(BaseModel):
    """Data model for the 'plots' section of the config file"""

    histogram: Optional[HistogramConfig] = None
    boxplot: Optional[BoxPlotConfig] = None
    spatial_map: Optional[SpatialMapConfig] = None
    time_series: Optional[TimeSeriesConfig] = None
    metric_table: Optional[TablePlotConfig] = None
    barchart: Optional[BarChartConfig] = None


class Config(BaseModel):
    """Define a data model for each section in the config file"""

    general: GeneralConfig
    file_paths: FilePathsConfig
    nwm_forecast: NWMForecastConfig
    flow_observation: FlowObservationConfig
    pair_data: PairDataConfig
    metrics: MetricsConfig
    plots: PlotsConfig

    @model_validator(mode="after")
    def check_dataset_configuration(self):
        """Check that the following fields has the same lenght as dataset_name.

        Fields include: nwm_version, forecast_start_date, forecast_end_date, eval_start_date, eval_end_date.
        """
        dataset_name = self.general.dataset_name
        nwm_version = self.general.nwm_version
        forecast_start_date = self.general.forecast_start_date
        forecast_end_date = self.general.forecast_end_date
        eval_start_date = self.general.eval_start_date
        eval_end_date = self.general.eval_end_date

        fields_to_check = {
            "nwm_version": nwm_version,
            "forecast_start_date": forecast_start_date,
            "forecast_end_date": forecast_end_date,
            "eval_start_date": eval_start_date,
            "eval_end_date": eval_end_date,
        }

        for field_name, field_value in fields_to_check.items():
            if field_value and len(field_value) != len(dataset_name):
                msg = f"Length of '{field_name} ({len(field_value)})' does not match length of 'dataset_name' ({len(dataset_name)})."
                logger.error(msg)
                raise ValueError(msg)

        return self

    @model_validator(mode="after")
    def check_forecast_data_file(self):
        """Make sure forecast data file and/or directory is provided except for GCS."""
        if (
            self.nwm_forecast.data_source.upper() != "GCS"
            and self.file_paths.fcst_data_file is None
            and self.file_paths.fcst_data_dir is None
        ):
            msg = "file_paths.fcst_data_file or file_paths.fcst_data_dir must be provided when "
            msg += "nwm_forecast.data_source is not 'GCS'"
            logger.error(msg)
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_plot_config(self):
        """Check that plot configurations are compatible with the specified data source.

        Time series, metric_table, and barchart plots are only applicable if nwm_forecast.data_source is ngenCERF or hindcast.
        Spatial maps, histograms, and boxplots are only applicable if nwm_forecast.data_source is GCS or ngenSIM.
        """
        for plot_type in ["time_series", "metric_table", "barchart"]:
            plot_conf = getattr(self.plots, plot_type, None)
            if plot_conf and getattr(plot_conf, "plot", False):
                if self.nwm_forecast.data_source.lower() not in [
                    "ngencerf",
                    "hindcast",
                ]:
                    msg = f"{plot_type} is only applicable if nwm_forecast.data_source is 'ngenCERF' or 'hindcast'"
                    logger.error(msg)
                    raise ValueError(msg)

        for plot_type in ["spatial_map", "histogram", "boxplot"]:
            plot_conf = getattr(self.plots, plot_type, None)
            if plot_conf and getattr(plot_conf, "plot", False):
                if self.nwm_forecast.data_source.lower() not in [
                    "gcs",
                    "ngensim",
                ]:
                    msg = f"{plot_type} is only applicable if nwm_forecast.data_source is 'GCS' or 'ngenSIM'"
                    logger.error(msg)
                    raise ValueError(msg)
        return self
