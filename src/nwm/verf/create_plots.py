import logging
from functools import reduce
from pathlib import Path
from typing import List, Union

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from .nwm_configs import ForecastConfig
from .settings import (
    dict_nwm_eval_metrics,
    dict_teehr_metrics,
    get_metric_bins,
    get_metric_colormap,
)
from .utils import clean_data

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# get long names for metrics
def get_metric_long_name(metrics: list, library: str):
    if library == "teehr":
        dict1 = dict_teehr_metrics
    elif library == "nwm.eval":
        dict1 = dict_nwm_eval_metrics
    else:
        raise Exception(f" Metric libray not supported: {library}")

    metrics_long = []
    for m1 in metrics:
        if m1 in dict1.keys():
            metrics_long = metrics_long + [dict1.get(m1)]
        else:
            metrics_long = metrics_long + [m1]

    return metrics_long


# filter metric dataframe by required lead times and metrics
def filter_by_lead_metric(
    df_metrics: pd.DataFrame, conf: dict, nwm_config: str, fcst_config_file: str
):
    # first filter by lead times
    # leads0 = [str(x) for x in conf["lead_times"]]
    fc = ForecastConfig(fcst_config_file)
    leads0, missing_leads = fc.interpret_lead_times(conf["lead_times"], nwm_config)
    leads = df_metrics["lead_group"].unique()
    leads1 = [l1 for l1 in leads0 if l1 not in leads]
    if len(leads1) > 0:
        raise Exception(f"Lead times {leads1} not found in computed metric results")

    df_metrics1 = df_metrics[df_metrics["lead_group"].isin(leads0)]

    # then fitler by metric
    mts0 = conf["metric_subset"]
    mts = df_metrics1["metric"].unique()
    mts1 = [m1 for m1 in mts0 if m1 not in mts]
    if len(mts1) > 0:
        raise Exception(f"Metrics {mts1} not found in computed metric results")
    df_metrics1 = df_metrics1[df_metrics1["metric"].isin(mts0)]

    # sort the data by lead times as shown in the configuratio
    df_metrics1["lead_group"] = pd.Categorical(
        df_metrics1["lead_group"].astype(str), categories=leads0, ordered=True
    )
    df_metrics1 = df_metrics1.sort_values("lead_group")

    return df_metrics1


# gather metrics calculated for all datasets
def gather_all_metrics(datasets: list, data_paths: dict):
    df_metrics = pd.DataFrame()
    dfs = []
    for dataset in datasets:
        if data_paths[dataset].suffix.lower() == ".csv":
            df = pd.read_csv(data_paths[dataset])
        else:
            df = pd.read_parquet(data_paths[dataset])
        df = df.melt(
            id_vars=["lead_group", "primary_location_id"],
            var_name="metric",
            value_name=dataset,
        )
        dfs = dfs + [df]

    df_metrics = reduce(
        lambda left, right: pd.merge(
            left, right, on=["primary_location_id", "lead_group", "metric"], how="inner"
        ),
        dfs,
    )
    df_metrics = df_metrics.melt(
        id_vars=["lead_group", "primary_location_id", "metric"],
        value_vars=datasets,
        var_name="dataset",
    )

    return df_metrics


