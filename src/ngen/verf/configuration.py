import yaml
from pathlib import Path
from pydantic import BaseModel, Field, ValidationError, FilePath
from typing import List, Dict, Optional, Union


class GeneralConfig(BaseModel):
    """ Data model for the 'general' section of the config file """
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
    """ Data model for the 'file_paths' section of the config file """
    data_dir_root: str
    location_list_file: Optional[str] = None
    crosswalk_file: Dict[str, FilePath]
    gage_meta_file: FilePath
    geometry_file: FilePath


class NWMForecastConfig(BaseModel):
    """ Data model for the 'nwm_forecast' section of the config file """
    fetch_fcst: List[bool]
    output_type: str
    t_minus: Optional[List[int]] = None
    data_source: str
    kerchunk_method: str
    process_by_z_hour: bool
    stepsize: Optional[int] = 100
    ignore_missing_file: bool
    overwrite_output: bool
    memory_per_worker_gb: Optional[int] = 3  # configurable memory (in GB) assigned to each worker


class FlowObservationConfig(BaseModel):
    """ Data model for the 'flow_observation' section of the config file """
    usgs: Dict[str, Union[str, int, bool]]


class PairDataConfig(BaseModel):
    """ Data model for the 'pair_data' section of the config file """

    overwrite: bool    
    group_size: Optional[int] = 200


class MetricsConfig(BaseModel):
    """ Data model for the 'metrics' section of the config file """
    overwrite: bool
    library: str
    #metric_subset: Optional[Union[str,List[str]]] = 'all'
    metric_subset: Union[str,List[str]]
    flow_threshold_categorical: Optional[float] = 0.9
    flow_threshold_event: Optional[float] = 0.9
    lead_times: List[Union[str, int]]


class HistogramConfig(BaseModel):
    """ Data model for the 'plots/histogram' section of the config file """
    plot: bool
    metric_subset: List[str]
    binning: Optional[Dict[str, List[Union[int, float]]]] = None
    lead_times: List[Union[str, int]]
    tag: Optional[str] = None


class BoxPlotConfig(BaseModel):
    """ Data model for the 'plots/boxplots' section of the config file """
    plot: bool
    metric_subset: List[str]
    lead_times: List[Union[int, str]]
    tag: Optional[str] = None


class SpatialMapConfig(BaseModel):
    """ Data model for the 'plots/spatial maps' section of the config file """
    plot: bool
    metric_subset: List[str]
    scaling: Optional[Dict[str, List[Union[int, float]]]] = None
    lead_times: List[Union[int, str]]


class PlotsConfig(BaseModel):
    """ Data model for the 'plots' section of the config file """
    histogram: HistogramConfig
    boxplot: BoxPlotConfig
    spatial_map: SpatialMapConfig


class Config(BaseModel):
    """ Define a data model for each section in the config file"""
    general: GeneralConfig
    file_paths: FilePathsConfig
    nwm_forecast: NWMForecastConfig
    flow_observation: FlowObservationConfig
    pair_data: PairDataConfig
    metrics: MetricsConfig
    plots: PlotsConfig


def load_and_validate_yaml(file_path: str):
    """Load a YAML file and validate its structure using Pydantic."""
    try:
        with open(Path(file_path), "r") as file:
            data = yaml.safe_load(file)
            validated_config = Config(**data)
            return data
            #return validated_config
    except ValidationError as e:
        raise Exception(f'Validation Error: {e}')
    except Exception as e:
        raise Exception(f'Error loading YAML file: {e}')

