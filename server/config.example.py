# =============================================================================
# CONFIGURATION TEMPLATE
# =============================================================================
# Copy this file to config.py and fill in your values:
#   cp config.example.py config.py
#
# See the README for detailed instructions on finding each value.

# Bambu Cloud MQTT Configuration
# Server: "us.mqtt.bambulab.com" for most users, "cn.mqtt.bambulab.com" for China
BAMBU_MQTT_SERVER = "us.mqtt.bambulab.com"
BAMBU_MQTT_PORT = 8883

# Your Bambu Lab account user ID (numeric)
# How to find: See README section "Finding Your Bambu Credentials"
BAMBU_USER_ID = "YOUR_USER_ID_HERE"

# Your Bambu Lab access token
# How to find: See README section "Finding Your Bambu Credentials"
BAMBU_ACCESS_TOKEN = "YOUR_ACCESS_TOKEN_HERE"

# Your printer's serial number
# How to find: Bambu Handy app -> Printer settings, or printed on the printer itself
BAMBU_PRINTER_SERIAL = "YOUR_PRINTER_SERIAL_HERE"

# Path to your Firebase service account JSON file
# How to get: See README section "Firebase Setup"
FIREBASE_CREDENTIALS_FILE = "firebase-service-account.json"

# Your Android device's FCM token(s)
# How to get: Open the BambuNowBar app -> tap "Copy FCM Token"
# You can add multiple device tokens for multi-device support
FCM_DEVICE_TOKENS = [
    "YOUR_FCM_TOKEN_HERE",
]