# create spatial maps for each dataset, metric and lead time
def create_spatial_maps(conf: dict, data_paths: dict):
    # gather all metrics calcualted
    datasets = conf["general"]["dataset_name"]
    df_metrics = gather_all_metrics(datasets, data_paths["metrics"])

    # filter metric dataframe by lead times and metrics
    conf1 = conf["plots"]["spatial_map"]
    df_metrics = filter_by_lead_metric(
        df_metrics,
        conf1,
        conf["general"]["nwm_configuration"],
        conf["file_paths"]["fcst_config_file"],
    )
    leads = df_metrics["lead_group"].unique()

    # get metric long names
    metrics = conf1["metric_subset"]
    metrics_long = get_metric_long_name(metrics, conf["metrics"]["library"])

    # add geometry (lat/lon)
    df_geo = gpd.read_parquet(data_paths["geofile"])
    df_geo = df_geo[["primary_location_id", "geometry"]]
    gdf_metrics = df_geo.merge(df_metrics, on="primary_location_id", how="inner")

    fig_dir = Path(data_paths["plots"], "maps")
    fig_dir.mkdir(parents=True, exist_ok=True)

    # loop through lead times, metrics, and datasets to create spatial maps
    cmap1 = get_metric_colormap(conf1, "map")
    for lead1 in leads:
        for metric1, metric_long in zip(metrics, metrics_long):
            for case1 in gdf_metrics["dataset"].unique():
                # filter data based on lead time, metric, and dataset
                filtered_gdf = gdf_metrics.query(
                    f"lead_group == '{lead1}' & metric == '{metric1}' & dataset == '{case1}'"
                )

                # clean the data by removing NaN and infinite values
                filtered_gdf = clean_data(filtered_gdf, "value")
                if filtered_gdf.empty:
                    logger.warning(
                        f"No data available for metric {metric1} at lead time {lead1} for dataset {case1}. "
                        f"Skipping map creation."
                    )
                    continue

                # clip the data
                if not np.isnan(cmap1[metric1]["clim"][0]) and not np.isnan(
                    cmap1[metric1]["clim"][1]
                ):
                    filtered_gdf["value"] = np.clip(
                        filtered_gdf["value"],
                        cmap1[metric1]["clim"][0],
                        cmap1[metric1]["clim"][1],
                    )

                # draw points color coded with the metric value
                fig, ax = plt.subplots(
                    figsize=(8.5, 6), subplot_kw={"projection": ccrs.PlateCarree()}
                )
                ax.set_title(
                    f"{metric1} ({metric_long}), lead_time={lead1}h, dataset={case1}"
                )

                # Add map features
                ax.add_feature(cfeature.COASTLINE)
                ax.add_feature(cfeature.BORDERS, linestyle=":")
                ax.add_feature(cfeature.LAND, facecolor="lightgray")
                ax.add_feature(cfeature.OCEAN, facecolor="lightblue")

                # Dynamically compute point size
                n_points = len(filtered_gdf)
                base_size = 10000  # adjust this constant to control density sensitivity
                point_size = max(
                    10, base_size / n_points
                )  # minimum size to keep the points visible
                point_size = min(100, point_size)  # don't want them too big either

                # Plot points
                sc = ax.scatter(
                    filtered_gdf.geometry.x,
                    filtered_gdf.geometry.y,
                    c=filtered_gdf["value"],
                    cmap=cmap1[metric1]["cmap"],
                    edgecolor="k",
                    linewidth=0.5,
                    s=point_size,
                    alpha=0.8,
                )
                plt.colorbar(sc, ax=ax, label="", orientation="horizontal", pad=0.02)
                ax.set_aspect(1.35)

                # export static plot to png
                file1 = "map_" + metric1 + "_h" + str(lead1) + "_" + case1 + ".png"
                if "tag" in conf1.keys() and conf1["tag"] is not None:
                    file1 = (
                        "map_"
                        + metric1
                        + "_h"
                        + str(lead1)
                        + "_"
                        + case1
                        + "_"
                        + conf1["tag"]
                        + ".png"
                    )
                fig_file = Path(fig_dir, file1)
                plt.savefig(fig_file, dpi=300, bbox_inches="tight")
                plt.close(fig)

    logger.info(f"  Spatial maps created at: {fig_dir}")


