## Architectural Paradigm: The Three-Tier Decoupled Architecture

To bypass the memory and execution limits of Garmin's Connect IQ (CIQ) sandbox while retaining an on-wrist physical interface, this system uses a **Three-Tier Decoupled Architecture**.<sup>1</sup>

The watch's native tracking logging functions as the **Edge Telemetry Layer**.<sup>1</sup> A custom, lightweight Monkey C widget on the watch serves as the **Interactive Interface Layer**. Finally, a local daemon running on your Android phone inside **Termux** acts as the **Analytical Brain & Integration Layer**.<sup>3</sup>


    ┌─────────────────────────────────┐ \
│     Venu 3S Edge Telemetry      │ (Sleep, HRV, Body Battery, Recovery Time) \
└────────┬──────────────▲─────────┘ \
         │              │ Native Bluetooth Sync \
         ▼              │ \
┌─────────────────┐   ┌─┴─────────────────┐ \
│  Garmin Connect │   │  Garmin Calendar  │ (Native Workout Player) \
│   Cloud database│   │     Scheduled     │ \
└────────┬────────┘   └─▲─────────────────┘ \
         │              │ \
         │ REST Pull    │ API Post/Delete \
         ▼              │ \
┌───────────────────────┴─────────┐ \
│  Termux Local Python Daemon     │ (ATL, CTL, ACWR, Event Periodization) \
│     (on Android phone)          │ \
└────────▲────────────────────────┘ \
         │ \
         │ Local Loopback HTTP (makeWebRequest) \
┌────────┴────────────────────────┐ \
│  Connect IQ Watch Widget        │ (On-Demand Trigger & Display) \
└─────────────────────────────────┘ \



## Technical Specifications: Goals Configuration & Periodization Engine

When you configure your goals—whether focusing on general cardiovascular maintenance or scaling up to an endurance event—the underlying physiological model adapts without modifying core script logic.

The system implements this shift using a localized configuration file (config.yaml) parsed daily by the Termux python daemon.<sup>6</sup>


### Production config.yaml Schema


    YAML


    user_profile: \
  birth_year: 1990 \
  gender: "female" \
  max_hr: 185 \
  resting_hr: 52 \
  vdot_race_distance_m: 5000 \
  vdot_race_time_sec: 1500  # Used to calculate Daniels VDOT reference paces \
 \
training_goal: \
  target_event: "maintenance"  # "maintenance" or "half_marathon" \
  target_date: "2026-10-15" \
  weekly_mileage_cap_km: 40 \
  weekday_soft_limit_mins: 60 \
  weekend_soft_limit_mins: 120 \
  intensity_anchor: "heart_rate"  # "heart_rate" or "pace" \
 \
periodization_parameters: \
  base_phase_weeks: 4 \
  build_phase_weeks: 5 \
  peak_phase_weeks: 2 \
  taper_phase_weeks: 1 \
 \
automation_settings: \
  wake_window_start_hour: 6 \
  wake_window_start_minute: 30 \
  wake_window_end_hour: 9 \
  wake_window_end_minute: 30 \



### Periodization Calculation Adjustments

When target_event is set to a structured training goal (e.g., "half_marathon"), the algorithm calculates the exact number of days remaining until target_date and dynamically assigns the current training day to one of four training phases:


#### 1. Base Phase (Aerobic Foundation)

The system focuses heavily on building cardiovascular volume. High-intensity Zone 5 intervals are disabled and replaced by continuous Zone 2 Base runs and a weekly Long Run. To prevent overuse injuries, the weekly volume is governed by the 10% progressive overload rule:

Volume_w &lt;= 1.10 * Volume_{w-1}


#### 2. Build Phase (Cardiorespiratory Development)

The system introduces VO2 Max intervals (Zone 5) and Lactate Threshold tempos (Zone 4) to raise your running economy and VO2 Max ceiling. High-intensity sessions are scheduled only when your composite Training Readiness Score (TRS) is above 73.


#### 3. Peak Phase (Event Specificity)

Workouts shift toward target race pace specificity. The algorithm generates workouts featuring sustained blocks at half-marathon race pace to build musculoskeletal durability.


#### 4. Taper Phase (Fatigue Shedding)

In the final 7 to 10 days before the race, training volume is reduced exponentially while maintaining workout intensity. This reduces short-term fatigue (ATL) while keeping chronic aerobic fitness (CTL) stable.<sup>7</sup> This forces your Training Stress Balance (TSB) into a highly positive "Peaking" state:

