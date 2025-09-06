import subprocess
from pathlib import Path

import yaml

from nwm.verf.configuration import Config
from nwm.verf.utils import save_data

# Paths
data_dir = Path("/home/yuqiong.liu/repos/nwm-verf/data/inputs")
fcst_def_file = Path(
    data_dir / "nwm_forecast_configuration.yaml"
)  # YAML with forecast configs
base_config_file = Path("../config_fs.yaml")  # the template config
tmp_config_file = Path("config_tmp.yaml")  # temporary file to run with

# Load forecast configurations
with open(fcst_def_file, "r") as f:
    forecast_configs = yaml.safe_load(f)

# Iterate through each configuration
for fcst_name in forecast_configs.keys():
    print(
        f"\n------------------  Running forecast configuration: {fcst_name} ------------------"
    )

    # Load base config
    with open(base_config_file, "r") as f:
        data = yaml.safe_load(f)
        config = Config(**data)

    # Replace nwm_configuration
    config.general.nwm_configuration = fcst_name

    # replace fcst_data_file (for hawaii)
    f1 = Path(config.file_paths.fcst_data_file)

    if isinstance(forecast_configs[fcst_name][0], list):
        files = [
            f1.parent / f"{f1.stem}_{i}{f1.suffix}"
            for i in range(1, len(forecast_configs[fcst_name]) + 1)
        ]

    else:
        files = [f1]

    for f1 in files:
        config.file_paths.fcst_data_file = str(f1)

        # Write out temporary config file
        save_data(config, tmp_config_file)

        # Run your tool
        try:
            subprocess.run(
                ["python", "-m", "nwm.verf", str(tmp_config_file)], check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error running configuration {fcst_name}: {e}")
