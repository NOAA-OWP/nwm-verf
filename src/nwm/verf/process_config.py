import logging
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
# logging.basicConfig(level=logging.INFO)


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
            "fcst_data_file": {"Time", "sim_flow"},
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

        # Substitute placeholders in the config
        self.substitute_placeholders()

        # validate file paths
        paths = self.assemble_file_paths()
        self.validate_paths(paths)

        # setup logger
        self.setup_logger()

        # check required columns in files
        self.check_file_columns(paths)

        # save file config
        out_file = (
            Path(self.config.file_paths.output_dir) / "nwm_verf_config_expanded.yaml"
        )
        save_data(self.config, out_file)
        logger.info(f"Expanded config saved to {out_file}")

        return self.config.model_dump()