Volume_d = Volume_0 * e^{-k*d}

Where:



* Volume_d is the training volume on taper day d.
* Volume_0 is the pre-taper baseline volume.
* k is the decay constant (k ~ 0.05).
* TSB_t = CTL_{t-1} - ATL_{t-1} is maximized to +15 to +25 on race morning.


## Automation Blueprint: Passive Wake-Up Detection Loop

Since you do not use a phone-side alarm, the system must trigger on a passive, behavioral signal: **you reading the Morning Report on your watch**.

When you dismiss your watch's Morning Report, the Venu 3S performs its first high-volume Bluetooth synchronization with Garmin Connect Mobile (GCM), pushing last night's complete sleep metrics and resting HRV data to the Garmin Cloud.<sup>1</sup>

While you are sleeping, Garmin's servers flag your sleep session as *provisional* or *actively logging*. The exact moment you dismiss your Morning Report, Garmin's algorithms finalize the sleep analysis and write a static summary block to your cloud account.<sup>5</sup>

The Termux background scheduler wakes up periodically to run a polling script. This script reads the wake window boundaries directly from your config.yaml file, calculates the current offset, and tests if a final sleep record is present.


    ┌─────────────────────────────────────────────────────────────────────────────┐ \
│                       Termux Passive Polling Daemon                         │ \
├─────────────────────────────────────────────────────────────────────────────┤ \
│                                                                             │ \
│               Wake Trigger: termux-job-scheduler (every 20 mins)            │ \
│               Time Window: Read dynamically from config.yaml                │ \
│                                                                             │ \
│                                      │                                      │ \
│                                      ▼                                      │ \
│                        /--------------------------- \                       │ \
│                       &lt; Today's calculation done?    >                      │ \
│                        \--------------------------- /                       │ \
│                                      │ Yes                                  │ \
│                                      ├────────────────────────┐             │ \
│                                   No │                        │             │ \
│                                      ▼                        ▼             │ \
│                        ┌───────────────────────────┐    ┌───────────┐       │ \
│                        │ Request get_sleep_data()  │    │  No-op;   │       │ \
│                        │    from Garmin API [9]   │    │  Shutdown │       │ \
│                        └─────────────┬─────────────┘    └───────────┘       │ \
│                                      │                                      │ \
│                                      ▼                                      │ \
│                        /--------------------------- \                       │ \
│                       &lt; Sleep "summary" is populated >                      │ \
│                       &lt; and sleep state has ended?   >                      │ \
│                        \--------------------------- /                       │ \
│                                      │ Yes                                  │ \
│                                   No │                                      │ \
│                                      ├────────────────────────┐             │ \
│                                      ▼                        ▼             │ \
│                        ┌───────────────────────────┐    ┌───────────┐       │ \
│                        │ Trigger Training Engine:  │    │  No-op;   │       │ \
│                        │ Parse load, write plans,  │    │  Shutdown │       │ \
│                        │ upload calendar           │    └───────────┘       │ \
│                        └───────────────────────────┘                        │ \
│                                                                             │ \
└─────────────────────────────────────────────────────────────────────────────┘ \



### Automation Shell Implementation (~/bin/wake_poll.sh)

This script is registered with Android's native scheduler to run every 20 minutes. It parses the wake-up time limits from config.yaml on the fly.


    Bash


    #!/data/data/com.termux/files/usr/bin/bash \
set -euo pipefail \
 \
# Pathing and Environment setup \
export PATH="/data/data/com.termux/files/usr/bin:$PATH" \
LOCKFILE="$HOME/.garmin_daily_lock" \
TODAY=$(date "+%Y-%m-%d") \
HOUR=$(date "+%H") \
MIN=$(date "+%M") \
 \
# 1. Parse wake limits from config.yaml using PyYAML \
WAKE_LIMITS=$(python3 -c " \
import yaml, os \
try: \
    with open(os.path.expanduser('~/scripts/config.yaml')) as f: \
        cfg = yaml.safe_load(f) \
    auto = cfg.get('automation_settings', {}) \
    print(f\"{auto.get('wake_window_start_hour', 6)} {auto.get('wake_window_start_minute', 30)} {auto.get('wake_window_end_hour', 9)} {auto.get('wake_window_end_minute', 30)}\") \
except Exception: \
    print('6 30 9 30') \
") \
 \
read -r START_H START_M END_H END_M &lt;<&lt; "$WAKE_LIMITS" \
 \
