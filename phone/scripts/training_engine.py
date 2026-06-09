import os
import yaml
import math
import datetime
import sys
from garminconnect import Garmin

# Load config files
def load_config():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config.yaml")
    secrets_path = os.path.join(os.path.expanduser("~"), ".config", "garmin", "secrets.yaml")
    
    # Fallback to local secrets.yaml if home dir secrets don't exist
    if not os.path.exists(secrets_path):
        secrets_path = os.path.join(base_dir, "secrets.yaml")
        
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
        
    if os.path.exists(secrets_path):
        with open(secrets_path, "r") as f:
            secrets = yaml.safe_load(f)
            config.update(secrets)
            
    return config

# Jack Daniels VDOT pacing calculations
def calculate_vdot_paces(distance_m, time_sec):
    t_min = time_sec / 60.0
    velocity = distance_m / t_min
    
    # Daniels VDOT Formulas
    vo2 = -4.60 + 0.182258 * velocity + 0.000104 * (velocity ** 2)
    percent_vo2max = 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)
    vdot = vo2 / percent_vo2max
    
    def pace_from_intensity(intensity):
        vo2_target = vdot * intensity
        # Quadratic formula to find velocity: 0.000104*v^2 + 0.182258*v - (4.60 + vo2_target) = 0
        a, b, c = 0.000104, 0.182258, -(4.60 + vo2_target)
        v = (-b + math.sqrt(b**2 - 4 * a * c)) / (2 * a)
        pace_sec_km = 60000.0 / v
        return pace_sec_km

    # Standard intensities: Easy (62%), Marathon (80%), Threshold (86%), Interval (98%)
    return {
        "vdot": vdot,
        "easy": pace_from_intensity(0.62),
        "marathon": pace_from_intensity(0.80),
        "threshold": pace_from_intensity(0.86),
        "interval": pace_from_intensity(0.98)
    }

# Format pace seconds to MM:SS
def format_pace(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}/km"

# Retrieve activity training load
def get_activity_load(activity, resting_hr, max_hr):
    if "trainingLoad" in activity and activity["trainingLoad"] is not None:
        return float(activity["trainingLoad"])
    
    # Fallback 1: aerobicTrainingEffect
    aerobic_te = activity.get("aerobicTrainingEffect")
    if aerobic_te is not None and aerobic_te > 0:
        return float((aerobic_te ** 2) * 10)
    
    # Fallback 2: TRIMP approximation
    duration = activity.get("duration", 0)  # seconds
    avg_hr = activity.get("averageHR") or activity.get("averageHeartRateInBeatsPerMinute")
    if duration > 0 and avg_hr is not None:
        duration_mins = duration / 60.0
        intensity = (avg_hr - resting_hr) / (max_hr - resting_hr) if max_hr > resting_hr else 0.5
        intensity = max(0.0, min(1.0, intensity))
        return duration_mins * intensity * 10.0
    
    # Fallback 3: generic duration-based load (5 points per minute)
    return (activity.get("duration", 0) / 60.0) * 5.0

# ACWR workload engine
def calculate_acwr(activities, resting_hr, max_hr):
    today = datetime.date.today()
    daily_loads = { (today - datetime.timedelta(days=i)).isoformat(): 0.0 for i in range(28) }
    
    for activity in activities:
        start_time_str = activity.get("startTimeLocal")
        if start_time_str:
            act_date = start_time_str.split(" ")[0]
            if act_date in daily_loads:
                daily_loads[act_date] += get_activity_load(activity, resting_hr, max_hr)
                
    acute_sum = sum(daily_loads[(today - datetime.timedelta(days=i)).isoformat()] for i in range(7))
    chronic_sum = sum(daily_loads[(today - datetime.timedelta(days=i)).isoformat()] for i in range(28))
    
    acute_avg = acute_sum / 7.0
    chronic_avg = chronic_sum / 28.0
    
    acwr = acute_avg / chronic_avg if chronic_avg > 0 else (1.0 if acute_avg > 0 else 0.0)
    
    # Previous week volume (days 7 to 13) vs current week volume (days 0 to 6)
    current_week_volume = sum(daily_loads[(today - datetime.timedelta(days=i)).isoformat()] for i in range(7))
    prev_week_volume = sum(daily_loads[(today - datetime.timedelta(days=i)).isoformat()] for i in range(7, 14))
    
    return acwr, current_week_volume, prev_week_volume

