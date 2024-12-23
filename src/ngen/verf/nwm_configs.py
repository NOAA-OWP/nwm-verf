import pandas as pd

def get_nwm_cycle_frequency(nwm_config: str):

    """
    nwm_config: a string indicating the NMW configuration. Currently supported options: short_range, medium_range and long_range

    Returns the cycle frequency in hours for the given NWM configuration

    """

    freqs = {
        'short_range': 1,
        'medium_range': 6,
        'long_range': 6,
    }

    return freqs.get(nwm_config.lower(), 'Invalid nwm configuration; only short_range, medium_range and long_range are supported')

def get_nwm_fcst_window(nwm_config: str):

    """
    nwm_config: a string indicating the NMW configuration. Currently supported options: short_range, medium_range and long_range

    Returns the length of the forecast window in hours for the given NWM configuration

    """

    freqs = {
        'short_range': 18,
        'medium_range': 240,
        'long_range': 720,
    }

    return freqs.get(nwm_config.lower(), 'Invalid nwm configuration; only short_range, medium_range and long_range are supported')