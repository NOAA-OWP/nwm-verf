import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from .configuration import Config
from .logging_utils import setup_logging
from .utils import (
    check_columns_dataframe,
    flatten_dict,
    recursive_substitute,
    save_data,
)

logger = logging.getLogger(__name__)


class ProcessConfig(BaseModel):
    """Class to process and validate configuration for NWM verification."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    config_path: str | Path
    config: Optional[Config] = None

    def substitute_placeholders(self):
        """Substitute placeholders in the config with actual values."""
        # Create a context dictionary with general config parameters
        context = {
            "base_dir": self.config.file_paths.base_dir
            if hasattr(self.config.file_paths, "base_dir")
            else None,
            "domain": self.config.general.domain
            if hasattr(self.config.general, "domain")
            else None,
            "location_set_name": self.config.general.location_set_name
            if hasattr(self.config.general, "location_set_name")
            else None,
            "dataset_name": self.config.general.dataset_name
            if hasattr(self.config.general, "dataset_name")
            else None,
            "nwm_configuration": self.config.general.nwm_configuration
            if hasattr(self.config.general, "nwm_configuration")
            else None,
            "nwm_version": self.config.general.nwm_version
            if hasattr(self.config.general, "nwm_version")
            else None,
            "forecast_start_date": datetime.strptime(
                self.config.general.forecast_start_date[0], "%Y-%m-%d %H:%M:%S"
            ).strftime("%Y%m%d%H%M")
            if hasattr(self.config.general, "forecast_start_date")
            else None,
        }

        # remove items with None values from context
        context = {k: v for k, v in context.items() if v is not None}

        # substitute placeholders in the config
        self.config = recursive_substitute(self.config, context)

    def file_required_column_map(self) -> Dict[str, str]:
        """Return a dictionary mapping files to required columns."""
        file_dict = {
            "crosswalk_file": {
                "domain",
                "primary_location_id",
                "secondary_location_id",
            },
            "gage_hydrofabric_file": {"primary_location_id", "agency", "geometry"},
            # "fcst_data_file": {"Time", "sim_flow"},
            "location_list_file": {},
            "calib_param_file": {"gage_id"},
        }
        return file_dict

    def assemble_file_paths(
        self, exclude: set[str] = None, include: set[str] = None
    ) -> dict[str, Path]:
        """Assemble file paths from the configuration.

        Args:
            exclude: Optional set of fields to exclude from the list of paths.
            include: Optional set of fields to include in the list of paths.

        Returns:
            Dictionary mapping path names to their Path objects.

        """
        # all input file paths to be checked in the config
        path_fields = self.file_required_column_map()

        if exclude:
            # exclude specified fields from the list
            path_fields = [field for field in path_fields if field not in exclude]

        if include:
            # include specified fields in the list
            path_fields = [field for field in path_fields if field in include]

        # create a dictionary to hold the paths
        paths = {}
        for path1 in path_fields:
            val = getattr(self.config.file_paths, path1, None)
            if val is not None:
                if isinstance(val, (str, Path)):
                    paths[path1] = Path(val)
                elif isinstance(val, dict):
                    paths[path1] = {
                        k: Path(v) for k, v in val.items() if isinstance(v, (str, Path))
                    }
                else:
                    logger.warning(f"Unsupported type for {path1}: {type(val)}")

        # Remove any None values and return the paths dictionary
        return {k: v for k, v in paths.items() if v is not None}

    def validate_paths(
        self, paths: str | Path | list[str | Path] | dict[str, str | Path]
    ) -> None:
        """Validate that all file and directory paths exist.

        Args:
            paths: A string, Path, list, or dict of strings/Paths to validate.

        Raises:
            FileNotFoundError: If any path does not exist.

        """
        if isinstance(paths, (str, Path)):
            paths = [paths]
        elif isinstance(paths, dict):
            paths = list(flatten_dict(paths).values())

        missing_paths = [p for p in paths if not Path(p).exists()]
        if missing_paths:
            msg = f"Missing paths: {missing_paths}"
            logger.error(msg)
            raise FileNotFoundError(msg)

    def check_file_columns(
        self,
        dict_path: Dict[str, str | Path | dict[str, str | Path]] = None,
    ) -> None:
        """Check if the required columns are present in the files in the configuration.

        Args:
            config: The configuration object to check.
            dict_path: Optional dictionary of file paths to check.

        Raises:
            ValueError: If any required columns are missing in the files.

        """
        if dict_path is None:
            msg = "No file paths provided for checking columns."
            logger.error(msg)
            raise ValueError(msg)

        dict_cols = self.file_required_column_map()
        logger.debug("Required columns for files: %s", dict_cols)

        # loop through the required files and check their columns
        for file_key, file_path in dict_path.items():
            if file_key not in dict_cols:
                logger.warning(
                    f"No required columns defined for {file_key}. Skipping column check."
                )
                continue

            if isinstance(file_path, (str, Path)):
                file_path = [
                    Path(file_path)
                ]  # Ensure file_path is a list of Path objects
            elif isinstance(file_path, dict):
                file_path = [Path(v) for v in file_path.values()]
            else:
                msg = f"Invalid type for file path '{file_key}': {type(file_path)}. Must be str, Path, or dict."
                logger.error(msg)
                raise ValueError(msg)

            required_columns = dict_cols[file_key]
            if not required_columns:
                logger.warning(
                    f"No required columns defined for {file_key}. Skipping column check."
                )
                continue

            for file in file_path:
                check_columns_dataframe(file, required_columns)

    def setup_logger(self) -> None:
        """Set up logging configuration."""
        log_file = Path(self.config.file_paths.output_dir) / "verification.log"
        log_level = "INFO"
        setup_logging(
            level=log_level,
            target_packages=("__main__", "nwm.verf"),
            log_file=log_file,
            file_level=log_level,
        )
        logger.info(f"Config file {self.config_path} loaded successfully.")
        logger.info(f"Logging initialized with log level: {log_level}.")
        logger.info(f"Log file: {log_file}")

    def _expand_user(self, val: str | Path) -> Path:
        """Expand user home directory and environment variables in a file path."""
        s = str(val)

        user = os.environ.get("LOGNAME") or os.environ.get("USER")
        if user:
            user = user.split("@", 1)[0]
            s = re.sub(r"\$USER\b", user, s)

        s = os.path.expandvars(s)
        s = os.path.expanduser(s)

        return str(s)

    def _expand_user_file_paths(self, obj) -> None:
        if isinstance(obj, BaseModel):
            for name in obj.__class__.model_fields:
                val = getattr(obj, name)
                new_val = self._expand_user_file_paths(val)
                if new_val is not val:
                    setattr(obj, name, new_val)

        elif isinstance(obj, dict):
            for k, v in obj.items():
                new_v = self._expand_user_file_paths(v)
                if new_v is not v:
                    obj[k] = new_v

        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                new_v = self._expand_user_file_paths(v)
                if new_v is not v:
                    obj[i] = new_v

        elif isinstance(obj, tuple):
            return tuple(self._expand_user_file_paths(v) for v in obj)

        elif isinstance(obj, (str, Path)):
            s = str(obj)
            if any(x in s for x in ("~", "$")):
                return self._expand_user(s)

        return obj

    def check_forecast_period(self):
        """Check forecast period configuration.

        If forecast_start_date and forecast_end_date are the same and nwm_forecast.data_source is not 'ngenCERF',
        raise a warning.
        """
        if (
            self.config.nwm_forecast.data_source.lower() != "ngencerf"
            and self.config.general.forecast_start_date
            and self.config.general.forecast_end_date
        ):
            start_dates = self.config.general.forecast_start_date
            end_dates = self.config.general.forecast_end_date
            for dataset in self.config.general.dataset_name:
                idx = self.config.general.dataset_name.index(dataset)
                if start_dates[idx] == end_dates[idx]:
                    logger.warning(
                        f"Forecast start date and end date are the same for dataset {dataset}. "
                        "Metrics for individual lead times (e.g., hour 1, 2, 3 etc) cannot be computed, and "
                        "some plots may not be generated properly."
                    )
        return self

    def load_and_validate_yaml(self):
        """Load a YAML file and validate its structure using Pydantic."""
        try:
            with open(Path(self.config_path), "r") as file:
                data = yaml.safe_load(file)
                self.config = Config(**data)

        except ValidationError as e:
            raise Exception(f"Validation Error: {e}")
        except Exception as e:
            raise Exception(f"Error loading YAML file: {e}")

        # expand all paths (with ~ or environment variables)
        self._expand_user_file_paths(self.config)

        # Substitute placeholders in the config
        self.substitute_placeholders()

        # validate file paths
        exclude_files = set()
        # if self.config.nwm_forecast.data_source not in ["ngenCERF", "ngenSIM"]:
        #    exclude_files.add("fcst_data_file")
        if self.config.general.location_list or self.config.general.assemble_domain:
            exclude_files.add("location_list_file")
        if not self.config.general.separate_calibrated:
            exclude_files.add("calib_param_file")

        # validate paths
        paths = self.assemble_file_paths(exclude=exclude_files)
        self.validate_paths(paths)

        # setup logger
        self.setup_logger()

        # check required columns in files
        self.check_file_columns(paths)

        # check forecast period configuration
        self.check_forecast_period()

        # save file config
        out_file = (
            Path(self.config.file_paths.output_dir) / "nwm_verf_config_expanded.yaml"
        )
        save_data(self.config, out_file)
        logger.info(f"Expanded config saved to {out_file}")

        return self.config.model_dump()
