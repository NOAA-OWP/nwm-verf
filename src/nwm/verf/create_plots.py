import logging
from functools import reduce
from pathlib import Path

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.patches import Patch

from .configuration import PlotsConfig
from .nwm_configs import ForecastConfig
from .settings import (
    dict_nwm_eval_metrics,
    dict_teehr_metrics,
    get_metric_bins,
    get_metric_colormap,
)
from .utils import clean_data, read_data

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_metric_long_name(metrics: list, library: str):
    """Get long names for metrics."""
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


def filter_by_lead_metric(
    df_metrics: pd.DataFrame, conf: dict, nwm_config: str, fcst_config_file: str
):
    """Filter the metric DataFrame by lead times and metrics."""
    # first filter by lead times
    fc = ForecastConfig(fcst_config_file)
    leads0, _, _ = fc.interpret_lead_times(conf["lead_times"], nwm_config)

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


def gather_all_metrics(datasets: list, data_paths: dict):
    """Gather metrics from all datasets into a single DataFrame."""
    df_metrics = pd.DataFrame()
    dfs = []
    for dataset in datasets:
        metric_file = data_paths[dataset]
        if not metric_file.exists():
            msg = f"Metric file for dataset {dataset} does not exist at {metric_file}; compute metrics first."
            logger.error(msg)
            raise FileNotFoundError(msg)
        if metric_file.suffix.lower() == ".csv":
            df = pd.read_csv(metric_file)
        else:
            df = pd.read_parquet(metric_file)
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


def add_tag_to_filename(conf: dict, file_name: str) -> str:
    """Add a tag to the filename if it exists in the config."""
    path = Path(file_name)
    tag = conf.get("tag")
    if tag:
        path = path.with_name(f"{path.stem}_{tag}{path.suffix}")
    return path.as_posix()


def save_plot(
    plt: plt,
    conf: dict,
    data_paths: dict,
    plt_type: str,
    plt_name: str = None,
    lead: str = None,
    dataset: str = None,
    metric: str = None,
) -> Path:
    """Save the plot to a file."""
    fig_dir = Path(data_paths["plots"], plt_type)
    fig_dir.mkdir(parents=True, exist_ok=True)

    if not plt_name:
        plt_name = plt_type
    if plt_type in ["time_series", "barchart", "metric_table"]:
        file1 = f"{plt_name}_{conf['general']['location_list'][0]}.png"
    else:
        if lead and dataset and metric:  # spatial map
            if str(lead) == "0":
                file1 = f"{plt_name}_{metric}_{dataset}.png"
            else:
                file1 = f"{plt_name}_{metric}_h{lead}_{dataset}.png"
        elif metric and not lead and not dataset:  # boxplot
            file1 = f"{plt_name}_{metric}.png"
        elif metric and lead:  # histogram
            if str(lead) == "0":
                file1 = f"{plt_name}_{metric}.png"
            else:
                file1 = f"{plt_name}_{metric}_h{lead}.png"
        else:
            msg = f"Insufficient information to name the plot file: plt_type={plt_type}, plt_name={plt_name}, "
            msg += f"lead={lead}, dataset={dataset}, metric={metric}"
            logger.error(msg)
            raise ValueError(msg)

    file1 = add_tag_to_filename(conf["plots"][plt_type], file1)
    fig_file = Path(fig_dir, file1)
    plt.savefig(fig_file)
    plt.close()

    return fig_dir


def group_df_by_location(
    df: pd.DataFrame | gpd.GeoDataFrame, location_list: list, location_col: str
) -> tuple:
    """Group DataFrame by location and return a tuple of DataFrames (in_list, out_list)."""
    df_inlist = df[df[location_col].isin(location_list)]
    df_outlist = df[~df[location_col].isin(location_list)]
    return df_inlist, df_outlist


