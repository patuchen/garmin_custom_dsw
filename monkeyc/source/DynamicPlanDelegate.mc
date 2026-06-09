import Toybox.WatchUi;
import Toybox.Communications;
import Toybox.System;
import Toybox.Time;
import Toybox.Cryptography as Crypto;
import Toybox.StringUtil;
import Toybox.Application.Properties;

class DynamicPlanDelegate extends WatchUi.BehaviorDelegate {
    private var _view as DynamicPlanView;

    function initialize(view as DynamicPlanView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    function onTap(evt as ClickEvent) as Boolean {
        triggerLocalSync();
        return true;
    }

    function triggerLocalSync() as Void {
        _view.setSyncStatus("Syncing...");
        
        var psk = Properties.getValue("psk") as String;
        var url = Properties.getValue("serverUrl") as String;

        // 1. Generate Timestamp
        var now = Time.now().value();
        var timestampStr = now.toString();

        // 2. Cryptographically Hashed HMAC-SHA256 Signature
        try {
            var keyBytes = StringUtil.convertEncodedString(psk, {
                :fromRepresentation => StringUtil.REPRESENTATION_STRING_PLAIN_TEXT,
                :toRepresentation => StringUtil.REPRESENTATION_BYTE_ARRAY,
                :encoding => StringUtil.CHAR_ENCODING_UTF8
            });

            var msgBytes = StringUtil.convertEncodedString(timestampStr, {
                :fromRepresentation => StringUtil.REPRESENTATION_STRING_PLAIN_TEXT,
                :toRepresentation => StringUtil.REPRESENTATION_BYTE_ARRAY,
                :encoding => StringUtil.CHAR_ENCODING_UTF8
            });

            var hmac = new Crypto.HashBasedMessageAuthenticationCode({
                :algorithm => Crypto.HASH_SHA256,
                :key => keyBytes
            });
            hmac.update(msgBytes);
            var signatureBytes = hmac.digest();

            var signatureStr = StringUtil.convertEncodedString(signatureBytes, {
                :fromRepresentation => StringUtil.REPRESENTATION_BYTE_ARRAY,
                :toRepresentation => StringUtil.REPRESENTATION_STRING_HEX
            });

            // 3. Make Secure Loopback POST request
            var params = {
                "device" => "Venu3S",
                "request_type" => "on_demand_sync"
            };
            
            var options = {
                :method => Communications.HTTP_REQUEST_METHOD_POST,
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON,
                :headers => {
                    "Content-Type" => Communications.REQUEST_HEADER_URL_ENCODED,
                    "X-Signature" => signatureStr,
                    "X-Timestamp" => timestampStr
                }
            };

            Communications.makeWebRequest(url, params, options, method(:onSyncResponse));

        } catch (ex) {
            System.println("Cryptography error: " + ex.getErrorMessage());
            _view.setSyncStatus("Crypto Error");
        }
    }

    function onSyncResponse(responseCode as Number, data as Dictionary or String or Null) as Void {
        if (responseCode == 200 && data != null && data instanceof Dictionary) {
            System.println("Sync Successful: " + data);
            
            var trs = data.get("ready_score") as Number?;
            var acwr = data.get("acwr") as Float?;
            var workout = data.get("scheduled_workout") as String?;
            
            if (trs != null && acwr != null && workout != null) {
                _view.updateMetrics(trs, acwr, workout);
            } else {
                _view.setSyncStatus("Invalid JSON");
            }
        } else {
            System.println("Sync Failed. Code: " + responseCode);
            if (responseCode == -1001) {
                _view.setSyncStatus("SSL Error (Check cert)");
            } else if (responseCode == -400) {
                _view.setSyncStatus("Bad Request");
            } else if (responseCode == 401) {
                _view.setSyncStatus("Auth Failed (Bad PSK)");
            } else {
                _view.setSyncStatus("Sync Err: " + responseCode);
            }
        }
    }
}
