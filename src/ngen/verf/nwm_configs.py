import pandas as pd

def get_nwm_cycle_config(nwm_config: str):

    """
    nwm_config: a string indicating the NMW configuration. 

    Returns the cycle configuration ([start_hour, end_hour, frecency]) for the given NWM configuration

    """

    cycle_config = {
        'short_range': {'start_hr': 0, 'end_hr': 23, 'freq_hr': 1},
        'short_range_alaska': {'start_hr': 0, 'end_hr': 21, 'freq_hr': 3},
        'short_range_hawaii': {'start_hr': 0, 'end_hr': 12, 'freq_hr': 12},
        'short_range_puertorico': {'start_hr': 6, 'end_hr': 18, 'freq_hr': 12},
    }

    config = nwm_config.lower()
    if config not in cycle_config.keys():
        raise ValueError(f"Invalid nwm configuration; only {cycle_config.keys()} are supported.")

    return cycle_config[config]

def get_nwm_fcst_window(nwm_config: str):

    """
    nwm_config: a string indicating the NMW configuration.

    Returns the length of the forecast window in hours for the given NWM configuration

    """

    fcst_win = {
        'short_range': 18,
        'short_range_alaska': 45,
        'short_range_hawaii': 48,
        'short_range_puertorico': 48,
        #'medium_range': 240,
        #'long_range': 720,
    }

    config = nwm_config.lower()
    if config not in fcst_win.keys():
        raise ValueError(f" get_nwm_fcst_window: invalid nwm configuration; only {fcst_win.keys()} are supported.")

    return fcst_win[config]
    