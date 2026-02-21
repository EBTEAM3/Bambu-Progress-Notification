# Bambu FCM Bridge Server Setup

This server maintains a persistent MQTT connection to your Bambu printer and sends
Firebase Cloud Messaging (FCM) push notifications to your Android app.

**Battery Impact on Phone: Near Zero** - The app only wakes when a push arrives.

---

## Step 1: Create Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com/)

2. Click **"Create a project"** (or "Add project")

3. Enter project name: `bambu-now-bar` (or any name you like)

4. Disable Google Analytics (not needed) → Click **Create Project**

5. Wait for project creation → Click **Continue**

---

## Step 2: Add Android App to Firebase

1. In Firebase Console, click the **Android icon** to add an Android app

2. Enter your Android package name: `com.elliot.bamboonowbar`

3. App nickname: `Bambu Now Bar`

4. Skip the SHA-1 certificate (not needed for FCM)

5. Click **Register app**

6. **Download `google-services.json`** → Click **Download google-services.json**

7. Place this file in your Android project:
   ```
   BambuNowBar/app/google-services.json
   ```

8. Click **Next** through the remaining steps

---

## Step 3: Get Server Credentials

1. In Firebase Console → Click **gear icon** → **Project settings**

2. Go to **Service accounts** tab

3. Click **"Generate new private key"**

4. Click **Generate key** → Downloads a JSON file

5. Rename this file to `firebase-service-account.json`

6. This file goes on your Linux server (next step)

---

## Step 4: Setup Linux Server

### Copy files to server:

```bash
# On your local machine, copy the server folder to your Linux server
scp -r server/* your_username@your_server:/home/your_username/bambu-fcm-bridge/
```

### On your Linux server:

```bash
# Navigate to the directory
cd /home/your_username/bambu-fcm-bridge/

# Install Python dependencies
pip3 install -r requirements.txt

# Make sure firebase-service-account.json is in this directory

# Test run (Ctrl+C to stop)
python3 bambu_fcm_bridge.py
```

---

## Step 5: Get FCM Token from Android App

1. Build and run the updated Android app

2. The app will print the FCM token to Logcat:
   ```
   D/FCMService: FCM Token: xxxxxxxx
   ```

3. Copy this token

4. Edit `bambu_fcm_bridge.py` on your server:
   ```python
   FCM_DEVICE_TOKENS = [
       "paste_your_token_here",
   ]
   ```

5. Restart the server script

---

## Step 6: Run as System Service (Optional but Recommended)

```bash
# Edit the service file with your username
nano bambu-fcm-bridge.service
# Replace YOUR_USERNAME with your actual username

# Copy to systemd
sudo cp bambu-fcm-bridge.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable bambu-fcm-bridge

# Start the service
sudo systemctl start bambu-fcm-bridge

# Check status
sudo systemctl status bambu-fcm-bridge

# View logs
journalctl -u bambu-fcm-bridge -f
```

---

## Testing

1. Start a print on your Bambu printer

2. Watch the server logs:
   ```bash
   journalctl -u bambu-fcm-bridge -f
   ```

3. You should see:
   ```
   INFO - State changed: IDLE -> PREPARE
   INFO - Sending FCM: starting - 0%
   INFO - FCM sent successfully: projects/...
   ```

4. Your phone should receive a notification!

---

## Troubleshooting

### "FCM token not configured"
- Get the token from Logcat and add it to the Python script

### "Failed to initialize Firebase"
- Make sure `firebase-service-account.json` exists in the same directory

### "Bambu MQTT connection failed"
- Check your Bambu credentials in the script
- Make sure port 8883 is not blocked by firewall

### No notifications received
- Check that the FCM token is correct
- Make sure the Android app has `google-services.json`
- Check Firebase Console → Cloud Messaging → check for errors

---

## Multiple Devices

To send notifications to multiple phones, add more tokens:

```python
FCM_DEVICE_TOKENS = [
    "token_for_phone_1",
    "token_for_phone_2",
    "token_for_tablet",
]
```

---

## Update Frequency

Adjust `PROGRESS_UPDATE_INTERVAL` in the Python script:

```python
PROGRESS_UPDATE_INTERVAL = 120  # 2 minutes (default)
PROGRESS_UPDATE_INTERVAL = 300  # 5 minutes (more battery saving)
PROGRESS_UPDATE_INTERVAL = 60   # 1 minute (more updates)
```

State changes (start, complete, cancel) are always sent immediately.
