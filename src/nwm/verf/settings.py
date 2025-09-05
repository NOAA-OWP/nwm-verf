import logging
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# bins for each metric for creating the histograms (in create_plots.py)
metric_value_bins_default = {
    "KGE": [float("-inf"), -1, -0.5, 0, 0.2, 0.4, 0.6, 0.8, 1.0],
    "NSE": [float("-inf"), -1, -0.5, 0, 0.2, 0.4, 0.6, 0.8, 1.0],
    "NNSE": [0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0],
    "CORR": [-1, -0.5, 0, 0.2, 0.4, 0.6, 0.8, 1.0],
}

# color maps for each metric for creating the spatial maps (in create_plots.py)
metric_color_scale_default = dict(
    KGE=(-0.5, 1),
    NSE=(-0.5, 1),
    CORR=(-0.5, 1),
    NNSE=(0, 1),
)

# define different groups of metrics
metric_groups = dict(
    higher_is_better=[
        "CORR",
        "sCORR",
        "NSE",
        "NNSE",
        "NSElog",
        "NSEwt",
        "KGE",
        "KGE1",
        "KGE2",
        "R2",
        "POD",
        "CSI",
        "n_obs",
        "n_mod",
        "min_obs",
        "min_mod",
        "max_obs",
        "max_mod",
        "mean_obs",
        "mean_mod",
        "sum_obs",
        "sum_mod",
        # "pt_obs",
        # "pt_mod",
    ],
    lower_is_better=[
        "ME",
        "MAE",
        "MSE",
        "RMSE",
        "RMAE",
        "PBIAS",
        "RBIAS",
        "MBAIS",
        "aprBIAS",
        "RSR",
        "HSEG_FDC",
        "MSEG_FDC",
        "LSEG_FDC",
        "FAR",
        "FBIAS",
        "PKBIAS",
        "PKTE",
        "EVBIAS",
        "var_obs",
        "var_mod",
        "max_delta",
        # "pt_err",
    ],
    abs_applicable=["ME", "PBIAS", "HSEG_FDC", "MSEG_FDC", "LSEG_FDC"],
)


# function to define the colormaps and scaling of spatial maps
def get_metric_colormap(conf: dict, plot_type: str) -> dict:
    metric_cmaps = dict()
    for m1 in conf["metric_subset"]:
        metric_cmaps[m1] = dict()

        # define scale
        if (
            "scaling" in conf.keys()
            and m1 in conf["scaling"]
            and conf["scaling"][m1] is not None
        ):
            metric_cmaps[m1]["clim"] = tuple(conf["scaling"][m1])
        elif m1 in metric_color_scale_default.keys():
            metric_cmaps[m1]["clim"] = metric_color_scale_default[m1]
        else:
            logger.info(
                f"scaling not defined for {m1}; metric data will not be scaled when creating {plot_type}"
            )
            metric_cmaps[m1]["clim"] = (float("nan"), float("nan"))

        # define color maps
        if plot_type == "map":
            if m1 in metric_groups["higher_is_better"]:
                metric_cmaps[m1]["cmap"] = "rainbow_r"  # cc.rainbow[::-1]
            elif m1 in metric_groups["lower_is_better"]:
                metric_cmaps[m1]["cmap"] = "rainbow"  # cc.rainbow
            else:
                logger.info(
                    f"metric orientation not defined for {m1}; set to default (rainbow_r)"
                )

    return metric_cmaps


# function to define the binnings for creating the histograms
def get_metric_bins(conf: dict) -> dict:
    metric_bins = dict()
    for m1 in conf["metric_subset"]:
        if (
            "binning" in conf.keys()
            and m1 in conf["binning"]
            and conf["binning"][m1] is not None
        ):
            bins = conf["binning"][m1]
            bins = [float(x.lower()) if type(x) is str else x for x in bins]
            metric_bins[m1] = bins
        elif m1 in metric_value_bins_default.keys():
            metric_bins[m1] = metric_value_bins_default[m1]
        else:
            metric_bins[m1] = []
            logger.info(f"binning is not defined for {m1}; use equal-width bins")

    return metric_bins


