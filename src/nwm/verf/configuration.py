import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from .utils import check_columns_dataframe, flatten_dict, recursive_substitute

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class GeneralConfig(BaseModel):
    """Data model for the 'general' section of the config file"""

    steps: Dict[str, bool]
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


class FilePathsConfig(BaseModel):
    """Data model for the 'file_paths' section of the config file"""

    base_dir: Path
    location_list_file: Optional[str] = None
    crosswalk_file: Optional[Path | str | Dict[str, Path] | Dict[str, str]] = Field()
    # gage_meta_file: str | Path
    # geometry_file: str | Path
    gage_hydrofabric_file: str | Path
    fcst_data_file: Optional[Path | str | Dict[str, Path] | Dict[str, str]] = Field()
    output_dir: str | Path

    @model_validator(mode="after")
    def expand_all_paths(self):
        """Expand all paths to ensure they are absolute."""
        for field, value in self.__dict__.items():
            if isinstance(value, Path):
                self.__dict__[field] = value.expanduser()
        return self


class NWMForecastConfig(BaseModel):
    """Data model for the 'nwm_forecast' section of the config file"""

    fetch_fcst: List[bool]
    output_type: str
    t_minus: Optional[List[int]] = None
    data_source: str
    kerchunk_method: str
    process_by_z_hour: bool
    stepsize: Optional[int] = 100
    ignore_missing_file: bool
    overwrite_output: bool
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


class MetricsConfig(BaseModel):
    """Data model for the 'metrics' section of the config file"""

    overwrite: bool
    library: str
    # metric_subset: Optional[Union[str,List[str]]] = 'all'
    metric_subset: Union[str, List[str]]
    metric_exclude: Optional[List[str]] = None
    flow_threshold_categorical: Optional[float] = 0.9
    flow_threshold_event: Optional[float] = 0.9
    lead_times: List[Union[str, int]]


Number = Union[int, float]


class BasePlotConfig(BaseModel):
    """Common fields for all plot configs"""

    plot: bool
    metric_subset: List[str]
    lead_times: List[Union[int, str]]
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


class PlotsConfig(BaseModel):
    """Data model for the 'plots' section of the config file"""

    histogram: HistogramConfig
    boxplot: BoxPlotConfig
    spatial_map: SpatialMapConfig


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
        if (
            self.nwm_forecast.data_source == "ngenCERF"
            and self.file_paths.fcst_data_file is None
        ):
            raise ValueError(
                "file_paths.fcst_data_file must be provided when "
                "nwm_forecast.data_source is 'ngenCERF'"
            )
        return self
