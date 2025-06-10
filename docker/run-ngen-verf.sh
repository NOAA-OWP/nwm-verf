#!/bin/bash
# Define valid commands
VALID_COMMANDS=("verification")

# This shell script lives in the ngen-verf repo.  It is used by CerfServer when calling ngen-verf
#
# It is used by CerfServer directly when running in LOCAL mode.
# It is used by the ngen-verf docker container when the server is running in DOCKER or PARALLEL_WORKS mode

SCRIPT_TO_RUN=/ngen-app/ngen-verf/verification.py

# Set the umask so files and directories are created with 777 permissions
umask 000

# Function to display help message
show_help() {
  echo "Usage: $(basename "$0") <command> <config_file> [stdout_file]"
  echo ""
  echo ""
  echo "COMMAND:"
  echo "  verification          Run verification script."
  echo ""
  echo "CONFIG_FILE: Path to the config yaml file for a verification run."
  echo "STDOUT_FILE (optional): Path to the stdout file where the script's console output will be saved."
  echo ""
  echo "Examples:"
  echo "  $(basename "$0") verification test_data/verf_config.yaml"
  echo "  $(basename "$0") verification test_data/verf_config.yaml /path/to/output/ngen-verf.log"
  echo ""
  exit 1
}

# Show help if the user requests it with --help or -h
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
  show_help
fi

# Check if the command for the script is provided as the first argument
if [ -z "$1" ]; then
  echo "Error: No script command provided. Allowable commands are: ${VALID_COMMANDS[*]}."
  show_help
fi

# Get the script command and select the corresponding script path
SCRIPT_COMMAND=$1
shift 1

case "$SCRIPT_COMMAND" in
  "verification")
    SCRIPT_PATH=$SCRIPT_TO_RUN
    REQUIRED_ARGS=1
    ;;
  *)
    echo "Error: Invalid script command: '$SCRIPT_COMMAND'. Allowable commands are: ${VALID_COMMANDS[*]}."
    show_help
    ;;
esac

# Check if the selected script exists
if [ ! -f "$SCRIPT_PATH" ]; then
  echo "Error: Script not found at $SCRIPT_PATH"
  exit 1
fi

# Check if the correct number of arguments are provided for the selected command
if [ $# -lt $REQUIRED_ARGS ]; then
  echo "Error: Insufficient arguments. $SCRIPT_COMMAND requires $REQUIRED_ARGS arguments."
  show_help
fi

CONFIG_FILE=$1
shift $REQUIRED_ARGS

echo "CONFIG_FILE: ${CONFIG_FILE}"

# Check if the configuration file exists
if [ ! -f "${CONFIG_FILE}" ]; then
  echo "Configuration file not found at ${CONFIG_FILE}"
fi

if [ $# -ge 1 ]; then
  STDOUT_FILE=$1
  echo "Output file: $STDOUT_FILE"

  # Create output directory if it doesn't exist
  STDOUT_DIR=$(dirname "$STDOUT_FILE")
  if [ ! -d "$STDOUT_DIR" ]; then
    mkdir --parents "$STDOUT_DIR"
  fi

  shift 1
fi

# patch teehr (point_utils.py) prior to running the verification script
TARGET_FILE=$(find ${VIRTUAL_ENV} -type f -name "*.py" | grep 'point_utils.py')
if [[ -f "$TARGET_FILE" ]]; then
  if grep -q 'feature_ids = ds\.feature_id\.astype("int32")\.values' "$TARGET_FILE"; then
    sed -i 's/feature_ids = ds\.feature_id\.astype("int32")\.values/feature_ids = ds.feature_id.values/' "$TARGET_FILE"
    echo "Patched $TARGET_FILE"
  fi
else
  echo "Target file ${TARGET_FILE} not found! Please check the venv path."
fi

# Run the Python script, redirecting its output if an output file is provided
echo "   Running $(basename "$SCRIPT_PATH") with input file: $CONFIG_FILE"
if [ -z "$STDOUT_FILE" ]; then
  python "${SCRIPT_PATH}" "${CONFIG_FILE}"
else
  python "${SCRIPT_PATH}" "${CONFIG_FILE}" &> "${STDOUT_FILE}"
fi

python_exit_code=$?
if [ $python_exit_code -ne 0 ]; then
  echo "$(basename "$SCRIPT_PATH") exited with code $python_exit_code"
fi

# Display output if redirected to a file
if [ -n "$STDOUT_FILE" ]; then
  echo "Output from running $(basename "$SCRIPT_PATH")"
  echo "-------------- start of $STDOUT_FILE -----------------------------"
  cat "$STDOUT_FILE"
  echo "---------------- end of $STDOUT_FILE -----------------------------"
fi

echo "Done running $(basename "$SCRIPT_PATH")"

exit $python_exit_code