# create boxplot for each metric
def create_boxplots(conf: dict, data_paths: dict):
    # gather all metrics calcualted
    datasets = conf["general"]["dataset_name"]
    df_metrics = gather_all_metrics(datasets, data_paths["metrics"])

    # sort metric dataframe by dataset
    df_metrics = df_metrics.sort_values(by="dataset")

    # filter metric dataframe by lead times and metrics
    conf1 = conf["plots"]["boxplot"]
    df_metrics = filter_by_lead_metric(
        df_metrics,
        conf1,
        conf["general"]["nwm_configuration"],
        conf["file_paths"]["fcst_config_file"],
    )

    # get metric long names
    metrics = conf1["metric_subset"]
    metrics_long = get_metric_long_name(metrics, conf["metrics"]["library"])

    # ensure consistent colors applied to each dataset across metrics
    dataset_names = sorted(df_metrics["dataset"].unique())
    palette = dict(zip(dataset_names, sns.color_palette("tab10", len(dataset_names))))

    # create boxplot for each metric
    cmap1 = get_metric_colormap(conf1, "boxplot")
    for metric1, metric_long in zip(metrics, metrics_long):
        # filter the data by metric
        df1 = df_metrics[df_metrics["metric"] == metric1]

        # clean the data by removing NaN and infinite values
        df1 = clean_data(df1, "value")
        if df1.empty:
            logger.warning(
                f"No data available for metric {metric1}. Skipping boxplot creation."
            )
            continue

        # clip the data
        if not np.isnan(cmap1[metric1]["clim"][0]) and not np.isnan(
            cmap1[metric1]["clim"][1]
        ):
            df1["value"] = np.clip(
                df1["value"], cmap1[metric1]["clim"][0], cmap1[metric1]["clim"][1]
            )

        # start a new plot
        plt.figure()
        plt.set_loglevel("WARNING")
        if conf1["show_outliers"]:
            sns.boxplot(
                x=df1["lead_group"],
                y="value",
                data=df1,
                hue="dataset",
                hue_order=dataset_names,
                showfliers=True,
                palette=palette,
            )
        else:
            sns.boxplot(
                x=df1["lead_group"],
                y="value",
                data=df1,
                hue="dataset",
                hue_order=dataset_names,
                showfliers=False,
                palette=palette,
            )
        plt.title(f"{metric1}({metric_long})")
        plt.xlabel("Lead time (hours)")
        plt.ylabel("")

        # save plot to png
        fig_dir = Path(data_paths["plots"], "boxplots")
        fig_dir.mkdir(parents=True, exist_ok=True)
        file1 = "boxplot_" + metric1 + ".png"
        if "tag" in conf1.keys() and conf1["tag"] is not None:
            file1 = "boxplot_" + metric1 + "_" + conf1["tag"] + ".png"
        fig_file = Path(fig_dir, file1)
        plt.savefig(fig_file)

    logger.info(f"  Boxplots created at: {fig_dir}")


def create_histograms(conf: dict, data_paths: dict):
    # gather all metrics calcualted
    datasets = conf["general"]["dataset_name"]
    df_metrics = gather_all_metrics(datasets, data_paths["metrics"])

    # sort metric dataframe by dataset
    df_metrics = df_metrics.sort_values(by="dataset")

    # filter metric dataframe by lead times and metrics
    conf1 = conf["plots"]["histogram"]
    df_metrics = filter_by_lead_metric(
        df_metrics,
        conf1,
        conf["general"]["nwm_configuration"],
        conf["file_paths"]["fcst_config_file"],
    )
    leads = df_metrics["lead_group"].unique()

    # get metric long names
    metrics = conf1["metric_subset"]
    metrics_long = get_metric_long_name(metrics, conf["metrics"]["library"])

    # get custom bin edges for the metrics
    custom_bins = get_metric_bins(conf1)

    # ensure consistent colors applied to each dataset across metrics
    dataset_names = sorted(df_metrics["dataset"].unique())
    palette = dict(zip(dataset_names, sns.color_palette("tab10", len(dataset_names))))

    # loop through metrics and lead times to create histograms
    for metric1, metric_long in zip(metrics, metrics_long):
        # bin edges for the metric
        bins1 = custom_bins.get(metric1)

        for lead1 in leads:
            # filter data by metric and lead time
            df = df_metrics[
                (df_metrics["metric"] == metric1) & (df_metrics["lead_group"] == lead1)
            ]

            # clean the data by removing NaN and infinite values
            df = clean_data(df, "value")
            if df.empty:
                logger.warning(
                    f"No data available for metric {metric1} at lead time {lead1}. Skipping histogram creation."
                )
                continue

            # bin the data to create customized histograms
            if len(bins1) > 0:
                df["binned"] = pd.cut(df["value"], bins=bins1)
            else:
                df["binned"] = pd.cut(df["value"], bins=8)
            df = df.sort_values(by=["binned"])

            # create histogram
            plt.figure()
            plt.set_loglevel("WARNING")
            ax = sns.histplot(
                data=df,
                x=df["binned"].astype(str),
                hue="dataset",
                hue_order=dataset_names,
                multiple="dodge",
                shrink=0.8,
                palette=palette,
            )
            plt.setp(ax.get_xticklabels(), rotation=30)
            plt.title(f"{metric1}({metric_long})    lead_time={lead1}h")
            plt.xlabel("")
            plt.ylabel("Count")
            plt.subplots_adjust(bottom=0.2)

            # save plot to png
            fig_dir = Path(data_paths["plots"], "histograms")
            fig_dir.mkdir(parents=True, exist_ok=True)
            file1 = "hist_" + metric1 + "_h" + str(lead1) + ".png"
            if "tag" in conf1.keys() and conf1["tag"] is not None:
                file1 = (
                    "hist_" + metric1 + "_h" + str(lead1) + "_" + conf1["tag"] + ".png"
                )
            fig_file = Path(fig_dir, file1)
            plt.savefig(fig_file)

    logger.info(f"  Histograms created at: {fig_dir}")