def create_spatial_map(conf: dict, data_paths: dict):
    """Create spatial maps for each dataset, metric, and lead time."""
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
    df_geo = read_data(data_paths["crosswalk"][list(data_paths["crosswalk"].keys())[0]])
    if "geometry" not in df_geo.columns:
        logger.warning(
            f"Geometry column not found in crosswalk file: {data_paths['crosswalk']}"
            f"; spatial maps cannot be created."
        )
        return

    df_geo = df_geo[["primary_location_id", "geometry"]]
    gdf_metrics = df_geo.merge(df_metrics, on="primary_location_id", how="inner")

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

                logger.debug(
                    f"Number of locations after filtering nan and inf: {filtered_gdf['primary_location_id'].nunique()}"
                )

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
                    f"{metric1} ({metric_long}), "
                    f"{'' if lead1 == '0' else f'lead={lead1}h, '}"
                    f"{case1}",
                    fontsize=16,
                    pad=16,
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

                # Split GeoDataFrame into calibrated and non-calibrated subsets
                gdf_calib, gdf_noncalib = group_df_by_location(
                    filtered_gdf,
                    conf["general"].get("calib_gages", []),
                    "primary_location_id",
                )

                # Plot non-calibrated points (circles)
                sc1 = ax.scatter(
                    gdf_noncalib.geometry.x,
                    gdf_noncalib.geometry.y,
                    c=gdf_noncalib["value"],
                    cmap=cmap1[metric1]["cmap"],
                    marker="o",
                    edgecolor="k",
                    linewidth=0.5,
                    s=point_size,
                    alpha=0.8,
                    label=f"Non-calibrated(n={gdf_noncalib['primary_location_id'].nunique()})",
                )

                # Plot calibrated points (triangle symbols)
                if not gdf_calib.empty:
                    sc2 = ax.scatter(
                        gdf_calib.geometry.x,
                        gdf_calib.geometry.y,
                        c=gdf_calib["value"],
                        cmap=cmap1[metric1]["cmap"],
                        marker="^",
                        edgecolor="k",
                        linewidth=1.0,
                        s=point_size * 1.2,  # make them slightly more visible
                        alpha=0.8,
                        label=f"Calibrated(n={gdf_calib['primary_location_id'].nunique()})",
                    )

                    # Add legend outside the plot (to the right)
                    # ax.legend(
                    #     loc="upper left",  # anchor point of the legend box
                    #     bbox_to_anchor=(0.95, 1),  # position relative to axes
                    #     borderaxespad=0.0,  # no extra padding
                    #     frameon=True,
                    #     fontsize=12,
                    # )

                    # Add legend under the colorbar to avoid being clipped
                    ax.legend(
                        loc="upper center",
                        bbox_to_anchor=(
                            0.5,
                            -0.25,
                        ),  # centered, below the axes & colorbar
                        frameon=True,
                        fontsize=12,
                        ncol=2,
                    )

                # Colorbar from one of the scatter plots
                cbar = plt.colorbar(
                    sc1,
                    ax=ax,
                    label="",
                    orientation="horizontal",
                    pad=0.02,
                )
                cbar.ax.tick_params(labelsize=14)

                # set aspect ratio
                ax.set_aspect(1.35)

                # save plot to png
                fig_dir = save_plot(
                    plt,
                    conf,
                    data_paths,
                    "spatial_map",
                    "map",
                    str(lead1),
                    case1,
                    metric1,
                )

    logger.info(f"  Spatial maps created at: {fig_dir}")


def set_up_figure(df1: pd.DataFrame, df2: pd.DataFrame, plot_type: str = "boxplot"):
    """Set up a matplotlib figure with dynamic sizing based on data."""
    # Determine if multiple subplots are needed
    multi_plot = len(df1) > 0

    # Count number of unique groups on x-axis for each subplot
    n_groups2 = df2["lead_group"].nunique()
    n_groups1 = df1["lead_group"].nunique()

    # number of datasets
    n_datasets = df2["dataset"].nunique()

    if plot_type == "boxplot":
        # Width per category
        width_per_group = 0.7 if n_datasets <= 3 else 1.0
        subplot_widths = [
            n_groups2 * width_per_group,
            n_groups1 * width_per_group,
        ]
        spacing = 1 if multi_plot else 0
        fig_width = sum(subplot_widths) + spacing
        fig_width = max(fig_width, 8 if multi_plot else 4)

    elif plot_type == "histogram":
        # Histograms need more horizontal space
        if multi_plot:
            fig_width = 9  # wide figure for two subplots
        else:
            fig_width = 6  # single subplot
    else:
        # default fallback
        fig_width = 8

    # Create subplots
    if multi_plot:
        fig, axes = plt.subplots(
            1, 2, figsize=(fig_width, 5), sharey=True, constrained_layout=True
        )
    else:
        fig, axes = plt.subplots(
            1, 1, figsize=(fig_width, 5), sharey=True, constrained_layout=True
        )

    # Make axes always iterable
    if not isinstance(axes, (list, np.ndarray)):
        axes = [axes]

    return fig, axes


