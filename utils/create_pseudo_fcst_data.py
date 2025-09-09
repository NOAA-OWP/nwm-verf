from pathlib import Path

import pandas as pd
import yaml

# --- inputs ---
formulation = "noah_cfes"
data_dir = Path("/home/yuqiong.liu/repos/nwm-verf/data/inputs")
csv_file = Path(data_dir / "usgs_01123000/01123000.csv")
yaml_file = Path(data_dir / "nwm_forecast_configuration.yaml")
output_dir = Path(data_dir / f"usgs_01123000/{formulation}")
output_dir.mkdir(exist_ok=True)

# --- load data ---
df = pd.read_csv(csv_file, parse_dates=["Time"])
df["Time"] = pd.to_datetime(df["Time"])
df = df.sort_values("Time")  # required for merge_asof

# --- load yaml config ---
with open(yaml_file, "r") as f:
    configs = yaml.safe_load(f)

# --- loop over forecast configs ---
for name, config in configs.items():
    # normalize config (could be a list of lists or single list)
    if isinstance(config[0], list):
        config_list = config
    else:
        config_list = [config]

    for i, cfg in enumerate(config_list, start=1):
        cycle_start, cycle_end, cycle_freq, fcst_win, fcst_timestep = cfg

        # --- subset starting point ---
        start_time = (
            pd.Timestamp("2022-12-01 00:00:00")
            + pd.to_timedelta(cycle_start, unit="h")
            + pd.to_timedelta(fcst_timestep, unit="h")
        )

        # build target time index
        periods = int(fcst_win / fcst_timestep)  # + 1
        time_index = pd.date_range(
            start=start_time,
            periods=periods,
            freq=pd.to_timedelta(fcst_timestep, unit="h"),
        )

        # wrap into dataframe for merge_asof
        target_df = pd.DataFrame({"Time": time_index}).sort_values("Time")

        # nearest match join
        subset = pd.merge_asof(
            target_df,
            df,
            on="Time",
            direction="nearest",
            tolerance=pd.Timedelta("30min"),  # adjust tolerance as needed
        )

        # filename: handle multiple configs per key
        if len(config_list) > 1:
            out_name = f"{name}_{i}.csv"
        else:
            out_name = f"{name}.csv"

        subset.to_csv(output_dir / out_name, index=False)
        print(f"Wrote {out_name} with {len(subset)} rows")