def create_timeseries_plot(conf: dict, data_paths: dict):
    # Load all files and merge on "value_time"
    merged_df = None
    for dataset in conf["general"]["dataset_name"]:
        file = data_paths["joined"].get(dataset, None)
        if file is None or not Path(file).exists():
            msg = f"File not found for dataset {dataset}: {file}"
            logger.error(msg)
            raise FileNotFoundError(msg)

        df = pd.read_parquet(file)[
            ["value_time", "primary_value", "secondary_value", "measurement_unit"]
        ]
        unit = (
            df["measurement_unit"].iloc[0]
            if not df["measurement_unit"].isnull().all()
            else None
        )
        df.drop(columns=["measurement_unit"], inplace=True)
        df = df.rename(columns={"secondary_value": dataset})

        if merged_df is None:
            merged_df = df
        else:
            merged_df = pd.merge(
                merged_df,
                df[["value_time", dataset]],
                on="value_time",
            )

    # Ensure datetime
    merged_df["value_time"] = pd.to_datetime(merged_df["value_time"])

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))
    # plt.figure(figsize=(12, 6))
    ax.plot(
        merged_df["value_time"],
        merged_df["primary_value"],
        label="Observed",
        color="black",
        linewidth=1.2,
    )

    for dataset in conf["general"]["dataset_name"]:
        ax.plot(
            merged_df["value_time"],
            merged_df[dataset],
            label=dataset,
        )

    ax.set_xlabel("Time")
    ax.set_ylabel(f"Streamflow ({unit})")
    ax.set_title(
        f"Simulated vs Observed Streamflow at {conf['general']['location_list'][0]}\n"
        f"{conf['general']['nwm_configuration']}    T0 = {conf['general']['forecast_start_date'][0]}"
    )
    ax.legend()
    ax.grid(True)

    fig.autofmt_xdate()

    # save plot to png
    fig_dir = Path(data_paths["plots"], "timeseries")
    fig_dir.mkdir(parents=True, exist_ok=True)
    file1 = "ts_" + conf["general"]["location_list"][0] + ".png"
    conf1 = conf["plots"]["time_series"]
    if "tag" in conf1.keys() and conf1["tag"] is not None:
        file1 = (
            "ts_" + conf["general"]["location_list"][0] + "_" + conf1["tag"] + ".png"
        )
    fig_file = Path(fig_dir, file1)
    plt.savefig(fig_file)


def create_all_plots(conf: dict, data_paths: dict):
    """Create all plots based on the configuration."""
    plot_functions = {
        "spatial_map": create_spatial_maps,
        "histogram": create_histograms,
        "boxplot": create_boxplots,
        "time_series": create_timeseries_plot,
    }

    for plot_type, func in plot_functions.items():
        plot_conf = conf["plots"].get(plot_type) or {}
        if plot_conf.get("plot", False):
            func(conf, data_paths)
