import pandas as pd
import geopandas as gpd
from pathlib import Path
from functools import reduce
import geoviews as gv
import holoviews as hv
import seaborn as sns
import matplotlib.pyplot as plt
from bokeh.io import export_png
from selenium.webdriver.firefox.options import Options
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from .settings import metric_colors, metric_value_bins, dict_ngen_eval_metrics, dict_teehr_metrics

import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# get long names for metrics
def get_metric_long_name(metrics: list, library: str):

    if library == 'teehr':
        dict1 = dict_teehr_metrics
    elif library == 'ngen.eval':
        dict1 = dict_ngen_eval_metrics
    else:
        raise Exception(f' Metric libray not supported: {library}')
    
    metrics_long = []
    for m1 in metrics:
        if m1 in dict1.keys():
            metrics_long = metrics_long + [dict1.get(m1)]
        else:
            metrics_long = metrics_long + [m1]
    
    return metrics_long

# filter metric dataframe by required lead times and metrics
def filter_by_lead_metric(df_metrics:pd.DataFrame, conf:dict):

    # first filter by lead times
    leads0 = conf['lead_times']
    leads = df_metrics['lead_time'].unique()
    leads1 = [l1 for l1 in leads0 if l1 not in leads]
    if len(leads1) > 0:
        raise Exception(f'Lead times {leads1} not found in computed metric results')
    
    df_metrics1 = df_metrics[df_metrics['lead_time'].isin(leads0)]

    # then fitler by metric
    mts0 = conf['metric_subset']
    mts = df_metrics1['metric'].unique()
    mts1 = [m1 for m1 in mts0 if m1 not in mts]
    if len(mts1) > 0:
        raise Exception(f'Metrics {mts1} not found in computed metric results')
    df_metrics1 = df_metrics1[df_metrics1['metric'].isin(mts0)]

    return df_metrics1
    
# gather metrics calculated for all datasets
def gather_all_metrics(datasets:list, data_paths:dict):
    
    df_metrics = pd.DataFrame()
    dfs = []
    for dataset in datasets:
        df = pd.read_parquet(data_paths[dataset])
        df = df.melt(id_vars=['lead_time', 'primary_location_id'],var_name='metric',value_name=dataset)
        dfs = dfs + [df]

    df_metrics = reduce(lambda left, right: pd.merge(left, right, on=['primary_location_id', 'lead_time', 'metric'], how='inner'), dfs)
    df_metrics = df_metrics.melt(id_vars=['lead_time', 'primary_location_id', 'metric'],
                          value_vars=datasets,var_name='dataset')
    
    return df_metrics

# create spatial maps for each dataset, metric and lead time
def create_spatial_maps(conf:dict, data_paths: dict):

    # gather all metrics calcualted
    datasets = conf['general']['dataset_name']
    df_metrics = gather_all_metrics(datasets, data_paths['metrics'])

    # filter metric dataframe by lead times and metrics
    conf1 = conf['plots']['spatial_map']
    df_metrics = filter_by_lead_metric(df_metrics, conf1)

    # get metric long names
    metrics = conf1['metric_subset']
    metrics_long = get_metric_long_name(metrics,conf['metrics']['library'])

    # add geometry (lat/lon)
    df_geo = gpd.read_parquet(data_paths['geofile'])
    df_geo = df_geo[['id','geometry']]
    df_geo = df_geo.rename(columns={'id':'primary_location_id'})
    gdf_metrics = df_geo.merge(df_metrics, on="primary_location_id", how="inner")
    gdf_metrics.rename(columns={'dataset':'case'}, inplace=True)

    # set up hv/gv plotting service 
    hv.extension('bokeh', logo=False)
    gv.extension('bokeh', logo=False)
    basemap = hv.element.tiles.CartoLight()
    service = Service(executable_path=conf1['geckodriver_path'])
    options = Options()
    driver = webdriver.Firefox(service=service, options=options)

    # loop through lead times, metrics, and datasets to create spatial maps
    for lead1 in conf1['lead_times']:
        for metric1,metric_long in zip(metrics, metrics_long):
            for case1 in gdf_metrics['case'].unique():
                points = basemap * gv.Points(gdf_metrics, vdims=['value','lead_time','metric','case']).select(
                    lead_time=lead1,metric=metric1,case=case1).opts(
                    color='value', 
                    #tools = ['hover'], 
                    xaxis = 'bare', yaxis = 'bare',
                    title = f'{metric1}({metric_long})   lead_time={lead1}h   dataset={case1}',
                    show_legend = True,
                    height=400, width=600, size=7, 
                    clim = metric_colors[metric1]['clim'],
                    cmap = metric_colors[metric1]['cmap'],
                    colorbar=True)
            
                # Render the plot to a Bokeh figure
                plot = gv.render(points,backend='bokeh')

                # export spatial map to png
                fig_dir = Path(data_paths['plots'],'maps')
                fig_dir.mkdir(parents=True, exist_ok=True) 
                fig_file = str(fig_dir) + '/map_' + metric1 + '_h' + str(lead1) + '_' + case1 +'.png'
                export_png(plot, filename= fig_file, webdriver=driver)

    logger.info(f'Spatial maps created at: {fig_dir}')


