# BambuNowBar

Real-time 3D print progress on your Samsung Galaxy lock screen via the **Now Bar** (One UI 8 / Android 16 Live Notifications).

A lightweight Linux server monitors your Bambu Lab printer over MQTT and pushes live progress updates to your phone via Firebase Cloud Messaging. Your phone displays print progress as a **Live Notification** in the Samsung Now Bar - visible on the lock screen, status bar, and notification panel - with zero battery drain on the phone.

![Screenshot_20260222_221152_One UI Home](https://github.com/user-attachments/assets/714ecb8c-84b0-43eb-b0e8-9c4ec00fe628)
![Screenshot_20260222_221151_One UI Home](https://github.com/user-attachments/assets/b98b7370-30fe-4da4-b973-d197064cadb5)
![Screenshot_20260222_221146_One UI Home](https://github.com/user-attachments/assets/cb9ef2a8-3f96-46de-b592-081409a4c2a5)
![Screenshot_20260222_221143_One UI Home](https://github.com/user-attachments/assets/696f20ce-59ab-47be-8266-dae7b04bb752)
![Screenshot_20260222_221127_One UI Home](https://github.com/user-attachments/assets/3e581f82-1d4a-4806-a0fd-cf53bccc10e7)


## How It Works

```
Bambu Printer ──MQTT──> Linux Server ──FCM Push──> Android App ──> Now Bar
     (24/7)              (Python)        (wake only)           (lock screen)
```

1. **Linux server** maintains a persistent MQTT connection to Bambu Cloud
2. When the printer state changes (progress, layer, start, finish), the server sends a **Firebase Cloud Messaging** push notification
3. The Android app receives the push, creates a **Live Notification** that appears in Samsung's Now Bar
4. Your phone only wakes when a notification arrives - **near-zero battery impact**

## Features

- Live progress bar on the Samsung Now Bar (lock screen bottom)
- Status bar chip showing current percentage
- Progress, ETA, layer info, and job name
- Start, complete, and cancel notifications
- Multi-device support (send to multiple phones)
- Runs as a systemd service for 24/7 operation

## Requirements

- **Phone**: Samsung Galaxy with One UI 8 (Android 16) for Now Bar support
  - Older Android versions get standard progress notifications instead
- **Printer**: Any Bambu Lab printer connected to Bambu Cloud (X1C, P1S, P1P, A1, A1 Mini, etc.)
- **Server**: Any always-on Linux machine (Raspberry Pi, home server, VPS, WSL, etc.)
- **Accounts**: Bambu Lab account, Google/Firebase account (free tier)

---

## Setup Guide

### Part 1: Finding Your Bambu Credentials

You need three pieces of information from your Bambu Lab account:

#### 1. Printer Serial Number

Your printer's serial number is printed on a sticker on the printer itself. You can also find it in:
- **Bambu Handy app** > tap your printer > Settings (gear icon) > scroll to "Serial Number"
- **Bambu Studio** > Device tab > click your printer > Info

It looks like: `01S00C123456789` or `01P00A123456789`

#### 2. User ID and Access Token

These come from your Bambu Lab account. A helper script is included that handles the login and 2FA for you.

**Method A - Credential Helper Script (Recommended)**

```bash
cd server
pip3 install requests
python3 get_credentials.py
```

The script will:
1. Prompt for your Bambu Lab email and password
2. Handle 2FA verification (sends a code to your email)
3. Output your **User ID** and **Access Token** ready to paste into `config.py`

**Method B - Bambu Studio Config Files**

1. Open **Bambu Studio** on your computer and make sure you're logged in
2. Navigate to the config directory:
   - **Windows**: `%APPDATA%\BambuStudio\`
   - **macOS**: `~/Library/Application Support/BambuStudio/`
   - **Linux**: `~/.config/BambuStudio/`
3. Look inside the most recently modified folder - search for files containing your email address
4. Your **User ID** is the numeric ID associated with your account
5. Your **Access Token** starts with `AAD` and is a long string

#### MQTT Server Region

| Region | Server |
|--------|--------|
| Global (most users) | `us.mqtt.bambulab.com` |
| China | `cn.mqtt.bambulab.com` |

---

### Part 2: Firebase Setup

Firebase Cloud Messaging (FCM) is free and handles delivering push notifications from your server to your phone.

#### Step 1: Create Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click **"Create a project"** (or "Add project")
3. Enter a project name (e.g., `bambu-now-bar`)
4. Disable Google Analytics (not needed) and click **Create Project**
5. Wait for project creation and click **Continue**

#### Step 2: Add Android App to Firebase

1. In Firebase Console, click the **Android icon** to add an Android app
2. Enter the Android package name: `com.elliot.bamboonowbar`
3. App nickname: `Bambu Now Bar`
4. Skip the SHA-1 certificate (not needed for FCM)
5. Click **Register app**
6. **Download `google-services.json`**
7. Place this file in your Android project at:
   ```
   BambuNowBar/app/google-services.json
   ```
8. Click **Next** through the remaining steps

#### Step 3: Get Server Credentials

1. In Firebase Console, click the **gear icon** next to "Project Overview" and select **Project settings**
2. Go to the **Service accounts** tab
3. Click **"Generate new private key"**
4. Click **Generate key** - this downloads a JSON file
5. Rename this file to `firebase-service-account.json`
6. This file goes on your Linux server (next step)

---

### Part 3: Server Setup

#### Install Dependencies

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/BambuNowBar.git
cd BambuNowBar/server

# Install Python dependencies
pip3 install -r requirements.txt
```

#### Configure

```bash
# Create your config from the template
cp config.example.py config.py

# Edit with your values
nano config.py
```

Fill in your `config.py`:
```python
BAMBU_USER_ID = "YOUR_NUMERIC_USER_ID"
BAMBU_ACCESS_TOKEN = "YOUR_AAD_TOKEN_HERE"
BAMBU_PRINTER_SERIAL = "YOUR_PRINTER_SERIAL"
FCM_DEVICE_TOKENS = [
    "paste_token_from_app_here",
]
```

#### Place Firebase Credentials

Copy the `firebase-service-account.json` file you downloaded earlier into the `server/` directory.

#### Test Run

```bash
python3 bambu_fcm_bridge.py
```

You should see:
```
Firebase initialized successfully
Bambu FCM Bridge Starting
Connected to Bambu MQTT successfully!
Sending startup test notification...
FCM sent successfully: projects/...
WAITING FOR PRINTER UPDATES...
```

#### Run as System Service (Recommended)

For 24/7 operation, set up a systemd service:

```bash
# Edit the service file with your username
nano bambu-fcm-bridge.service
# Replace YOUR_USERNAME with your actual Linux username

# Copy to systemd
sudo cp bambu-fcm-bridge.service /etc/systemd/system/

# Enable auto-start on boot
sudo systemctl daemon-reload
sudo systemctl enable bambu-fcm-bridge
sudo systemctl start bambu-fcm-bridge

# Check it's running
sudo systemctl status bambu-fcm-bridge

# View live logs
journalctl -u bambu-fcm-bridge -f
```

---

### Part 4: Android App Setup

#### Android Studio Requirements

This project targets **Android 16 (API 36)** which is currently in preview. You'll need a recent preview/canary version of Android Studio.

| Component | Version |
|-----------|---------|
| Android Studio | **Narwhal** or newer (canary/preview channel) |
| Android Gradle Plugin (AGP) | 9.0.0 |
| Gradle | 9.1.0 |
| Kotlin | 2.2.10 |
| JDK | 17 |
| compileSdk / targetSdk | 36 (Android 16) |
| minSdk | 34 (Android 14) |

#### Required SDK Components

In Android Studio, open **SDK Manager** (Settings > Android SDK) and install:

1. **SDK Platforms** tab:
   - Android 16 (API 36) - including "Android SDK Platform 36"

2. **SDK Tools** tab:
   - Android SDK Build-Tools (latest)
   - Android SDK Platform-Tools

#### Build the App

1. Open the project in **Android Studio**
2. Make sure `app/google-services.json` is in place (from Part 2, Step 2)
3. Wait for Gradle sync to complete (may take a few minutes on first open)
4. If prompted to update AGP or Gradle, keep the versions as-is - the project is configured for specific versions
5. Build and install the app on your phone

#### Enable Now Bar

1. Open the app and grant **notification permission** when prompted
2. Go to **Settings > Lock screen > Now Bar** (or search for "Now Bar" in Settings)
3. Enable **Live notifications** for BambuNowBar
4. Optional: Go to **Developer Options** and enable **"Live notifications for all apps"** to ensure it works

#### Get FCM Token

1. In the app, tap **"Copy FCM Token"**
2. Paste this token into your server's `config.py` in the `FCM_DEVICE_TOKENS` list
3. Restart the server script

---

## Verifying Everything Works

1. Start the server (`python3 bambu_fcm_bridge.py` or via systemd)
2. You should receive a **"Server Connected"** notification on your phone
3. The app should show **"Server Active"** under the Copy FCM Token button
4. Start a print on your Bambu printer
5. Watch the Now Bar light up with live progress!

---

## Multiple Devices

Add more FCM tokens to `config.py` to send notifications to multiple phones:

```python
FCM_DEVICE_TOKENS = [
    "token_for_phone_1",
    "token_for_phone_2",
    "token_for_tablet",
]
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "config.py not found!" | Copy `config.example.py` to `config.py` and fill in your values |
| "Failed to initialize Firebase" | Make sure `firebase-service-account.json` exists in the server directory |
| "Bambu MQTT connection failed" | Check your Bambu credentials. Make sure port 8883 is not blocked by your firewall |
| "FCM token not configured" | Copy the FCM token from the app and paste it into `config.py` |
| No notifications received | 1. Check FCM token is correct 2. Ensure `google-services.json` is in the app 3. Check Firebase Console for errors |
| Now Bar not showing | Enable "Live notifications for all apps" in Developer Options |
| Server disconnects frequently | This is normal - the MQTT client auto-reconnects. Check your network stability |

---

## Project Structure

```
BambuNowBar/
├── app/                          # Android app
│   ├── google-services.json      # Firebase config (NOT in repo - you create this)
│   └── src/main/java/.../
│       ├── MainActivity.kt       # Main UI
│       ├── BambuFCMService.kt    # Receives FCM push notifications
│       ├── LiveUpdateManager.kt  # Creates Now Bar live notifications
│       └── ...
├── server/                       # Linux server
│   ├── bambu_fcm_bridge.py       # Main server script
│   ├── get_credentials.py        # Helper to retrieve Bambu User ID & Access Token
│   ├── config.example.py         # Configuration template
│   ├── config.py                 # Your config (NOT in repo - you create this)
│   ├── firebase-service-account.json  # Firebase credentials (NOT in repo)
│   ├── bambu-fcm-bridge.service  # systemd service file
│   └── requirements.txt          # Python dependencies
└── README.md
```

---

## Security Notes

- `config.py`, `google-services.json`, and `firebase-service-account.json` are all `.gitignore`'d and will never be committed
- Never share your Bambu access token - it grants full access to your printer
- The Firebase service account key should be kept private
- FCM tokens are device-specific and rotate periodically

---

## License

MIT

