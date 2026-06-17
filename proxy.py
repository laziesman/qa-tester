#!/usr/bin/env python3
"""
proxy.py — Local proxy server สำหรับ QA Dashboard → Taiga

Usage:
    python proxy.py

เปิดค้างไว้ขณะตรวจสอบ ฟัง localhost:8765
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json, os, re, base64, io, sys
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH   = os.path.join(SCRIPT_DIR, ".env")
PORT       = 8765


def load_env(path):
    env = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def send_to_taiga(data):
    env      = load_env(ENV_PATH)
    BASE_URL = env["TAIGA_URL"].rstrip("/")
    USERNAME = env["TAIGA_USERNAME"]
    PASSWORD = env["TAIGA_PASSWORD"]

    task_url  = data["task_url"]
    task_num  = data["task_number"]
    task_name = data["task_name"]
    bugs      = data["bugs"]
    t_pass    = data["total_pass"]
    t_fail    = data["total_fail"]
    t_skip    = data["total_skip"]
    t_tc      = data["total_tc"]

    m = re.search(r"/project/([^/]+)/task/(\d+)", task_url)
    if not m:
        raise Exception(f"ไม่สามารถ parse URL ได้: {task_url}")
    slug = m.group(1)
    ref  = int(m.group(2))

    # Auth
    print(f"  🔌 Login {USERNAME}...")
    resp = requests.post(f"{BASE_URL}/api/v1/auth",
                         json={"type": "normal", "username": USERNAME, "password": PASSWORD})
    if not resp.ok:
        raise Exception(f"Login ล้มเหลว ({resp.status_code})")
    token        = resp.json()["auth_token"]
    headers_auth = {"Authorization": f"Bearer {token}"}

    # Get project
    resp = requests.get(f"{BASE_URL}/api/v1/projects/by_slug?slug={slug}", headers=headers_auth)
    if not resp.ok:
        raise Exception(f"ไม่พบ project '{slug}'")
    pid = resp.json()["id"]

    # Get task by ref (correct endpoint)
    resp = requests.get(f"{BASE_URL}/api/v1/tasks/by_ref?ref={ref}&project__slug={slug}",
                        headers=headers_auth)
    if not resp.ok:
        raise Exception(f"ไม่พบ task #{ref}")
    task    = resp.json()
    task_id = task["id"]
    print(f"  ✅ Task #{ref}: {task.get('subject','')[:50]} (id={task_id})")

    # Upload image helper
    def upload_image(b64_data_url, filename):
        match = re.match(r"data:([^;]+);base64,(.+)", b64_data_url, re.DOTALL)
        if not match:
            return None
        mime      = match.group(1)
        img_bytes = base64.b64decode(match.group(2))
        ext       = {"image/png": "png", "image/jpeg": "jpg",
                     "image/gif": "gif", "image/webp": "webp"}.get(mime, "png")
        files   = {"attached_file": (f"{filename}.{ext}", io.BytesIO(img_bytes), mime)}
        payload = {"project": pid, "object_id": task_id, "from_comment": "true"}
        r = requests.post(f"{BASE_URL}/api/v1/tasks/attachments",
                          headers=headers_auth, data=payload, files=files)
        if r.status_code in (200, 201):
            url = r.json().get("url") or r.json().get("attached_file", "")
            return (BASE_URL + url) if url.startswith("/") else url
        return None

    # Build comment
    lines = [
        f"## 🐛 QA Report — Task #{task_num}",
        f"**{task_name}**", "",
        "| ✅ Pass | ❌ Fail | ⏭ Skip | Total |",
        "|--------|--------|--------|-------|",
        f"| {t_pass} | {t_fail} | {t_skip} | {t_tc} TC |", "",
    ]

    total_images = 0
    if not bugs:
        lines.append("ไม่มี Test Case ที่ Fail ✅")
    else:
        for i, bug in enumerate(bugs, 1):
            lines += ["---", f"### BUG-{str(i).zfill(3)} · {bug['tc_id']}",
                      f"**{bug['name']}**", f"*{bug['section']}*", ""]
            if bug.get("precondition"):
                lines += [f"**Precondition:** {bug['precondition']}", ""]
            lines.append("**Steps:**")
            for step in bug["steps"].split("\n"):
                if step.strip():
                    lines.append(step.strip())
            lines += ["", f"**Expected:** {bug['expected']}", "",
                      f"**Actual:** {bug['actual']}", ""]

            images = bug.get("images", [])
            if images:
                print(f"  📎 BUG-{str(i).zfill(3)}: อัปโหลด {len(images)} รูป...")
                uploaded = []
                for j, img in enumerate(images, 1):
                    url = upload_image(img, f"bug-{str(i).zfill(3)}-{bug['tc_id'].lower()}-{j}")
                    if url:
                        uploaded.append(url)
                        total_images += 1
                if uploaded:
                    lines.append("**Screenshots:**")
                    lines += [f"![screenshot]({u})" for u in uploaded]
                    lines.append("")

    lines += ["---", "*ส่งโดย QA Dashboard*"]
    comment_text = "\n".join(lines)

    # Post comment via PATCH task
    r = requests.get(f"{BASE_URL}/api/v1/tasks/{task_id}", headers=headers_auth)
    version = r.json().get("version", 1) if r.ok else 1
    resp = requests.patch(
        f"{BASE_URL}/api/v1/tasks/{task_id}",
        headers={**headers_auth, "Content-Type": "application/json"},
        json={"version": version, "comment": comment_text},
    )
    if not resp.ok:
        raise Exception(f"ส่ง comment ล้มเหลว ({resp.status_code}): {resp.text[:120]}")

    print(f"  ✅ ส่ง comment สำเร็จ!")
    return {
        "message": f"ส่ง {t_fail} bugs เข้า Task #{task_num} สำเร็จ",
        "task_url": task_url,
        "images_uploaded": total_images,
    }


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True, "message": "QA Proxy running"})
        else:
            self._json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        if self.path != "/send":
            self._json(404, {"ok": False, "error": "Not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            data = json.loads(body)
        except Exception:
            self._json(400, {"ok": False, "error": "Invalid JSON"})
            return
        print(f"\n📨 รับ request: Task #{data.get('task_number')} — {data.get('total_fail')} bugs")
        try:
            result = send_to_taiga(data)
            self._json(200, {"ok": True, **result})
        except Exception as e:
            print(f"  ❌ Error: {e}")
            self._json(500, {"ok": False, "error": str(e)})

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # suppress default access log


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print(f"🚀 QA Proxy พร้อมใช้งาน → http://localhost:{PORT}")
    print(f"   กด Ctrl+C เพื่อหยุด\n")
    server = HTTPServer(("localhost", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⛔ หยุด proxy")