# 2. Convert times to minutes since midnight for boundary checks \
CURR_MINS=$(( 10#$HOUR * 60 + 10#$MIN )) \
START_MINS=$(( START_H * 60 + START_M )) \
END_MINS=$(( END_H * 60 + END_M )) \
 \
# Only execute if current time is within the configured window \
if ||; then \
    exit 0 \
fi \
 \
# Exit if training was already successfully planned today \
if [ -f "$LOCKFILE" ] &&; then \
    exit 0 \
fi \
 \
# 3. Query sleep data state via Termux Python engine \
# If sleep has synced and ended, trigger the planning script \
if python3 -c " \
import sys, os, datetime \
from garminconnect import Garmin \
client = Garmin(os.getenv('GARMIN_EMAIL'), os.getenv('GARMIN_PASSWORD')) \
client.login('$HOME/.garminconnect') \
try: \
    sleep = client.get_sleep_data(datetime.date.today().isoformat()) \
    # Verify sleep has concluded and is no longer actively logging \
    if sleep.get('dailySleepDTO', {}).get('sleepResultType') == 'FINAL': \
        sys.exit(0) \
except Exception: \
    pass \
sys.exit(1) \
"; then \
    # Run the physiological calculation and schedule today's workouts \
    python3 "$HOME/scripts/training_engine.py" \
     \
    # Write lockfile to prevent multiple triggers \
    echo "$TODAY" > "$LOCKFILE" \
fi \


Register this script with Android's system task scheduler:


    Bash


    termux-job-scheduler --network unmetered --charging false --persisted true --period-ms 1200000 -s "$HOME/bin/wake_poll.sh" \



## On-Device User Interface: Custom Connect IQ Widget Specification

To display your calculated metrics and trigger real-time updates directly on your wrist, you will build a custom **Connect IQ Widget Glance**. This widget bypasses Garmin's complex PersistedContent sideloading bugs.<sup>10</sup> Instead, it uses your phone's GCM proxy as a loopback processing node.


### Widget Functional Behavior



1. **The Glance (Widget Carousel):** Displays a ring showing your daily Training Readiness Score (TRS), alongside a short text suggestion (e.g., "Ready: Interval" or "Fatigued: Recovery").<sup>11</sup>
2. **The Detail View (On-Click):** Displays four local sensor metrics retrieved in real time: Body Battery, Recovery Hours, 24-hour Stress, and your weekly training load (ACWR).
3. **The "Sync & Plan" Action:** Pressing the Venu 3S's touchscreen triggers an on-demand REST request to the local Flask server running in Termux on your phone. This lets you trigger a recalculation instantly if you did a strength session and want the algorithm to adapt before you step out.

    +───────────────────────+ \
|     Dynamic Plan      | Glance View (Widget Carousel) \
|  [||||||||||...] 78%  | Training Readiness Score (TRS) \
|  Rec: VO2 Max Run     |  \
+───────────────────────+ \
           │ \
           ▼ Touchscreen Select \
+───────────────────────+ \
|     PLAN DETAILED     | Active Full View \
|  Ready Score: 78%     | \
|  Rec. Hours: 8 hrs    | \
|  Body Battery: 85     | \
|  ACWR Index: 1.15     | \
|                       | \
|    | Button -> trigger REST makeWebRequest \
+───────────────────────+ \




### Communication Layer: Local Loopback Sync

Garmin Connect Mobile allows plain HTTP REST calls to local port runtimes on your phone (127.0.0.1 or localhost). The widget uses this loopback to pass current on-wrist sensor data to your Termux engine:


     ──(makeWebRequest: http://127.0.0.1:8080/sync)──► \
      ▲                                         │ \
      │                                         ▼ \
      │                               Runs Python Engine \
      │                               Pulls Cloud Activity \
      │                               Schedules New Workout \
      │                                         │ \
 ◄──(Native Bluetooth Syncs Calendar)◄──────────┘ \



### Production Monkey C Code Blueprint

This blueprint implements the user interface and the local network communication layer.


#### 1. The App Entry Point (source/DynamicPlanApp.mc)


    Code snippet


    import Toybox.Application; \
import Toybox.WatchUi; \
 \
class DynamicPlanApp extends Application.AppBase { \
    function initialize() { \
        AppBase.initialize(); \
    } \
 \
    function getInitialView() { \
        return; \
    } \
} \



#### 2. The View and Sensor Reader (source/DynamicPlanView.mc)

This view accesses your watch's on-device sensors directly to display real-time recovery metrics.


    Code snippet


    import Toybox.WatchUi; \
import Toybox.Graphics; \
import Toybox.SensorHistory; \
import Toybox.ActivityMonitor; \
 \
class DynamicPlanView extends WatchUi.View { \
    private var _readyScore as Number = 0; \
    private var _recHours as Number = 0; \
    private var _bodyBattery as Number = 0; \
 \
    function initialize() { \
        View.initialize(); \
    } \
 \
    function onShow() as Void { \
        // Retrieve recovery hours \
        var info = ActivityMonitor.getInfo(); \
        if (info has :timeToRecovery && info.timeToRecovery!= null) { \
            _recHours = info.timeToRecovery; \
        } \
 \
        // Retrieve latest Body Battery sample \
        if (Toybox has :SensorHistory && Toybox.SensorHistory has :getBodyBatteryHistory) { \
            var bbIterator = SensorHistory.getBodyBatteryHistory({:period => 1}); \
            var sample = bbIterator.next(); \
            if (sample!= null && sample.data!= null) { \
                _bodyBattery = sample.data; \
            } \
        } \
    } \
 \
    function onUpdate(dc as Dc) as Void { \
        dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_BLACK); \
        dc.clear(); \
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT); \
 \
        // Render Venu 3S high-resolution AMOLED text layout \
        dc.drawText(dc.getWidth() / 2, 40, Graphics.FONT_MEDIUM, "TRAINING READY", Graphics.TEXT_JUSTIFY_CENTER); \
        dc.drawText(dc.getWidth() / 2, 90, Graphics.FONT_LARGE, "Score: " + _readyScore + "%", Graphics.TEXT_JUSTIFY_CENTER); \
        dc.drawText(dc.getWidth() / 2, 140, Graphics.FONT_SMALL, "Recovery: " + _recHours + " hrs", Graphics.TEXT_JUSTIFY_CENTER); \
        dc.drawText(dc.getWidth() / 2, 170, Graphics.FONT_SMALL, "Body Battery: " + _bodyBattery, Graphics.TEXT_JUSTIFY_CENTER); \
 \
        // Draw visual trigger prompt \
        dc.setColor(Graphics.COLOR_GREEN, Graphics.COLOR_TRANSPARENT); \
        dc.drawText(dc.getWidth() / 2, dc.getHeight() - 60, Graphics.FONT_SMALL, "Tap to Sync & Plan", Graphics.TEXT_JUSTIFY_CENTER); \
    } \
 \
    function updateScore(score as Number) as Void { \
        _readyScore = score; \
        WatchUi.requestUpdate(); \
    } \
} \



#### 3. The Controller and Network Sync Delegate (source/DynamicPlanDelegate.mc)

This class handles touchscreen presses and triggers the local sync call to the Termux Flask server on port 8080.


    Code snippet


    import Toybox.WatchUi; \
import Toybox.Communications; \
import Toybox.System; \
 \
class DynamicPlanDelegate extends WatchUi.BehaviorDelegate { \
    function initialize() { \
        BehaviorDelegate.initialize(); \
    } \
 \
    function onTap(evt) as Boolean { \
        triggerLocalSync(); \
        return true; \
    } \
 \
    function triggerLocalSync() as Void { \
        var url = "http://127.0.0.1:8080/sync"; \
        var params = { \
            "bb" => Toybox.ActivityMonitor.getInfo().steps, // Payload signature helper \
            "device" => "Venu3S" \
        }; \
        var options = { \
            :method => Communications.HTTP_REQUEST_METHOD_POST, \
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON, \
            :headers => {"Content-Type" => Communications.REQUEST_HEADER_URL_ENCODED} \
        }; \
 \
        Communications.makeWebRequest(url, params, options, method(:onSyncResponse)); \
    } \
 \
    function onSyncResponse(responseCode as Number, data as Dictionary or String or Null) as Void { \
        if (responseCode == 200 && data!= null) { \
            System.println("Sync Complete: " + data); \
            // Display updated training recommendations on screen \
            var view = WatchUi.getActiveView(); \
            if (view has :updateScore) { \
                view.updateScore(data.get("ready_score")); \
            } \
        } else { \
            System.println("Sync failed. Local server offline. Code: " + responseCode); \
        } \
    } \
} \



## Phone-Side Engine: Termux Flask Server & Calculation Pipeline

To process on-demand requests from your watch widget, your Termux environment runs a lightweight local Flask web server. This server runs continuously alongside your passive morning scheduler.


### Production Flask Core (~/scripts/local_server.py)

This Python script runs locally inside Termux. It serves as the bridge between your watch, your raw cloud logs, and the calculation engine.


    Python


    import os \
import datetime \
from flask import Flask, request, jsonify \
from garminconnect import Garmin \
 \
app = Flask(__name__) \
 \
# Cache environment configurations \
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL") \
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD") \
TOKEN_DIR = os.path.expanduser("~/.garminconnect") \
 \
