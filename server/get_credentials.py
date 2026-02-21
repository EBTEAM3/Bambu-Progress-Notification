#!/usr/bin/env python3
"""
Bambu Lab Credential Helper
----------------------------
Logs into your Bambu Lab account and retrieves the User ID and Access Token
needed for the MQTT connection.

Usage:
    python3 get_credentials.py

You will be prompted for your Bambu Lab email and password.
If 2FA is enabled, you'll be asked for the verification code sent to your email.

After running, copy the User ID and Access Token into your config.py file.
"""

import json
import sys

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library required.")
    print("Install it with: pip3 install requests")
    sys.exit(1)


def login_to_bambu():
    """Login to Bambu Cloud and retrieve MQTT credentials."""
    print()
    print("=" * 60)
    print("  Bambu Lab Credential Helper")
    print("=" * 60)
    print()

    email = input("Bambu Lab email: ").strip()
    password = input("Bambu Lab password: ").strip()

    if not email or not password:
        print("ERROR: Email and password are required.")
        return

    print()
    print("Logging in...")

    url = "https://api.bambulab.com/v1/user-service/user/login"
    headers = {"Content-Type": "application/json"}
    payload = {"account": email, "password": password}

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Check if 2FA is required
        if data.get("loginType") == "verifyCode" or "tfa" in str(data).lower():
            print("2FA required! Check your email for the verification code.")
            print()
            tfa_code = input("Enter verification code: ").strip()

            tfa_payload = {"account": email, "code": tfa_code}
            response = requests.post(url, json=tfa_payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            print("2FA verification successful!")
            print()

        if not data.get("accessToken"):
            print(f"ERROR: Login failed: {data.get('message', 'Unknown error')}")
            return

        access_token = data["accessToken"]

        # Try to get User ID from the API
        user_id = None
        try:
            pref_url = "https://api.bambulab.com/v1/design-user-service/my/preference"
            pref_headers = {"Authorization": f"Bearer {access_token}"}
            pref_response = requests.get(pref_url, headers=pref_headers)
            if pref_response.status_code == 200:
                pref_data = pref_response.json()
                user_id = pref_data.get("uid") or pref_data.get("id")
        except Exception:
            pass

        if not user_id:
            print("Could not retrieve User ID automatically.")
            print("You can find it in: Bambu Handy app > Settings > Account")
            user_id = input("Enter your User ID manually (or press Enter to skip): ").strip()

        # Display results
        print()
        print("=" * 60)
        print("  SUCCESS! Here are your credentials:")
        print("=" * 60)
        print()
        print(f"  BAMBU_USER_ID = \"{user_id}\"")
        print(f"  BAMBU_ACCESS_TOKEN = \"{access_token}\"")
        print()
        print("=" * 60)
        print()
        print("Copy these values into your config.py file.")
        print("You also need your printer's serial number -")
        print("find it in: Bambu Handy app > Printer > Settings > Serial Number")
        print()

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Network error: {e}")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    login_to_bambu()
