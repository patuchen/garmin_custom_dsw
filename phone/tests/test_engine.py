import sys
import os
from unittest.mock import MagicMock

# Mock garminconnect module before importing training_engine
mock_garmin = MagicMock()
sys.modules["garminconnect"] = mock_garmin

import unittest
import hmac
import hashlib
import time

# Add scripts directory to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from training_engine import calculate_vdot_paces, calculate_acwr, plan_workout, format_pace
from local_server import verify_signature

class TestPhysiologicalEngine(unittest.TestCase):

    def test_vdot_calculations(self):
        # 5K in 25:00 -> 5000m in 1500s
        paces = calculate_vdot_paces(5000, 1500)
        self.assertAlmostEqual(paces["vdot"], 38.3, delta=0.5)
        
        # Verify interval pace is faster than easy pace
        self.assertLess(paces["interval"], paces["easy"])
        self.assertLess(paces["threshold"], paces["easy"])
        
        # Easy pace format check
        formatted_easy = format_pace(paces["easy"])
        self.assertTrue(formatted_easy.endswith("/km"))
        print(f"Test VDOT paces: { {k: format_pace(v) for k, v in paces.items() if k != 'vdot'} }")

    def test_acwr_workload(self):
        # Mocking activities with dummy load
        resting_hr = 52
        max_hr = 185
        
        # Create activities list: past 28 days
        # Days 0-6: high load (acute load)
        # Days 7-27: lower load (chronic base)
        activities = []
        for i in range(28):
            act_date = (time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400)))
            # Days 0-6 get high load (e.g. 150 load value)
            # Days 7-27 get lower load (e.g. 50 load value)
            load = 150.0 if i < 7 else 50.0
            activities.append({
                "startTimeLocal": f"{act_date} 08:00:00",
                "trainingLoad": load
            })
            
        acwr, current_vol, prev_vol = calculate_acwr(activities, resting_hr, max_hr)
        # Days 0-6: 7 days * 150 = 1050 sum -> 150 average
        # Days 7-27: 21 days * 50 = 1050 sum + Days 0-6 1050 sum = 2100 total sum / 28 = 75 average.
        # ACWR = 150 / 75 = 2.0. Let's assert it is around 2.0.
        self.assertAlmostEqual(acwr, 2.0, delta=0.1)

    def test_brisk_walk_conversion(self):
        paces = calculate_vdot_paces(5000, 1500)
        config = {
            "user_profile": {"resting_hr": 52, "max_hr": 185},
            "training_goal": {
                "intensity_anchor": "heart_rate",
                "weekday_soft_limit_mins": 60,
                "weekend_soft_limit_mins": 120,
                "minimum_run_length_km": 10.0, # force walk conversion by setting a high minimum run length
                "minimum_run_duration_mins": 90
            }
        }
        
        # Generate an easy base run that is short (e.g. 30 mins)
        plan = plan_workout("Base", 80, 1.0, 100, 100, config, paces)
        self.assertTrue(plan["name"].startswith("Brisk Walk"))
        print(f"Test Walk Conversion: {plan['name']} - {plan['details']}")
        
        # Now test that a specific VO2 Max interval workout is EXEMPT from walk conversion
        plan_vo2 = plan_workout("Build", 85, 1.0, 100, 100, config, paces)
        self.assertEqual(plan_vo2["name"], "Dynamic VO2 Max Intervals")

    def test_signature_verification(self):
        # Mock request context for local_server verify_signature test
        class MockRequest:
            def __init__(self, headers):
                self.headers = headers
                
        psk = "my_secret_key"
        timestamp = str(int(time.time()))
        signature = hmac.new(
            psk.encode("utf-8"),
            timestamp.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        config = {
            "automation_settings": {"shared_psk": psk}
        }
        
        # We need to temporarily mock flask request
        import local_server
        original_request = local_server.request
        
        try:
            local_server.request = MockRequest({
                "X-Signature": signature,
                "X-Timestamp": timestamp
            })
            is_valid, err = verify_signature(config)
            self.assertTrue(is_valid)
            self.assertIsNone(err)
            
            # Test incorrect signature
            local_server.request = MockRequest({
                "X-Signature": "wrong_signature",
                "X-Timestamp": timestamp
            })
            is_valid, err = verify_signature(config)
            self.assertFalse(is_valid)
            self.assertEqual(err, "Invalid HMAC signature.")
            
            # Test expired signature (older than 30s)
            old_timestamp = str(int(time.time()) - 45)
            old_signature = hmac.new(
                psk.encode("utf-8"),
                old_timestamp.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()
            local_server.request = MockRequest({
                "X-Signature": old_signature,
                "X-Timestamp": old_timestamp
            })
            is_valid, err = verify_signature(config)
            self.assertFalse(is_valid)
            self.assertTrue("timestamp expired" in err)
            
        finally:
            local_server.request = original_request

if __name__ == "__main__":
    unittest.main()