def add_shared_legend(fig, axes, dataset_names, palette):
    """Add a shared legend to the figure."""
    # Create manual legend handles
    handles_labels = {
        name: Patch(color=palette[name], label=name) for name in dataset_names
    }

    # Remove axes legends if they exist
    for ax in axes:
        if ax.get_legend() is not None:
            ax.get_legend().remove()

    # Add shared legend to the figure
    fig.legend(
        handles_labels.values(),
        handles_labels.keys(),
        loc="upper center",
        ncol=len(handles_labels),
        frameon=True,
        fontsize=12,
        bbox_to_anchor=(0.5, 0.98),
        borderaxespad=0.0,
    )

    # leave space for the legend
    plt.tight_layout(rect=[0, 0, 1, 0.92])


def create_boxplot(conf: dict, data_paths: dict):
    """Create boxplots for each metric in the configuration."""
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

        logger.debug(
            f"Number of locations after filtering nan and inf: {df1['primary_location_id'].nunique()}"
        )

        # clip the data
        if not np.isnan(cmap1[metric1]["clim"][0]) and not np.isnan(
            cmap1[metric1]["clim"][1]
        ):
            df1["value"] = np.clip(
                df1["value"], cmap1[metric1]["clim"][0], cmap1[metric1]["clim"][1]
            )

        # break data into calibrated and non-calibrated subsets
        df_calib, df_noncalib = group_df_by_location(
            df1, conf["general"].get("calib_gages", []), "primary_location_id"
        )

        # set up figure
        fig, axes = set_up_figure(df_calib, df_noncalib, plot_type="boxplot")

        # Plot non-calibrated
        sns.boxplot(
            x="lead_group",
            y="value",
            data=df_noncalib,
            hue="dataset",
            hue_order=dataset_names,
            showfliers=conf1["show_outliers"],
            palette=palette,
            ax=axes[0],
        )
        str1 = df_noncalib["primary_location_id"].nunique()
        tit1 = (
            f"Non-Calibrated Locations \n(n={str1})"
            if len(df_calib) > 0
            else f"All Locations \n(n={str1})"
        )
        axes[0].set_title(tit1)
        axes[0].set_ylabel(f"{metric1} ({metric_long})", fontsize=12)
        axes[0].set_yticklabels(axes[0].get_yticklabels(), fontsize=10)

        # Plot calibrated if it exists
        if len(df_calib) > 0:
            sns.boxplot(
                x="lead_group",
                y="value",
                data=df_calib,
                hue="dataset",
                hue_order=dataset_names,
                showfliers=conf1["show_outliers"],
                palette=palette,
                ax=axes[1],
            )
            str2 = df_calib["primary_location_id"].nunique()
            axes[1].set_title(f"Calibrated Locations \n(n={str2})")

        # Remove x-ticks and labels from all subplots
        if (df1["lead_group"] == "0").all():
            for ax in axes:
                ax.set_xticks([])
                ax.set_xticklabels([])
                ax.set_xlabel("")
        else:
            for ax in axes:
                ax.set_xlabel("Lead time (hours)", fontsize=12)
                ax.set_xticklabels(ax.get_xticklabels(), rotation=45, fontsize=12)

        # set y-axis label font size
        for ax in axes:
            ax.set_ylabel(f"{metric1} ({metric_long})", fontsize=12)
            ax.tick_params(axis="y", labelsize=12)

        # Add shared legend
        add_shared_legend(fig, axes, dataset_names, palette)

        # save plot to png
        fig_dir = save_plot(
            plt,
            conf,
            data_paths,
            "boxplot",
            metric=metric1,
        )

    logger.info(f"  Boxplots created at: {fig_dir}")


