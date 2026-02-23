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

    def send(self, device_token: str, payload_dict: dict) -> bool:
        """Send an APNs Live Activity notification."""
        if not self._enabled:
            return False
        try:
            auth = self._get_auth_token()
            topic = f"{self._bundle_id}.push-type.liveactivity"
            headers = {
                "authorization": f"bearer {auth}",
                "apns-push-type": "liveactivity",
                "apns-topic": topic,
                "apns-priority": "10",
            }
            url = f"{self._base_url}/3/device/{device_token}"
            response = self._client.post(url, json=payload_dict, headers=headers)
            if response.status_code == 200:
                logger.info(f"APNs sent to ...{device_token[-8:]}")
                return True
            else:
                logger.error(f"APNs error {response.status_code}: {response.text}")
                return False
        except Exception as e:
            logger.error(f"APNs send failed: {e}")
            return False


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


class PrinterState:
    """Tracks current printer state"""
    def __init__(self):
        self.gcode_state: str = "UNKNOWN"
        self.progress: int = 0
        self.remaining_time_minutes: int = 0  # Bambu sends minutes
        self.job_name: str = ""
        self.layer_num: int = 0
        self.total_layers: int = 0
        self.nozzle_temp: int = 0
        self.bed_temp: int = 0
        # For tracking changes
        self.last_sent_state: str = "UNKNOWN"
        self.last_sent_progress: int = -1
        self.last_sent_layer: int = -1

class BambuFCMBridge:
    def __init__(self):
        self.state = PrinterState()
        self.mqtt_client: Optional[mqtt.Client] = None
        self.firebase_app = None
        self.apns: Optional[APNsSender] = None
        self.token_listener = FirestoreTokenListener()
        self._apns_activity_active = False
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

    def _build_content_state(self) -> dict:
        """Build the ContentState dict matching the iOS Swift struct."""
        gcode = self.state.gcode_state
        if gcode in ("FINISH", "COMPLETED"):
            state_str = "completed"
        elif gcode in ("CANCELLED", "FAILED"):
            state_str = "cancelled"
        elif gcode == "PREPARE":
            state_str = "starting"
        elif gcode in ("RUNNING", "PRINTING"):
            state_str = "printing"
        else:
            state_str = "idle"

        return {
            "progress": self.state.progress,
            "remainingMinutes": self.state.remaining_time_minutes,
            "jobName": self.state.job_name,
            "layerNum": self.state.layer_num,
            "totalLayers": self.state.total_layers,
            "state": state_str,
        }

    def _send_apns_start(self):
        """Start a Live Activity on iOS via APNs push-to-start."""
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
            self.apns.send(token, payload)

    def _send_apns_update(self):
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
            self.apns.send(token, payload)

    def _send_apns_end(self, dismissal_seconds: int = 300):
        """End the Live Activity on iOS via APNs."""
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
            self.apns.send(token, payload)

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
        """Send print progress update via FCM"""
        now = time.time()

        # Check state type
        is_printing = self.state.gcode_state in ["RUNNING", "PRINTING", "PREPARE"]
        is_finished = self.state.gcode_state in ["FINISH", "COMPLETED"]
        is_cancelled = self.state.gcode_state in ["CANCELLED", "FAILED"]
        is_idle = self.state.gcode_state in ["IDLE", "UNKNOWN"]

        # Determine notification content
        if is_finished:
            title = "Print Complete!"
            body = f"{self.state.job_name or 'Print'} finished successfully"
            notification_type = "completed"
        elif is_cancelled:
            title = "Print Cancelled"
            body = f"{self.state.job_name or 'Print'} was cancelled"
            notification_type = "cancelled"
        elif self.state.gcode_state == "PREPARE":
            title = "Print Starting..."
            body = f"Preparing: {self.state.job_name or 'Print job'}"
            notification_type = "starting"
        elif is_printing:
            remaining = self._format_time(self.state.remaining_time_minutes)
            title = f"Printing: {self.state.progress}%"
            body = f"{self.state.job_name or 'Print'} - {remaining} remaining"
            notification_type = "progress"
        elif is_idle:
            # Send idle state too so app can clear notification
            title = "Printer Idle"
            body = "Ready for next print"
            notification_type = "idle"
        else:
            title = f"Printer: {self.state.gcode_state}"
            body = self.state.job_name or "Unknown state"
            notification_type = "unknown"

        # Data payload for the app
        data = {
            "type": notification_type,
            "gcode_state": self.state.gcode_state,
            "progress": str(self.state.progress),
            "remaining_minutes": str(self.state.remaining_time_minutes),
            "job_name": self.state.job_name,
            "layer_num": str(self.state.layer_num),
            "total_layers": str(self.state.total_layers),
            "timestamp": str(int(now)),
        }

        logger.info(f"Sending FCM: {notification_type} - {self.state.progress}%")
        self.send_fcm_notification(title, body, data)

        # Also send to iOS via APNs Live Activity
        if self.apns and self.apns.enabled:
            pts_count = len(self.token_listener.push_to_start_tokens)
            apt_count = len(self.token_listener.activity_push_tokens)

            if notification_type == "starting":
                if pts_count > 0:
                    logger.info(f"APNs: starting Live Activity ({pts_count} push-to-start token(s))")
                    self._send_apns_start()
                    self._apns_activity_active = True
                else:
                    logger.warning("APNs: no push-to-start tokens in Firestore — cannot start Live Activity")
            elif notification_type == "progress":
                if not self._apns_activity_active:
                    if pts_count > 0:
                        logger.info(f"APNs: starting Live Activity (first progress, {pts_count} token(s))")
                        self._send_apns_start()
                        self._apns_activity_active = True
                    else:
                        logger.warning("APNs: no push-to-start tokens — cannot start Live Activity")
                else:
                    if apt_count > 0:
                        self._send_apns_update()
                    else:
                        logger.warning("APNs: no activity push tokens yet — waiting for iOS app to provide one")
            elif notification_type in ("completed", "cancelled"):
                if self._apns_activity_active:
                    self._send_apns_end(dismissal_seconds=300)
                    self._apns_activity_active = False
            elif notification_type == "idle":
                if self._apns_activity_active:
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

                if "bed_temper" in print_data:
                    self.state.bed_temp = print_data["bed_temper"]
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

        # Print formatted update (same format as reference script)
        print(f"[{timestamp}] 📊 {self.state.job_name or 'Unknown'} | "
              f"{self.state.gcode_state} | "
              f"{self.state.progress}% | "
              f"Layer {self.state.layer_num}/{self.state.total_layers} | "
              f"ETA: {time_str} | "
              f"Nozzle: {self.state.nozzle_temp}°C | "
              f"Bed: {self.state.bed_temp}°C")

    def _has_meaningful_change(self) -> bool:
        """Check if state has changed enough to warrant sending FCM"""
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
    bridge.run()
