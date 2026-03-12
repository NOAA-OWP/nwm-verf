#!/bin/bash  
# This script is used to download the NHF GPKG files for different VPUs.
set -e

id_type="vpu_id" # use "gage_id" for gage-based GPKG files
version="v1" # specify the version of the NHF GPKG files to download

# conus vpus
vpus=('01' '02' '03N' '03S' '03W' '04' '05' '06' '07' '08' '09' '10L' '10U' '11' '12' '13' '14' '15' '16' '17' '18')

dest_dir="$HOME/data/hydrofabric/gpkg_nhf/"
mkdir -p "$dest_dir"


for vpu in "${vpus[@]}"; do
    # skip if file already exists
    dest_file="${dest_dir}vpu_${vpu}.gpkg"
    if [[ -f "$dest_file" ]]; then
        echo "File for VPU $vpu already exists, skipping download."
        continue
    fi

    echo "Downloading GPKG for VPU $vpu..."
    url="https://edfs.oe.nextgenwaterprediction.com/api/${version}/hydrofabric/$vpu/gpkg?id_type=${id_type}"
    curl -fL --progress-bar -o "$dest_file" "$url"
done