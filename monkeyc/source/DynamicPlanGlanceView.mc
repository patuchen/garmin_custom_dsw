import Toybox.WatchUi;
import Toybox.Graphics;
import Toybox.Application.Storage;

(:glance)
class DynamicPlanGlanceView extends WatchUi.GlanceView {

    function initialize() {
        GlanceView.initialize();
    }

    function onUpdate(dc as Dc) as Void {
        dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_BLACK);
        dc.clear();

        var trs = Storage.getValue("trs") as Number?;
        if (trs == null) {
            trs = 70; // default placeholder
        }
        
        var workout = Storage.getValue("workout") as String?;
        if (workout == null) {
            workout = "Not Synced";
        }

        // 1. Draw TRS Colored Ring/Arc on the left
        var cx = 30;
        var cy = dc.getHeight() / 2;
        var radius = 15;
        
        // Draw background gray circle
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(4);
        dc.drawArc(cx, cy, radius, Graphics.ARC_COUNTER_CLOCKWISE, 0, 360);

        // Draw foreground colored arc representing TRS
        var color = Graphics.COLOR_GREEN;
        if (trs < 60) {
            color = Graphics.COLOR_RED;
        } else if (trs < 73) {
            color = Graphics.COLOR_YELLOW;
        }
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        
        // Convert trs (0-100) to degrees (0-360)
        // In Garmin, 0 degrees is 3 o'clock. We draw counter-clockwise.
        var endAngle = (trs.toFloat() / 100.0) * 360.0;
        dc.drawArc(cx, cy, radius, Graphics.ARC_COUNTER_CLOCKWISE, 0, endAngle);

        // 2. Draw TRS Text inside/near the ring
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx + radius + 15, cy - 12, Graphics.FONT_GLANCE, "TRS: " + trs + "%", Graphics.TEXT_JUSTIFY_LEFT);
        
        // 3. Draw Recommendation
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx + radius + 15, cy + 2, Graphics.FONT_GLANCE_NUMBER, workout, Graphics.TEXT_JUSTIFY_LEFT);
    }
}
