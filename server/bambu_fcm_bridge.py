#!/usr/bin/env python3
"""
Bambu FCM Bridge Server — Notification Service
------------------------------------------------
Maintains persistent MQTT connection to Bambu Labs printer and sends
Firebase Cloud Messaging (FCM) push notifications to the Android app,
and ActivityKit push notifications (APNs) to the iOS app's Live Activities.

Uses the modular BambuMQTTClient from bambu_mqtt.py for the MQTT connection,
which can be shared with other services (e.g. FilamentTracker).

This runs on your Linux server 24/7.

Setup:
1. pip install -r requirements.txt
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

from bambu_mqtt import BambuMQTTClient, PrinterState, PREPARATION_STAGES, STAGE_CATEGORIES

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, messaging

# =============================================================================
# CONFIGURATION - loaded from config.py
# =============================================================================
try:
    import config as _config_module
except ImportError:
    print("ERROR: config.py not found!")
    print("Copy config.example.py to config.py and fill in your values:")
    print("  cp config.example.py config.py")
    sys.exit(1)

# MQTT settings (required)
BAMBU_MQTT_SERVER = getattr(_config_module, 'BAMBU_MQTT_SERVER', 'us.mqtt.bambulab.com')
BAMBU_MQTT_PORT = getattr(_config_module, 'BAMBU_MQTT_PORT', 8883)
BAMBU_USER_ID = getattr(_config_module, 'BAMBU_USER_ID', '')
BAMBU_ACCESS_TOKEN = getattr(_config_module, 'BAMBU_ACCESS_TOKEN', '')
BAMBU_PRINTER_SERIAL = getattr(_config_module, 'BAMBU_PRINTER_SERIAL', '')

# Firebase/FCM settings
FIREBASE_CREDENTIALS_FILE = getattr(_config_module, 'FIREBASE_CREDENTIALS_FILE', 'firebase-service-account.json')
FCM_DEVICE_TOKENS = getattr(_config_module, 'FCM_DEVICE_TOKENS', [])

# Optional iOS/APNs configuration
APNS_KEY_FILE = getattr(_config_module, 'APNS_KEY_FILE', '')
APNS_TEAM_ID = getattr(_config_module, 'APNS_TEAM_ID', '')
APNS_KEY_ID = getattr(_config_module, 'APNS_KEY_ID', '')
APNS_BUNDLE_ID = getattr(_config_module, 'APNS_BUNDLE_ID', 'com.elliot.bamboonowbar')
APNS_USE_SANDBOX = getattr(_config_module, 'APNS_USE_SANDBOX', True)
APNS_PRINTER_NAME = getattr(_config_module, 'APNS_PRINTER_NAME', 'Bambu Lab')

# Optional FilamentTracker (loaded from sibling folder)
ENABLE_FILAMENT_TRACKER = getattr(_config_module, 'ENABLE_FILAMENT_TRACKER', False)
FILAMENT_TRACKER_PORT = getattr(_config_module, 'FILAMENT_TRACKER_PORT', 5000)
FILAMENT_TRACKER_HOST = getattr(_config_module, 'FILAMENT_TRACKER_HOST', '0.0.0.0')
FILAMENT_LOW_ALERT_GRAMS = getattr(_config_module, 'FILAMENT_LOW_ALERT_GRAMS', 150)
FILAMENT_LOW_ALERT_FCM = getattr(_config_module, 'FILAMENT_LOW_ALERT_FCM', True)

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
                logger.warning(f"APNs 410 Gone - token expired: ...{device_token[-8:]}")
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
# BAMBU FCM BRIDGE - Notification service
# =============================================================================

class BambuFCMBridge:
    def __init__(self, mqtt_client: BambuMQTTClient):
        self.mqtt = mqtt_client
        self.firebase_app = None
        self.apns: Optional[APNsSender] = None
        self.token_listener = FirestoreTokenListener()
        self._apns_activity_active = False
        self._apns_ending = False
        self.filament_tracker = None

        # Track last sent values for change detection
        self._last_sent_state: str = "UNKNOWN"
        self._last_sent_progress: int = -1
        self._last_sent_layer: int = -1
        self._last_sent_remaining: int = -1
        self._last_sent_bed_temp: int = -1
        self._last_sent_chamber_temp: int = -1
        self._last_sent_nozzle_temp: int = -1
        self._last_sent_stg_cur: int = -1

        self._init_firebase()
        self._init_apns()
        if self.apns and self.apns.enabled:
            self.token_listener.start()

        # Register MQTT callbacks
        self.mqtt.on_print_update(self._on_print_update)
        self.mqtt.on_connect(self._on_connected)

    @property
    def state(self) -> PrinterState:
        """Proxy to the shared MQTT client's printer state."""
        return self.mqtt.state

    @property
    def mqtt_client(self):
        """Proxy to the underlying paho MQTT client (for connection status checks)."""
        return self.mqtt.mqtt_client

    def _on_connected(self):
        """Called when MQTT connects successfully."""
        self._send_startup_notification()

    def _on_print_update(self, print_data: dict):
        """Called when print state changes. Checks for meaningful changes and sends notifications."""
        if self._has_meaningful_change():
            self.send_print_update()
            # Update last sent values
            self._last_sent_state = self.state.gcode_state
            self._last_sent_progress = self.state.progress
            self._last_sent_layer = self.state.layer_num
            self._last_sent_remaining = self.state.remaining_time_minutes
            self._last_sent_bed_temp = self.state.bed_temp
            self._last_sent_chamber_temp = self.state.chamber_temp
            self._last_sent_nozzle_temp = self.state.nozzle_temp
            self._last_sent_stg_cur = self.state.stg_cur
        else:
            print(f"         -> Skipping notification (no change)")

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
        """Determine notification state and stage category from printer state."""
        gcode = self.state.gcode_state
        stg = self.state.stg_cur
        layer = self.state.layer_num

        if gcode in ("FINISH", "COMPLETED"):
            return "completed", None
        if gcode in ("CANCELLED", "FAILED"):
            return "cancelled", None

        if gcode == "PAUSE":
            return "paused", STAGE_CATEGORIES.get(stg, "paused")

        category = STAGE_CATEGORIES.get(stg)
        stage_name = PREPARATION_STAGES.get(stg)

        if category in ("paused", "issue"):
            return category, category

        if category in ("prepare", "calibrate", "filament"):
            if gcode == "PREPARE" or (gcode in ("RUNNING", "PRINTING") and stage_name is not None):
                if layer >= 1:
                    return "paused", category
                else:
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
        """Update the Live Activity on iOS via APNs."""
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
        """Send FCM data-only message to all registered devices."""
        for token in FCM_DEVICE_TOKENS:
            if token == "YOUR_FCM_TOKEN_HERE":
                logger.warning("FCM token not configured! Update FCM_DEVICE_TOKENS")
                continue

            try:
                message = messaging.Message(
                    data=data,
                    token=token,
                    android=messaging.AndroidConfig(
                        priority="high",
                        ttl=300,
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
                        self._send_apns_start()
                        self._apns_activity_active = True
                    else:
                        logger.warning("APNs: no push-to-start tokens in Firestore")
                else:
                    if apt_count > 0:
                        priority = 10 if notification_type in ("paused", "issue") else 5
                        self._send_apns_update(priority=priority)
                    else:
                        logger.debug("APNs: waiting for activity push token during PREPARE")
            elif notification_type == "progress":
                if not self._apns_activity_active:
                    if pts_count > 0:
                        logger.info(f"APNs: starting Live Activity (first progress, {pts_count} token(s))")
                        self._send_apns_start()
                        self._apns_activity_active = True
                    else:
                        logger.warning("APNs: no push-to-start tokens")
                else:
                    if apt_count > 0:
                        self._send_apns_update(priority=5)
                    else:
                        logger.warning("APNs: no activity push tokens yet")
            elif notification_type in ("completed", "cancelled"):
                if self._apns_activity_active and not self._apns_ending:
                    self._send_apns_update(priority=10)
                    self._apns_ending = True
                    delay = 5.0
                    threading.Timer(delay, self._end_apns_activity, args=[14400]).start()
                    logger.info(f"APNs: will end Live Activity in {delay:.0f}s")
            elif notification_type == "idle":
                if self._apns_activity_active and not self._apns_ending:
                    self._send_apns_end(dismissal_seconds=0)
                    self._apns_activity_active = False
        elif not self.apns:
            pass  # APNs not configured

    def _format_time(self, minutes: int) -> str:
        """Format minutes to human readable string"""
        if minutes <= 0:
            return "<1m"
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"

    def _has_meaningful_change(self) -> bool:
        """Check if state has changed enough to warrant sending FCM"""
        # Terminal states only need to be sent once
        if (self.state.gcode_state in ("FINISH", "COMPLETED", "CANCELLED", "FAILED", "IDLE")
                and self.state.gcode_state == self._last_sent_state):
            return False

        # APNs Live Activity not started yet - keep retrying
        if (self.apns and self.apns.enabled and not self._apns_activity_active
                and self.state.gcode_state in ("RUNNING", "PRINTING", "PREPARE", "PAUSE")):
            print(f"         -> APNs activity not started yet - retrying")
            return True

        # State change
        if self.state.gcode_state != self._last_sent_state:
            print(f"         -> State changed: {self._last_sent_state} -> {self.state.gcode_state}")
            return True

        # Progress change
        if self.state.progress != self._last_sent_progress:
            print(f"         -> Progress changed: {self._last_sent_progress}% -> {self.state.progress}%")
            return True

        # Layer change
        if self.state.layer_num != self._last_sent_layer:
            print(f"         -> Layer changed: {self._last_sent_layer} -> {self.state.layer_num}")
            return True

        # ETA change
        if self.state.remaining_time_minutes != self._last_sent_remaining:
            print(f"         -> ETA changed: {self._last_sent_remaining}m -> {self.state.remaining_time_minutes}m")
            return True

        # Bed temp change
        if self.state.bed_temp != self._last_sent_bed_temp:
            print(f"         -> Bed temp changed: {self._last_sent_bed_temp} C -> {self.state.bed_temp} C")
            return True

        # Chamber temp change
        if self.state.chamber_temp != self._last_sent_chamber_temp:
            print(f"         -> Chamber temp changed: {self._last_sent_chamber_temp} C -> {self.state.chamber_temp} C")
            return True

        # Nozzle temp change - only if >3 C difference
        if abs(self.state.nozzle_temp - self._last_sent_nozzle_temp) > 3:
            print(f"         -> Nozzle temp changed: {self._last_sent_nozzle_temp} C -> {self.state.nozzle_temp} C")
            return True

        # Preparation substage change
        if self.state.stg_cur != self._last_sent_stg_cur:
            old_name = PREPARATION_STAGES.get(self._last_sent_stg_cur, str(self._last_sent_stg_cur))
            new_name = PREPARATION_STAGES.get(self.state.stg_cur, str(self.state.stg_cur))
            print(f"         -> Prep stage changed: {old_name} -> {new_name}")
            return True

        return False

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
            "Server Started",
            f"Bambu FCM Bridge connected to printer {BAMBU_PRINTER_SERIAL}",
            data
        )

    def run_test_mode(self):
        """Simulate a full print cycle for testing notifications."""
        logger.info("=" * 50)
        logger.info("TEST MODE: Simulating a ~35-second print cycle...")
        logger.info("=" * 50)

        # Wait for Firestore tokens to load
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
                logger.warning("No iOS tokens found in Firestore")

        fcm_count = len([t for t in FCM_DEVICE_TOKENS if t != "YOUR_FCM_TOKEN_HERE"])
        logger.info(f"Targets: {fcm_count} FCM device(s)")

        job_name = "Test Print"
        total_layers = 200
        target_nozzle = 220
        target_bed = 60

        # Reset tracking state
        self._last_sent_state = "UNKNOWN"
        self._last_sent_progress = -1
        self._last_sent_layer = -1
        self._last_sent_remaining = -1
        self._last_sent_bed_temp = -1
        self._last_sent_chamber_temp = -1
        self._last_sent_nozzle_temp = -1
        self._last_sent_stg_cur = -1

        # Phase 1: PREPARE
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
            frac = (i + 1) / len(prep_stages)
            self.state.nozzle_temp = min(target_nozzle, int(25 + frac * (target_nozzle - 25)))
            self.state.bed_temp = min(target_bed, int(25 + frac * (target_bed - 25)))
            self.state.chamber_temp = int(22 + frac * 16)
            logger.info(f"  Prep stage: {stg_name} (stg_cur={stg_id})")
            self.mqtt.print_status()
            self.send_print_update()
            self._last_sent_state = self.state.gcode_state
            self._last_sent_stg_cur = self.state.stg_cur
            time.sleep(2)

        # Phase 2: RUNNING 0->40%
        logger.info("Phase 2/5: RUNNING (printing)")
        self.state.gcode_state = "RUNNING"
        self.state.stg_cur = 0
        for pct in (20, 40):
            self.state.progress = pct
            self.state.layer_num = int(pct * total_layers / 100)
            self.state.remaining_time_minutes = max(0, int(45 * (1 - pct / 100)))
            self.mqtt.print_status()
            self.send_print_update()
            self._last_sent_state = self.state.gcode_state
            self._last_sent_progress = self.state.progress
            self._last_sent_layer = self.state.layer_num
            self._last_sent_stg_cur = self.state.stg_cur
            time.sleep(2)

        # Phase 3: Mid-print filament change
        logger.info("Phase 3/5: Mid-print filament change (paused)")
        self.state.stg_cur = 4
        self.mqtt.print_status()
        self.send_print_update()
        self._last_sent_stg_cur = self.state.stg_cur
        time.sleep(3)

        # Phase 3b: Mid-print nozzle clog
        logger.info("Phase 3/5: Mid-print nozzle clog (issue)")
        self.state.stg_cur = 35
        self.mqtt.print_status()
        self.send_print_update()
        self._last_sent_stg_cur = self.state.stg_cur
        time.sleep(3)

        # Phase 4: Resume 60->100%
        logger.info("Phase 4/5: RUNNING (resumed)")
        self.state.stg_cur = 0
        for pct in (60, 80, 100):
            self.state.progress = pct
            self.state.layer_num = int(pct * total_layers / 100)
            self.state.remaining_time_minutes = max(0, int(45 * (1 - pct / 100)))
            self.mqtt.print_status()
            self.send_print_update()
            self._last_sent_state = self.state.gcode_state
            self._last_sent_progress = self.state.progress
            self._last_sent_layer = self.state.layer_num
            self._last_sent_stg_cur = self.state.stg_cur
            time.sleep(2)

        # Phase 5: FINISH
        logger.info("Phase 5/5: FINISH (completed)")
        self.state.gcode_state = "FINISH"
        self.state.progress = 100
        self.state.layer_num = total_layers
        self.state.remaining_time_minutes = 0
        self.mqtt.print_status()
        self.send_print_update()
        time.sleep(7)

        logger.info("=" * 50)
        logger.info("TEST MODE: Complete! Check your devices for notifications.")
        logger.info("=" * 50)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Validate required config
    if not BAMBU_USER_ID or not BAMBU_ACCESS_TOKEN or not BAMBU_PRINTER_SERIAL:
        logger.error("Missing required config: BAMBU_USER_ID, BAMBU_ACCESS_TOKEN, BAMBU_PRINTER_SERIAL")
        sys.exit(1)

    # Create shared MQTT client
    mqtt = BambuMQTTClient(
        BAMBU_MQTT_SERVER, BAMBU_MQTT_PORT,
        BAMBU_USER_ID, BAMBU_ACCESS_TOKEN, BAMBU_PRINTER_SERIAL
    )

    # Create notification service
    bridge = BambuFCMBridge(mqtt)

    # Optional: load FilamentTracker from sibling folder
    if ENABLE_FILAMENT_TRACKER:
        _server_dir = os.path.dirname(os.path.abspath(__file__))
        _tracker_path = os.path.normpath(os.path.join(_server_dir, '..', '..', 'FilamentTracker'))
        if os.path.isdir(_tracker_path):
            sys.path.insert(0, _tracker_path)
            try:
                from filament_tracker import FilamentTracker
                bridge.filament_tracker = FilamentTracker(
                    bridge=bridge,
                    port=FILAMENT_TRACKER_PORT,
                    host=FILAMENT_TRACKER_HOST,
                    low_alert_grams=FILAMENT_LOW_ALERT_GRAMS,
                    low_alert_fcm=FILAMENT_LOW_ALERT_FCM,
                )
                mqtt.on_ams_data(bridge.filament_tracker.update_ams_data)
                bridge.filament_tracker.start()
                logger.info(f"FilamentTracker loaded from {_tracker_path}")
            except ImportError as e:
                logger.error(f"Failed to import FilamentTracker: {e}")
                logger.error("Make sure flask is installed: pip install flask")
        else:
            logger.warning(f"ENABLE_FILAMENT_TRACKER is True but folder not found: {_tracker_path}")

    if "--test" in sys.argv:
        bridge.run_test_mode()
    else:
        logger.info("=" * 50)
        logger.info("Bambu FCM Bridge Starting")
        logger.info(f"Printer: {BAMBU_PRINTER_SERIAL}")
        logger.info("Real-time mode: sending updates immediately")
        logger.info("=" * 50)

        try:
            mqtt.run()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            mqtt.disconnect()
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise
