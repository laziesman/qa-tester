"""
hr_helpers.py — shared helpers สำหรับ HR Staging auto-test
ใช้ร่วมกันทุก task: login + เลือกบริษัท อรุณเบิกฟ้า
"""

import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import Page

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR     = Path(__file__).parent.parent   # project root
SESSION_FILE = BASE_DIR / '_misc' / 'session.json'

# ── Load .env ──────────────────────────────────────────────────────────────────
def load_env(path: Path) -> dict:
    env = {}
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, _, rest = line.partition('=')
            v = re.sub(r'\s+#.*$', '', rest).strip()
            env[k.strip()] = v
    except FileNotFoundError:
        pass
    return env

def _base_url(raw: str) -> str:
    raw = raw.strip().rstrip('/')
    p = urlparse(raw)
    if p.scheme and p.netloc:
        return f"{p.scheme}://{p.netloc}"
    return raw

E           = load_env(BASE_DIR / '.env')   # .env อยู่ที่ project root
HR_APP_URL  = _base_url(E.get('HR_APP_URL', ''))
HR_USERNAME = E.get('HR_USERNAME', '')
HR_PASSWORD = E.get('HR_PASSWORD', '')

# ── Login ──────────────────────────────────────────────────────────────────────
def manual_login(page: Page, timeout: int = 180):
    """เปิด browser รอ user login + OTP เอง"""
    page.goto(f"{HR_APP_URL}/login")
    print(f"\n  🌐 กรุณา login (และกรอก OTP ถ้ามี) ใน browser")
    print(f"  ⏳ รอสูงสุด {timeout} วินาที")

    auth_pages = {'/login', '/otp', '/auth', '/2fa', '/mfa', '/verify'}
    waited, interval = 0, 2
    while waited < timeout:
        if not any(p in page.url for p in auth_pages):
            print(f"  🔐 Login สำเร็จ → {page.url}")
            return
        page.wait_for_timeout(interval * 1000)
        waited += interval
        if (timeout - waited) % 20 == 0 and (timeout - waited) > 0:
            print(f"  ⏳ เหลืออีก {timeout - waited}s ...")
    raise RuntimeError("ไม่ได้รับการ login ภายในเวลาที่กำหนด")


