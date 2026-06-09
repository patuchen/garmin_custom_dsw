import Toybox.WatchUi;
import Toybox.Graphics;
import Toybox.SensorHistory;
import Toybox.ActivityMonitor;
import Toybox.Application.Storage;

class DynamicPlanView extends WatchUi.View {
    private var _readyScore as Number = 70;
    private var _recHours as Number = 0;
    private var _bodyBattery as Number = 0;
    private var _acwr as Float = 1.0;
    private var _workoutSuggestion as String = "Not Synced";
    private var _syncStatus as String = "Tap Screen to Sync";

    function initialize() {
        View.initialize();
    }

    function onShow() as Void {
        // Retrieve stored data if available
        var storedTrs = Storage.getValue("trs") as Number?;
        if (storedTrs != null) { { _readyScore = storedTrs; } }
        
        var storedAcwr = Storage.getValue("acwr") as Float?;
        if (storedAcwr != null) { { _acwr = storedAcwr; } }
        
        var storedWorkout = Storage.getValue("workout") as String?;
        if (storedWorkout != null) { { _workoutSuggestion = storedWorkout; } }

        // Retrieve real-time Recovery Hours
        var info = ActivityMonitor.getInfo();
        if (info has :timeToRecovery && info.timeToRecovery != null) {
            _recHours = info.timeToRecovery;
        }

        // Retrieve latest Body Battery sample
        if (Toybox has :SensorHistory && Toybox.SensorHistory has :getBodyBatteryHistory) {
            var bbIterator = SensorHistory.getBodyBatteryHistory({:period => 1});
            if (bbIterator != null) {
                var sample = bbIterator.next();
                if (sample != null && sample.data != null) {
                    _bodyBattery = sample.data as Number;
                }
            }
        }
    }

    function onUpdate(dc as Dc) as Void {
        dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_BLACK);
        dc.clear();

        var width = dc.getWidth();
        var height = dc.getHeight();
        var centerX = width / 2;

        // 1. Title
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(centerX, 25, Graphics.FONT_TINY, "DYNAMIC PLAN", Graphics.TEXT_JUSTIFY_CENTER);

        // 2. Training Readiness Score (TRS) Large Display
        var trsColor = Graphics.COLOR_GREEN;
        if (_readyScore < 60) {
            trsColor = Graphics.COLOR_RED;
        } else if (_readyScore < 73) {
            trsColor = Graphics.COLOR_YELLOW;
        }
        dc.setColor(trsColor, Graphics.COLOR_TRANSPARENT);
        dc.drawText(centerX, 45, Graphics.FONT_SYSTEM_NUMBER_MEDIUM, _readyScore.toString() + "%", Graphics.TEXT_JUSTIFY_CENTER);
        
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(centerX, 95, Graphics.FONT_TINY, _workoutSuggestion, Graphics.TEXT_JUSTIFY_CENTER);

        // Draw horizontal divider line
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(2);
        dc.drawLine(40, 120, width - 40, 120);

        // 3. Grid for metrics
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        
        // Left Column: Recovery and Body Battery
        dc.drawText(50, 130, Graphics.FONT_XTINY, "Recovery: " + _recHours + "h", Graphics.TEXT_JUSTIFY_LEFT);
        dc.drawText(50, 150, Graphics.FONT_XTINY, "Body Bat: " + _bodyBattery, Graphics.TEXT_JUSTIFY_LEFT);

        // Right Column: ACWR Index and Status
        var acwrStr = _acwr.format("%.2f");
        var acwrColor = Graphics.COLOR_GREEN;
        if (_acwr > 1.5) {
            acwrColor = Graphics.COLOR_RED;
        } else if (_acwr > 1.3) {
            acwrColor = Graphics.COLOR_ORANGE;
        } else if (_acwr < 0.8) {
            acwrColor = Graphics.COLOR_YELLOW;
        }
        
        dc.drawText(width - 50, 130, Graphics.FONT_XTINY, "ACWR Index:", Graphics.TEXT_JUSTIFY_RIGHT);
        dc.setColor(acwrColor, Graphics.COLOR_TRANSPARENT);
        dc.drawText(width - 50, 150, Graphics.FONT_XTINY, acwrStr, Graphics.TEXT_JUSTIFY_RIGHT);

        // 4. Action / Status Text at the bottom
        dc.setColor(Graphics.COLOR_GREEN, Graphics.COLOR_TRANSPARENT);
        dc.drawText(centerX, height - 45, Graphics.FONT_XTINY, _syncStatus, Graphics.TEXT_JUSTIFY_CENTER);
    }

    function updateMetrics(trs as Number, acwr as Float, workout as String) as Void {
        _readyScore = trs;
        _acwr = acwr;
        _workoutSuggestion = workout;
        _syncStatus = "Sync Complete";
        
        // Save to persistent storage
        Storage.setValue("trs", trs);
        Storage.setValue("acwr", acwr);
        Storage.setValue("workout", workout);
        
        WatchUi.requestUpdate();
    }

    function setSyncStatus(status as String) as Void {
        _syncStatus = status;
        WatchUi.requestUpdate();
    }
}