# create boxplot for each metric
def create_boxplots(conf:dict, data_paths: dict):

    # gather all metrics calcualted
    datasets = conf['general']['dataset_name']
    df_metrics = gather_all_metrics(datasets, data_paths['metrics'])

    # filter metric dataframe by lead times and metrics
    conf1 = conf['plots']['boxplot']
    df_metrics = filter_by_lead_metric(df_metrics, conf1)

    # get metric long names
    metrics = conf1['metric_subset']
    metrics_long = get_metric_long_name(metrics,conf['metrics']['library'])

    # create boxplot for each metric
    for metric1,metric_long in zip(metrics, metrics_long):

        # filter and scale the data first
        df1 = df_metrics[df_metrics['metric']==metric1]
        df1['value'][df1['value'] < -1] = -1.0

        # start a new plot
        plt.figure()
        sns.boxplot(x=df1['lead_time'].astype(str),y='value',data=df1,hue='dataset')
        plt.title(f'{metric1}({metric_long})')
        plt.xlabel('Lead time (hours)')
        plt.ylabel('')

        # save plot to png
        fig_dir = Path(data_paths['plots'],'boxplots')
        fig_dir.mkdir(parents=True, exist_ok=True) 
        fig_file = str(fig_dir) + '/boxplot_' + metric1 +'.png'
        plt.savefig(fig_file)

    logger.info(f'Boxplots created at: {fig_dir}')

def create_histograms(conf:dict, data_paths: dict):

    # gather all metrics calcualted
    datasets = conf['general']['dataset_name']
    df_metrics = gather_all_metrics(datasets, data_paths['metrics'])

    # filter metric dataframe by lead times and metrics
    conf1 = conf['plots']['histogram']
    df_metrics = filter_by_lead_metric(df_metrics, conf1)

    # get metric long names
    metrics = conf1['metric_subset']
    metrics_long = get_metric_long_name(metrics,conf['metrics']['library'])

    # loop through metrics and lead times to create histograms
    for metric1,metric_long in zip(metrics, metrics_long):
        for lead1 in conf1['lead_times']:

            # filter data by metric and lead time
            df = df_metrics[(df_metrics['metric']==metric1) & (df_metrics['lead_time']==lead1)]
            df = df.dropna(subset='value')

            # bin the data to create customized histograms
            df['binned'] = pd.cut(df['value'],metric_value_bins.get(metric1))
            df = df.sort_values(by=['binned'])

            # create histogram
            plt.figure()
            ax = sns.histplot(data=df, x=df["binned"].astype(str), hue="dataset", multiple="dodge", shrink=.8)
            plt.setp(ax.get_xticklabels(), rotation=30)
            plt.title(f'{metric1}({metric_long})    lead_time={lead1}h')
            plt.xlabel('')
            plt.ylabel('Count')

            # save plot to png
            fig_dir = Path(data_paths['plots'],'histograms')
            fig_dir.mkdir(parents=True, exist_ok=True) 
            fig_file = str(fig_dir) + '/hist_' + metric1 +'_h' + str(lead1) +'.png'
            plt.savefig(fig_file)
    
    logger.info(f'Histograms created at: {fig_dir}')