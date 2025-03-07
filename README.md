# ngen-verf

## Name
ngen Verification (ngen.verf)

## Description
A python library for conducting verification for NWM forecasts

### Clone & Build ngen.verf

1. clone ngen-verf from Gitlab

```bash
cd [NGEN_VERF_ROOT]
git clone -b development --recurse-submodules https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/ngen-verf.git
```

2. clone ngen-eval from Gitlab (since ngen.verf requires ngen.eval as a dependency)

```bash
cd [NGEN_EVAL_ROOT]
git clone -b development --recurse-submodules https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/ngen-eval.git
```

3. create python venv

```bash
cd [VENV_ROOT]
/usr/bin/python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```
4. install ngen.eval

```bash
cd [NGEN_EVAL_ROOT]/ngen-eval
pip install .
```

5. install ngen.verf

```bash
cd [NGEN_VERF_ROOT]/ngen-verf
pip install .
```
where [NGEN_EVAL_ROOT], [NGEN_VERF_ROOT], [VENV_ROOT] refer to the directory to install ngen-eval, ngen-verf, and python venv in your local workspace, respectively


### Usage

1) set up configuration yaml file (e.g., config.yaml)

Follow the sample config file (ngen-verf/sample_files/config.yaml) and the detailed comments therein to set up the configurations for your verification application as needed.

2) run the verification script

```bash
python [NGEN_VERF_ROOT]/ngen-verf/verification.py config.yaml
```

3) repeat the first two steps as many times as needed


## Docker container

### Requirements

To build and run ngen-fcst, you will need the following software installed and running on your system:
- Docker Engine

You will also need the following data:
- a GitLab Personal Access Token (PAT)

### Build

To build the ngen-verf container, execute the following command:
```
GITLAB_TOKEN=$(cat ~/.gitlab_token) docker build --secret id=GITLAB_TOKEN,env=GITLAB_TOKEN --tag=ngen-verf .
```

### Running

To run the ngen-verf applicaton, execute the following command:
```
docker run ngen-verf
```

This will print a usage statement for the container:
```
Usage: run-ngen-verf.sh <command> <config_file> [stdout_file]


COMMAND:
  verification          Run verification script.

CONFIG_FILE: Path to the config yaml file for a verification run.
STDOUT_FILE (optional): Path to the stdout file where the script's console output will be saved.

Examples:
  run-ngen-verf.sh verification test_data/verf_config.yaml
  run-ngen-verf.sh verification test_data/verf_config.yaml /path/to/output/ngen-verf.log
```

The path provided for any files should match the path within the container, as well as the paths inside your configuration file.
