#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Pathing and Environment setup
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
LOCKFILE="$HOME/.garmin_daily_lock"
LOGFILE="$HOME/.config/garmin/sync.log"
TODAY=$(date "+%Y-%m-%d")
HOUR=$(date "+%H")
MIN=$(date "+%M")

# Path to config.yaml and scripts
SCRIPTS_DIR="$HOME/scripts"
CONFIG_FILE="$SCRIPTS_DIR/config.yaml"

# 1. Parse wake limits from config.yaml using PyYAML
WAKE_LIMITS=$(python3 -c "
import yaml, os
config_path = os.path.expanduser('$CONFIG_FILE')
try:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    auto = cfg.get('automation_settings', {})
    print(f\"{auto.get('wake_window_start_hour', 6)} {auto.get('wake_window_start_minute', 30)} {auto.get('wake_window_end_hour', 9)} {auto.get('wake_window_end_minute', 30)}\")
except Exception as e:
    # Print default wake window if config is missing or parsing fails
    print('6 30 9 30')
")

read -r START_H START_M END_H END_M <<< "$WAKE_LIMITS"

# 2. Convert times to minutes since midnight for boundary checks
CURR_MINS=$(( 10#$HOUR * 60 + 10#$MIN ))
START_MINS=$(( START_H * 60 + START_M ))
END_MINS=$(( END_H * 60 + END_M ))

# Only execute if current time is within the configured window
if [ "$CURR_MINS" -lt "$START_MINS" ] || [ "$CURR_MINS" -gt "$END_MINS" ]; then
    exit 0
fi

# Exit if training was already successfully planned today
if [ -f "$LOCKFILE" ] && [ "$(cat "$LOCKFILE")" = "$TODAY" ]; then
    exit 0
fi

# 3. Query sleep data state via Garmin Connect API
# If sleep has synced and ended, trigger the planning script
if python3 -c "
import sys, os, datetime
sys.path.append('$SCRIPTS_DIR')
from training_engine import load_config
from garminconnect import Garmin

try:
    config = load_config()
    client = Garmin(
        email=config['garmin_email'],
        password=None,
        prompt_mfa=None
    )
    client.login(os.path.expanduser('~/.garminconnect'))
    
    sleep = client.get_sleep_data(datetime.date.today().isoformat())
    # Verify sleep has concluded and is no longer actively logging (FINAL state)
    if sleep.get('dailySleepDTO', {}).get('sleepResultType') == 'FINAL':
        sys.exit(0)
except Exception as e:
    # Log background check failures (such as expired session tokens)
    with open(os.path.expanduser('$LOGFILE'), 'a') as f:
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        f.write(f'[{now}] Background sleep check failed: {str(e)}\n')
        if 'auth' in str(e).lower() or 'login' in str(e).lower():
            f.write(f'[{now}] TIP: Garmin session expired. Run: python3 ~/scripts/training_engine.py --interactive\\n')
sys.exit(1)
"; then
    # Run the physiological calculation and schedule today's workouts
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting dynamic workout planning calculation..." >> "$LOGFILE"
    if python3 "$SCRIPTS_DIR/training_engine.py" >> "$LOGFILE" 2>&1; then
        # Write lockfile to prevent multiple triggers
        echo "$TODAY" > "$LOCKFILE"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Training engine execution failed." >> "$LOGFILE"
    fi
fi
