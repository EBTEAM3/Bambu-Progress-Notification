# BambuNowBar

Real-time 3D print progress on your **Samsung Galaxy lock screen** (Now Bar) and **iPhone lock screen & Dynamic Island** (Live Activities).

A lightweight Linux server monitors your Bambu Lab printer over MQTT and pushes live progress updates to your phone. On **Android**, it uses Firebase Cloud Messaging to display progress in Samsung's Now Bar. On **iOS**, it uses Apple's ActivityKit push notifications to display Live Activities on the lock screen and Dynamic Island — with zero battery drain on the phone.


## Android Pics
<img src="https://github.com/user-attachments/assets/714ecb8c-84b0-43eb-b0e8-9c4ec00fe628" width="20%"> <img src="https://github.com/user-attachments/assets/b98b7370-30fe-4da4-b973-d197064cadb5" width="20%"> <img src="https://github.com/user-attachments/assets/3e581f82-1d4a-4806-a0fd-cf53bccc10e7" width="20%">
<img src="https://github.com/user-attachments/assets/cb9ef2a8-3f96-46de-b592-081409a4c2a5" width="45%"> <img src="https://github.com/user-attachments/assets/696f20ce-59ab-47be-8266-dae7b04bb752" width="45%">

## IOS Pics
![554168342-d8e663c5-c912-442d-a839-f7aef2bfe3b7](https://github.com/user-attachments/assets/79ff2d50-722a-4fbc-9b8d-769655b44e9a)
![554168339-44872c56-7d6d-4625-ad2c-1f9283525624](https://github.com/user-attachments/assets/1ec3e649-9dbb-42a7-80d3-dda7defe973d)
![554168336-6a5a85b5-31d8-4bf6-b7b6-b78fe7cd3146](https://github.com/user-attachments/assets/f2dc2f88-4d85-4e53-88ae-13f93ef158ca)
![554168326-d581f78c-19e9-4422-b461-31bb615b524b](https://github.com/user-attachments/assets/bc5b7195-c0fd-4318-a865-71f78d8fc47a)



## How It Works

```
                                       ┌──FCM Push──> Android App ──> Now Bar (Samsung lock screen)
Bambu Printer ──MQTT──> Linux Server ──┤
     (24/7)              (Python)      └──APNs Push──> iOS App ──> Live Activity (Dynamic Island / lock screen)
```

1. **Linux server** maintains a persistent MQTT connection to Bambu Cloud
2. When the printer state changes (progress, layer, start, finish), the server sends push notifications
3. **Android**: FCM push → Now Bar live notification on Samsung lock screen
4. **iOS**: APNs push → Live Activity on lock screen & Dynamic Island
5. Your phone only wakes when a notification arrives - **near-zero battery impact**

## Features

- **Android**: Live progress bar in Samsung Now Bar, status bar chip, notification panel
- **iOS**: Live Activity on lock screen, Dynamic Island (compact, expanded, minimal)
- Progress, ETA, layer info, and job name
- Start, complete, and cancel notifications
- Multi-device support (send to multiple phones, mix of Android and iOS)
- iOS tokens auto-sync via Firebase Firestore (no manual token copying for iOS)
- Runs as a systemd service for 24/7 operation

## Requirements

- **Android Phone**: Samsung Galaxy with One UI 8 (Android 16) for Now Bar support
  - Older Android versions get standard progress notifications instead
- **iPhone**: Any iPhone with iOS 18+ (Dynamic Island requires iPhone 14 Pro or newer)
- **Printer**: Any Bambu Lab printer connected to Bambu Cloud (X1C, P1S, P1P, A1, A1 Mini, etc.)
- **Server**: Any always-on Linux machine (Raspberry Pi, home server, VPS, WSL, etc.)
- **Accounts**: Bambu Lab account, Google/Firebase account (free tier)

### iOS Requires a Paid Apple Developer Account ($99/year)

Android works out of the box — you build the APK, sideload it, done.

iOS is different. The way Live Activities work on iPhone, your server needs to send push notifications through Apple's Push Notification service (APNs) to start, update, and end the Live Activity on your lock screen and Dynamic Island. There is no local alternative — Apple requires all Live Activity updates from a server to go through APNs.

To authenticate with APNs, your server needs a `.p8` key file that can only be generated with a paid Apple Developer Program membership. A free Apple ID is not enough — Apple does not grant push notification capabilities to free accounts. This is an Apple platform restriction, not a limitation of this project.

**What the $99/year gets you:**
- A `.p8` APNs authentication key (needed for the server to send Live Activity pushes)
- The ability to sign the app and install it on your iPhone without 7-day expiry
- Push notification entitlements required by the app

**Without it**, the iOS app will build and install via Xcode, but the server cannot send push notifications, so Live Activities will never appear. The Android side is completely unaffected and works without any paid memberships.

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

### Part 2.5: Apple Developer Setup (iOS only)

Skip this section if you only have an Android device.

#### Step 1: Create an APNs Key

1. Go to [developer.apple.com](https://developer.apple.com/) and sign in
2. Navigate to **Certificates, Identifiers & Keys** > **Keys**
3. Click the **+** button to create a new key
4. Enter a name (e.g., `BambuNowBar APNs Key`)
5. Check **Apple Push Notifications service (APNs)**
6. Click **Continue**, then **Register**
7. **Download the `.p8` file** — you can only download this once!
8. Note the **Key ID** shown on the page (10-character string)

> **Environment note**: When creating the key, select **Sandbox** environment. This matches the `aps-environment = development` entitlement used by debug builds in Xcode and the `APNS_USE_SANDBOX = True` server setting. Apple uses different names for the same thing: "Sandbox" (APNs/Developer Portal) = "development" (Xcode entitlements). When you later distribute via TestFlight or the App Store, switch to **Sandbox & Production** and set `APNS_USE_SANDBOX = False` on your server.

#### Step 2: Note Your Team ID

1. Go to [developer.apple.com/account](https://developer.apple.com/account)
2. Under **Membership details**, find your **Team ID** (10-character string)

#### Step 3: Place the Key File

Copy the `.p8` file to your server's `server/` directory:
```bash
scp ~/Downloads/AuthKey_XXXXXXXXXX.p8 your-server:~/BambuNowBar/server/
```

#### Step 4: Enable Firestore

Firestore is used to automatically sync iOS push tokens between the iOS app and your server.

1. In [Firebase Console](https://console.firebase.google.com/), select your project
2. In the left sidebar, click **Build** > **Firestore Database**
3. Click **Create database**
4. Choose **Start in production mode**, click **Next**
5. Select a location close to your server, click **Enable**
6. Go to the **Rules** tab and replace the rules with:
   ```
   rules_version = '2';
   service cloud.firestore {
     match /databases/{database}/documents {
       match /bambu_tokens/{deviceId} {
         allow read, write: if true;
       }
     }
   }
   ```
7. Click **Publish**

> **Note**: These open rules are suitable for personal use. For a more secure setup, use Firebase Authentication and restrict writes to authenticated users.

#### Step 5: Add iOS App to Firebase

1. In Firebase Console, click **Add app** > **iOS**
2. Enter the iOS bundle ID: `com.elliot.bamboonowbar`
3. App nickname: `Bambu Now Bar iOS`
4. Click **Register app**
5. **Download `GoogleService-Info.plist`**
6. Place this file in your iOS project at:
   ```
   ios/BambuNowBar/GoogleService-Info.plist
   ```
7. Click **Next** through the remaining steps (SDK is already configured in the project)

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
    "paste_token_from_android_app_here",
]

# iOS only (leave empty if you don't have an iOS device):
APNS_KEY_FILE = "AuthKey_XXXXXXXXXX.p8"
APNS_TEAM_ID = "YOUR_TEAM_ID"
APNS_KEY_ID = "YOUR_KEY_ID"
# APNS_USE_SANDBOX = True  # True for Xcode debug builds, False for TestFlight/App Store
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

### Part 5: iOS App Setup

Skip this section if you only have an Android device.

#### Prerequisites

| Component | Version |
|-----------|---------|
| Xcode | **16.0** or newer |
| iOS SDK | 18.0+ |
| XcodeGen | Latest (`brew install xcodegen`) |
| Apple Developer Account | Paid membership ($99/year) |

#### Build the App

```bash
# Install XcodeGen if you haven't already
brew install xcodegen

# Generate the Xcode project
cd ios
xcodegen

# Open in Xcode
open BambuNowBar.xcodeproj
```

1. In Xcode, select the **BambuNowBar** target
2. Under **Signing & Capabilities**, select your **Team** (Apple Developer account)
3. Do the same for the **BambuNowBarWidgets** target
4. Make sure `GoogleService-Info.plist` is in `ios/BambuNowBar/` (from Part 2.5, Step 5)
5. Build and run on a **physical iPhone** (Live Activities require a real device)

#### Verify Token Sync

1. Open the app on your iPhone
2. The app should show **Live Activities: Enabled**
3. The push-to-start token should appear and sync to Firestore automatically
4. Verify in [Firebase Console](https://console.firebase.google.com/) > **Firestore Database** > `bambu_tokens` collection

#### How It Works

Unlike Android where you manually copy the FCM token, iOS tokens are synced automatically:

1. The iOS app registers for push-to-start tokens with Apple
2. Tokens are written to Firebase Firestore automatically
3. Your server reads tokens from Firestore in real-time
4. When a print starts, the server sends an APNs push that starts the Live Activity
5. Progress updates are sent via APNs directly to the Live Activity
6. When the print ends, the Live Activity is dismissed

---

## Verifying Everything Works

1. Start the server (`python3 bambu_fcm_bridge.py` or via systemd)
2. **Android**: You should receive a **"Server Connected"** notification
3. **iOS**: Check the app shows "Firestore Sync: Synced" and a push-to-start token
4. Start a print on your Bambu printer
5. **Android**: Watch the Now Bar light up with live progress!
6. **iOS**: A Live Activity should appear on the lock screen and Dynamic Island

#### Test Mode

To verify notifications work without a real print, run:

```bash
cd server
python3 bambu_fcm_bridge.py --test
```

This simulates a full print cycle (start → progress → complete) in about 30 seconds, sending real notifications to all configured devices. No MQTT connection to the printer is needed.

---

## Multiple Devices

**Android**: Add more FCM tokens to `config.py`:

```python
FCM_DEVICE_TOKENS = [
    "token_for_phone_1",
    "token_for_phone_2",
    "token_for_tablet",
]
```

**iOS**: Multiple iPhones are supported automatically. Each iPhone that opens the app registers its push token in Firestore, and the server sends updates to all registered iOS devices.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "config.py not found!" | Copy `config.example.py` to `config.py` and fill in your values |
| "Failed to initialize Firebase" | Make sure `firebase-service-account.json` exists in the server directory |
| "Bambu MQTT connection failed" | Check your Bambu credentials. Make sure port 8883 is not blocked by your firewall |
| "FCM token not configured" | Copy the FCM token from the Android app and paste it into `config.py` |
| No Android notifications | 1. Check FCM token is correct 2. Ensure `google-services.json` is in the app 3. Check Firebase Console for errors |
| Now Bar not showing | Enable "Live notifications for all apps" in Developer Options |
| No iOS Live Activity | 1. Check APNs config in `config.py` 2. Ensure `.p8` key file is in `server/` 3. Check Firestore for tokens 4. Verify Live Activities enabled in iOS Settings |
| iOS token not syncing | 1. Check `GoogleService-Info.plist` is in the iOS project 2. Verify Firestore is enabled in Firebase Console 3. Check Firestore security rules |
| "APNs error 403" | Your `.p8` key may be invalid or revoked. Generate a new one in Apple Developer portal |
| Server disconnects frequently | This is normal - the MQTT client auto-reconnects. Check your network stability |

---

## FilamentTracker Integration (Optional)

If you also want filament tracking, clone the [FilamentTracker](https://github.com/EBTEAM3/Bambu-Filament-Tracker) repo as a sibling folder:

```
YourFolder/
  BambuNowBar/         ← this repo
  FilamentTracker/     ← clone here
```

Then set `ENABLE_FILAMENT_TRACKER = True` in your `config.py`. Both services will share a single MQTT connection.

See the [FilamentTracker README](https://github.com/EBTEAM3/Bambu-Filament-Tracker) for more details.

---

## Project Structure

```
BambuNowBar/
├── app/                              # Android app
│   ├── google-services.json          # Firebase config (NOT in repo)
│   └── src/main/java/.../
│       ├── MainActivity.kt           # Main UI
│       ├── BambuFCMService.kt        # Receives FCM push notifications
│       ├── LiveUpdateManager.kt      # Creates Now Bar live notifications
│       └── ...
├── ios/                              # iOS app
│   ├── project.yml                   # XcodeGen project spec
│   ├── BambuNowBar/                  # Main app target
│   │   ├── BambuNowBarApp.swift      # App entry point
│   │   ├── ContentView.swift         # Status UI
│   │   ├── TokenManager.swift        # Firestore token sync
│   │   └── GoogleService-Info.plist  # Firebase config (NOT in repo)
│   ├── Shared/
│   │   └── PrinterAttributes.swift   # Live Activity data model
│   └── BambuNowBarWidgets/           # Widget extension (Live Activity)
│       ├── PrinterActivityLiveActivity.swift  # All Live Activity views
│       └── BambuNowBarWidgetsBundle.swift
├── server/                           # Linux server
│   ├── bambu_mqtt.py                 # Shared MQTT module (printer state + callbacks)
│   ├── bambu_fcm_bridge.py           # Notification service (FCM + APNs)
│   ├── get_credentials.py            # Bambu credential helper
│   ├── config.example.py             # Configuration template
│   ├── config.py                     # Your config (NOT in repo)
│   ├── firebase-service-account.json # Firebase credentials (NOT in repo)
│   ├── AuthKey_*.p8                  # APNs key (NOT in repo)
│   ├── bambu-fcm-bridge.service      # systemd service file
│   └── requirements.txt              # Python dependencies
└── README.md
```

---

## Security Notes

- `config.py`, `google-services.json`, `GoogleService-Info.plist`, `firebase-service-account.json`, and APNs `.p8` keys are all `.gitignore`'d and will never be committed
- Never share your Bambu access token - it grants full access to your printer
- The Firebase service account key and APNs `.p8` key should be kept private
- FCM tokens are device-specific and rotate periodically
- iOS push tokens are synced via Firestore with open rules for simplicity — suitable for personal use

---

## License

MIT




