# nwm-verf

## Name
NWM/NextGen Verification (nwm.verf)

## Description
A python library for conducting verification for NWM/NextGen forecasts

### Clone & Build nwm.verf

1. clone nwm-verf

```bash
cd [NWM_VERF_ROOT]
git clone -b development --recurse-submodules https://github.com/NGWPC/nwm-verf.git
```

2. clone nwm.eval (since nwm.verf requires nwm.eval as a dependency)

```bash
cd [NWM_EVAL_ROOT]
git clone -b development --recurse-submodules https://github.com/NGWPC/nwm-eval-mgr.git
```

3. create python venv

```bash
cd [VENV_ROOT]
/usr/bin/python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```
4. install nwm.eval

```bash
cd [NWM_EVAL_ROOT]/nwm-eval-mgr
pip install .
```

5. install nwm.verf

```bash
cd [NWM_VERF_ROOT]/nwm-verf
pip install .
```
where [NWM_EVAL_ROOT], [NWM_VERF_ROOT], [VENV_ROOT] refer to the directory to install nwm.eval, nwm.verf, and python venv in your local workspace, respectively


### Usage

1) set up configuration yaml file

Follow the sample config file (nwm-verf/data/configs) to set up the configurations for your verification application.
- For verifyinf ngeCERF forecasts, use: config_ngencerf.yaml 
- For verifying NWM v30 forecasts, use: config_nwm.yaml

1) run the verification script

```bash
python -m nwm.verf config.yaml
```

3) repeat the first two steps as many times as needed


## Docker container

### Requirements

To build and run nwm-verf, you will need the following software installed and running on your system:
- Docker Engine

You will also need the following data:
- a GitLab Personal Access Token (PAT)

### Build

To build the nwm-verf container, execute the following command:
```
GITLAB_TOKEN=$(cat ~/.gitlab_token) docker build --secret id=GITLAB_TOKEN,env=GITLAB_TOKEN --tag=nwm-verf .
```

### Running

To run the nwm-verf applicaton, execute the following command:
```
docker run nwm-verf
```

This will print a usage statement for the container:
```
Usage: run-nwm-verf.sh <command> <config_file> [stdout_file]


COMMAND:
  verification          Run verification script.

CONFIG_FILE: Path to the config yaml file for a verification run.
STDOUT_FILE (optional): Path to the stdout file where the script's console output will be saved.

Examples:
  run-nwm-verf.sh verification test_data/verf_config.yaml
  run-nwm-verf.sh verification test_data/verf_config.yaml /path/to/output/nwm-verf.log
```

The path provided for any files should match the path within the container, as well as the paths inside your configuration file.
