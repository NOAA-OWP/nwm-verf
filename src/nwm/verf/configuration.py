import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class GeneralConfig(BaseModel):
    """Data model for the 'general' section of the config file"""

    steps: Dict[str, bool]
    domain: Optional[str] = None
    assemble_domain: Optional[bool] = False
    location_set_name: str
    location_list: Optional[List[Union[str, int]]] = None
    location_type: Optional[str] = None
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
        return [str(lt) for lt in v]


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


class TimeSeriesConfig(BasePlotConfig):
    """Config for time series plots"""

    pass


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
    def check_forecast_data_file(self):
        """Make sure forecast data file is provided for ngenCERF."""
        if (
            self.nwm_forecast.data_source == "ngenCERF"
            and self.file_paths.fcst_data_file is None
        ):
            msg = "file_paths.fcst_data_file must be provided when "
            msg += "nwm_forecast.data_source is 'ngenCERF'"
            logger.error(msg)
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_plot_config(self):
        """Time series and metric_table plots are only applicable if nwm_fcst/data_source is ngenCERF."""
        for plot_type in ["time_series", "metric_table", "barchart"]:
            plot_conf = getattr(self.plots, plot_type, None)
            if plot_conf and getattr(plot_conf, "plot", False):
                if self.nwm_forecast.data_source != "ngenCERF":
                    msg = f"{plot_type} is only applicable if nwm_forecast.data_source is 'ngenCERF'"
                    logger.error(msg)
                    raise ValueError(msg)
        return self
