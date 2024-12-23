from pathlib import Path
import colorcet as cc

# color maps for each metric for creating the spatial maps (in create_plots.py)
metric_colors=dict(
    KGE  = {'cmap': cc.rainbow[::-1], 'clim': (-0.5,1)},  
    NSE  = {'cmap': cc.rainbow[::-1], 'clim': (-0.5,1)},   
    CORR = {'cmap': cc.rainbow[::-1], 'clim': (-0.5,1)},     
    NNSE = {'cmap': cc.rainbow[::-1], 'clim': (0,1)}, 
)

# bins for each metric for creating the histograms (in create_plots.py)
metric_value_bins = {
    'KGE': [float('-inf'), -1,-0.5,0,0.2,0.4,0.6,0.8,1.0],
    'NSE': [float('-inf'), -1,-0.5,0,0.2,0.4,0.6,0.8,1.0],
    'NNSE': [0,0.2,0.4,0.5,0.6,0.7,0.8,1.0],
    'CORR': [-1,-0.5,0,0.2,0.4,0.6,0.8,1.0],
}

dict_teehr_metrics = {
    'n_obs': 'primary_count', 
    'n_mod': 'secondary_count',
    'min_obs': 'primary_minimum', 
    'min_mod': 'secondary_minimum', 
    'max_obs': 'primary_maximum',
    'max_mod': 'secondary_maximum', 
    'mean_obs': 'primary_average', 
    'mean_mod': 'secondary_average',
    'sum_obs': 'primary_sum', 
    'sum_mod': 'secondary_sum', 
    'var_obs': 'primary_variance',
    'var_mod': 'secondary_variance', 
    'max_delta': 'max_value_delta', 
    'NSE': 'nash_sutcliffe_efficiency',
    'NNSE': 'nash_sutcliffe_efficiency_normalized', 
    'KGE': 'kling_gupta_efficiency',
    'KGE1': 'kling_gupta_efficiency_mod1', 
    'KGE2': 'kling_gupta_efficiency_mod2',
    'ME': 'mean_error', 
    'MAE': 'mean_absolute_error', 
    'MSE': 'mean_squared_error',
    'RMSE': 'root_mean_squared_error',
    'pt_obs': 'primary_max_value_time',
    'pt_mod': 'secondary_max_value_time', 
    'pt_err': 'max_value_timedelta',
    'RBIAS': 'relative_bias',
    'MBAIS': 'multiplicative_bias', 
    'RMAE': 'mean_absolute_relative_error',
    'CORR': 'pearson_correlation',
    'sCORR': 'spearman_correlation',    
    'R2': 'r_squared', 
    'aprBIAS': 'annual_peak_relative_bias',
}

dict_ngen_eval_metrics = { 
    'CORR': 'pearson correlation',
    'NSE': 'nash_sutcliffe_efficiency',
    'NNSE': 'nash_sutcliffe_efficiency_normalized', 
    'NSElog': "logrithmic nash_sutcliffe_efficiency",
    'NSEwt': 'weighted NSE and NSElog',
    'KGE': 'kling_gupta_efficiency',
    'MAE': 'mean_absolute_error', 
    'RMSE': 'root_mean_squared_error',
    'PBIAS': 'percent_bias',
    'RSR': 'RMSE_observation_std_ratio',
    'HSEG_FDC': 'pbias_high_flow_FDC',
    'MSEG_FDC': 'pbias_medium_flow_FDC',
    'LSEG_FDC': 'pbias_low_flow_FDC',
    'POD': 'probability_of_detection',
    'FAR': 'false_alarm_ratio',
    'CSI': 'critical_success_index',
    'FBIAS': 'frequency_bias',
    'PKBIAS': 'percent_peak_flow_bias',
    'PKTE': 'peak_timing_error',
    'EVBIAS': 'event_volume_bias',
}


def data_paths(conf:dict) -> dict:

    conf1 = conf['general']
    conf2 = conf['file_paths']
    root_dir = conf2['data_dir_root']
    sub_dir = conf1['location_set_name']
    config = conf1['nwm_configuration']

    # paths for all observations
    obs_dir = Path(root_dir, sub_dir, 'usgs')
    obs_dir.mkdir(parents=True, exist_ok=True) 

    # paths for forecast datasets
    fcst_data_dir = dict()
    fcst_json_dir = dict()
    fcst_data_link_dir = dict()
    paired_data_file = dict()
    metric_file = dict()
    for dataset in conf1['dataset_name']:

        # dataset index
        idx = conf1['dataset_name'].index(dataset)

        # create output directories based on NWM version
        fcst_json_dir[dataset] = Path(root_dir, sub_dir, conf1['nwm_version'][idx], 'zarr', config)
        fcst_data_dir[dataset] = Path(root_dir, sub_dir, conf1['nwm_version'][idx], 'timeseries', config)

        # create additional directory for storing symbolic links to parquet files required for each dataset
        fcst_data_link_dir[dataset] = Path(root_dir, sub_dir, conf1['dataset_name'][idx],'fcst')                 
   
        # path for joined parquet files
        paired_data_file[dataset] = Path(root_dir, sub_dir, 'joined', dataset + '.joined.parquet')

        # path for metric output files
        metric_file[dataset] = Path(root_dir, sub_dir, 'metrics', dataset + '.metrics.parquet')

    # paths for plots
    plot_dir = Path(root_dir, sub_dir, 'plots')

    # path for crosswalk file
    cwt_file = Path(conf2['crosswalk_file']).resolve(strict=True)

    # path for geometry file
    geo_file = Path(conf2['geometry_file']).resolve(strict=True)

    # assemble all paths into a dictionary
    data_paths = {'fcst': fcst_data_dir, 
                  'fcst_json':fcst_json_dir, 
                  'fcst_link':fcst_data_link_dir,
                  'obs': obs_dir, 
                  'joined': paired_data_file,
                  'metrics': metric_file,
                  'plots': plot_dir,
                  'crosswalk': cwt_file,
                  'geofile': geo_file,
                  }

    return data_paths