import Toybox.Application;
import Toybox.WatchUi;
import Toybox.System;

class DynamicPlanApp extends Application.AppBase {

    private var _view as DynamicPlanView?;

    function initialize() {
        AppBase.initialize();
    }

    // Return the initial view and delegate for the widget detail view
    function getInitialView() {
        _view = new DynamicPlanView();
        var delegate = new DynamicPlanDelegate(_view as DynamicPlanView);
        return [ _view, delegate ];
    }

    // Return the glance view
    (:glance)
    function getGlanceView() {
        return [ new DynamicPlanGlanceView() ];
    }

    // Handle settings updates dynamically
    function onSettingsChanged() as Void {
        WatchUi.requestUpdate();
    }
}

function getApp() as DynamicPlanApp {
    return Application.getApp() as DynamicPlanApp;
}