# Periodic phase logic
def determine_training_phase(config):
    goal = config["training_goal"]
    target_event = goal.get("target_event", "improving_fitness")
    
    if target_event not in ["half_marathon"]:
        return target_event.capitalize()
        
    target_dt = datetime.date.fromisoformat(goal["target_date"])
    days_left = (target_dt - datetime.date.today()).days
    
    params = config["periodization_parameters"]
    taper_days = params.get("taper_phase_weeks", 1) * 7
    peak_days = params.get("peak_phase_weeks", 2) * 7
    build_days = params.get("build_phase_weeks", 5) * 7
    base_days = params.get("base_phase_weeks", 4) * 7
    
    if days_left < 0:
        return "Recovery/Post-Event"
    elif days_left < taper_days:
        return "Taper"
    elif days_left < taper_days + peak_days:
        return "Peak"
    elif days_left < taper_days + peak_days + build_days:
        return "Build"
    elif days_left < taper_days + peak_days + build_days + base_days:
        return "Base"
    else:
        return "Base (Pre-Plan)"

# Choose workout archetype
def plan_workout(phase, trs, acwr, current_vol, prev_vol, config, paces):
    goal = config["training_goal"]
    weekday = datetime.date.today().weekday()
    is_weekend = weekday >= 5
    
    resting_hr = config["user_profile"]["resting_hr"]
    max_hr = config["user_profile"]["max_hr"]
    hr_reserve = max_hr - resting_hr
    
    # Default parameters
    intensity_anchor = goal.get("intensity_anchor", "heart_rate")
    weekday_limit = goal.get("weekday_soft_limit_mins", 60)
    weekend_limit = goal.get("weekend_soft_limit_mins", 120)
    max_duration = weekend_limit if is_weekend else weekday_limit
    
    # Overload limits (Base phase progressive overload: 10%)
    if phase == "Base" and prev_vol > 0 and current_vol >= 1.10 * prev_vol:
        # Prevent progression overload by restricting to short base or recovery
        trs = min(trs, 60)
        
    # Selection logic based on ACWR risk
    if acwr > 1.5:
        # Critical Zone
        name = "Rest Day"
        details = "Workload ratio is critically high (ACWR > 1.5). Mandatory complete rest to avoid injury."
        return {"name": name, "details": details, "steps": [], "is_specific": False}
    elif acwr > 1.3:
        # Danger Zone: restrict to Recovery
        name = "Recovery Walk/Run"
        duration = 20
        is_specific = False
        target_hr_min = int(resting_hr + 0.50 * hr_reserve)
        target_hr_max = int(resting_hr + 0.60 * hr_reserve)
        steps = [
            {"type": "warmup", "duration_mins": 5, "hr_min": target_hr_min, "hr_max": target_hr_max, "pace": paces["easy"] * 1.2},
            {"type": "interval", "duration_mins": 10, "hr_min": target_hr_min, "hr_max": target_hr_max, "pace": paces["easy"] * 1.1},
            {"type": "cooldown", "duration_mins": 5, "hr_min": target_hr_min, "hr_max": target_hr_max, "pace": paces["easy"] * 1.2}
        ]
        details = f"Active Recovery (ACWR: {acwr:.2f}). Keep heart rate low."
    else:
        # Sweet Spot / Safe Zone
        if phase in ["Base", "Base (Pre-Plan)"]:
            # Volume building
            if is_weekend and trs >= 70:
                name = "Long Run"
                duration = min(90, max_duration)
                is_specific = False
                target_hr_min = int(resting_hr + 0.60 * hr_reserve)
                target_hr_max = int(resting_hr + 0.72 * hr_reserve)
                steps = [
                    {"type": "warmup", "duration_mins": 10, "hr_min": target_hr_min - 5, "hr_max": target_hr_min, "pace": paces["easy"] * 1.1},
                    {"type": "interval", "duration_mins": duration - 20, "hr_min": target_hr_min, "hr_max": target_hr_max, "pace": paces["easy"]},
                    {"type": "cooldown", "duration_mins": 10, "hr_min": target_hr_min - 5, "hr_max": target_hr_min, "pace": paces["easy"] * 1.1}
                ]
                details = "Aerobic volume building. Long continuous run."
            elif trs >= 65:
                name = "Easy Base Run"
                duration = min(45, max_duration)
                is_specific = False
                target_hr_min = int(resting_hr + 0.60 * hr_reserve)
                target_hr_max = int(resting_hr + 0.70 * hr_reserve)
                steps = [
                    {"type": "warmup", "duration_mins": 5, "hr_min": target_hr_min - 5, "hr_max": target_hr_min, "pace": paces["easy"] * 1.1},
                    {"type": "interval", "duration_mins": duration - 10, "hr_min": target_hr_min, "hr_max": target_hr_max, "pace": paces["easy"]},
                    {"type": "cooldown", "duration_mins": 5, "hr_min": target_hr_min - 5, "hr_max": target_hr_min, "pace": paces["easy"] * 1.1}
                ]
                details = "Standard aerobic base building run."
            else:
                name = "Recovery Run"
                duration = 25
                is_specific = False
                target_hr_min = int(resting_hr + 0.50 * hr_reserve)
                target_hr_max = int(resting_hr + 0.60 * hr_reserve)
                steps = [
                    {"type": "warmup", "duration_mins": 5, "hr_min": target_hr_min, "hr_max": target_hr_min + 5, "pace": paces["easy"] * 1.2},
                    {"type": "interval", "duration_mins": 15, "hr_min": target_hr_min, "hr_max": target_hr_max, "pace": paces["easy"] * 1.15},
                    {"type": "cooldown", "duration_mins": 5, "hr_min": target_hr_min, "hr_max": target_hr_min + 5, "pace": paces["easy"] * 1.2}
                ]
                details = "Easy recovery run to shed fatigue."
                
        elif phase in ["Build", "Improving_fitness"]:
            # Cardiorespiratory development
            if trs >= 73:
                # High-intensity Intervals (Zone 5)
                name = "Dynamic VO2 Max Intervals"
                is_specific = True
                steps = [
                    {"type": "warmup", "duration_mins": 10, "hr_min": int(resting_hr + 0.60 * hr_reserve), "hr_max": int(resting_hr + 0.70 * hr_reserve), "pace": paces["easy"]},
                    {"type": "interval", "duration_mins": 4, "hr_min": int(resting_hr + 0.90 * hr_reserve), "hr_max": int(resting_hr + 0.98 * hr_reserve), "pace": paces["interval"]},
                    {"type": "recovery", "duration_mins": 3, "hr_min": int(resting_hr + 0.50 * hr_reserve), "hr_max": int(resting_hr + 0.60 * hr_reserve), "pace": paces["easy"] * 1.3},
                    {"type": "interval", "duration_mins": 4, "hr_min": int(resting_hr + 0.90 * hr_reserve), "hr_max": int(resting_hr + 0.98 * hr_reserve), "pace": paces["interval"]},
                    {"type": "recovery", "duration_mins": 3, "hr_min": int(resting_hr + 0.50 * hr_reserve), "hr_max": int(resting_hr + 0.60 * hr_reserve), "pace": paces["easy"] * 1.3},
                    {"type": "interval", "duration_mins": 4, "hr_min": int(resting_hr + 0.90 * hr_reserve), "hr_max": int(resting_hr + 0.98 * hr_reserve), "pace": paces["interval"]},
                    {"type": "recovery", "duration_mins": 3, "hr_min": int(resting_hr + 0.50 * hr_reserve), "hr_max": int(resting_hr + 0.60 * hr_reserve), "pace": paces["easy"] * 1.3},
                    {"type": "interval", "duration_mins": 4, "hr_min": int(resting_hr + 0.90 * hr_reserve), "hr_max": int(resting_hr + 0.98 * hr_reserve), "pace": paces["interval"]},
                    {"type": "cooldown", "duration_mins": 10, "hr_min": int(resting_hr + 0.55 * hr_reserve), "hr_max": int(resting_hr + 0.65 * hr_reserve), "pace": paces["easy"]}
                ]
                details = "VO2 Max development. 4x4 mins hard intervals."
            elif trs >= 65:
                # Lactate Threshold (Zone 4)
                name = "Lactate Threshold Tempo"
                is_specific = True
                tempo_dur = min(20, max_duration - 20)
                steps = [
                    {"type": "warmup", "duration_mins": 10, "hr_min": int(resting_hr + 0.60 * hr_reserve), "hr_max": int(resting_hr + 0.70 * hr_reserve), "pace": paces["easy"]},
                    {"type": "interval", "duration_mins": tempo_dur, "hr_min": int(resting_hr + 0.82 * hr_reserve), "hr_max": int(resting_hr + 0.88 * hr_reserve), "pace": paces["threshold"]},
                    {"type": "cooldown", "duration_mins": 10, "hr_min": int(resting_hr + 0.55 * hr_reserve), "hr_max": int(resting_hr + 0.65 * hr_reserve), "pace": paces["easy"]}
                ]
                details = f"Lactate threshold improvement. {tempo_dur} mins steady tempo."
            else:
                name = "Recovery Run"
                duration = 20
                is_specific = False
                target_hr_min = int(resting_hr + 0.50 * hr_reserve)
                target_hr_max = int(resting_hr + 0.60 * hr_reserve)
                steps = [
                    {"type": "warmup", "duration_mins": 5, "hr_min": target_hr_min, "hr_max": target_hr_min + 5, "pace": paces["easy"] * 1.2},
                    {"type": "interval", "duration_mins": 10, "hr_min": target_hr_min, "hr_max": target_hr_max, "pace": paces["easy"] * 1.15},
                    {"type": "cooldown", "duration_mins": 5, "hr_min": target_hr_min, "hr_max": target_hr_min + 5, "pace": paces["easy"] * 1.2}
                ]
                details = "Build phase recovery session."
                
        elif phase == "Peak":
            # Sustained blocks at target event race pace (Zone 3/4)
            if trs >= 70:
                name = "Race Pace Tempo"
                is_specific = True
                steps = [
                    {"type": "warmup", "duration_mins": 10, "hr_min": int(resting_hr + 0.60 * hr_reserve), "hr_max": int(resting_hr + 0.70 * hr_reserve), "pace": paces["easy"]},
                    {"type": "interval", "duration_mins": 15, "hr_min": int(resting_hr + 0.75 * hr_reserve), "hr_max": int(resting_hr + 0.82 * hr_reserve), "pace": paces["marathon"]},
                    {"type": "recovery", "duration_mins": 5, "hr_min": int(resting_hr + 0.50 * hr_reserve), "hr_max": int(resting_hr + 0.60 * hr_reserve), "pace": paces["easy"] * 1.2},
                    {"type": "interval", "duration_mins": 15, "hr_min": int(resting_hr + 0.75 * hr_reserve), "hr_max": int(resting_hr + 0.82 * hr_reserve), "pace": paces["marathon"]},
                    {"type": "cooldown", "duration_mins": 10, "hr_min": int(resting_hr + 0.55 * hr_reserve), "hr_max": int(resting_hr + 0.65 * hr_reserve), "pace": paces["easy"]}
                ]
                details = "Peak specificity workout. 2x15 mins at marathon race pace."
            else:
                name = "Easy Base Run"
                duration = 35
                is_specific = False
                target_hr_min = int(resting_hr + 0.60 * hr_reserve)
                target_hr_max = int(resting_hr + 0.70 * hr_reserve)
                steps = [
                    {"type": "warmup", "duration_mins": 5, "hr_min": target_hr_min - 5, "hr_max": target_hr_min, "pace": paces["easy"] * 1.1},
                    {"type": "interval", "duration_mins": 25, "hr_min": target_hr_min, "hr_max": target_hr_max, "pace": paces["easy"]},
                    {"type": "cooldown", "duration_mins": 5, "hr_min": target_hr_min - 5, "hr_max": target_hr_min, "pace": paces["easy"] * 1.1}
                ]
                details = "Standard easy run in peak phase."
                
        else: # Taper Phase
            # Decay volume exponentially but maintain intensity
            # Taper day d calculation
            target_dt = datetime.date.fromisoformat(goal["target_date"])
            days_left = (target_dt - datetime.date.today()).days
            taper_day = max(0, 7 - days_left)
            decay_factor = math.exp(-0.05 * taper_day)
            
            if trs >= 72:
                name = "Taper Speed Intervals"
                is_specific = True
                steps = [
                    {"type": "warmup", "duration_mins": 8, "hr_min": int(resting_hr + 0.60 * hr_reserve), "hr_max": int(resting_hr + 0.70 * hr_reserve), "pace": paces["easy"]},
                    {"type": "interval", "duration_mins": 2, "hr_min": int(resting_hr + 0.90 * hr_reserve), "hr_max": int(resting_hr + 0.98 * hr_reserve), "pace": paces["interval"]},
                    {"type": "recovery", "duration_mins": 2, "hr_min": int(resting_hr + 0.50 * hr_reserve), "hr_max": int(resting_hr + 0.60 * hr_reserve), "pace": paces["easy"] * 1.3},
                    {"type": "interval", "duration_mins": 2, "hr_min": int(resting_hr + 0.90 * hr_reserve), "hr_max": int(resting_hr + 0.98 * hr_reserve), "pace": paces["interval"]},
                    {"type": "recovery", "duration_mins": 2, "hr_min": int(resting_hr + 0.50 * hr_reserve), "hr_max": int(resting_hr + 0.60 * hr_reserve), "pace": paces["easy"] * 1.3},
                    {"type": "interval", "duration_mins": 2, "hr_min": int(resting_hr + 0.90 * hr_reserve), "hr_max": int(resting_hr + 0.98 * hr_reserve), "pace": paces["interval"]},
                    {"type": "cooldown", "duration_mins": 8, "hr_min": int(resting_hr + 0.55 * hr_reserve), "hr_max": int(resting_hr + 0.65 * hr_reserve), "pace": paces["easy"]}
                ]
                details = f"Taper speed intervals. Volume scaled down ({int(decay_factor * 100)}%)."
            else:
                name = "Easy Taper Run"
                duration = int(30 * decay_factor)
                duration = max(15, duration)
                is_specific = False
                target_hr_min = int(resting_hr + 0.60 * hr_reserve)
                target_hr_max = int(resting_hr + 0.70 * hr_reserve)
                steps = [
                    {"type": "warmup", "duration_mins": 5, "hr_min": target_hr_min - 5, "hr_max": target_hr_min, "pace": paces["easy"] * 1.1},
                    {"type": "interval", "duration_mins": duration - 10, "hr_min": target_hr_min, "hr_max": target_hr_max, "pace": paces["easy"]},
                    {"type": "cooldown", "duration_mins": 5, "hr_min": target_hr_min - 5, "hr_max": target_hr_min, "pace": paces["easy"] * 1.1}
                ]
                details = f"Easy taper run. Reduced volume ({duration} mins)."

    # BRISK WALK CONVERSION CHECK
    # Convert easy base or recovery runs that are too short/short-duration into Brisk Walks.
    # High-intensity workouts (is_specific = True) like VO2 Max or tempo run are exempt.
    if not is_specific and name != "Rest Day":
        total_duration_mins = sum(s["duration_mins"] for s in steps)
        # Approximate distance in km: (total duration mins / 60) * (1000m / target pace in secs) * 60
        # Simplification: (total duration in mins) * 60 / easy pace in seconds
        avg_pace_secs = paces["easy"]
        est_distance_km = (total_duration_mins * 60.0) / avg_pace_secs
        
        min_len = goal.get("minimum_run_length_km", 2.0)
        min_dur = goal.get("minimum_run_duration_mins")
        
        should_convert = False
        reasons = []
        if est_distance_km < min_len:
            should_convert = True
            reasons.append(f"distance ({est_distance_km:.2f} km < {min_len} km)")
        if min_dur is not None and total_duration_mins < min_dur:
            should_convert = True
            reasons.append(f"duration ({total_duration_mins} mins < {min_dur} mins)")
            
        if should_convert:
            name = f"Brisk Walk ({name})"
            details = f"Converted run to a Brisk Walk due to {', '.join(reasons)}. No running gear required."
            # Convert targets to walking targets (slower paces and lower heart rate zones)
            for s in steps:
                s["hr_min"] = int(resting_hr + 0.30 * hr_reserve)
                s["hr_max"] = int(resting_hr + 0.50 * hr_reserve)
                s["pace"] = paces["easy"] * 1.6 # much slower pace
                
    return {"name": name, "details": details, "steps": steps, "is_specific": is_specific}

