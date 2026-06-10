import os
import time
import hmac
import hashlib
import datetime
from flask import Flask, request, jsonify
from training_engine import run_physiological_training_engine, load_config

app = Flask(__name__)

# Verify signature
def verify_signature(config):
    psk = config["automation_settings"].get("shared_psk")
    if not psk:
        return False, "Preshared Key (PSK) is not configured on the server."
        
    signature = request.headers.get("X-Signature")
    timestamp_str = request.headers.get("X-Timestamp")
    
    if not signature or not timestamp_str:
        return False, "Missing X-Signature or X-Timestamp headers."
        
    try:
        timestamp = int(timestamp_str)
    except ValueError:
        return False, "Invalid timestamp format."
        
    # Check timestamp age to prevent replay attacks (allow 30 seconds drift)
    current_time = int(time.time())
    if abs(current_time - timestamp) > 30:
        return False, f"Request timestamp expired. Drift: {current_time - timestamp} seconds."
        
    # Compute expected signature
    # Signature = HMAC-SHA256(PSK, Timestamp)
    expected = hmac.new(
        psk.encode("utf-8"),
        timestamp_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    # Secure comparison to prevent timing attacks
    if not hmac.compare_digest(expected, signature):
        return False, "Invalid HMAC signature."
        
    return True, None

@app.route('/sync', methods=['POST'])
def sync_handler():
    config = load_config()
    is_valid, error_msg = verify_signature(config)
    if not is_valid:
        return jsonify({
            "status": "unauthorized",
            "message": error_msg
        }), 401
        
    try:
        # Run calculations and sync workout on the fly
        results = run_physiological_training_engine()
        
        return jsonify({
            "status": "success",
            "ready_score": results["ready_score"],
            "acwr": results["acwr"],
            "phase": results["phase"],
            "scheduled_workout": results["scheduled_workout"],
            "details": results["details"],
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        err_msg = str(e)
        print(f"ERROR: Sync failed: {err_msg}")
        if "Authentication" in err_msg or "login" in err_msg.lower():
            print("TIP: Your Garmin session may have expired. Please run the interactive login to renew:")
            print("     python3 ~/scripts/training_engine.py --interactive")
        return jsonify({
            "status": "error",
            "message": err_msg
        }), 500

if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cert_file = os.path.join(base_dir, "cert.pem")
    key_file = os.path.join(base_dir, "key.pem")
    
    ssl_context = None
    if os.path.exists(cert_file) and os.path.exists(key_file):
        ssl_context = (cert_file, key_file)
        print(f"Starting server with HTTPS using certificates {cert_file} and {key_file}")
    else:
        print("Starting server with HTTP. Please place 'cert.pem' and 'key.pem' in this directory to use HTTPS.")
        
    app.run(host='127.0.0.1', port=8080, ssl_context=ssl_context, debug=False)
