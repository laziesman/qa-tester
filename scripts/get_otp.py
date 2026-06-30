#!/usr/bin/env python3
"""
get_otp.py — ดึง OTP ล่าสุดจาก Django admin สำหรับ hr-stg login

Usage:
    python3 scripts/get_otp.py
    python3 scripts/get_otp.py --user nawaphan  # filter by username
"""

import sys, re, json, os, argparse
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APPS_JSON  = os.path.join(SCRIPT_DIR, "..", "apps.json")

def load_admin_creds():
    with open(APPS_JSON, encoding="utf-8") as f:
        apps = json.load(f)
    hr = apps["apps"]["hrfi"]
    return hr["admin_url"], hr["admin_username"], hr["admin_password"]

def get_otp(username_filter=None):
    admin_url, admin_user, admin_pass = load_admin_creds()
    login_url = admin_url.rstrip("/") + "/login/"
    otp_url   = admin_url.rstrip("/") + "/accounts/userotp/?o=-7"

    s = requests.Session()
    r = s.get(login_url)
    r.raise_for_status()
    csrf = re.search(r'csrfmiddlewaretoken" value="([^"]+)"', r.text)
    if not csrf:
        raise RuntimeError("ไม่พบ CSRF token ในหน้า login")

    r2 = s.post(login_url,
        data={"csrfmiddlewaretoken": csrf.group(1),
              "username": admin_user, "password": admin_pass, "next": "/admin/"},
        headers={"Referer": login_url},
        allow_redirects=True)
    r2.raise_for_status()
    if "login" in r2.url:
        raise RuntimeError("Login ล้มเหลว — ตรวจ admin credentials ใน apps.json")

    r3 = s.get(otp_url)
    r3.raise_for_status()

    if username_filter:
        # Find row containing the username, then extract OTP from same row
        rows = re.findall(r'<tr[^>]*>.*?</tr>', r3.text, re.DOTALL)
        for row in rows:
            if username_filter.lower() in row.lower():
                otp = re.search(r'data-label="otp code">([0-9]+)', row)
                if otp:
                    return otp.group(1).strip()
        raise RuntimeError(f"ไม่พบ OTP สำหรับ user '{username_filter}'")
    else:
        otp = re.search(r'data-label="otp code">([0-9]+)', r3.text)
        if not otp:
            raise RuntimeError("ไม่พบ OTP ในหน้า admin")
        return otp.group(1).strip()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", help="filter by username")
    args = parser.parse_args()
    try:
        otp = get_otp(args.user)
        print(otp)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
