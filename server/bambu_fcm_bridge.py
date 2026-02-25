#!/usr/bin/env python3
"""
Bambu FCM Bridge Server
-----------------------
Maintains persistent MQTT connection to Bambu Labs printer and sends
Firebase Cloud Messaging (FCM) push notifications to the Android app,
and ActivityKit push notifications (APNs) to the iOS app's Live Activities.

This runs on your Linux server 24/7.

Setup:
1. pip install paho-mqtt firebase-admin httpx[http2] PyJWT cryptography
2. Copy config.example.py to config.py and fill in your values
3. Place your Firebase service account JSON file in same directory
4. Run: python3 bambu_fcm_bridge.py

Author: Bambu Now Bar
"""

import json
import os
import ssl
import sys
import time
import logging
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List

import paho.mqtt.client as mqtt

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, messaging

# =============================================================================
# CONFIGURATION - loaded from config.py
# =============================================================================
try:
    from config import (
        BAMBU_MQTT_SERVER,
        BAMBU_MQTT_PORT,
        BAMBU_USER_ID,
        BAMBU_ACCESS_TOKEN,
        BAMBU_PRINTER_SERIAL,
        FIREBASE_CREDENTIALS_FILE,
        FCM_DEVICE_TOKENS,
    )
except ImportError:
    print("ERROR: config.py not found!")
    print("Copy config.example.py to config.py and fill in your values:")
    print("  cp config.example.py config.py")
    sys.exit(1)

# Optional iOS/APNs configuration - defaults if not present in config.py
try:
    import config as _config_module
except ImportError:
    _config_module = None

APNS_KEY_FILE = getattr(_config_module, 'APNS_KEY_FILE', '')
APNS_TEAM_ID = getattr(_config_module, 'APNS_TEAM_ID', '')
APNS_KEY_ID = getattr(_config_module, 'APNS_KEY_ID', '')
APNS_BUNDLE_ID = getattr(_config_module, 'APNS_BUNDLE_ID', 'com.elliot.bamboonowbar')
APNS_USE_SANDBOX = getattr(_config_module, 'APNS_USE_SANDBOX', True)
APNS_PRINTER_NAME = getattr(_config_module, 'APNS_PRINTER_NAME', 'Bambu Lab')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bambu_fcm_bridge.log')
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# APNs SENDER - Direct Apple Push Notifications for iOS Live Activities
# =============================================================================

class APNsSender:
    """Sends ActivityKit push notifications to iOS devices via APNs HTTP/2."""

    def __init__(self, key_file: str, key_id: str, team_id: str, bundle_id: str,
                 use_sandbox: bool = True):
        try:
            import httpx
            import jwt as pyjwt
        except ImportError:
            logger.warning("httpx or PyJWT not installed. iOS notifications disabled.")
            logger.warning("Install with: pip install 'httpx[http2]' PyJWT cryptography")
            self._enabled = False
            return

        with open(key_file, 'r') as f:
            self._auth_key = f.read()
        self._key_id = key_id
        self._team_id = team_id
        self._bundle_id = bundle_id
        self._base_url = (
            "https://api.sandbox.push.apple.com"
            if use_sandbox
            else "https://api.push.apple.com"
        )
        self._client = httpx.Client(http2=True, timeout=30.0)
        self._jwt_module = pyjwt
        self._token: Optional[str] = None
        self._token_time: float = 0
        self._enabled = True
        mode = "sandbox" if use_sandbox else "production"
        logger.info(f"APNs initialized ({mode})")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _get_auth_token(self) -> str:
        """Generate or reuse JWT bearer token (valid for 1 hour)."""
        now = time.time()
        if self._token and (now - self._token_time) < 3500:
            return self._token
        headers = {"alg": "ES256", "kid": self._key_id}
        payload = {"iss": self._team_id, "iat": int(now)}
        self._token = self._jwt_module.encode(
            payload, self._auth_key, algorithm="ES256", headers=headers
        )
        self._token_time = now
        return self._token

    def send(self, device_token: str, payload_dict: dict, priority: int = 10) -> int:
        """Send an APNs Live Activity notification.

        Args:
            priority: 10 = high (counts toward budget), 5 = low (doesn't count).

        Returns:
            HTTP status code (200 = success, 410 = token expired, 0 = exception).
        """
        if not self._enabled:
            return 0
        try:
            auth = self._get_auth_token()
            topic = f"{self._bundle_id}.push-type.liveactivity"
            headers = {
                "authorization": f"bearer {auth}",
                "apns-push-type": "liveactivity",
                "apns-topic": topic,
                "apns-priority": str(priority),
            }
            url = f"{self._base_url}/3/device/{device_token}"
            response = self._client.post(url, json=payload_dict, headers=headers)
            if response.status_code == 200:
                logger.info(f"APNs sent (p={priority}) to ...{device_token[-8:]}")
            elif response.status_code == 410:
                logger.warning(f"APNs 410 Gone — token expired: ...{device_token[-8:]}")
            else:
                logger.error(f"APNs error {response.status_code}: {response.text}")
            return response.status_code
        except Exception as e:
            logger.error(f"APNs send failed: {e}")
            return 0


# =============================================================================
# FIRESTORE TOKEN LISTENER - Reads iOS push tokens from Firestore
# =============================================================================