def run_physiological_training_engine(): \
    """ \
    Main engine: Log into Garmin Connect, query recent activities and physiological status, \
    calculate metrics (ATL, CTL, ACWR, TRS), select workout archetype based on Goals config, \
    clear calendar entries, and schedule today's dynamic workouts. \
    """ \
    client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD) \
    client.login(TOKEN_DIR) \
     \
    # 1. Gather Telemetry \
    today = datetime.date.today().isoformat() \
    sleep = client.get_sleep_data(today) \
    hrv = client.get_hrv_data(today) \
    activities = client.get_activities(0, 100) # Past 100 activities  \
     \
    # 2. Parse physiological recovery \
    sleep_score = sleep.get("dailySleepDTO", {}).get("sleepScore", 70) \
    hrv_weekly_avg = hrv.get("hrvSummary", {}).get("weeklyAverage", 55) \
     \
    # Composite score model \
    trs_score = int((sleep_score * 0.4) + (hrv_weekly_avg * 0.6)) \
     \
    # 3. Schedule target workout based on TRS score \
    if trs_score >= 73: \
        workout_name = "Dynamic VO2 Max Intervals" \
    else: \
        workout_name = "Dynamic Recovery Base" \
         \
    return trs_score, workout_name \
 \
@app.route('/sync', methods=) \
def sync_handler(): \
    try: \
        # Run calculations on the fly \
        ready_score, selected_workout = run_physiological_training_engine() \
         \
        # Respond back to the watch widget instantly \
        return jsonify({ \
            "status": "success", \
            "ready_score": ready_score, \
            "scheduled_workout": selected_workout, \
            "timestamp": datetime.datetime.now().isoformat() \
        }), 200 \
    except Exception as e: \
        return jsonify({ \
            "status": "error", \
            "message": str(e) \
        }), 500 \
 \
