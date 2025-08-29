import pandas as pd


def get_nwm_cycle_config(nwm_config: str):
    """
    nwm_config: a string indicating the NMW configuration.

    Returns the cycle configuration ([start_hour, end_hour, frecency]) for the given NWM configuration

    """

    cycle_config = {
        "short_range": {"start_hr": 0, "end_hr": 23, "freq_hr": 1},
        "short_range_alaska": {"start_hr": 0, "end_hr": 21, "freq_hr": 3},
        "short_range_hawaii": {"start_hr": 0, "end_hr": 12, "freq_hr": 12},
        "short_range_puertorico": {"start_hr": 6, "end_hr": 18, "freq_hr": 12},
        "medium_range_blend": {"start_hr": 0, "end_hr": 21, "freq_hr": 3},
    }

    config = nwm_config.lower()
    if config not in cycle_config.keys():
        raise ValueError(
            f"Invalid nwm configuration; only {cycle_config.keys()} are supported."
        )

    return cycle_config[config]


def get_nwm_fcst_window_timestep(nwm_config: str):
    """
    nwm_config: a string indicating the NMW configuration.

    Returns the length of the forecast window and timestep in hours for the given NWM configuration

    """

    fcst_win = {
        "short_range": [18, 1],
        "short_range_alaska": [45, 1],
        "short_range_hawaii": [48, 1],
        "short_range_puertorico": [48, 1],
        "medium_range_blend": [240, 1],
        "medium_range_mem1": [240, 1],
        "medium_range_mem2": [204, 1],
        "medium_range_mem3": [204, 1],
        "medium_range_mem4": [204, 1],
        "medium_range_mem5": [204, 1],
        "medium_range_mem6": [204, 1],
        "long_range_mem1": [720, 6],
        "long_range_mem2": [720, 6],
        "long_range_mem3": [720, 6],
        "long_range_mem4": [720, 6],
    }

    config = nwm_config.lower()
    if config not in fcst_win.keys():
        raise ValueError(
            f" get_nwm_fcst_window: invalid nwm configuration; only {fcst_win.keys()} are supported."
        )

    return fcst_win[config]


def interpret_lead_times(lead_times: list[str], nwm_config: str, leads: list[int] = []):
    """Interpret lead times based on the NWM configuration.

    Args:
        lead_times: a list of lead time strings (e.g., ['1','1-5','all', 'all-aggregated'])
        nwm_config: a string indicating the NWM configuration.
        leads: a list of computed lead times  (optional)

    Returns:
        a list of strings representing the lead time groups given forecast configuration.

    """
    fcst_win, timestep = get_nwm_fcst_window_timestep(nwm_config)
    all_leads = [i for i in range(timestep, fcst_win + 1, timestep)]

    # check if all_leads covered by leads
    missing_leads = []
    existing_leads = all_leads
    if len(leads) > 0:
        missing_leads = [l1 for l1 in all_leads if l1 not in leads]
        existing_leads = [l1 for l1 in all_leads if l1 in leads]

    lead_times = lead_times.copy()
    if "all" in lead_times:
        lead_times = [str(i) for i in existing_leads] + [
            x for x in lead_times if x != "all"
        ]
    elif "all_aggregated" in lead_times:
        lead_times = [str(existing_leads[0]) + "-" + str(existing_leads[-1])] + [
            x for x in lead_times if x != "all_aggregated"
        ]

    return lead_times, missing_leads