class FirestoreTokenListener:
    """Listens for iOS device push tokens in Firestore."""

    def __init__(self):
        self._push_to_start_tokens: Dict[str, str] = {}  # device_id -> token
        self._activity_push_tokens: Dict[str, str] = {}   # device_id -> token
        self._listener = None

    def start(self):
        """Start listening to the bambu_tokens Firestore collection."""
        try:
            from firebase_admin import firestore
            db = firestore.client()
            collection_ref = db.collection('bambu_tokens')

            def on_snapshot(col_snapshot, changes, read_time):
                for change in changes:
                    doc = change.document
                    data = doc.to_dict()
                    device_id = doc.id

                    if data.get('platform') != 'ios':
                        continue

                    if change.type.name in ('ADDED', 'MODIFIED'):
                        if 'pushToStartToken' in data:
                            self._push_to_start_tokens[device_id] = data['pushToStartToken']
                            logger.info(f"iOS push-to-start token updated for {device_id[:8]}...")
                        if 'activityPushToken' in data:
                            self._activity_push_tokens[device_id] = data['activityPushToken']
                            logger.info(f"iOS activity push token updated for {device_id[:8]}...")
                    elif change.type.name == 'REMOVED':
                        self._push_to_start_tokens.pop(device_id, None)
                        self._activity_push_tokens.pop(device_id, None)

            self._listener = collection_ref.on_snapshot(on_snapshot)
            logger.info("Firestore token listener started")
        except ImportError:
            logger.info("Firestore not available - iOS token sync disabled")
        except Exception as e:
            logger.warning(f"Failed to start Firestore listener: {e}")
            logger.info("iOS push tokens will not be auto-synced")

    @property
    def push_to_start_tokens(self) -> List[str]:
        return list(self._push_to_start_tokens.values())

    @property
    def activity_push_tokens(self) -> List[str]:
        return list(self._activity_push_tokens.values())

    def has_tokens(self) -> bool:
        return bool(self._push_to_start_tokens or self._activity_push_tokens)

    def remove_expired_token(self, token: str):
        """Remove an expired token from local cache and Firestore."""
        # Find which device_id owns this token
        for device_id, t in list(self._push_to_start_tokens.items()):
            if t == token:
                self._push_to_start_tokens.pop(device_id, None)
                logger.info(f"Removed expired push-to-start token for {device_id[:8]}...")
                self._delete_token_field(device_id, 'pushToStartToken')
                return
        for device_id, t in list(self._activity_push_tokens.items()):
            if t == token:
                self._activity_push_tokens.pop(device_id, None)
                logger.info(f"Removed expired activity push token for {device_id[:8]}...")
                self._delete_token_field(device_id, 'activityPushToken')
                return

    def _delete_token_field(self, device_id: str, field: str):
        """Delete a specific token field from Firestore."""
        try:
            from firebase_admin import firestore
            db = firestore.client()
            db.collection('bambu_tokens').document(device_id).update({
                field: firestore.DELETE_FIELD
            })
            logger.info(f"Deleted {field} from Firestore for {device_id[:8]}...")
        except Exception as e:
            logger.warning(f"Failed to delete {field} from Firestore: {e}")


# =============================================================================
# PREPARATION STAGE MAPPING — maps stg_cur numeric values to human-readable names
# Source: ha-bambulab Home Assistant integration (https://github.com/greghesp/ha-bambulab)
#         CURRENT_STAGE_IDS in custom_components/bambu_lab/pybambu/const.py
# =============================================================================
PREPARATION_STAGES = {
    -1: None,                           # idle
    0: None,                            # printing (not a prep stage)
    1: "Auto bed leveling",
    2: "Preheating heatbed",
    3: "Vibration compensation",
    4: "Changing filament",
    5: "M400 pause",
    6: "Filament runout pause",
    7: "Heating hotend",
    8: "Calibrating extrusion",
    9: "Scanning bed surface",
    10: "Inspecting first layer",
    11: "Identifying build plate",
    12: "Calibrating micro lidar",
    13: "Homing toolhead",
    14: "Cleaning nozzle tip",
    15: "Checking extruder temp",
    16: "Paused by user",
    17: "Front cover falling",
    18: "Calibrating micro lidar",
    19: "Calibrating extrusion flow",
    20: "Nozzle temp malfunction",
    21: "Heatbed temp malfunction",
    22: "Filament unloading",
    23: "Paused: skipped step",
    24: "Filament loading",
    25: "Calibrating motor noise",
    26: "Paused: AMS lost",
    27: "Paused: low fan speed",
    28: "Chamber temp control error",
    29: "Cooling chamber",
    30: "Paused by G-code",
    31: "Motor noise calibration",
    32: "Paused: nozzle filament covered",
    33: "Paused: cutter error",
    34: "Paused: first layer error",
    35: "Paused: nozzle clog",
    36: "Checking absolute accuracy",
    37: "Absolute accuracy calibration",
    38: "Checking absolute accuracy",
    39: "Calibrating nozzle offset",
    40: "Bed leveling (high temp)",
    41: "Checking quick release",
    42: "Checking door and cover",
    43: "Laser calibration",
    44: "Checking platform",
    45: "Checking camera position",
    46: "Calibrating camera",
    47: "Bed leveling phase 1",
    48: "Bed leveling phase 2",
    49: "Heating chamber",
    50: "Cooling heatbed",
    51: "Printing calibration lines",
    52: "Checking material",
    53: "Live view camera calibration",
    54: "Waiting for heatbed temp",
    55: "Checking material position",
    56: "Cutting module offset calibration",
    57: "Measuring surface",
    58: "Thermal preconditioning",
    59: "Homing blade holder",
    60: "Calibrating camera offset",
    61: "Calibrating blade holder",
    62: "Hotend pick and place test",
    63: "Waiting for chamber temp",
    64: "Preparing hotend",
    65: "Calibrating nozzle clump detection",
    66: "Purifying chamber air",
    77: "Preparing AMS",
    255: None,                          # idle
}

