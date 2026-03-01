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
# How to get: Open the BambuNowBar Android app -> tap "Copy FCM Token"
# You can add multiple device tokens for multi-device support
FCM_DEVICE_TOKENS = [
    "YOUR_FCM_TOKEN_HERE",
]

# =============================================================================
# iOS Live Activity (APNs) Configuration — OPTIONAL
# =============================================================================
# Leave these empty if you don't have an iOS device.
# iOS tokens are synced automatically via Firebase Firestore.
# See README section "Apple Developer Setup" for instructions.

# Path to your Apple Push Notification .p8 key file
# How to get: developer.apple.com -> Keys -> Create key with APNs enabled
APNS_KEY_FILE = ""  # e.g., "AuthKey_XXXXXXXXXX.p8"

# Your Apple Developer Team ID (10-character string)
# How to find: developer.apple.com -> Account -> Membership -> Team ID
APNS_TEAM_ID = ""  # e.g., "ABCDE12345"

# The Key ID for your .p8 key (10-character string)
# Shown when you create the key in Apple Developer portal
APNS_KEY_ID = ""  # e.g., "XXXXXXXXXX"

# Your iOS app's bundle ID (default matches the Xcode project)
APNS_BUNDLE_ID = "com.elliot.bamboonowbar"

# Use sandbox (True) for development builds, production (False) for TestFlight/App Store
APNS_USE_SANDBOX = True

# Printer name displayed in the iOS Live Activity
APNS_PRINTER_NAME = "Bambu Lab"