dict_teehr_metrics = {
    "n_obs": "primary_count",
    "n_mod": "secondary_count",
    "min_obs": "primary_minimum",
    "min_mod": "secondary_minimum",
    "max_obs": "primary_maximum",
    "max_mod": "secondary_maximum",
    "mean_obs": "primary_average",
    "mean_mod": "secondary_average",
    "sum_obs": "primary_sum",
    "sum_mod": "secondary_sum",
    "var_obs": "primary_variance",
    "var_mod": "secondary_variance",
    "max_delta": "max_value_delta",
    "NSE": "nash_sutcliffe_efficiency",
    "NNSE": "nash_sutcliffe_efficiency_normalized",
    "KGE": "kling_gupta_efficiency",
    "KGE1": "kling_gupta_efficiency_mod1",
    "KGE2": "kling_gupta_efficiency_mod2",
    "ME": "mean_error",
    "MAE": "mean_absolute_error",
    "MSE": "mean_squared_error",
    "RMSE": "root_mean_squared_error",
    # "pt_obs": "primary_max_value_time",  # these timestamps based metrics are currently not supported
    # "pt_mod": "secondary_max_value_time",
    # "pt_err": "max_value_timedelta",
    "RBIAS": "relative_bias",
    "MBAIS": "multiplicative_bias",
    "RMAE": "mean_absolute_relative_error",
    "CORR": "pearson_correlation",
    "sCORR": "spearman_correlation",
    "R2": "r_squared",
    "aprBIAS": "annual_peak_relative_bias",
}

dict_nwm_eval_metrics = {
    "CORR": "pearson correlation",
    "NSE": "nash_sutcliffe_efficiency",
    "NNSE": "nash_sutcliffe_efficiency_normalized",
    "NSElog": "logrithmic nash_sutcliffe_efficiency",
    "NSEwt": "weighted NSE and NSElog",
    "KGE": "kling_gupta_efficiency",
    "MAE": "mean_absolute_error",
    "RMSE": "root_mean_squared_error",
    "PBIAS": "percent_bias",
    "RSR": "RMSE_observation_std_ratio",
    "HSEG_FDC": "pbias_high_flow_FDC",
    "MSEG_FDC": "pbias_medium_flow_FDC",
    "LSEG_FDC": "pbias_low_flow_FDC",
    "POD": "probability_of_detection",
    "FAR": "false_alarm_ratio",
    "CSI": "critical_success_index",
    "FBIAS": "frequency_bias",
    "PKBIAS": "percent_peak_flow_bias",
    "PKTE": "peak_timing_error",
    "EVBIAS": "event_volume_bias",
}


def data_paths(conf: dict) -> dict:
    conf1 = conf["general"]
    conf2 = conf["file_paths"]
    root_dir = conf2["base_dir"]
    sub_dir = conf2["output_dir"]  # conf1["location_set_name"]
    config = conf1["nwm_configuration"]

    # paths for all observations
    obs_dir = Path(root_dir, sub_dir, "usgs")
    obs_dir.mkdir(parents=True, exist_ok=True)

    # paths for forecast datasets
    fcst_data_dir = dict()
    fcst_json_dir = dict()
    fcst_data_link_dir = dict()
    paired_data_file = dict()
    metric_file = dict()
    for idx, dataset in enumerate(conf1["dataset_name"]):
        # create output directories based on NWM version
        fcst_json_dir[dataset] = Path(
            root_dir, sub_dir, conf1["nwm_version"][idx], "zarr", config
        )
        fcst_data_dir[dataset] = Path(
            root_dir, sub_dir, conf1["nwm_version"][idx], "timeseries", config
        )

        # create additional directory for storing symbolic links to parquet files required for each dataset
        fcst_data_link_dir[dataset] = Path(
            root_dir,
            sub_dir,
            conf1["dataset_name"][idx],
            conf1["nwm_configuration"],  # "fcst"
        )

        # path for joined parquet files (note in pair_data.py, 'group*' will be added to the file name for individual location groups)
        filename = (
            f"{dataset}."
            f"{conf1['nwm_version'][idx]}."
            f"{conf1['nwm_configuration']}."
            "joined.parquet"
        )
        paired_data_file[dataset] = Path(root_dir, sub_dir, "joined", filename)

        # path for metric output files
        metric_file[dataset] = Path(
            root_dir, sub_dir, "metrics", filename.replace("joined", "metrics")
        )

        if conf["metrics"]["file_format"] == "csv":
            metric_file[dataset] = metric_file[dataset].with_suffix(".csv")

    # path for plots
    plot_dir = Path(root_dir, sub_dir, "plots", conf1["nwm_configuration"])

    # path for crosswalk file
    cwt_file = dict()
    for ver1 in list(set(conf1["nwm_version"])):
        if ver1 in conf2["crosswalk_file"].keys():
            cwt_file[ver1] = Path(conf2["crosswalk_file"][ver1])
        elif ver1 != "ngen":
            raise Exception(f"crosswalk file not found for {ver1}")

    # path for geometry file
    geo_file = Path(conf2["gage_hydrofabric_file"]).resolve(strict=True)

    # assemble all paths into a dictionary
    data_paths = {
        "fcst": fcst_data_dir,
        "fcst_json": fcst_json_dir,
        "fcst_link": fcst_data_link_dir,
        "obs": obs_dir,
        "joined": paired_data_file,
        "metrics": metric_file,
        "plots": plot_dir,
        "crosswalk": cwt_file,
        "geofile": geo_file,
    }

    return data_paths
