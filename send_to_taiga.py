#!/usr/bin/env python3
"""
send_to_taiga.py — ส่ง QA Bug Report พร้อมรูปภาพเข้า Taiga task เป็น comment

Usage:
    python send_to_taiga.py bug-report-403.json

ต้องมีไฟล์ .env ใน folder เดียวกับ script:
    TAIGA_URL=https://boards.intelligent-bytes.com
    TAIGA_USERNAME=your_username
    TAIGA_PASSWORD=your_password
"""

import sys
import json
import os
import re
import base64
import io
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH   = os.path.join(SCRIPT_DIR, ".env")

# ── Load .env ──────────────────────────────────────────────────
def load_env(path):
    env = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

env      = load_env(ENV_PATH)
BASE_URL = env["TAIGA_URL"].rstrip("/")
USERNAME = env["TAIGA_USERNAME"]
PASSWORD = env["TAIGA_PASSWORD"]

# ── Load JSON ──────────────────────────────────────────────────
if len(sys.argv) < 2:
    print("Usage: python send_to_taiga.py bug-report-{NUMBER}.json")
    sys.exit(1)

json_path = sys.argv[1]
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

task_url     = data["task_url"]
task_name    = data["task_name"]
task_num     = data["task_number"]
bugs         = data["bugs"]
t_pass       = data["total_pass"]
t_fail       = data["total_fail"]
t_skip       = data["total_skip"]
t_tc         = data["total_tc"]
us_id        = data.get("user_story_id")   # user story ID (if available)
api_task_id  = data.get("task_id")         # internal task ID

# ── Parse slug + ref from URL ──────────────────────────────────
m = re.search(r"/project/([^/]+)/task/(\d+)", task_url)
if not m:
    print(f"❌ ไม่สามารถ parse URL ได้: {task_url}")
    sys.exit(1)

slug = m.group(1)
ref  = int(m.group(2))

# ── Auth ───────────────────────────────────────────────────────
print(f"🔌 เชื่อมต่อ Taiga ({BASE_URL})...")
resp = requests.post(
    f"{BASE_URL}/api/v1/auth",
    json={"type": "normal", "username": USERNAME, "password": PASSWORD}
)
if resp.status_code != 200:
    print(f"❌ Login ล้มเหลว {resp.status_code}: {resp.text[:200]}")
    sys.exit(1)

token = resp.json()["auth_token"]
headers_auth = {"Authorization": f"Bearer {token}"}
print(f"✅ Login สำเร็จ")

# ── Get project ────────────────────────────────────────────────
resp = requests.get(
    f"{BASE_URL}/api/v1/projects/by_slug?slug={slug}",
    headers=headers_auth
)
if resp.status_code != 200:
    print(f"❌ ไม่พบ project slug={slug}: {resp.status_code}")
    sys.exit(1)

proj = resp.json()
pid  = proj["id"]
print(f"✅ Project: {proj['name']} (id={pid})")

# ── Get task by ref ────────────────────────────────────────────
print(f"🔍 ค้นหา task #{ref}...")
resp = requests.get(
    f"{BASE_URL}/api/v1/tasks/by_ref?ref={ref}&project__slug={slug}",
    headers=headers_auth
)
if resp.status_code != 200:
    print(f"❌ ไม่พบ task ref={ref}: {resp.status_code}")
    sys.exit(1)

task_card = resp.json()
task_id   = task_card["id"]
print(f"✅ พบ task: {task_card['subject']} (id={task_id})")

# ── Upload image helper ────────────────────────────────────────
def upload_image(base64_data_url, filename, task_id, project_id):
    try:
        match = re.match(r"data:([^;]+);base64,(.+)", base64_data_url, re.DOTALL)
        if not match:
            return None
        mime_type = match.group(1)
        b64_data  = match.group(2)
        img_bytes = base64.b64decode(b64_data)

        ext_map = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}
        ext   = ext_map.get(mime_type, "png")
        fname = f"{filename}.{ext}"

        url   = f"{BASE_URL}/api/v1/tasks/attachments"
        files   = {"attached_file": (fname, io.BytesIO(img_bytes), mime_type)}
        payload = {"project": project_id, "object_id": task_id, "from_comment": "true"}

        resp = requests.post(url, headers=headers_auth, data=payload, files=files)
        if resp.status_code in (200, 201):
            result  = resp.json()
            img_url = result.get("url") or result.get("attached_file")
            if img_url and img_url.startswith("/"):
                img_url = BASE_URL + img_url
            return img_url
        else:
            print(f"   ⚠️  อัปโหลดรูปล้มเหลว {resp.status_code}: {resp.text[:100]}")
            return None
    except Exception as e:
        print(f"   ⚠️  Error upload: {e}")
        return None

