# =============================================================================
# CONFIGURATION TEMPLATE
# =============================================================================
# Copy this file to config.py and fill in your values:
#   cp config.example.py config.py
#
# This config file is compatible with both BambuNowBar and FilamentTracker.
# You can copy config.py between the two projects — each will use what it
# needs and ignore settings for the other.

# =============================================================================
# Bambu Cloud MQTT Configuration (required)
# =============================================================================
# Server: "us.mqtt.bambulab.com" for most users, "cn.mqtt.bambulab.com" for China
BAMBU_MQTT_SERVER = "us.mqtt.bambulab.com"
BAMBU_MQTT_PORT = 8883

# Your Bambu Lab account user ID (numeric)
# How to find: Run python3 get_credentials.py
BAMBU_USER_ID = "YOUR_USER_ID_HERE"

# Your Bambu Lab access token
BAMBU_ACCESS_TOKEN = "YOUR_ACCESS_TOKEN_HERE"

# Your printer's serial number
# How to find: Bambu Handy app -> Printer settings, or printed on the printer
BAMBU_PRINTER_SERIAL = "YOUR_PRINTER_SERIAL_HERE"

# =============================================================================
# Filament Tracker Settings
# =============================================================================
# These are used by the FilamentTracker service.
# If running BambuNowBar only, you can leave these as defaults.

FILAMENT_TRACKER_PORT = 5000
FILAMENT_TRACKER_HOST = "0.0.0.0"  # Listen on all interfaces

# Alert when a spool drops below this weight (grams). Set to 0 to disable.
FILAMENT_LOW_ALERT_GRAMS = 150

# Send FCM push notification when filament is low (requires notifications)
FILAMENT_LOW_ALERT_FCM = False

# =============================================================================
# Notification Service Settings (FCM / Firebase)
# =============================================================================
# These are used by the BambuNowBar notification service.
# If running FilamentTracker only, you can leave these as defaults.

# Path to your Firebase service account JSON file
FIREBASE_CREDENTIALS_FILE = "firebase-service-account.json"

# Your Android device's FCM token(s)
# How to get: Open the BambuNowBar Android app -> tap "Copy FCM Token"
FCM_DEVICE_TOKENS = [
    "YOUR_FCM_TOKEN_HERE",
]

# =============================================================================
# iOS Live Activity (APNs) Configuration — OPTIONAL
# =============================================================================
# Leave these empty if you don't have an iOS device.

APNS_KEY_FILE = ""          # e.g., "AuthKey_XXXXXXXXXX.p8"
APNS_TEAM_ID = ""           # e.g., "ABCDE12345"
APNS_KEY_ID = ""            # e.g., "XXXXXXXXXX"
APNS_BUNDLE_ID = "com.elliot.bamboonowbar"
APNS_USE_SANDBOX = True
APNS_PRINTER_NAME = "Bambu Lab"

# =============================================================================
# Cross-Service Integration — OPTIONAL
# =============================================================================
# If you have both BambuNowBar and FilamentTracker cloned as sibling folders:
#   YourFolder/
#     BambuNowBar/
#     FilamentTracker/
#
# You can enable the other service here to run both on a single MQTT connection.

# Set True in BambuNowBar to also run the filament tracker
ENABLE_FILAMENT_TRACKER = False

# Set True in FilamentTracker to also run the notification service
ENABLE_NOTIFICATIONS = False
