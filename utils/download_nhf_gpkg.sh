#!/bin/bash  
# This script is used to download the NHF GPKG files for different VPUs.
set -e

id_type="vpu_id" # use "gage_id" for gage-based GPKG files
version="v1" # specify the version of the NHF GPKG files to download
api="test" # test or oe

domain=("CONUS" "Hawaii" "Alaska" "Puerto_Rico")

for domain in "${domain[@]}"; do
    if [[ "$domain" == "CONUS" ]]; then
        vpus=('01' '02' '03N' '03S' '03W' '04' '05' '06' '07' '08' '09' '10L' '10U' '11' '12' '13' '14' '15' '16' '17' '18')
    elif [[ "$domain" == "Hawaii" ]]; then
        vpus=('20')
    elif [[ "$domain" == "Alaska" ]]; then
        vpus=('19')
    elif [[ "$domain" == "Puerto_Rico" ]]; then
        vpus=('21')
    else
        echo "Unknown domain: ${domain}"
        exit 1
    fi

    for vpu in "${vpus[@]}"; do
        # skip if file already exists
        dest_file="$HOME/data/hydrofabric/gpkg_nhf/vpu_${vpu}.gpkg"
        if [[ -f "$dest_file" ]]; then
            echo "File for VPU $vpu already exists, skipping download."
            continue
        fi

        echo "Downloading GPKG for VPU $vpu..."
        url="http://edfs.${api}.nextgenwaterprediction.com/api/${version}/hydrofabric/${vpu}/gpkg?id_type=${id_type}&source=nhf&domain=${domain}"
        dest_file="$HOME/data/hydrofabric/gpkg_nhf/vpu_${vpu}.gpkg"
        mkdir -p "$(dirname "$dest_file")"
        curl -L -o "$dest_file" "$url"
    done

done