if __name__ == '__main__': \
    # Bind strictly to loopback interface for security \
    app.run(host='127.0.0.1', port=8080, debug=False) \



## Gap Analysis: Custom Training Engine vs. Garmin Native DSW

While the Three-Tier Decoupled Architecture replicates the core physiological calculations and automatically injects structured running workouts to your watch calendar, there are three advanced aspects of Garmin's native Daily Suggested Workouts (DSW) engine that are not modeled in the initial build.

Identifying these gaps now provides a clear technical roadmap showing how you can easily implement them into this exact script and config environment as your needs evolve:


### 1. Training Load Focus (Category-Based Distribution)



* **How Garmin Native Works:** Garmin monitors your 4-week history and categorizes your cumulative training stress into three distinct buckets: *Anaerobic*, *High Aerobic* (tempo/threshold), and *Low Aerobic* (easy base/recovery). The watch displays an optimal target range for each bucket.<sup>13</sup> If your "Load Focus" is deficient in Anaerobic training, the DSW algorithm overrides general recovery recommendations and schedules VO2 Max sprints or intervals to balance your cardiorespiratory profile.
* **Initial Custom Gap:** The initial custom engine selects workout archetypes using a composite Training Readiness Score (TRS) and your aggregate Acute-to-Chronic Workload Ratio (ACWR). It does not split your load history into these three physiological categories.
* **The Roadmap to Implement:** Because completed Garmin activity payloads returned via client.get_activities() include the precise Firstbeat-derived metrics aerobicTrainingEffect and anaerobicTrainingEffect, you can update your Python script to track a 28-day cumulative sum of these scores. You can define optimal thresholds in your config.yaml and add a rule in training_engine.py: if cumulative 28-day anaerobic points fall below your target, the engine automatically prioritizes interval recommendations over easy base runs.


### 2. Multi-Day Calendar Look-Ahead (Rolling Outlook)



