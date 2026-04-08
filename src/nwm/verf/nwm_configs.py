from asyncio.log import logger
from pathlib import Path
from typing import List, Union

import numpy as np
import yaml
from pydantic import BaseModel, field_validator


class CycleConfig(BaseModel):
    """A forecast cycle configuration defined with 5 numbers: first 4 ints, last a float."""

    values: List[Union[int, float]]

    @field_validator("values")
    @classmethod
    def check_config(cls, v: List[Union[int, float]]) -> List[Union[int, float]]:
        if len(v) != 5:
            raise ValueError(
                f"Cycle configuration must have exactly 5 elements, got {len(v)}"
            )
        if not all(isinstance(x, int) for x in v[:4]):
            raise TypeError(
                f"First 4 elements of cycle configuration must be ints, got {[type(x).__name__ for x in v[:4]]}"
            )
        if not isinstance(v[4], float) and not isinstance(v[4], int):
            raise TypeError(
                f"Last element of cycle configuration must be a float or int, got {type(v[4]).__name__}"
            )
        return v

    def __iter__(self):
        """Allow unpacking like a list."""
        return iter(self.values)


class ForecastConfig:
    """Class for handling forecast configurations."""

    def __init__(self, config_file: str | Path = None):
        """Initialize the ForecastConfig with a configuration file."""
        if config_file:
            self.config_file = Path(config_file)
            self.config_dict = {}
            self.read_config_file()

    def read_config_file(self):
        """Read the configuration file."""
        try:
            with open(self.config_file, "r") as f:
                self.config_dict = yaml.safe_load(f) or {}
        except Exception as e:
            self.config_dict = {}
            msg = f"Error reading {self.config_file}: {e}"
            logger.error(msg)
            raise RuntimeError(msg)

    def get_cycle_info(self, fcst_config: str) -> List[Union[int, float]]:
        """Get the cycle info for a specific forecast configuration."""
        if fcst_config not in self.config_dict:
            msg = f"Invalid forecast configuration: {fcst_config}"
            logger.error(msg)
            raise ValueError(msg)
        cycle_info = self.config_dict[fcst_config]
        if not isinstance(cycle_info[0], list):
            cycle_info = [cycle_info]

        return cycle_info

    def validate_cycle_info(self, fcst_config: str) -> None:
        """Validate the cycle info for a specific forecast configuration."""
        for c1 in self.get_cycle_info(fcst_config):
            CycleConfig.model_validate({"values": c1})

    def get_valid_cycles(self, fcst_config: str):
        """Return the valid cycles for the given forecast configuration.

        Args:
            fcst_config: a string indicating the forecast configuration.

        """
        cycles = []
        for c1 in self.get_cycle_info(fcst_config):
            cycle_start, cycle_end, cycle_freq, fcst_win, fcst_timestep = c1
            cycles.extend(range(cycle_start, cycle_end + 1, cycle_freq))

        return sorted(cycles)

    def get_fcst_window_timestep(
        self, fcst_config: str, fcst_cycle: int = None
    ) -> tuple[float, float]:
        """Return the forecast window for the given forecast configuration and cycle.

        Args:
            fcst_config: a string indicating the forecast configuration.
            fcst_cycle: an integer indicating the forecast cycle hour.

        Returns: a tuple containing the forecast window and timestep for the given configuration and cycle.

        """
        try:
            return next(
                (fcst_win, fcst_timestep)
                for cycle_start, cycle_end, cycle_freq, fcst_win, fcst_timestep in self.get_cycle_info(
                    fcst_config
                )
                if not fcst_cycle
                or fcst_cycle in range(cycle_start, cycle_end + 1, cycle_freq)
            )
        except StopIteration:
            raise ValueError(f"No matching cycle found for fcst_cycle={fcst_cycle!r}")

    def interpret_lead_times(
        self, lead_times: list[str], fcst_config: str, leads: list[int] = []
    ):
        """Interpret lead times based on the NWM configuration.

        Args:
            lead_times: a list of lead time strings (e.g., ['1','1-5','all', 'all-aggregated'])
            fcst_config: a string indicating the NWM configuration.
            leads: a list of computed lead times  (optional)

        Returns:
            a list of strings representing the lead time groups given forecast configuration.

        """
        if fcst_config == "ngen_simulation":  # for simulation, only lead time 0
            return ["0"], [], 0

        fcst_win, timestep = self.get_fcst_window_timestep(fcst_config)
        if fcst_win >= 0:
            all_leads = list(np.arange(timestep, fcst_win + timestep, timestep))
        else:
            all_leads = list(np.arange(fcst_win + timestep, timestep, timestep))

        # check if all_leads covered by leads
        missing_leads = []
        existing_leads = all_leads
        if len(leads) > 0:
            missing_leads = [l1 for l1 in all_leads if l1 not in leads]
            existing_leads = [l1 for l1 in all_leads if l1 in leads]

        existing_leads = [
            str(round(l1, 2)) if l1 >= 0 else "m" + str(round(abs(l1), 2))
            for l1 in existing_leads
        ]  # ensure all are strings, prepend 'm' for negative leads

        def clean_num_str(s):
            return str(int(float(s))) if float(s).is_integer() else s

        def clean_num(x):
            try:
                f = float(x)
            except (ValueError, TypeError):
                msg = f"Invalid lead time value: {x!r}. Must be numerical or a string representing a number."
                logger.error(msg)
                raise ValueError(msg)
            return f"{f:g}"

        existing_leads = [clean_num(l1) for l1 in existing_leads]

        interpreted_leads = []

        for lt in lead_times:
            if lt == "all":
                interpreted_leads.extend(existing_leads)
            elif lt == "all_aggregated":
                if existing_leads:
                    interpreted_leads.append(
                        f"{existing_leads[0]}-{existing_leads[-1]}"
                    )
            elif "-" in lt:  # range like "1-5"
                start_str, end_str = lt.split("-")
                start = clean_num(start_str)
                end = clean_num(end_str)
                if start not in existing_leads or end not in existing_leads:
                    logger.warning(
                        f"Lead time range '{lt}' has start or end not in existing leads {existing_leads}. Skip this lead time."
                    )
                else:
                    interpreted_leads.append(f"{start}-{end}")

            else:  # single lead time
                lt_clean = clean_num(lt)
                if lt_clean in existing_leads:
                    interpreted_leads.append(lt_clean)
                else:
                    logger.info(
                        f"Lead time '{lt_clean}' not found in existing leads {existing_leads}. Skip this lead time."
                    )

        # remove duplicated lead times while preserving order
        lead_times = list(dict.fromkeys(interpreted_leads))

        return lead_times, missing_leads, timestep