# Generate Garmin API json dictionary payload
def build_garmin_workout(plan, intensity_anchor):
    workout_name = f"Dynamic: {plan['name']}"
    description = plan["details"]
    
    # Translate steps to Garmin Connect JSON
    garmin_steps = []
    step_order = 1
    
    # Mapping step types
    type_ids = {"warmup": 1, "cooldown": 2, "interval": 3, "recovery": 4, "rest": 5}
    
    for s in plan["steps"]:
        stype = s["type"]
        duration_sec = s["duration_mins"] * 60.0
        
        step = {
            "type": "ExecutableStep",
            "stepOrder": step_order,
            "stepType": {
                "stepTypeId": type_ids.get(stype, 3),
                "stepTypeKey": stype
            },
            "childStepId": None,
            "endCondition": {
                "conditionTypeId": 2,
                "conditionTypeKey": "time"
            },
            "endConditionValue": duration_sec,
            "description": f"Target: {stype.capitalize()}"
        }
        
        if intensity_anchor == "heart_rate":
            step["targetType"] = {
                "workoutTargetTypeId": 4,
                "workoutTargetTypeKey": "heart.rate.zone"
            }
            step["targetValueLow"] = float(s["hr_min"])
            step["targetValueHigh"] = float(s["hr_max"])
        else: # pace-based speed target in m/s
            step["targetType"] = {
                "workoutTargetTypeId": 5,
                "workoutTargetTypeKey": "speed.zone"
            }
            # pace (sec/km) to speed (m/s) -> 1000 / pace
            # slower pace is targetValueLow (which is smaller speed)
            # faster pace is targetValueHigh (which is higher speed)
            pace = s["pace"]
            speed_low = 1000.0 / (pace * 1.05)
            speed_high = 1000.0 / (pace * 0.95)
            step["targetValueLow"] = float(round(speed_low, 2))
            step["targetValueHigh"] = float(round(speed_high, 2))
            
        garmin_steps.append(step)
        step_order += 1
        
    return {
        "workoutId": None,
        "workoutName": workout_name,
        "description": description,
        "sportType": {
            "sportTypeId": 1,
            "sportTypeKey": "running"
        },
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": {
                    "sportTypeId": 1,
                    "sportTypeKey": "running"
                },
                "workoutSteps": garmin_steps
            }
        ]
    }