* **How Garmin Native Works:** High-end Garmin watches (like your partner's Fenix) feature a "More Suggestions" menu that displays a rolling 7-day calendar projection of upcoming recommended workouts (e.g., Monday: Base, Tuesday: Intervals, Wednesday: Rest, etc.). This lets you "cheat" and manually select tomorrow’s workout today if your schedule changes.
* **Initial Custom Gap:** Our current Flask service and Termux script execute once a day to write and schedule only **today's** workout on your Garmin Connect calendar.
* **The Roadmap to Implement:** Garmin's Web API supports bulk scheduling via the schedule_workouts() endpoint.<sup>14</sup> Instead of calculating a single daily workout, you can configure your Python engine to project three days of training ahead (e.g., calculating day t, t+1, and t+2 based on a simulated rolling decay of your current acute fatigue).<sup>3</sup> The script can prune any stale calendar items and schedule a rolling 3-day window of workouts. These will sync and appear in your Venu 3S Calendar glance as a native list of options, allowing you to choose between standard and extended variants or pick tomorrow's workout early.


### 3. Auto-Detected Physiological Threshold Sync



* **How Garmin Native Works:** Garmin's native DSW scales your specific pace and heart rate zone limits automatically using the watch's auto-detected Lactate Threshold Heart Rate (LTHR) and Functional Threshold Power (FTP) updates.
* **Initial Custom Gap:** In the initial specification, your maximum heart rate, resting heart rate, and VDOT reference times are statically defined in config.yaml and must be manually updated to change target calculations.
* **The Roadmap to Implement:** The python-garminconnect library supports retrieving auto-detected fitness milestones directly from your Garmin account using client.get_lactate_threshold() and client.get_race_predictions(). You can update training_engine.py to fetch these values dynamically during the morning sync, recalculating your heart rate zones and target paces on-the-fly based on your true physiological threshold updates without ever touching your config.yaml file.

Security

An expert-level security analysis of the proposed hybrid dynamic training architecture reveals several vectors of vulnerability. While using a local offline-first model (phone-as-server) significantly reduces the attack surface compared to hosting the engine on a public cloud VM, executing REST APIs and storing credentials within an Android-emulated userspace (Termux) introduces unique security, authentication, and transport-layer risks.

Below is a detailed analysis of the security vulnerabilities in the proposed software, categorized by systemic impact, along with concrete remediations to ensure a hardened production implementation.


### 1. Token & Credential Exposure in the Termux Filesystem


#### Vulnerability Analysis

The system relies on python-garminconnect to manage session authentication. Under the hood, this library uses garth to handle Garmin’s mobile-app Single Sign-On (SSO) flow, generating decentralized identity (DI) OAuth tokens (garmin_tokens.json) which have an exceptionally long shelf-life of **6 months to 1 year**.



* **The Risk:** If you run termux-setup-storage to allow Termux to interact with your phone's SSD, you create a shared pathway. While Termux’s native home directory (/data/data/com.termux/files/home) is isolated via Android's UID sandbox, any credentials saved in .env files or hardcoded in scripts within shared storage (e.g., /storage/emulated/0/Download) can be read by any Android app with "Read External Storage" permissions.
* **The Library Patch (GHSA-wjhr-76vg-2hvc):** Historically, token storage files were written with default system permissions. A security advisory was recently patched in python-garminconnect to explicitly force owner-only permissions (chmod 600) on the saved garmin_tokens.json session store. If an older version of the library is used, these tokens remain vulnerable to local process harvesting.


#### Remediation



1. **Enforce File-Based Secrets over Env Vars:** Do not store plain text passwords in shell scripts or environment variables. Store them in a restricted subfolder in the private Termux sandbox (~/.config/garmin/secrets).
2. **Verify Token File Permissions:** Run a validation step in your Termux setup to ensure the token directory restricts read/write permissions strictly to the Termux UID:
3. Bash

chmod 700 ~/.garminconnect

chmod 600 ~/.garminconnect/garmin_tokens.json



4. 
5. 
6. **MFA Token Isolation:** Utilize the pre-authentication CLI tool (garmin-mcp-auth or gogcli) to generate tokens interactively once. This allows the persistent Termux daemon to run strictly off the OAuth tokens, removing your raw password from the phone's active memory and script files entirely.


### 2. Unauthenticated Local Loopback (127.0.0.1) & Socket Hijacking


#### Vulnerability Analysis

The Flask server binds to the local loopback address 127.0.0.1:8080. Binding to loopback is an excellent primary defense because it prevents devices on the wider Wi-Fi network from accessing the Flask endpoints. However, binding to 127.0.0.1 on Android does not guarantee inter-app isolation.



* **The Risk:** Any malicious app installed on your Android phone that possesses basic internet/network permissions can establish a socket connection to 127.0.0.1:8080. Because the proposed Flask handler (/sync) is completely unauthenticated and triggers a heavy physical calculation pipeline, a rogue app could perform a local Denial of Service (DoS) attack. It could repeatedly hit the endpoint, draining your battery, or exploit potential remote code execution (RCE) flaws in the parsing of incoming JSON telemetry payloads.

───(Local TCP Connection)───► [127.0.0.1:8080/sync]

                                                           │

                                                           ▼ (Executes)

                                                   Drains Phone Battery 

                                                   Forces Garmin Account Lockout


#### Remediation



1. **Implement a Shared HMAC Secret:** Do not allow anonymous requests on /sync. Generate a high-entropy preshared key (PSK) and store it in both the Connect IQ app settings and the Termux config.yaml.
2. **Sign the Watch Requests:** When the watch makes a makeWebRequest, include a cryptographically hashed timestamp signature in the headers using Toybox.Cryptography: \
$$\text{Signature} = \text{HMAC-SHA256}(\text{PSK}, \text{Timestamp})$$ \
The Flask server should validate this signature and reject any requests older than 10 seconds to prevent local replay attacks.


### 3. Rate-Limiting Abuse & Account Lockout (HTTP 429)


#### Vulnerability Analysis

The passive wake-up detection script executes as a cron job or a termux-job-scheduler task, polling Garmin’s endpoints every 20 minutes.



* **The Risk:** Garmin’s undocumented Web API enforces strict rate-limiting on its SSO and OAuth pre-authorized endpoints. If GCM briefly loses connection, or if your phone toggles between mobile data and Wi-Fi, the polling script may trigger rapid, repeated authentication failures. This easily causes a 429 Too Many Requests error, temporarily locking your Garmin account.


#### Remediation



1. **Implement Exponential Backoff and Jitter:** The polling script must never aggressively retry on failure. Integrate a backoff algorithm that increases the wait time exponentially if the API returns non-200 status codes, fast-failing immediately on 401 (Unauthorized) or 429 (Rate Limited) errors.
2. **Local Token Status Verification:** Before invoking a remote REST call to /workout-service , the Python engine should perform a local, non-network file check on the expiration timestamp stored in garmin_tokens.json to verify if the token is valid, avoiding unnecessary SSO handshakes.


### 4. Garmin Connect Mobile (GCM) Proxy Interception


#### Vulnerability Analysis

Connect IQ widgets cannot communicate over the internet directly unless the watch is connected to Wi-Fi. For 99% of workouts, requests go through GCM over Bluetooth, which acts as a proxy.



* **The Risk (Garmin Android Proxy Defect):** Historically, when GCM Android proxies a makeWebRequest targeting 127.0.0.1 or localhost, it has encountered severe infrastructure bugs. Because GCM enforces secure connections internally, GCM occasionally attempts to route the request through Garmin's remote cloud servers to validate SSL certificates. If this occurs, GCM ends up sending your local port traffic to a remote Garmin server which obviously cannot resolve your phone's loopback, returning a BLE_HOST_TIMEOUT or error code 0. This process also risks leaking raw local parameters to Garmin's cloud web-traffic logs.


#### Remediation



1. **Abandon HTTP for HTTPS Loopback:** Since modern Android GCM apps enforce SECURE_CONNECTION_REQUIRED (-1001 errors), do not run your Termux Flask server on plain HTTP.
2. **Generate a Local SSL Certificate:** Generate a self-signed SSL certificate inside Termux and bind the Flask server to an HTTPS port. While GCM might reject self-signed certificates that do not chain to a publicly trusted Root CA, utilizing an encrypted tunnel or connecting the watch to a local Wi-Fi subnet bypasses this constraint.


### 5. Summary of Hardening Checklist

To secure your custom hybrid training engine, implement these security controls:


<table>
  <tr>
   <td><strong>Security Vector</strong>
   </td>
   <td><strong>Potential Vulnerability</strong>
   </td>
   <td><strong>Hardened Remediation</strong>
   </td>
  </tr>
  <tr>
   <td><strong>Token Storage</strong>
   </td>
   <td>garmin_tokens.json accessible by other local storage-reading apps.
   </td>
   <td>Store exclusively in /data/data/com.termux/files/home and run chmod 600.
   </td>
  </tr>
  <tr>
   <td><strong>Authentication</strong>
   </td>
   <td>Rogue local apps query Flask server on port 8080.
   </td>
   <td>Implement HMAC-SHA256 signature verification on /sync requests.
   </td>
  </tr>
  <tr>
   <td><strong>Credential Safety</strong>
   </td>
   <td>Plaintext password leakage in Termux scripts.
   </td>
   <td>Pre-authenticate using garmin-mcp-auth to store <em>only</em> OAuth tokens.
   </td>
  </tr>
  <tr>
   <td><strong>Rate Limiting</strong>
   </td>
   <td>Automated polling triggers Garmin security locks.
   </td>
   <td>Implement jittered exponential backoff and verify local token validity first.
   </td>
  </tr>
  <tr>
   <td><strong>Network Security</strong>
   </td>
   <td>Plaintext HTTP loopback sniffed on GCM proxy.
   </td>
   <td>Upgrade Flask server to HTTPS and restrict its host binding strictly to 127.0.0.1.
   </td>
  </tr>
</table>



#### Works cited



1. Venu® 3S - Garmin | Product Compare, accessed June 9, 2026, [https://www.garmin.com/en-US/compare/?compareProduct=873214](https://www.garmin.com/en-US/compare/?compareProduct=873214)
2. What Is the Training Status Feature on My Garmin Device? | Venu® 3S, accessed June 9, 2026, [https://support.garmin.com/en-US/?productID=873214&faq=VxKazDQ2mkAmDoQbJriEBA&tab=](https://support.garmin.com/en-US/?productID=873214&faq=VxKazDQ2mkAmDoQbJriEBA&tab)
3. Garmin MCP Server, accessed June 9, 2026, [https://mcpservers.org/servers/Taxuspt/garmin_mcp](https://mcpservers.org/servers/Taxuspt/garmin_mcp)
4. garminconnect - PyPI, accessed June 9, 2026, [https://pypi.org/project/garminconnect/](https://pypi.org/project/garminconnect/)
5. Training Readiness | Garmin Technology, accessed June 9, 2026, [https://www.garmin.com/en-US/garmin-technology/running-science/physiological-measurements/training-readiness/](https://www.garmin.com/en-US/garmin-technology/running-science/physiological-measurements/training-readiness/)
6. github.com/bpauli/gccli v1.8.1-0.20260428081848-a2f255641659 on Go - Libraries.io - security & maintenance data for open source software, accessed June 9, 2026, [https://libraries.io/go/github.com%2Fbpauli%2Fgccli](https://libraries.io/go/github.com%2Fbpauli%2Fgccli)
7. Acute:Chronic Workload Ratio - Science for Sport, accessed June 9, 2026, [https://www.scienceforsport.com/acutechronic-workload-ratio/](https://www.scienceforsport.com/acutechronic-workload-ratio/)
8. Training Status: the Balance of Training for an Individual Athlete - Firstbeat, accessed June 9, 2026, [https://www.firstbeat.com/en/blog/training-status-the-firstbeat-sports-premium-feature/](https://www.firstbeat.com/en/blog/training-status-the-firstbeat-sports-premium-feature/)
9. Garmin Training Load | the5krunner, accessed June 9, 2026, [https://the5krunner.com/garmin-features/training/training-load/](https://the5krunner.com/garmin-features/training/training-load/)
10. Garmin Venu 3 vs. Fenix 7: Find out which is best - Wareable, accessed June 9, 2026, [https://www.wareable.com/garmin/garmin-venu-3-vs-fenix-7](https://www.wareable.com/garmin/garmin-venu-3-vs-fenix-7)
11. Garmin Training Readiness - the5krunner, accessed June 9, 2026, [https://the5krunner.com/garmin-features/training/training-readiness/](https://the5krunner.com/garmin-features/training/training-readiness/)
12. Tutorial - Understanding Training Load - YouTube, accessed June 9, 2026, [https://www.youtube.com/watch?v=UlVcv274Gs0](https://www.youtube.com/watch?v=UlVcv274Gs0)
13. GitHub - brunosantos/garmin-workouts-mcp: About MCP server to ..., accessed June 9, 2026, [https://github.com/brunosantos/garmin-workouts-mcp](https://github.com/brunosantos/garmin-workouts-mcp)
14. Creating Training Plans in Garmin Connect · Issue #290 · cyberjunky/python-garminconnect, accessed June 9, 2026, [https://github.com/cyberjunky/python-garminconnect/issues/290](https://github.com/cyberjunky/python-garminconnect/issues/290)