def create_histogram(conf: dict, data_paths: dict):
    """Create histograms for each metric in the configuration."""
    # gather all metrics calculated
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

            logger.debug(
                f"Number of locations after filtering nan and inf: {df['primary_location_id'].nunique()}"
            )

            # bin the data to create customized histograms
            if len(bins1) > 0:
                df["binned"] = pd.cut(df["value"], bins=bins1, include_lowest=True)
            else:
                df["binned"] = pd.cut(df["value"], bins=8, include_lowest=True)
            df = df.sort_values(by=["binned"])

            # check if any nan values after binning
            if df["binned"].isnull().any():
                logger.warning(
                    f"Some binned values are NaN for metric {metric1} at lead time {lead1}. Check bin edges."
                )

            # convert binned column to string for plotting
            df["binned"] = df["binned"].astype(str)

            # break data into calibrated and non-calibrated subsets
            df_calib, df_noncalib = group_df_by_location(
                df, conf["general"].get("calib_gages", []), "primary_location_id"
            )

            # set up figure
            fig, axes = set_up_figure(df_calib, df_noncalib, plot_type="histogram")
            plt.set_loglevel("WARNING")

            # Plot non-calibrated
            ax = sns.histplot(
                data=df_noncalib,
                x="binned",
                hue="dataset",
                hue_order=dataset_names,
                multiple="dodge",
                shrink=0.8,
                palette=palette,
                discrete=True,
                ax=axes[0],
            )
            str1 = df_noncalib["primary_location_id"].nunique()
            tit1 = (
                f"Non-Calibrated Locations (n={str1})"
                if len(df_calib) > 0
                else f"All Locations (n={str1})"
            )
            axes[0].set_title(tit1)
            axes[0].set_ylabel(f"{metric1} ({metric_long})", fontsize=12)
            axes[0].set_yticklabels(axes[0].get_yticklabels(), fontsize=10)

            if len(df_calib) > 0:
                ax = sns.histplot(
                    data=df_calib,
                    x="binned",
                    hue="dataset",
                    hue_order=dataset_names,
                    multiple="dodge",
                    shrink=0.8,
                    palette=palette,
                    discrete=True,
                    ax=axes[1],
                )
                str2 = df_calib["primary_location_id"].nunique()
                axes[1].set_title(f"Calibrated Locations (n={str2})")

            # set x-tick labels rotation and titles
            for ax in axes:
                plt.setp(ax.get_xticklabels(), rotation=30, fontsize=10)
                ax.set_ylabel("Number of locations", fontsize=12)
                ax.tick_params(axis="y", labelsize=12)
                ax.set_xlabel(
                    f"{metric1} ({metric_long})"
                    f"{'' if lead1 == '0' else f'   lead={lead1}h'}",
                    fontsize=12,
                )
                plt.subplots_adjust(bottom=0.2)

            # add shared legend
            add_shared_legend(fig, axes, dataset_names, palette)

            # save plot to png
            fig_dir = save_plot(
                plt,
                conf,
                data_paths,
                "histogram",
                "hist",
                lead=str(lead1),
                metric=metric1,
            )

    logger.info(f"  Histograms created at: {fig_dir}")


def create_time_series(conf: dict, data_paths: dict):
    """Create a time series plot for each dataset in the configuration."""
    # Load all files and merge on "value_time"
    merged_df = None
    for dataset in conf["general"]["dataset_name"]:
        # get observed data from paired data file
        file = data_paths["joined"].get(dataset, None)
        if file is None or not Path(file).exists():
            msg = f"Paired data file not found for dataset {dataset}: {file}. Cannot create time series plot."
            logger.warning(msg)
            continue

        df = pd.read_parquet(file)[["value_time", "primary_value", "measurement_unit"]]

        # get forecast data from forecast data file (because paired data file trimmed forecast data to
        # the time range of observed data by teehr)
        fcst_dir = Path(data_paths.get("fcst_link", {}).get(dataset, ""))
        if not fcst_dir.exists():
            msg = f"Forecast data directory not found for dataset {dataset}: {fcst_dir}. Cannot create time series plot."
            logger.error(msg)
            raise FileNotFoundError(msg)

        parquet_files = list(fcst_dir.glob("*.parquet"))
        if not parquet_files:
            msg = f"No parquet files found in {fcst_dir} for dataset {dataset}. Cannot create time series plot."
            logger.error(msg)
            raise FileNotFoundError(msg)
        df_fcst = pd.concat(
            [pd.read_parquet(f)[["value_time", "value"]] for f in parquet_files],
            ignore_index=True,
        )

        # merge observed and forecast data on value_time
        df = pd.merge(df, df_fcst, on="value_time", how="outer")

        unit = (
            df["measurement_unit"].iloc[0]
            if not df["measurement_unit"].isnull().all()
            else None
        )
        df.drop(columns=["measurement_unit"], inplace=True)
        df = df.rename(columns={"value": dataset})

        if merged_df is None:
            merged_df = df
        else:
            merged_df = pd.merge(
                merged_df,
                df[["value_time", dataset]],
                on="value_time",
            )

    if merged_df is None or merged_df.empty:
        logger.error("No data available to create time series plot.")
        return

    # Ensure datetime
    merged_df["value_time"] = pd.to_datetime(merged_df["value_time"])

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))
    n_points = len(merged_df)
    ax.plot(
        merged_df["value_time"],
        merged_df["primary_value"],
        label="Observed",
        color="black",
        linewidth=1.2,
        marker="o" if n_points < 30 else None,
        linestyle="-" if n_points >= 2 else "None",
    )

    for dataset in conf["general"]["dataset_name"]:
        ax.plot(
            merged_df["value_time"],
            merged_df[dataset],
            label=dataset,
            marker="o" if n_points < 30 else None,
            linestyle="-" if n_points >= 2 else "None",
        )

    ax.set_xlabel("Time", fontsize=12)
    ax.set_ylabel(f"Streamflow ({unit})", fontsize=12)
    ax.set_yticklabels(ax.get_yticklabels(), fontsize=10)
    ax.set_xticklabels(ax.get_xticklabels(), fontsize=10)
    ax.set_title(
        f"Simulated vs Observed Streamflow at {conf['general']['location_list'][0]}\n"
        f"{conf['general']['nwm_configuration']}    T0 = {conf['general']['forecast_start_date'][0]}",
        fontsize=14,
    )
    ax.legend(fontsize=10)
    ax.grid(True)

    fig.autofmt_xdate()

    # save plot to png
    fig_dir = save_plot(
        plt,
        conf,
        data_paths,
        "time_series",
    )

    logger.info(f"  Time series plots created at: {fig_dir}")