# ── Build comment ──────────────────────────────────────────────
print(f"\n📝 สร้าง comment...")
lines = []
lines.append(f"## 🐛 QA Report — Task #{task_num}")
lines.append(f"**{task_name}**")
lines.append(f"")
lines.append(f"| ✅ Pass | ❌ Fail | ⏭ Skip | Total |")
lines.append(f"|--------|--------|--------|-------|")
lines.append(f"| {t_pass} | {t_fail} | {t_skip} | {t_tc} TC |")
lines.append(f"")

if not bugs:
    lines.append("ไม่มี Test Case ที่ Fail ✅")
else:
    for i, bug in enumerate(bugs, 1):
        lines.append(f"---")
        lines.append(f"### BUG-{str(i).zfill(3)} · {bug['tc_id']}")
        lines.append(f"**{bug['name']}**")
        lines.append(f"*{bug['section']}*")
        lines.append(f"")

        if bug.get("precondition"):
            lines.append(f"**Precondition:** {bug['precondition']}")
            lines.append(f"")

        lines.append(f"**Steps:**")
        for step in bug["steps"].split("\n"):
            if step.strip():
                lines.append(step.strip())
        lines.append(f"")

        lines.append(f"**Expected:** {bug['expected']}")
        lines.append(f"")
        lines.append(f"**Actual:** {bug['actual']}")
        lines.append(f"")

        images = bug.get("images", [])
        if images:
            print(f"   📎 BUG-{str(i).zfill(3)}: อัปโหลด {len(images)} รูป...")
            uploaded_urls = []
            for j, img_data in enumerate(images, 1):
                fname = f"bug-{str(i).zfill(3)}-tc-{bug['tc_id'].lower()}-{j}"
                url = upload_image(img_data, fname, task_id, pid)
                if url:
                    uploaded_urls.append(url)
                    print(f"      ✅ รูป {j}: {url[:60]}...")
                else:
                    print(f"      ❌ รูป {j}: อัปโหลดไม่สำเร็จ")

            if uploaded_urls:
                lines.append(f"**Screenshots:**")
                for url in uploaded_urls:
                    lines.append(f"![screenshot]({url})")
                lines.append(f"")

lines.append(f"---")
lines.append(f"*ส่งโดย QA Dashboard*")

comment_text = "\n".join(lines)

# ── Post comment ───────────────────────────────────────────────
print(f"\n💬 ส่ง comment...")

# PATCH task directly — board shows task history (confirmed working)
r = requests.get(f"{BASE_URL}/api/v1/tasks/{task_id}", headers=headers_auth)
tk_version = r.json().get("version", 1) if r.ok else 1
print(f"   → PATCH /tasks/{task_id} (version={tk_version})")
resp = requests.patch(
    f"{BASE_URL}/api/v1/tasks/{task_id}",
    headers={**headers_auth, "Content-Type": "application/json"},
    json={"version": tk_version, "comment": comment_text}
)
if resp.status_code not in (200, 201):
    print(f"❌ ส่ง comment ไม่สำเร็จ ({resp.status_code}): {resp.text[:120]}")
    sys.exit(1)

print(f"✅ ส่ง comment สำเร็จ!")

print(f"🔗 {task_url}")

# ── Summary ────────────────────────────────────────────────────
total_images = sum(len(b.get("images", [])) for b in bugs)
print(f"\n📋 สรุป:")
print(f"   Task   : #{task_num} {task_name}")
print(f"   Bugs   : {t_fail} cases")
print(f"   Images : {total_images} รูป")
print(f"   Board  : {task_url}")