# Sync and publish to Garmin Connect
def run_physiological_training_engine():
    config = load_config()
    
    # 1. Log in to Garmin
    client = Garmin(config["garmin_email"], config["garmin_password"])
    token_dir = os.path.expanduser("~/.garminconnect")
    client.login(token_dir)
    
    # 2. Gather Telemetry
    today_str = datetime.date.today().isoformat()
    sleep = client.get_sleep_data(today_str)
    hrv = client.get_hrv_data(today_str)
    
    # Default fallbacks if metrics are absent
    sleep_score = sleep.get("dailySleepDTO", {}).get("sleepScore", 70)
    hrv_weekly_avg = hrv.get("hrvSummary", {}).get("weeklyAverage", 55)
    
    # Calculate Training Readiness Score
    trs = int((sleep_score * 0.4) + (hrv_weekly_avg * 0.6))
    
    # Fetch activities
    activities = client.get_activities(0, 100)
    
    # 3. Calculations
    resting_hr = config["user_profile"]["resting_hr"]
    max_hr = config["user_profile"]["max_hr"]
    acwr, current_vol, prev_vol = calculate_acwr(activities, resting_hr, max_hr)
    
    paces = calculate_vdot_paces(config["user_profile"]["vdot_race_distance_m"], 
                                 config["user_profile"]["vdot_race_time_sec"])
                                 
    phase = determine_training_phase(config)
    plan = plan_workout(phase, trs, acwr, current_vol, prev_vol, config, paces)
    
    # 4. Garmin Calendar Scheduling
    # Clear previous dynamic workouts from account
    all_workouts = client.get_workouts(0, 100)
    for w in all_workouts:
        w_name = w.get("workoutName", "")
        if w_name.startswith("Dynamic: "):
            try:
                client.delete_workout(w["workoutId"])
            except Exception as e:
                print(f"Error deleting workout {w['workoutId']}: {e}", file=sys.stderr)
                
    if plan["name"] != "Rest Day":
        # Build payload
        workout_payload = build_garmin_workout(plan, config["training_goal"].get("intensity_anchor", "heart_rate"))
        # Upload workout
        res = client.upload_workout(workout_payload)
        workout_id = res["workoutId"]
        # Schedule on calendar
        client.schedule_workout(workout_id, today_str)
        scheduled_workout = plan["name"]
    else:
        scheduled_workout = "Rest Day"
        
    return {
        "ready_score": trs,
        "acwr": round(acwr, 2),
        "phase": phase,
        "scheduled_workout": scheduled_workout,
        "details": plan["details"]
    }

if __name__ == "__main__":
    try:
        results = run_physiological_training_engine()
        print("Plan Sync Success:")
        for k, v in results.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"Error running training engine: {e}", file=sys.stderr)
        sys.exit(1)