# Stage categories — groups stg_cur values by semantic meaning.
# Combined with layer_num to distinguish pre-print stages from mid-print interruptions.
STAGE_CATEGORIES = {
    # prepare — normal pre-print setup
    1: "prepare", 2: "prepare", 3: "prepare", 7: "prepare", 9: "prepare",
    11: "prepare", 13: "prepare", 14: "prepare", 15: "prepare", 29: "prepare",
    40: "prepare", 41: "prepare", 42: "prepare", 47: "prepare", 48: "prepare",
    49: "prepare", 50: "prepare", 51: "prepare", 52: "prepare", 54: "prepare",
    55: "prepare", 57: "prepare", 58: "prepare", 59: "prepare", 63: "prepare",
    64: "prepare", 66: "prepare", 77: "prepare",
    # calibrate — calibration/scanning steps
    8: "calibrate", 10: "calibrate", 12: "calibrate", 18: "calibrate",
    19: "calibrate", 25: "calibrate", 31: "calibrate", 36: "calibrate",
    37: "calibrate", 38: "calibrate", 39: "calibrate", 43: "calibrate",
    44: "calibrate", 45: "calibrate", 46: "calibrate", 53: "calibrate",
    56: "calibrate", 60: "calibrate", 61: "calibrate", 62: "calibrate",
    65: "calibrate",
    # paused — expected interruptions
    5: "paused", 16: "paused", 30: "paused",
    # filament — filament operations (context-dependent on layer_num)
    4: "filament", 22: "filament", 24: "filament",
    # issue — errors/malfunctions requiring attention
    6: "issue", 17: "issue", 20: "issue", 21: "issue", 23: "issue",
    26: "issue", 27: "issue", 28: "issue", 32: "issue", 33: "issue",
    34: "issue", 35: "issue",
}


class PrinterState:
    """Tracks current printer state"""
    def __init__(self):
        self.gcode_state: str = "UNKNOWN"
        self.stg_cur: int = -1          # current preparation stage
        self.progress: int = 0
        self.remaining_time_minutes: int = 0  # Bambu sends minutes
        self.job_name: str = ""
        self.layer_num: int = 0
        self.total_layers: int = 0
        self.nozzle_temp: int = 0
        self.nozzle_target_temp: int = 0
        self.bed_temp: int = 0
        self.bed_target_temp: int = 0
        self.chamber_temp: int = 0
        # For tracking changes
        self.last_sent_state: str = "UNKNOWN"
        self.last_sent_progress: int = -1
        self.last_sent_layer: int = -1
        self.last_sent_remaining: int = -1
        self.last_sent_bed_temp: int = -1
        self.last_sent_chamber_temp: int = -1
        self.last_sent_nozzle_temp: int = -1
        self.last_sent_stg_cur: int = -1