def ensure_logged_in(page: Page, use_session: bool, manual: bool, save_session: bool):
    """ตรวจสอบ/โหลด session แล้ว navigate ไปที่ app"""
    if use_session and SESSION_FILE.exists():
        print(f"  📂 โหลด session จาก {SESSION_FILE.name}")
        # context ต้องสร้างด้วย storage_state ก่อน — ฟังก์ชันนี้แค่ verify
        page.goto(HR_APP_URL, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(1000)
        if any(p in page.url for p in {'/login', '/otp', '/auth', '/2fa', '/mfa', '/verify'}):
            print('  ⚠️  Session หมดอายุ — กรุณา login ใหม่')
            manual_login(page)
        else:
            print(f'  ✅ Session ยังใช้ได้ → {page.url}')
    elif manual:
        manual_login(page)
    else:
        raise RuntimeError("ไม่มี credentials — ใช้ --manual-login หรือ --use-session")

    if save_session:
        page.context.storage_state(path=str(SESSION_FILE))
        print(f'  💾 บันทึก session → {SESSION_FILE.name}')
        print(f'  💡 ครั้งต่อไปใช้: --use-session')


# ── Company selection ──────────────────────────────────────────────────────────
def select_company(page: Page, company_name: str = 'อรุณเบิกฟ้า'):
    """เลือกบริษัทจาก topbar dropdown — ถ้าเลือกแล้วให้ข้าม"""
    print(f"  🏢 เลือกบริษัท: {company_name} ...")
    try:
        # navigate ไป dashboard ก่อนเพื่อให้ topbar โหลดครบ
        page.goto(f"{HR_APP_URL}/dashboard", wait_until='domcontentloaded', timeout=20000)
        page.wait_for_timeout(1000)

        # ปุ่มเปลี่ยนบริษัท: กดที่ "ชื่อบริษัท" หรือ "Superadmin" ได้เลย
        # element อาจเป็น button, div, span หรือ p ที่มี text แสดงชื่อบริษัทปัจจุบัน

        # ตรวจว่าเลือก company_name ถูกต้องแล้วหรือยัง
        header_sel = (
            f'header *:has-text("{company_name}"):visible, '
            f'[class*="MuiAppBar"] *:has-text("{company_name}"):visible'
        )
        # ใช้ locator ที่ exact หน่อย — ดู element เล็กที่สุดที่มีชื่อบริษัท
        if page.locator(header_sel).count() > 0:
            print(f"  ✅ บริษัท '{company_name}' ถูกเลือกแล้ว")
            return

        # หา element ที่แสดง "Superadmin" (ชื่อบริษัท default) แล้วคลิก
        trigger = None
        for sel in [
            # ลอง element ที่มีข้อความ "Superadmin" ใน header
            'header *:has-text("Superadmin"):visible',
            '[class*="MuiAppBar"] *:has-text("Superadmin"):visible',
            # ลอง clickable element ที่มีชื่อบริษัทใดๆ
            f'header *:has-text("{company_name}"):visible',
        ]:
            candidates = page.locator(sel).all()
            # เลือก element ที่เล็กที่สุด (leaf node) เพื่อหลีกเลี่ยง container ใหญ่
            for el in candidates:
                try:
                    children = el.locator('*').count()
                    txt = (el.inner_text() or '').strip()
                    if txt and children <= 2:
                        trigger = el
                        print(f"  🔍 พบ company trigger: '{txt}' (children={children})")
                        break
                except Exception:
                    continue
            if trigger:
                break

        if trigger is None:
            # debug — ดูทุก text ใน header
            header_texts = page.locator('header *:visible').all_inner_texts()
            visible = [t.strip() for t in header_texts if t.strip() and len(t.strip()) < 50]
            print(f"  ⚠️  ไม่พบ company trigger — header texts: {visible[:10]}")
            print(f"  ℹ️  session อาจเลือกบริษัทไว้แล้ว ดำเนินต่อ")
            return

        # click handler อาจอยู่ที่ parent — ลอง click ตัวเองก่อน แล้วลอง parent
        for click_target in [trigger, trigger.locator('..')]:
            try:
                click_target.click(timeout=5000)
            except Exception:
                continue
            page.wait_for_timeout(1000)
            menu = page.locator('[class*="MuiMenu-root"]:visible, [role="menu"]:visible, [role="listbox"]:visible')
            if menu.count() > 0:
                break
            page.keyboard.press('Escape')
            page.wait_for_timeout(300)
        else:
            print(f"  ⚠️  คลิกแล้วไม่มี dropdown เปิด")
            return

        menu = page.locator('[class*="MuiMenu-root"]:visible, [role="menu"]:visible, [role="listbox"]:visible')
        if menu.count() == 0:
            print(f"  ⚠️  dropdown ไม่ขึ้น")
            return

        opt = page.locator(
            f'[class*="MuiMenu-root"] li:has-text("{company_name}"):visible, '
            f'[role="menuitem"]:has-text("{company_name}"):visible, '
            f'[role="option"]:has-text("{company_name}"):visible'
        ).first
        if opt.count() > 0:
            opt.click()
            page.wait_for_timeout(1000)
            print(f"  ✅ เลือกบริษัท '{company_name}' สำเร็จ")
        else:
            page.keyboard.press('Escape')
            all_opts = page.locator('[class*="MuiMenu-root"] li:visible').all_inner_texts()
            print(f"  ⚠️  ไม่พบ option '{company_name}' — options: {all_opts[:5]}")
    except Exception as e:
        print(f"  ⚠️  select_company error: {e}")


# ── Browser launch helper ──────────────────────────────────────────────────────
def launch_browser(pw, headed: bool, use_session: bool):
    """Launch Edge พร้อม session (ถ้ามี)"""
    browser = pw.chromium.launch(
        channel='msedge',
        headless=not headed,
        slow_mo=120 if headed else 0
    )
    if use_session and SESSION_FILE.exists():
        ctx = browser.new_context(
            storage_state=str(SESSION_FILE),
            viewport={'width': 1440, 'height': 900},
            locale='th-TH'
        )
    else:
        ctx = browser.new_context(
            viewport={'width': 1440, 'height': 900},
            locale='th-TH'
        )
    return browser, ctx

import json as _json
import urllib.request as _urllib

FIREBASE_PROJECT = 'qa-tester-f005d'

def sync_to_firebase(results_data: dict, task_number: str):
    storage_key = f'qa_task_{task_number}'
    url = f'https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT}/databases/(default)/documents/qa_results/{storage_key}'
    doc = {'fields': {storage_key: {'stringValue': _json.dumps(results_data, ensure_ascii=False)}}}
    try:
        req = _urllib.Request(url, data=_json.dumps(doc).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='PATCH')
        with _urllib.urlopen(req, timeout=10) as resp:
            resp.read()
        print(f'  ✅ Firebase sync: {len(results_data)} TC → Firestore ({storage_key})')
    except Exception as e:
        print(f'  ⚠️  Firebase sync failed: {e}')