def get_metric_groups() -> dict:
    """Get metric groups for the configuration."""
    # Split metric columns into groups
    metric_groups = {
        "Standard": [
            "CORR",
            "KGE",
            "NNSE",
            "NSE",
            "NSElog",
            "NSEwt",
            "RSR",
            "RMSE",
            "MAE",
            "PBIAS",
        ],
        "Categorical": ["POD", "FAR", "CSI", "FBIAS"],
        "Event-based": ["PKBIAS", "PKTE", "EVBIAS"],
        "FDC-based": ["HSEG_FDC", "MSEG_FDC", "LSEG_FDC"],
    }
    return metric_groups


def create_metric_table(conf: dict, data_paths: dict):
    """Create a metric table based on the configuration."""
    # gather all metrics calcualted
    datasets = conf["general"]["dataset_name"]
    df_metrics = gather_all_metrics(datasets, data_paths["metrics"])

    # convert long format to wide format
    df_metrics = df_metrics[["dataset", "metric", "value"]].drop_duplicates()
    df_metrics.rename(columns={"dataset": "Formulation"}, inplace=True)
    df_metrics = df_metrics.pivot(
        index="Formulation", columns="metric", values="value"
    ).reset_index()

    metric_groups = get_metric_groups()
    n_groups = len(metric_groups)

    # Create subplots for each table
    max_form_len = df_metrics["Formulation"].str.len().max()
    fig, axes = plt.subplots(
        n_groups, 1, figsize=(9 + max_form_len * 0.1, 1.2 * n_groups)
    )

    if n_groups == 1:  # if only one group, axes is not iterable
        axes = [axes]

    for ax, group in zip(axes, metric_groups.keys()):
        ax.axis("off")  # hide axis

        # Round values to 2 digits and format large numbers in scientific notation
        def fmt_value(x):
            if isinstance(x, (int, float, np.floating)):
                if abs(x) >= 1e4:
                    return f"{x:.2e}"  # scientific notation for large numbers
                else:
                    return f"{x:.2f}"  # standard float with 2 decimals
            return x

        cols = ["Formulation"] + metric_groups[group]
        cols = [c1 for c1 in cols if c1 in df_metrics.columns]

        display_df = df_metrics[cols].copy().applymap(fmt_value)
        cell_values = display_df.values

        table = ax.table(
            cellText=cell_values,
            colLabels=cols,
            cellLoc="center",
            loc="center",
        )

        # automatically adjust the column widths
        table.auto_set_column_width(col=list(range(len(df_metrics.columns))))

        # Header styling
        for (i, j), cell in table.get_celld().items():
            if i == 0:  # first row = header
                cell.set_facecolor("teal")
                cell.set_text_props(weight="bold", color="white")

        table.auto_set_font_size(False)
        table.set_fontsize(11)
        table.scale(1.2, 2.0)

        # Add title above the table
        ax.set_title(
            f"{group} Metrics", fontsize=14, pad=8, weight="bold", color="dimgrey"
        )

    # Overall title
    conf1 = conf["general"]
    title = f"Metrics for {conf1['location_list'][0]} {conf1['nwm_configuration']} "
    title += f"(T0 = {conf1['forecast_start_date'][0]})"
    fig.suptitle(title, fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout()

    # save plot to png
    fig_dir = save_plot(
        plt,
        conf,
        data_paths,
        "metric_table",
    )

    logger.info(f"  Metric table plots created at: {fig_dir}")


def create_barchart(conf: dict, data_paths: dict):
    """Create a bar chart comparing datasets for each metric."""
    # gather all metrics calculated
    datasets = conf["general"]["dataset_name"]
    df_metrics = gather_all_metrics(datasets, data_paths["metrics"])

    # Get unique datasets and assign colors
    datasets = df_metrics["dataset"].unique()
    n_datasets = len(datasets)
    colors = plt.cm.tab10.colors  # categorical colormap
    color_map = {d: colors[i % len(colors)] for i, d in enumerate(datasets)}

    # Create subplots
    metrics = df_metrics["metric"].unique()
    n_metrics = len(metrics)
    ncols = 5
    nrows = -(-n_metrics // ncols)  # ceiling division
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(12, 8), squeeze=False)

    # bar width
    bar_width = 0.25  # fraction of total group width
    group_center = 0  # center of the single group

    # x positions for each bar in the group, centered at 0
    x_positions = np.linspace(
        group_center - bar_width * (n_datasets - 1) / 2,
        group_center + bar_width * (n_datasets - 1) / 2,
        n_datasets,
    )

    # Plot each metric
    for ax, metric in zip(axes.ravel(), metrics):
        values = df_metrics[df_metrics["metric"] == metric]["value"].values

        for xi, val, f in zip(x_positions, values, datasets):
            ax.bar(xi, val, width=bar_width, color=color_map[f])

        ax.set_title(metric, fontsize=14)
        ax.set_xticks([])  # no x-tick labels
        ax.set_xlabel("")
        ax.tick_params(axis="y", labelsize=14)
        ax.set_xlim(-0.5, 0.5)  # expand x-axis limits so bars don’t stretch

    # Remove unused subplots
    for j in range(len(metrics), len(axes.ravel())):
        fig.delaxes(axes.ravel()[j])

    # Add overall legend above subplots
    handles = [plt.Rectangle((0, 0), 1, 1, color=color_map[f]) for f in datasets]
    fig.legend(
        handles,
        datasets,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.95),
        ncol=len(datasets),
        fontsize=16,
        frameon=False,  # no legend box
    )

    # Add overall title
    conf1 = conf["general"]
    title = (
        f"Metrics for {conf1['location_list'][0]} {conf1['nwm_configuration']} "
        f"(T0 = {conf1['forecast_start_date'][0]})"
    )
    fig.suptitle(title, fontsize=20)
    plt.tight_layout(rect=[0, 0, 1, 0.92])  # leave space for legend and suptitle

    # save plot to png
    fig_dir = save_plot(
        plt,
        conf,
        data_paths,
        "barchart",
    )

    logger.info(f"  Barchart plots created at: {fig_dir}")


def create_all_plots(conf: dict, data_paths: dict):
    """Create all plots based on the configuration."""
    plot_types = list(PlotsConfig.model_fields.keys())
    plot_functions = {
        pt: globals()[f"create_{pt}"]
        for pt in plot_types
        if f"create_{pt}" in globals()
    }

    if conf["general"].get("separate_calibrated"):
        logger.info(
            "  Creating plots distinguishing calibrated and regionalized locations."
        )
        # retrieve calibrated location IDs and add prefix 'usgs-'
        calib_params_file = conf["file_paths"]["calib_param_file"]
        calib_gages = (
            read_data(calib_params_file)["gage_id"].unique().astype(str).tolist()
        )
        calib_gages = [f"usgs-{gid}" for gid in calib_gages]
        conf["general"]["calib_gages"] = calib_gages
    else:
        conf["general"]["calib_gages"] = []

    for plot_type, func in plot_functions.items():
        plot_conf = conf["plots"].get(plot_type) or {}
        if plot_conf.get("plot", False):
            func(conf, data_paths)