class BambuFCMBridge:
    def __init__(self):
        self.state = PrinterState()
        self.mqtt_client: Optional[mqtt.Client] = None
        self.firebase_app = None
        self.apns: Optional[APNsSender] = None
        self.token_listener = FirestoreTokenListener()
        self._apns_activity_active = False
        self._apns_ending = False
        self._init_firebase()
        self._init_apns()
        self.token_listener.start()

    def _init_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            cred = credentials.Certificate(FIREBASE_CREDENTIALS_FILE)
            self.firebase_app = firebase_admin.initialize_app(cred)
            logger.info("Firebase initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            logger.error("Make sure firebase-service-account.json exists!")
            raise

    def _init_apns(self):
        """Initialize APNs client for iOS Live Activities."""
        if not APNS_KEY_FILE or not APNS_TEAM_ID or not APNS_KEY_ID:
            logger.info("APNs not configured - iOS notifications disabled")
            return
        try:
            self.apns = APNsSender(
                key_file=APNS_KEY_FILE,
                key_id=APNS_KEY_ID,
                team_id=APNS_TEAM_ID,
                bundle_id=APNS_BUNDLE_ID,
                use_sandbox=APNS_USE_SANDBOX,
            )
        except FileNotFoundError:
            logger.error(f"APNs key file not found: {APNS_KEY_FILE}")
        except Exception as e:
            logger.error(f"Failed to initialize APNs: {e}")

    def _determine_state(self) -> tuple:
        """Determine notification state and stage category from printer state.

        Uses STAGE_CATEGORIES + layer_num to distinguish pre-print stages
        from mid-print interruptions.

        Returns:
            (state_str, category) where state_str is one of
            "completed", "cancelled", "starting", "paused", "issue", "printing", "idle"
            and category is "prepare"/"calibrate"/"paused"/"filament"/"issue" or None.
        """
        gcode = self.state.gcode_state
        stg = self.state.stg_cur
        layer = self.state.layer_num

        if gcode in ("FINISH", "COMPLETED"):
            return "completed", None
        if gcode in ("CANCELLED", "FAILED"):
            return "cancelled", None

        # Bambu Studio pause sends gcode_state "PAUSE"
        if gcode == "PAUSE":
            stage_name = PREPARATION_STAGES.get(stg)
            return "paused", STAGE_CATEGORIES.get(stg, "paused")

        category = STAGE_CATEGORIES.get(stg)
        stage_name = PREPARATION_STAGES.get(stg)

        # Pauses and issues are always interruptions, regardless of layer
        if category in ("paused", "issue"):
            return category, category

        # Prep/calibration/filament stages: use layer_num to determine context
        if category in ("prepare", "calibrate", "filament"):
            if gcode == "PREPARE" or (gcode in ("RUNNING", "PRINTING") and stage_name is not None):
                if layer >= 1:
                    # Mid-print interruption (e.g. AMS filament change at layer 50)
                    return "paused", category
                else:
                    # Normal pre-print stage
                    return "starting", category

        if gcode in ("RUNNING", "PRINTING"):
            return "printing", None

        return "idle", None

    def _build_content_state(self) -> dict:
        """Build the ContentState dict matching the iOS Swift struct."""
        state_str, category = self._determine_state()
        stage_name = PREPARATION_STAGES.get(self.state.stg_cur)

        return {
            "progress": self.state.progress,
            "remainingMinutes": self.state.remaining_time_minutes,
            "jobName": self.state.job_name,
            "layerNum": self.state.layer_num,
            "totalLayers": self.state.total_layers,
            "state": state_str,
            "prepareStage": stage_name or "",
            "stageCategory": category or "",
            "nozzleTemp": self.state.nozzle_temp,
            "bedTemp": self.state.bed_temp,
            "nozzleTargetTemp": self.state.nozzle_target_temp,
            "bedTargetTemp": self.state.bed_target_temp,
            "chamberTemp": self.state.chamber_temp,
        }

    def _send_apns_start(self):
        """Start a Live Activity on iOS via APNs push-to-start. Priority 10."""
        if not self.apns or not self.apns.enabled:
            return
        tokens = self.token_listener.push_to_start_tokens
        if not tokens:
            return

        now = int(time.time())
        content_state = self._build_content_state()
        payload = {
            "aps": {
                "timestamp": now,
                "event": "start",
                "content-state": content_state,
                "attributes-type": "PrinterAttributes",
                "attributes": {
                    "printerName": APNS_PRINTER_NAME,
                },
                "alert": {
                    "title": "Print Starting",
                    "body": self.state.job_name or "New print job",
                },
            }
        }
        for token in tokens:
            status = self.apns.send(token, payload, priority=10)
            if status == 410:
                self.token_listener.remove_expired_token(token)

    def _send_apns_update(self, priority: int = 5):
        """Update the Live Activity on iOS via APNs.

        Args:
            priority: 10 for state changes, 5 for routine progress (default).
        """
        if not self.apns or not self.apns.enabled:
            return
        tokens = self.token_listener.activity_push_tokens
        if not tokens:
            return

        now = int(time.time())
        content_state = self._build_content_state()
        payload = {
            "aps": {
                "timestamp": now,
                "event": "update",
                "content-state": content_state,
            }
        }
        for token in tokens:
            status = self.apns.send(token, payload, priority=priority)
            if status == 410:
                self.token_listener.remove_expired_token(token)

    def _send_apns_end(self, dismissal_seconds: int = 14400):
        """End the Live Activity on iOS via APNs. Priority 10."""
        if not self.apns or not self.apns.enabled:
            return
        tokens = self.token_listener.activity_push_tokens
        if not tokens:
            return

        now = int(time.time())
        content_state = self._build_content_state()
        payload = {
            "aps": {
                "timestamp": now,
                "event": "end",
                "content-state": content_state,
                "dismissal-date": now + dismissal_seconds,
            }
        }
        for token in tokens:
            status = self.apns.send(token, payload, priority=10)
            if status == 410:
                self.token_listener.remove_expired_token(token)

    def _end_apns_activity(self, dismissal_seconds: int = 14400):
        """End the Live Activity after showing the final state in the Dynamic Island."""
        self._send_apns_end(dismissal_seconds=dismissal_seconds)
        self._apns_activity_active = False
        self._apns_ending = False

    def send_fcm_notification(self, title: str, body: str, data: Dict[str, str]):
        """Send FCM data-only message to all registered devices.

        IMPORTANT: We send data-only (no 'notification' field) so that
        onMessageReceived() is ALWAYS called, even when app is in background.
        This allows us to create proper Live Notifications instead of
        Android's default notification display.
        """
        for token in FCM_DEVICE_TOKENS:
            if token == "YOUR_FCM_TOKEN_HERE":
                logger.warning("FCM token not configured! Update FCM_DEVICE_TOKENS")
                continue

            try:
                # Data-only message - no 'notification' field!
                # This ensures onMessageReceived() is always called
                message = messaging.Message(
                    data=data,  # Data-only payload
                    token=token,
                    android=messaging.AndroidConfig(
                        priority="high",  # Wake device from Doze
                        ttl=300,  # Message expires after 5 minutes
                    ),
                )

                response = messaging.send(message)
                logger.info(f"FCM sent successfully: {response}")

            except messaging.UnregisteredError:
                logger.error(f"FCM token is invalid/unregistered: {token[:20]}...")
            except Exception as e:
                logger.error(f"Failed to send FCM: {e}")

    def send_print_update(self):
        """Send print progress update via FCM and APNs"""
        now = time.time()
        state_str, category = self._determine_state()
        stage_name = PREPARATION_STAGES.get(self.state.stg_cur, "")

        # Map state to FCM notification type
        notification_type_map = {
            "completed": "completed",
            "cancelled": "cancelled",
            "starting": "starting",
            "paused": "paused",
            "issue": "issue",
            "printing": "progress",
            "idle": "idle",
        }
        notification_type = notification_type_map.get(state_str, "unknown")

        # Determine notification content
        if notification_type == "completed":
            title = "Print Complete!"
            body = f"{self.state.job_name or 'Print'} finished successfully"
        elif notification_type == "cancelled":
            title = "Print Cancelled"
            body = f"{self.state.job_name or 'Print'} was cancelled"
        elif notification_type == "starting":
            title = "Print Starting..."
            stage_desc = stage_name or "Preparing"
            body = f"{stage_desc}: {self.state.job_name or 'Print job'}"
        elif notification_type == "paused":
            title = "Print Paused"
            body = f"{stage_name or 'Paused'}: {self.state.job_name or 'Print job'}"
        elif notification_type == "issue":
            title = "Printer Issue"
            body = f"{stage_name or 'Issue'}: {self.state.job_name or 'Print job'}"
        elif notification_type == "progress":
            remaining = self._format_time(self.state.remaining_time_minutes)
            title = f"Printing: {self.state.progress}%"
            body = f"{self.state.job_name or 'Print'} - {remaining} remaining"
        elif notification_type == "idle":
            title = "Printer Idle"
            body = "Ready for next print"
        else:
            title = f"Printer: {self.state.gcode_state}"
            body = self.state.job_name or "Unknown state"

        # Data payload for the app
        data = {
            "type": notification_type,
            "gcode_state": self.state.gcode_state,
            "progress": str(self.state.progress),
            "remaining_minutes": str(self.state.remaining_time_minutes),
            "job_name": self.state.job_name,
            "layer_num": str(self.state.layer_num),
            "total_layers": str(self.state.total_layers),
            "nozzle_temp": str(self.state.nozzle_temp),
            "nozzle_target_temp": str(self.state.nozzle_target_temp),
            "bed_temp": str(self.state.bed_temp),
            "bed_target_temp": str(self.state.bed_target_temp),
            "chamber_temp": str(self.state.chamber_temp),
            "prepare_stage": stage_name or "",
            "stage_category": category or "",
            "timestamp": str(int(now)),
        }

        logger.info(f"Sending FCM: {notification_type} - {self.state.progress}%")
        self.send_fcm_notification(title, body, data)

        # Also send to iOS via APNs Live Activity
        if self.apns and self.apns.enabled:
            pts_count = len(self.token_listener.push_to_start_tokens)
            apt_count = len(self.token_listener.activity_push_tokens)

            if notification_type in ("starting", "paused", "issue"):
                if not self._apns_activity_active:
                    if pts_count > 0:
                        logger.info(f"APNs: starting Live Activity ({pts_count} push-to-start token(s))")
                        self._send_apns_start()  # always priority 10
                        self._apns_activity_active = True
                    else:
                        logger.warning("APNs: no push-to-start tokens in Firestore — cannot start Live Activity")
                else:
                    if apt_count > 0:
                        # Pauses and issues are important state changes (priority 10)
                        priority = 10 if notification_type in ("paused", "issue") else 5
                        self._send_apns_update(priority=priority)
                    else:
                        logger.debug("APNs: waiting for activity push token during PREPARE")
            elif notification_type == "progress":
                if not self._apns_activity_active:
                    if pts_count > 0:
                        logger.info(f"APNs: starting Live Activity (first progress, {pts_count} token(s))")
                        self._send_apns_start()  # always priority 10
                        self._apns_activity_active = True
                    else:
                        logger.warning("APNs: no push-to-start tokens — cannot start Live Activity")
                else:
                    if apt_count > 0:
                        self._send_apns_update(priority=5)  # routine progress update
                    else:
                        logger.warning("APNs: no activity push tokens yet — waiting for iOS app to provide one")
            elif notification_type in ("completed", "cancelled"):
                if self._apns_activity_active and not self._apns_ending:
                    # Send update so Dynamic Island shows completed/cancelled state
                    self._send_apns_update(priority=10)  # important state change
                    # End after a delay so the final state is visible in the Dynamic Island
                    self._apns_ending = True
                    delay = 5.0
                    threading.Timer(delay, self._end_apns_activity, args=[14400]).start()
                    logger.info(f"APNs: will end Live Activity in {delay:.0f}s")
            elif notification_type == "idle":
                if self._apns_activity_active and not self._apns_ending:
                    self._send_apns_end(dismissal_seconds=0)
                    self._apns_activity_active = False
        elif not self.apns:
            pass  # APNs not configured — silent

    def _format_time(self, minutes: int) -> str:
        """Format minutes to human readable string"""
        if minutes <= 0:
            return "<1m"
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"

    def on_mqtt_connect(self, client, userdata, flags, reason_code, properties):
        """Called when connected to Bambu MQTT (paho-mqtt v2 API)"""
        if reason_code == 0 or str(reason_code) == "Success":
            logger.info("=" * 50)
            logger.info("✅ Connected to Bambu MQTT successfully!")
            logger.info("=" * 50)

            # Subscribe to printer reports
            topic = f"device/{BAMBU_PRINTER_SERIAL}/report"
            client.subscribe(topic)
            logger.info(f"Subscribed to: {topic}")

            # Request current state
            self._request_push_all(client)

            # Send test notification on startup
            self._send_startup_notification()
        else:
            logger.error(f"Bambu MQTT connection failed with code: {reason_code}")

    def _send_startup_notification(self):
        """Send a test notification when server starts"""
        logger.info("Sending startup test notification...")
        data = {
            "type": "startup",
            "gcode_state": "IDLE",
            "progress": "0",
            "remaining_minutes": "0",
            "job_name": "",
            "layer_num": "0",
            "total_layers": "0",
            "timestamp": str(int(time.time())),
        }
        self.send_fcm_notification(
            "🖨️ Server Started",
            f"Bambu FCM Bridge connected to printer {BAMBU_PRINTER_SERIAL}",
            data
        )

    def on_mqtt_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        """Called when disconnected from Bambu MQTT (paho-mqtt v2 API)"""
        if reason_code != 0:
            logger.warning(f"Disconnected from Bambu MQTT (rc={reason_code}). Will reconnect...")

    def on_mqtt_message(self, client, userdata, msg):
        """Called when message received from Bambu printer"""
        try:
            raw = msg.payload.decode()

            # Skip empty or tiny messages
            if len(raw) < 10:
                return

            payload = json.loads(raw)

            if "print" in payload:
                print_data = payload["print"]
                updated = False

                if "gcode_state" in print_data:
                    self.state.gcode_state = print_data["gcode_state"]
                    updated = True

                if "mc_percent" in print_data:
                    self.state.progress = print_data["mc_percent"]
                    updated = True

                if "mc_remaining_time" in print_data:
                    self.state.remaining_time_minutes = print_data["mc_remaining_time"]
                    updated = True

                if "nozzle_temper" in print_data:
                    self.state.nozzle_temp = print_data["nozzle_temper"]
                    updated = True

                if "nozzle_target_temper" in print_data:
                    self.state.nozzle_target_temp = print_data["nozzle_target_temper"]
                    updated = True

                if "bed_temper" in print_data:
                    self.state.bed_temp = print_data["bed_temper"]
                    updated = True

                if "bed_target_temper" in print_data:
                    self.state.bed_target_temp = print_data["bed_target_temper"]
                    updated = True

                # Chamber temp: newer firmware (P2S, H2, X1E) uses CTC path
                ctc_temp = print_data.get("device", {}).get("ctc", {}).get("info", {}).get("temp", None)
                if ctc_temp is not None:
                    self.state.chamber_temp = ctc_temp & 0xFFFF
                    updated = True
                elif "chamber_temper" in print_data:
                    self.state.chamber_temp = round(print_data["chamber_temper"])
                    updated = True

                if "stg_cur" in print_data:
                    self.state.stg_cur = print_data["stg_cur"]
                    updated = True

                if "subtask_name" in print_data:
                    self.state.job_name = print_data["subtask_name"]
                    updated = True

                if "layer_num" in print_data:
                    self.state.layer_num = print_data["layer_num"]
                    updated = True

                if "total_layer_num" in print_data:
                    self.state.total_layers = print_data["total_layer_num"]
                    updated = True

                # Also check nested "3D" object for layer info
                if "3D" in print_data:
                    if "layer_num" in print_data["3D"]:
                        self.state.layer_num = print_data["3D"]["layer_num"]
                        updated = True
                    if "total_layer_num" in print_data["3D"]:
                        self.state.total_layers = print_data["3D"]["total_layer_num"]
                        updated = True

                # Always print status update when we have data (like reference script)
                if updated:
                    self._print_status_update()

                    # Only send FCM if meaningful data changed
                    should_send = self._has_meaningful_change()
                    if should_send:
                        self.send_print_update()
                        # Update last sent values
                        self.state.last_sent_state = self.state.gcode_state
                        self.state.last_sent_progress = self.state.progress
                        self.state.last_sent_layer = self.state.layer_num
                        self.state.last_sent_remaining = self.state.remaining_time_minutes
                        self.state.last_sent_bed_temp = self.state.bed_temp
                        self.state.last_sent_chamber_temp = self.state.chamber_temp
                        self.state.last_sent_nozzle_temp = self.state.nozzle_temp
                        self.state.last_sent_stg_cur = self.state.stg_cur
                    else:
                        print(f"         ↳ Skipping notification (no change)")

        except json.JSONDecodeError:
            logger.error("Failed to parse MQTT message")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def _print_status_update(self):
        """Print formatted status update to console (like reference script)"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Format remaining time (mc_remaining_time is in minutes)
        remaining = self.state.remaining_time_minutes
        hours = remaining // 60
        mins = remaining % 60
        time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

        # Show preparation substage if active
        stg_name = PREPARATION_STAGES.get(self.state.stg_cur)
        stage_str = f" [{stg_name}]" if stg_name else ""

        # Print formatted update (same format as reference script)
        print(f"[{timestamp}] 📊 {self.state.job_name or 'Unknown'} | "
              f"{self.state.gcode_state}{stage_str} | "
              f"{self.state.progress}% | "
              f"Layer {self.state.layer_num}/{self.state.total_layers} | "
              f"ETA: {time_str} | "
              f"Nozzle: {self.state.nozzle_temp}°C | "
              f"Bed: {self.state.bed_temp}°C | "
              f"Chamber: {self.state.chamber_temp}°C")

    def _has_meaningful_change(self) -> bool:
        """Check if state has changed enough to warrant sending FCM"""
        # APNs Live Activity not started yet — keep retrying so we pick up
        # running prints after a server restart (tokens may not be loaded yet)
        if (self.apns and self.apns.enabled and not self._apns_activity_active
                and self.state.gcode_state in ("RUNNING", "PRINTING", "PREPARE", "PAUSE")):
            print(f"         ↳ APNs activity not started yet — retrying")
            return True

        # State change (IDLE -> RUNNING, RUNNING -> FINISH, etc.) - always send
        if self.state.gcode_state != self.state.last_sent_state:
            print(f"         ↳ State changed: {self.state.last_sent_state} -> {self.state.gcode_state}")
            return True

        # Progress change - send on each percent change
        if self.state.progress != self.state.last_sent_progress:
            print(f"         ↳ Progress changed: {self.state.last_sent_progress}% -> {self.state.progress}%")
            return True

        # Layer change - send when layer advances
        if self.state.layer_num != self.state.last_sent_layer:
            print(f"         ↳ Layer changed: {self.state.last_sent_layer} -> {self.state.layer_num}")
            return True

        # ETA change
        if self.state.remaining_time_minutes != self.state.last_sent_remaining:
            print(f"         ↳ ETA changed: {self.state.last_sent_remaining}m -> {self.state.remaining_time_minutes}m")
            return True

        # Bed temp change
        if self.state.bed_temp != self.state.last_sent_bed_temp:
            print(f"         ↳ Bed temp changed: {self.state.last_sent_bed_temp}°C -> {self.state.bed_temp}°C")
            return True

        # Chamber temp change
        if self.state.chamber_temp != self.state.last_sent_chamber_temp:
            print(f"         ↳ Chamber temp changed: {self.state.last_sent_chamber_temp}°C -> {self.state.chamber_temp}°C")
            return True

        # Nozzle temp change - only if >3°C difference
        if abs(self.state.nozzle_temp - self.state.last_sent_nozzle_temp) > 3:
            print(f"         ↳ Nozzle temp changed: {self.state.last_sent_nozzle_temp}°C -> {self.state.nozzle_temp}°C")
            return True

        # Preparation substage change (e.g. homing → bed leveling → calibrating)
        if self.state.stg_cur != self.state.last_sent_stg_cur:
            old_name = PREPARATION_STAGES.get(self.state.last_sent_stg_cur, str(self.state.last_sent_stg_cur))
            new_name = PREPARATION_STAGES.get(self.state.stg_cur, str(self.state.stg_cur))
            print(f"         ↳ Prep stage changed: {old_name} -> {new_name}")
            return True

        # No meaningful change
        return False

    def on_mqtt_subscribe(self, client, userdata, mid, reason_codes, properties):
        """Called when subscription is confirmed (paho-mqtt v2 API)"""
        logger.info(f"Subscription confirmed (QoS: {reason_codes[0]})")
        logger.info("")
        logger.info("=" * 50)
        logger.info("WAITING FOR PRINTER UPDATES...")
        logger.info("=" * 50)
        logger.info("If printer is printing, you should see updates below.")
        logger.info("Press Ctrl+C to exit.")
        logger.info("=" * 50)
        logger.info("")

    def _request_push_all(self, client):
        """Request full state from printer"""
        topic = f"device/{BAMBU_PRINTER_SERIAL}/request"
        payload = json.dumps({
            "pushing": {
                "sequence_id": "0",
                "command": "pushall"
            }
        })
        client.publish(topic, payload)
        logger.info("Requested full state from printer")

    def run_test_mode(self):
        """Simulate a full print cycle (start → progress → complete) in ~25 seconds.

        Sends real FCM and APNs notifications without needing an actual print.
        Useful for verifying that notifications arrive correctly on all devices.
        """
        logger.info("=" * 50)
        logger.info("TEST MODE: Simulating a ~35-second print cycle...")
        logger.info("=" * 50)

        # Wait for Firestore tokens to load (they arrive asynchronously)
        if self.apns and self.apns.enabled:
            logger.info("Waiting for Firestore token sync...")
            for _ in range(10):
                if self.token_listener.has_tokens():
                    break
                time.sleep(1)

            pts = len(self.token_listener.push_to_start_tokens)
            apt = len(self.token_listener.activity_push_tokens)
            if pts > 0 or apt > 0:
                logger.info(f"Firestore tokens loaded: {pts} push-to-start, {apt} activity")
            else:
                logger.warning("No iOS tokens found in Firestore — iOS notifications will be skipped")

        fcm_count = len([t for t in FCM_DEVICE_TOKENS if t != "YOUR_FCM_TOKEN_HERE"])
        logger.info(f"Targets: {fcm_count} FCM device(s)")

        job_name = "Test Print"
        total_layers = 200
        target_nozzle = 220
        target_bed = 60

        # Reset tracking state
        self.state.last_sent_state = "UNKNOWN"
        self.state.last_sent_progress = -1
        self.state.last_sent_layer = -1
        self.state.last_sent_remaining = -1
        self.state.last_sent_bed_temp = -1
        self.state.last_sent_chamber_temp = -1
        self.state.last_sent_nozzle_temp = -1

        # Phase 1: PREPARE — heating, homing, calibrating (~12 seconds)
        logger.info("Phase 1/5: PREPARE (heating & calibrating)")
        self.state.gcode_state = "PREPARE"
        self.state.progress = 0
        self.state.layer_num = 0
        self.state.total_layers = total_layers
        self.state.remaining_time_minutes = 45
        self.state.job_name = job_name
        self.state.nozzle_temp = 25
        self.state.nozzle_target_temp = target_nozzle
        self.state.bed_temp = 25
        self.state.bed_target_temp = target_bed
        self.state.chamber_temp = 22

        # Simulate preparation substages in realistic Bambu print order:
        # 1. Homing → 2. Bed leveling → 3. Bed heating → 4. Hotend heating
        # → 5. Cleaning nozzle → 6. Calibrating extrusion
        prep_stages = [
            (13, "Homing toolhead"),
            (1, "Auto bed leveling"),
            (2, "Preheating heatbed"),
            (7, "Heating hotend"),
            (14, "Cleaning nozzle tip"),
            (8, "Calibrating extrusion"),
        ]
        for i, (stg_id, stg_name) in enumerate(prep_stages):
            self.state.stg_cur = stg_id
            # Ramp temperatures during preparation
            frac = (i + 1) / len(prep_stages)
            self.state.nozzle_temp = min(target_nozzle, int(25 + frac * (target_nozzle - 25)))
            self.state.bed_temp = min(target_bed, int(25 + frac * (target_bed - 25)))
            self.state.chamber_temp = int(22 + frac * 16)  # ramps ~22→38°C
            logger.info(f"  Prep stage: {stg_name} (stg_cur={stg_id})")
            self._print_status_update()
            self.send_print_update()
            self.state.last_sent_state = self.state.gcode_state
            self.state.last_sent_stg_cur = self.state.stg_cur
            time.sleep(2)

        # Phase 2: RUNNING — progress 0→40% (~4 seconds)
        logger.info("Phase 2/5: RUNNING (printing)")
        self.state.gcode_state = "RUNNING"
        self.state.stg_cur = 0  # stg_cur=0 means actual printing
        for pct in (20, 40):
            self.state.progress = pct
            self.state.layer_num = int(pct * total_layers / 100)
            self.state.remaining_time_minutes = max(0, int(45 * (1 - pct / 100)))
            self._print_status_update()
            self.send_print_update()
            self.state.last_sent_state = self.state.gcode_state
            self.state.last_sent_progress = self.state.progress
            self.state.last_sent_layer = self.state.layer_num
            self.state.last_sent_stg_cur = self.state.stg_cur
            time.sleep(2)

        # Phase 3: Mid-print filament change (paused state) (~3 seconds)
        logger.info("Phase 3/5: Mid-print filament change (paused)")
        self.state.stg_cur = 4  # Changing filament
        self._print_status_update()
        self.send_print_update()
        self.state.last_sent_stg_cur = self.state.stg_cur
        time.sleep(3)

        # Phase 3b: Mid-print nozzle clog (issue state) (~3 seconds)
        logger.info("Phase 3/5: Mid-print nozzle clog (issue)")
        self.state.stg_cur = 35  # Nozzle clog
        self._print_status_update()
        self.send_print_update()
        self.state.last_sent_stg_cur = self.state.stg_cur
        time.sleep(3)

        # Phase 4: Resume printing — progress 60→100% (~4 seconds)
        logger.info("Phase 4/5: RUNNING (resumed)")
        self.state.stg_cur = 0
        for pct in (60, 80, 100):
            self.state.progress = pct
            self.state.layer_num = int(pct * total_layers / 100)
            self.state.remaining_time_minutes = max(0, int(45 * (1 - pct / 100)))
            self._print_status_update()
            self.send_print_update()
            self.state.last_sent_state = self.state.gcode_state
            self.state.last_sent_progress = self.state.progress
            self.state.last_sent_layer = self.state.layer_num
            self.state.last_sent_stg_cur = self.state.stg_cur
            time.sleep(2)

        # Phase 5: FINISH — print complete (~3 seconds)
        logger.info("Phase 5/5: FINISH (completed)")
        self.state.gcode_state = "FINISH"
        self.state.progress = 100
        self.state.layer_num = total_layers
        self.state.remaining_time_minutes = 0
        self._print_status_update()
        self.send_print_update()
        # Wait for the delayed APNs end event (5s timer) to fire
        time.sleep(7)

        logger.info("=" * 50)
        logger.info("TEST MODE: Complete! Check your devices for notifications.")
        logger.info("=" * 50)

    def run(self):
        """Main run loop"""
        logger.info("=" * 50)
        logger.info("Bambu FCM Bridge Starting")
        logger.info(f"Printer: {BAMBU_PRINTER_SERIAL}")
        logger.info("Real-time mode: sending updates immediately")
        logger.info("=" * 50)

        # Setup MQTT client (same as working test_bambu_mqtt.py)
        client_id = f"bambu_fcm_bridge_{int(time.time())}"
        self.mqtt_client = mqtt.Client(
            client_id=client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )

        # Username format: "u_{USER_ID}" - this is critical!
        username = f"u_{BAMBU_USER_ID}"
        self.mqtt_client.username_pw_set(username, BAMBU_ACCESS_TOKEN)
        logger.info(f"Username: {username}")
        logger.info(f"Client ID: {client_id}")

        # TLS setup - same as working test (CERT_REQUIRED)
        self.mqtt_client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

        # Set callbacks
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        self.mqtt_client.on_message = self.on_mqtt_message
        self.mqtt_client.on_subscribe = self.on_mqtt_subscribe

        try:
            logger.info(f"Connecting to {BAMBU_MQTT_SERVER}:{BAMBU_MQTT_PORT}...")
            self.mqtt_client.connect(BAMBU_MQTT_SERVER, BAMBU_MQTT_PORT, keepalive=60)

            # Run forever
            self.mqtt_client.loop_forever()

        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.mqtt_client.disconnect()
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise


if __name__ == "__main__":
    bridge = BambuFCMBridge()
    if "--test" in sys.argv:
        bridge.run_test_mode()
    else:
        bridge.run()
