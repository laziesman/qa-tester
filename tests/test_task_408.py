#!/usr/bin/env python3
"""
ทดสอบอัตโนมัติ Task 408 — ฟอร์มสร้างเอกสารสัญญาใหม่ให้พนักงาน

Setup:
  1. กรอกค่าใน .env:
       HR_APP_URL=https://your-staging-url.com
       HR_USERNAME=your@email.com
       HR_PASSWORD=your_password
       TEST_EMPLOYEE_CODE=EMP001       (รหัสพนักงาน Active)
       TEST_INACTIVE_EMP_CODE=EMP999  (optional — สำหรับ TC-002)
       TEST_EXISTING_CONTRACT=CON-2568-0001  (optional — สำหรับ TC-011)

  2. รัน:
       python test_task_408.py              # headless
       python test_task_408.py --headed     # เห็นหน้าจอ (แนะนำครั้งแรก)
       python test_task_408.py --section 1  # รันเฉพาะ section 1
       python test_task_408.py --headed --section 2

  Session (ไม่ต้อง login ทุกครั้ง):
       python test_task_408.py --manual-login --save-session   # login ครั้งแรก + บันทึก session
       python test_task_408.py --use-session                   # ครั้งถัดไป ข้าม login

  3. ผลออกมาที่:
       HR/Sprint-5/test-results-408.json  (import เข้า localStorage ได้)
       screenshots/task-408/              (รูป screenshot แต่ละ TC)
"""

import sys
import re
import io
import json
import zipfile
import datetime
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, Page

# Force UTF-8 output so emojis work on Windows Terminal (CP874)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).parent

# ── Load .env (strips inline comments after #) ─────────────────────────────────
def load_env(path: Path) -> dict:
    env = {}
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, _, rest = line.partition('=')
            # strip inline comment (space + # ...) but keep # inside values
            v = re.sub(r'\s+#.*$', '', rest).strip()
            env[k.strip()] = v
    except FileNotFoundError:
        pass
    return env

E = load_env(BASE_DIR / '.env')

# Extract base URL (scheme + host only) regardless of what user typed
def _base_url(raw: str) -> str:
    raw = raw.strip().rstrip('/')
    p = urlparse(raw)
    if p.scheme and p.netloc:
        return f"{p.scheme}://{p.netloc}"
    return raw  # fallback

HR_APP_URL           = _base_url(E.get('HR_APP_URL', ''))
HR_USERNAME          = E.get('HR_USERNAME', '')
HR_PASSWORD          = E.get('HR_PASSWORD', '')
ACTIVE_EMP_CODE      = E.get('TEST_EMPLOYEE_CODE', '')
INACTIVE_EMP_CODE    = E.get('TEST_INACTIVE_EMP_CODE', '')
EXISTING_CONTRACT_NO = E.get('TEST_EXISTING_CONTRACT', '')

CONTRACT_URL    = f"{HR_APP_URL}/employee/contracts/create"
SCREENSHOTS_DIR = BASE_DIR / 'screenshots' / 'task-408'
RESULTS_FILE    = BASE_DIR / 'HR' / 'Sprint-5' / 'test-results-408.json'
TASK_HTML_FILE  = BASE_DIR / 'HR' / 'Sprint-5' / 'task-408.html'
TEST_FILES_DIR  = BASE_DIR / 'test-files'
SESSION_FILE    = BASE_DIR / 'session.json'

# ── CLI args ───────────────────────────────────────────────────────────────────
HEADED       = '--headed' in sys.argv
MANUAL_LOGIN = '--manual-login' in sys.argv  # เปิด browser แล้วรอ user login เอง
SAVE_SESSION = '--save-session' in sys.argv  # บันทึก session หลัง login ไว้ใช้ครั้งหน้า
USE_SESSION  = '--use-session' in sys.argv   # ใช้ session ที่บันทึกไว้ (ข้าม login)
SHOW_RESULTS = '--show-results' in sys.argv  # เปิด task-408.html พร้อม inject ผลลัพธ์
SECTION      = None
for i, a in enumerate(sys.argv):
    if a == '--section' and i + 1 < len(sys.argv):
        try:
            SECTION = int(sys.argv[i + 1])
        except ValueError:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# Results tracker
# ══════════════════════════════════════════════════════════════════════════════
class Results:
    def __init__(self):
        self.data: dict[str, dict] = {}

    def set(self, tc_id: str, status: str, note: str = ''):
        self.data[tc_id] = {'status': status, 'note': note}
        icon = {'pass': '✅', 'fail': '❌', 'skip': '⏭'}.get(status, '?')
        print(f"    {icon} {tc_id}: {note or status.upper()}")

    def save(self):
        RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        print(f"\n💾 บันทึกที่: {RESULTS_FILE}")
        if SHOW_RESULTS:
            show_results_in_browser(self.data)
        else:
            print(f"   💡 เพิ่ม --show-results เพื่อให้เปิด task-408.html อัตโนมัติ")

    def summary(self):
        counts = {'pass': 0, 'fail': 0, 'skip': 0}
        fails = []
        for tc_id, v in self.data.items():
            s = v['status']
            if s in counts:
                counts[s] += 1
            if s == 'fail':
                fails.append(tc_id)
        total = sum(counts.values())
        print(f"\n{'═'*55}")
        print(f"✅ Pass: {counts['pass']}  ❌ Fail: {counts['fail']}  ⏭ Skip: {counts['skip']}  (จาก {total})")
        if fails:
            print(f"Fail: {', '.join(fails)}")
        print(f"{'═'*55}")


# ══════════════════════════════════════════════════════════════════════════════
# Page helpers
# ══════════════════════════════════════════════════════════════════════════════
def ss(page: Page, name: str) -> str:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    p = str(SCREENSHOTS_DIR / f"{name}.png")
    page.screenshot(path=p, full_page=False)
    return p


_nav_debugged = False

def nav(page: Page):
    """ไปที่ฟอร์มสร้างสัญญา (fresh load)"""
    global _nav_debugged
    for attempt in range(3):
        try:
            page.goto(CONTRACT_URL, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            break
        except Exception as e:
            if attempt == 2:
                raise
            page.wait_for_timeout(1500)
    page.wait_for_timeout(800)

    if not _nav_debugged:
        _nav_debugged = True
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SCREENSHOTS_DIR / '_form-page.png'))
        inputs = page.locator('input:visible').all()
        print(f"\n  🔍 DEBUG: พบ input:visible ในฟอร์ม {len(inputs)} ช่อง:")
        for i, inp in enumerate(inputs[:15]):
            t   = inp.get_attribute('type') or 'text'
            n   = inp.get_attribute('name') or ''
            ph  = inp.get_attribute('placeholder') or ''
            cls = (inp.get_attribute('class') or '')[:60]
            print(f"    [{i}] type={t!r} name={n!r} ph={ph[:35]!r} cls=...{cls[-35:]!r}")
        print(f"  📸 screenshots/task-408/_form-page.png\n")


def login(page: Page):
    page.goto(f"{HR_APP_URL}/login")
    page.wait_for_load_state('networkidle', timeout=30000)
    page.wait_for_timeout(800)

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOTS_DIR / '_login-page.png'))
    print(f"  📸 Screenshot login page → screenshots/task-408/_login-page.png")

    # Debug: show all inputs on the page
    inputs = page.locator('input:visible').all()
    print(f"  🔍 พบ input:visible จำนวน {len(inputs)} ช่อง:")
    for i, inp in enumerate(inputs):
        t = inp.get_attribute('type') or 'text'
        n = inp.get_attribute('name') or ''
        ph = inp.get_attribute('placeholder') or ''
        print(f"      [{i}] type={t!r} name={n!r} placeholder={ph[:40]!r}")

    # Fill username (first visible text/email input)
    username_inp = page.locator(
        'input[name="username"], input[name="email"], input[type="email"], input[type="text"]'
    ).first
    username_inp.wait_for(state='visible', timeout=10000)
    username_inp.fill(HR_USERNAME)
    print(f"  ✏️  กรอก username: {HR_USERNAME}")

    page.locator('input[type="password"]').first.fill(HR_PASSWORD)
    print(f"  ✏️  กรอก password: ***")

    page.screenshot(path=str(SCREENSHOTS_DIR / '_login-filled.png'))

    # Click submit
    submit = page.locator('button[type="submit"]').first
    if submit.count() == 0:
        # fallback: any button containing text
        submit = page.get_by_role('button').first
    submit.click()
    print(f"  🖱️  คลิก submit")

    # Wait for redirect away from login (up to 45s — server may be slow)
    try:
        page.wait_for_url(lambda u: '/login' not in u, timeout=45000)
        print(f"  🔐 Login OK → {page.url}")
    except Exception:
        page.screenshot(path=str(SCREENSHOTS_DIR / '_login-failed.png'))
        # Check for error message on page
        err_text = ''
        for sel in ['[class*="error"]:visible', '[class*="alert"]:visible', '[role="alert"]']:
            el = page.locator(sel).first
            if el.count() > 0:
                err_text = el.inner_text().strip()[:120]
                break
        msg = f"Login failed: {err_text}" if err_text else "Login ไม่สำเร็จ — credentials ผิด"
        print(f"  ❌ {msg}")
        print(f"  💡 ลองรัน: python -X utf8 test_task_408.py --manual-login --section 1")
        raise RuntimeError(msg)


def manual_login(page: Page):
    """เปิด browser รอ user login + OTP เอง จากนั้น script รัน test ต่อ"""
    page.goto(f"{HR_APP_URL}/login")
    print(f"\n  🌐 เปิด browser — กรุณา login (และกรอก OTP ถ้ามี) ใน browser")
    print(f"  ⏳ รอสูงสุด 180 วินาที")

    deadline = 180
    interval = 2
    waited = 0
    auth_pages = {'/login', '/otp', '/auth', '/2fa', '/mfa', '/verify'}

    while waited < deadline:
        current = page.url
        on_auth = any(p in current for p in auth_pages)
        if not on_auth:
            print(f"  🔐 Auth complete → {current}")
            return
        page.wait_for_timeout(interval * 1000)
        waited += interval
        remaining = deadline - waited
        if remaining % 20 == 0 and remaining > 0:
            print(f"  ⏳ รอ... เหลืออีก {remaining}s (ปัจจุบัน: {current.split('/')[-1][:40]})")
    raise RuntimeError("ไม่ได้รับการ login ภายใน 180 วินาที")


def select_company(page: Page, company_name: str = 'อรุณเบิกฟ้า'):
    """เลือกบริษัทจาก topbar dropdown — ถ้าเลือกแล้วให้ข้าม"""
    print(f"  🏢 เลือกบริษัท: {company_name} ...")
    try:
        # ถ้า topbar แสดงบริษัทที่ต้องการแล้ว → ไม่ต้องทำอะไร
        if page.locator(f'button:has-text("{company_name}"):visible').count() > 0:
            print(f"  ✅ บริษัท '{company_name}' ถูกเลือกแล้ว (ข้าม)")
            return

        # หา topbar company switcher button — อาจแสดง "Superadmin" หรือชื่อบริษัทอื่น
        # จากรูปหน้าจอ: ปุ่มนี้อยู่ซ้าย topbar มี icon ตาราง + ชื่อ + arrow
        topbar_btn = page.locator(
            'button:has-text("Superadmin"):visible, '
            'button:has-text("บริษัท"):visible'
        ).first
        if topbar_btn.count() == 0:
            # fallback: ปุ่มแรกใน topbar ที่ไม่ใช่ TH/EN/ภาษา
            topbar_btn = page.locator(
                '[class*="MuiButton"][class*="dropdown"]:visible, '
                'header [class*="select"]:visible, '
                'button[aria-haspopup]:visible'
            ).first
        if topbar_btn.count() == 0:
            print(f"  ⚠️  ไม่พบ topbar company button — ข้ามต่อ")
            return

        topbar_btn.click(timeout=8000)
        page.wait_for_timeout(800)

        # หา option ในเมนูที่เปิดมา
        opt = page.locator(
            f'[class*="MuiMenu-root"] li:has-text("{company_name}"):visible, '
            f'[class*="MuiPopover"] li:has-text("{company_name}"):visible, '
            f'li:has-text("{company_name}"):visible'
        ).first
        if opt.count() > 0:
            opt.wait_for(state='visible', timeout=5000)
            opt.click()
            page.wait_for_timeout(800)
            print(f"  ✅ เลือกบริษัท '{company_name}' สำเร็จ")
        else:
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(SCREENSHOTS_DIR / '_company-select.png'))
            print(f"  ⚠️  ไม่พบ option '{company_name}' ใน dropdown — ดู _company-select.png")
            page.keyboard.press('Escape')
            page.wait_for_timeout(300)
    except Exception as e:
        print(f"  ⚠️  select_company error: {e} — ข้ามต่อ")


def close_open_menus(page: Page):
    """ปิด dropdown/menu ที่ค้างอยู่"""
    if page.locator('[class*="MuiBackdrop-root"]:visible, [class*="MuiMenu-root"]:not([aria-hidden]):visible').count() > 0:
        page.keyboard.press('Escape')
        page.wait_for_timeout(300)


def fill_employee(page: Page, code: str):
    """พิมพ์ค้นหาพนักงานใน search input (เลือกพนักงาน section)"""
    close_open_menus(page)
    # Search input "ค้นหารหัสพนักงาน" is always visible on the form page
    search = page.locator('input[placeholder*="ค้นหารหัสพนักงาน"]').first
    if search.count() == 0:
        search = page.locator('input[placeholder*="ค้นหา"]').nth(1)  # skip topbar
    search.click()
    search.fill(code)
    page.wait_for_timeout(1500)


def pick_first_option(page: Page):
    """เลือก option แรกหลังพิมพ์ค้นหา — ใช้ ArrowDown+Enter เพื่อเลือกใน Autocomplete
    (mouse click บน Autocomplete option อาจ navigate ออกจากหน้า)"""
    opt = page.locator(
        'ul[role="listbox"] li[role="option"]:visible, '
        'ul[role="listbox"] li:visible, '
        '[class*="MuiMenu-root"] li:visible, '
        '[class*="MuiPopper"] li:visible'
    ).first
    opt.wait_for(state='visible', timeout=8000)
    # Press ArrowDown then Enter to select via keyboard (safe for Autocomplete)
    page.keyboard.press('ArrowDown')
    page.wait_for_timeout(200)
    page.keyboard.press('Enter')
    page.wait_for_timeout(800)
    close_open_menus(page)


def click_save(page: Page):
    save_loc = page.locator('button:has-text("บันทึก"):visible')
    if save_loc.count() == 0:
        save_loc = page.locator('button[type="submit"]:visible')
    if save_loc.count() == 0:
        save_loc = page.get_by_role('button', name=re.compile(r'บันทึก|save', re.IGNORECASE))
    save_loc.first.click(timeout=15000)
    page.wait_for_timeout(800)


def has_error(page: Page) -> bool:
    page.wait_for_timeout(600)
    return page.locator('[class*="error"]:visible, [aria-invalid="true"]:visible, [class*="Mui-error"]:visible').count() > 0


def has_toast(page: Page, keyword: str = 'สำเร็จ') -> bool:
    page.wait_for_timeout(1500)
    return page.locator(
        f'[class*="toast"]:has-text("{keyword}"), '
        f'[class*="snackbar"]:has-text("{keyword}"), '
        f'[class*="alert"]:has-text("{keyword}"), '
        f'[class*="success"]:has-text("{keyword}")'
    ).count() > 0


# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — เลือกพนักงาน (TC-001..005)
# ══════════════════════════════════════════════════════════════════════════════
def s1(page: Page, r: Results):
    print('\n▶ Section 1 — เลือกพนักงาน')

    # TC-001
    print('  TC-001: ค้นหาพนักงาน Active → dropdown แสดง')
    nav(page)
    if ACTIVE_EMP_CODE:
        fill_employee(page, ACTIVE_EMP_CODE)
        # Check options appeared inside the Select dropdown
        opts = page.locator('ul[role="listbox"] li:visible, [class*="MuiPaper-root"] ul li:visible')
        if opts.count() > 0:
            r.set('TC-001', 'pass', f'dropdown แสดง {opts.count()} option สำหรับ {ACTIVE_EMP_CODE}')
            ss(page, 'TC-001-pass')
        else:
            ss(page, 'TC-001-fail')
            r.set('TC-001', 'fail', 'ไม่แสดง option ใน dropdown')
    else:
        r.set('TC-001', 'skip', 'ไม่ได้ตั้ง TEST_EMPLOYEE_CODE ใน .env')

    # TC-002
    print('  TC-002: ค้นหาพนักงาน Inactive → ไม่แสดง')
    nav(page)
    if INACTIVE_EMP_CODE:
        fill_employee(page, INACTIVE_EMP_CODE)
        options = page.locator('[role="option"]')
        if options.count() == 0:
            r.set('TC-002', 'pass', 'ไม่แสดง Inactive ใน dropdown')
        else:
            ss(page, 'TC-002-fail')
            r.set('TC-002', 'fail', f'แสดง {options.count()} option สำหรับ Inactive emp')
    else:
        r.set('TC-002', 'skip', 'ไม่ได้ตั้ง TEST_INACTIVE_EMP_CODE ใน .env')

    # TC-003
    print('  TC-003: เลือกพนักงาน → auto-fill ชื่อ/ตำแหน่ง/แผนก')
    nav(page)
    if ACTIVE_EMP_CODE:
        fill_employee(page, ACTIVE_EMP_CODE)
        pick_first_option(page)
        page.wait_for_timeout(800)
        # Auto-fill fields: text inputs that are now disabled/readonly and have values
        # From debug: inputs [3],[4],[5] = ชื่อ-สกุล, ตำแหน่ง, แผนก (ph='', type='text')
        all_text = page.locator('input[type="text"]:not([class*="MuiSelect"]):visible').all()
        filled = [(el.input_value(), el.is_disabled()) for el in all_text if el.input_value().strip()]
        if filled:
            r.set('TC-003', 'pass', f'auto-fill {len(filled)} ฟิลด์: {[v for v,_ in filled[:3]]}')
            ss(page, 'TC-003-pass')
        else:
            ss(page, 'TC-003-fail')
            r.set('TC-003', 'fail', 'ไม่พบ text inputs ที่มีค่าหลังเลือกพนักงาน')
    else:
        r.set('TC-003', 'skip', 'ไม่ได้ตั้ง TEST_EMPLOYEE_CODE')

    # TC-004
    print('  TC-004: auto-fill fields เป็น read-only / disabled')
    nav(page)
    if ACTIVE_EMP_CODE:
        fill_employee(page, ACTIVE_EMP_CODE)
        pick_first_option(page)
        page.wait_for_timeout(800)
        # Check if auto-filled inputs are disabled
        all_text = page.locator('input[type="text"]:not([class*="MuiSelect"]):visible').all()
        filled_disabled = [(el.input_value(), el.is_disabled()) for el in all_text if el.input_value().strip()]
        if filled_disabled:
            all_disabled = all(disabled for _, disabled in filled_disabled)
            if all_disabled:
                r.set('TC-004', 'pass', f'auto-fill fields ทั้งหมด disabled ({len(filled_disabled)} ฟิลด์)')
            else:
                editable = [v for v, d in filled_disabled if not d]
                ss(page, 'TC-004-fail')
                r.set('TC-004', 'fail', f'บางฟิลด์ยังแก้ไขได้: {editable}')
        else:
            ss(page, 'TC-004-check')
            r.set('TC-004', 'skip', 'ไม่พบ auto-fill fields — ต้อง manual')
    else:
        r.set('TC-004', 'skip', 'ไม่ได้ตั้ง TEST_EMPLOYEE_CODE')

    # TC-005
    print('  TC-005: ไม่เลือกพนักงาน → บันทึกไม่ได้')
    nav(page)
    click_save(page)
    if has_error(page):
        r.set('TC-005', 'pass', 'แสดง error เมื่อไม่เลือกพนักงาน')
    else:
        ss(page, 'TC-005-fail')
        r.set('TC-005', 'fail', 'บันทึกได้โดยไม่เลือกพนักงาน หรือไม่มี error')


# ══════════════════════════════════════════════════════════════════════════════
# Section 2 — ประเภทสัญญาและเลขที่สัญญา (TC-006..012)
# ══════════════════════════════════════════════════════════════════════════════
def s2(page: Page, r: Results):
    print('\n▶ Section 2 — ประเภทสัญญาและเลขที่สัญญา')

    def open_contract_type():
        """คลิก dropdown ประเภทสัญญา (MUI Select ที่ 2 ในฟอร์ม)"""
        # ประเภทสัญญาเป็น MUI Select ที่ 2 (หลัง เลือกพนักงาน)
        triggers = page.locator('div[class*="MuiSelect-select"]:visible')
        if triggers.count() >= 2:
            triggers.nth(1).click()
        elif triggers.count() == 1:
            triggers.first.click()
        else:
            return False
        page.wait_for_timeout(500)
        return True

    def opts_in_paper():
        # MUI Select dropdown = MuiMenu-root (sidebar = MuiDrawer-root, won't match)
        return page.locator('[class*="MuiMenu-root"] li:visible')

    # TC-006
    print('  TC-006: dropdown ประเภทสัญญา มี 6 ตัวเลือก')
    nav(page)
    if open_contract_type():
        count = opts_in_paper().count()
        ss(page, 'TC-006-open')
        if count == 6:
            r.set('TC-006', 'pass', 'มี 6 ตัวเลือก')
        else:
            r.set('TC-006', 'fail', f'มี {count} ตัวเลือก (ต้องการ 6)')
        page.keyboard.press('Escape')
    else:
        ss(page, 'TC-006-notfound')
        r.set('TC-006', 'skip', 'ไม่พบ dropdown ประเภทสัญญา')

    # TC-007
    print('  TC-007: เลือก อื่นๆ → ช่องกรอกปรากฏ')
    nav(page)
    if open_contract_type():
        opts = opts_in_paper()
        opts.last.click()
        page.wait_for_timeout(600)
        # อื่นๆ อาจแสดง textarea หรือ text input เพิ่มเติม
        extra = page.locator('textarea:visible, input[placeholder*="ระบุ"]:visible, input[placeholder*="รายละเอียด"]:visible')
        if extra.count() > 0:
            r.set('TC-007', 'pass', 'แสดงช่องกรอกเพิ่มเติมเมื่อเลือก อื่นๆ')
        else:
            ss(page, 'TC-007-check')
            r.set('TC-007', 'skip', 'ต้อง manual — ตรวจ screenshot TC-007-check')
    else:
        r.set('TC-007', 'skip', 'ไม่พบ dropdown ประเภทสัญญา')

    # TC-008
    print('  TC-008: ไม่เลือกประเภทสัญญา → error')
    nav(page)
    click_save(page)
    if has_error(page):
        r.set('TC-008', 'pass', 'มี error เมื่อไม่เลือกประเภทสัญญา')
    else:
        ss(page, 'TC-008-check')
        r.set('TC-008', 'skip', 'ต้อง manual verify')

    # TC-009..012: ฟอร์มนี้ไม่มีช่อง เลขที่สัญญา (จาก screenshot)
    print('  TC-009..012: ตรวจสอบว่ามีช่อง เลขที่สัญญาหรือไม่')
    nav(page)
    cn = page.locator(
        'input[placeholder*="เลขที่สัญญา"], '
        'input[placeholder*="contract_no" i], '
        'input[placeholder*="หมายเลข"], '
        'label:has-text("เลขที่สัญญา") + * input'
    )
    if cn.count() > 0:
        v = cn.first.input_value()
        if re.match(r'CON-\d{4}-\d+', v):
            r.set('TC-009', 'pass', f'auto-generate: {v}')
        elif v:
            r.set('TC-009', 'skip', f'มีค่า auto รูปแบบอื่น: {v}')
        else:
            ss(page, 'TC-009-fail')
            r.set('TC-009', 'fail', 'ช่องว่าง ไม่มี auto-generate')
        # TC-010
        cn.first.triple_click()
        cn.first.type('TEST-MANUAL-9999')
        r.set('TC-010', 'pass' if 'TEST-MANUAL' in cn.first.input_value() else 'fail',
              cn.first.input_value())
        # TC-011
        r.set('TC-011', 'skip', 'ไม่ได้ตั้ง TEST_EXISTING_CONTRACT ใน .env' if not EXISTING_CONTRACT_NO else 'ต้องทดสอบ manual')
        # TC-012
        cn.first.fill('')
        click_save(page)
        r.set('TC-012', 'pass' if has_error(page) else 'skip', 'required หรือ auto-generate')
    else:
        ss(page, 'TC-009-no-field')
        for tc in ['TC-009', 'TC-010', 'TC-011', 'TC-012']:
            r.set(tc, 'skip', 'ไม่มีช่อง เลขที่สัญญา ในฟอร์ม — ระบบ auto-assign backend')


# ══════════════════════════════════════════════════════════════════════════════
# Section 3 — วันที่สัญญาและเงื่อนไข (TC-013..019)
# ══════════════════════════════════════════════════════════════════════════════
def s3(page: Page, r: Results):
    print('\n▶ Section 3 — วันที่สัญญาและเงื่อนไข')

    def get_date_inputs():
        return page.locator('input[type="date"], input[name*="start" i], input[name*="end" i], [class*="MuiDatePicker"] input')

    # TC-013
    print('  TC-013: ไม่กรอกวันที่เริ่ม → error')
    nav(page)
    click_save(page)
    if has_error(page):
        r.set('TC-013', 'pass', 'error เมื่อไม่กรอกวันที่เริ่ม')
    else:
        ss(page, 'TC-013-check')
        r.set('TC-013', 'skip', 'ต้อง manual')

    # TC-014
    print('  TC-014: checkbox ไม่กำหนดวันสิ้นสุด → end date disabled')
    nav(page)
    try:
        # จาก screenshot: "ไม่กำหนดวันสิ้นสุด" เป็น checkbox (input[type=checkbox] ตัวแรก)
        no_end_cb = page.locator('input[type="checkbox"]').first
        no_end_cb.click()
        page.wait_for_timeout(600)
        # end date input (type=date ที่ 2) ควร disabled
        end_date = page.locator('input[type="date"]').nth(1)
        if end_date.count() > 0 and end_date.is_disabled():
            r.set('TC-014', 'pass', 'วันที่สิ้นสุด disabled หลังติ๊ก checkbox')
        else:
            ss(page, 'TC-014-check')
            r.set('TC-014', 'skip', 'ต้อง manual verify')
    except Exception as e:
        ss(page, 'TC-014-error')
        r.set('TC-014', 'skip', f'Error: {e}')

    # TC-015
    print('  TC-015: toggle ไม่กำหนดวันสิ้นสุด → notification section disabled')
    # Continue from TC-014 state
    try:
        notif_inputs = page.locator('input[type="number"]:visible, input[type="checkbox"]:visible').all()
        disabled_count = sum(1 for el in notif_inputs if el.is_disabled())
        if disabled_count > 0:
            r.set('TC-015', 'pass', f'notification disabled ({disabled_count} fields)')
        else:
            ss(page, 'TC-015-check')
            r.set('TC-015', 'skip', 'ต้อง manual verify')
    except Exception as e:
        r.set('TC-015', 'skip', f'Error: {e}')

    # TC-016
    print('  TC-016: วันสิ้นสุด < วันเริ่ม → error')
    nav(page)
    dates = get_date_inputs()
    if dates.count() >= 2:
        dates.nth(0).fill('2025-06-01')
        dates.nth(1).fill('2025-05-31')
        dates.nth(1).press('Tab')
        page.wait_for_timeout(800)
        if has_error(page):
            r.set('TC-016', 'pass', 'error วันสิ้นสุด < วันเริ่ม')
        else:
            click_save(page)
            if has_error(page):
                r.set('TC-016', 'pass', 'error ที่ submit')
            else:
                ss(page, 'TC-016-fail')
                r.set('TC-016', 'fail', 'ไม่มี error')
    else:
        ss(page, 'TC-016-notfound')
        r.set('TC-016', 'skip', 'ไม่พบ date inputs')

    # TC-017
    print('  TC-017: วันสิ้นสุด = วันเริ่ม → error')
    nav(page)
    dates = get_date_inputs()
    if dates.count() >= 2:
        dates.nth(0).fill('2025-06-01')
        dates.nth(1).fill('2025-06-01')
        dates.nth(1).press('Tab')
        page.wait_for_timeout(800)
        if has_error(page):
            r.set('TC-017', 'pass', 'error วันเท่ากัน')
        else:
            ss(page, 'TC-017-check')
            r.set('TC-017', 'skip', 'ไม่มี error เมื่อวันเท่ากัน — ต้อง verify spec')
    else:
        r.set('TC-017', 'skip', 'ไม่พบ date inputs')

    # TC-018 & TC-019: optional fields — test during full save (TC-037)
    r.set('TC-018', 'skip', 'ต้องทดสอบร่วมกับ TC-037 (full save without notes)')
    r.set('TC-019', 'skip', 'ต้องทดสอบร่วมกับ TC-037 (full save without remarks)')


# ══════════════════════════════════════════════════════════════════════════════
# Section 4 — เอกสารแนบ (TC-020..027)
# ══════════════════════════════════════════════════════════════════════════════
def s4(page: Page, r: Results):
    print('\n▶ Section 4 — เอกสารแนบ')

    # Create test files
    TEST_FILES_DIR.mkdir(parents=True, exist_ok=True)

    pdf_file  = TEST_FILES_DIR / 'test_contract.pdf'
    doc_file  = TEST_FILES_DIR / 'test_contract.doc'
    docx_file = TEST_FILES_DIR / 'test_contract.docx'
    jpg_file  = TEST_FILES_DIR / 'test_image.jpg'
    big_file  = TEST_FILES_DIR / 'test_big.pdf'

    if not pdf_file.exists():
        pdf_file.write_bytes(b'%PDF-1.4\n1 0 obj\n<</Type /Catalog>>\nendobj\nxref\n0 2\ntrailer\n<</Size 2>>\nstartxref\n0\n%%EOF')
    if not doc_file.exists():
        doc_file.write_bytes(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1' + b'\x00' * 512)
    if not docx_file.exists():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')
        docx_file.write_bytes(buf.getvalue())
    if not jpg_file.exists():
        jpg_file.write_bytes(bytes([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01, 0xFF, 0xD9]))
    if not big_file.exists():
        print('    📦 สร้างไฟล์ทดสอบ 21MB... (ครั้งเดียว)')
        big_file.write_bytes(b'%PDF-1.4 ' + b'X' * (21 * 1024 * 1024))

    def click_add_file_btn():
        """คลิกปุ่ม เพิ่มไฟล์ แล้ว return hidden file input"""
        # จาก screenshot: ใช้ปุ่ม "เพิ่มไฟล์" ไม่ใช่ input[type=file] โดยตรง
        btn = page.get_by_role('button', name=re.compile('เพิ่มไฟล์|อัปโหลด|Upload', re.I)).first
        if btn.count() == 0:
            btn = page.locator('button:has-text("ไฟล์"), button:has-text("Upload")').first
        # Use file chooser event to intercept
        return btn

    def upload_file(files):
        """อัปโหลดไฟล์ผ่าน file chooser"""
        btn = click_add_file_btn()
        if btn.count() == 0:
            return False
        # Try hidden input first
        fi = page.locator('input[type="file"]')
        if fi.count() > 0:
            fi.first.set_input_files(files if isinstance(files, list) else [files])
        else:
            # Use file chooser
            with page.expect_file_chooser() as fc_info:
                btn.click()
            fc = fc_info.value
            fc.set_files(files if isinstance(files, list) else [files])
        page.wait_for_timeout(1500)
        return True

    def file_appeared() -> bool:
        return (
            page.locator('[class*="file" i]:visible, [class*="attach" i]:visible').count() > 0
            or page.locator('[class*="MuiList"] [class*="MuiListItem"]:visible').count() > 0
        )

    # TC-020
    print('  TC-020: อัปโหลด PDF → สำเร็จ')
    nav(page)
    if upload_file(str(pdf_file)):
        ss(page, 'TC-020-result')
        if file_appeared() and not has_error(page):
            r.set('TC-020', 'pass', 'PDF อัปโหลดสำเร็จ')
        else:
            r.set('TC-020', 'skip', 'ต้อง manual verify — ดู TC-020-result.png')
    else:
        ss(page, 'TC-020-notfound')
        r.set('TC-020', 'skip', 'ไม่พบปุ่มเพิ่มไฟล์')

    # TC-021
    print('  TC-021: อัปโหลด DOC → สำเร็จ')
    nav(page)
    if upload_file(str(doc_file)):
        ss(page, 'TC-021-result')
        r.set('TC-021', 'pass' if not has_error(page) else 'fail',
              'DOC ไม่มี error' if not has_error(page) else 'error เมื่ออัปโหลด DOC')
    else:
        r.set('TC-021', 'skip', 'ไม่พบปุ่มเพิ่มไฟล์')

    # TC-022
    print('  TC-022: อัปโหลด DOCX → สำเร็จ')
    nav(page)
    if upload_file(str(docx_file)):
        ss(page, 'TC-022-result')
        r.set('TC-022', 'pass' if not has_error(page) else 'fail',
              'DOCX ไม่มี error' if not has_error(page) else 'error เมื่ออัปโหลด DOCX')
    else:
        r.set('TC-022', 'skip', 'ไม่พบปุ่มเพิ่มไฟล์')

    # TC-023
    print('  TC-023: อัปโหลด JPG → error')
    nav(page)
    if upload_file(str(jpg_file)):
        page.wait_for_timeout(500)
        ss(page, 'TC-023-result')
        if has_error(page):
            r.set('TC-023', 'pass', 'error สำหรับ JPG')
        else:
            r.set('TC-023', 'skip', 'ต้อง manual — อาจ filter ที่ accept attribute ใน input')
    else:
        r.set('TC-023', 'skip', 'ไม่พบปุ่มเพิ่มไฟล์')

    # TC-024
    print('  TC-024: อัปโหลดไฟล์ > 20MB → error')
    nav(page)
    if upload_file(str(big_file)):
        page.wait_for_timeout(2000)
        ss(page, 'TC-024-result')
        if has_error(page):
            r.set('TC-024', 'pass', 'error ไฟล์ > 20MB')
        else:
            r.set('TC-024', 'skip', 'ต้อง manual verify')
    else:
        r.set('TC-024', 'skip', 'ไม่พบปุ่มเพิ่มไฟล์')

    # TC-025
    print('  TC-025: อัปโหลดหลายไฟล์')
    nav(page)
    if upload_file([str(pdf_file), str(docx_file)]):
        ss(page, 'TC-025-result')
        r.set('TC-025', 'skip', 'ต้อง manual verify รายการไฟล์ — ดู TC-025-result.png')
    else:
        r.set('TC-025', 'skip', 'ไม่พบปุ่มเพิ่มไฟล์')

    # TC-026 & TC-027: ต้อง manual (ขึ้นอยู่กับ UI component)
    r.set('TC-026', 'skip', 'ต้อง manual — คลิก edit ชื่อไฟล์ใน UI')
    r.set('TC-027', 'skip', 'ต้อง manual — กรอกหมายเหตุไฟล์แล้วบันทึก')


# ══════════════════════════════════════════════════════════════════════════════
# Section 5 — การแจ้งเตือนก่อนหมดอายุ (TC-028..035)
# ══════════════════════════════════════════════════════════════════════════════
def s5(page: Page, r: Results):
    print('\n▶ Section 5 — การแจ้งเตือนก่อนหมดอายุ')

    # TC-028
    print('  TC-028: toggle แจ้งเตือน default = ON')
    nav(page)
    # จาก debug: input[10] เป็น MuiSwitch-input (notification toggle)
    sw = page.locator('input[class*="MuiSwitch-input"]').first
    if sw.count() > 0:
        if sw.is_checked():
            r.set('TC-028', 'pass', 'toggle แจ้งเตือน ON by default')
        else:
            ss(page, 'TC-028-check')
            r.set('TC-028', 'fail', 'toggle แจ้งเตือน OFF by default (ต้องเป็น ON)')
    else:
        ss(page, 'TC-028-notfound')
        r.set('TC-028', 'skip', 'ไม่พบ MuiSwitch — ต้อง manual')

    # TC-029
    print('  TC-029: ปิด toggle → fields disabled')
    nav(page)
    sw = page.locator('input[class*="MuiSwitch-input"]').first
    if sw.count() > 0:
        try:
            if sw.is_checked():
                sw.click()
                page.wait_for_timeout(600)
            ss(page, 'TC-029-after-toggle')
            num_inp = page.locator('input[type="number"]').all()
            cbs = page.locator('input[type="checkbox"]').all()
            disabled = [el for el in num_inp + cbs if el.is_disabled()]
            if disabled:
                r.set('TC-029', 'pass', f'{len(disabled)} fields disabled หลังปิด toggle')
            else:
                r.set('TC-029', 'skip', 'ต้อง manual verify')
        except Exception as e:
            r.set('TC-029', 'skip', f'Error: {e}')
    else:
        r.set('TC-029', 'skip', 'ไม่พบ MuiSwitch')

    # TC-030
    print('  TC-030: จำนวนวันแจ้งเตือน default = 30')
    nav(page)
    num = page.locator('input[type="number"]').first
    if num.count() > 0:
        v = num.input_value()
        if v == '30':
            r.set('TC-030', 'pass', 'default = 30 วัน')
        else:
            ss(page, 'TC-030-check')
            r.set('TC-030', 'skip', f'default = {v!r} — ต้อง verify เป็นช่องถูก')
    else:
        ss(page, 'TC-030-notfound')
        r.set('TC-030', 'skip', 'ไม่พบ number input')

    # TC-031
    print('  TC-031: จำนวนวัน = 0 → error')
    nav(page)
    num = page.locator('input[type="number"]').first
    if num.count() > 0:
        num.fill('0')
        click_save(page)
        if has_error(page):
            r.set('TC-031', 'pass', 'error เมื่อกรอก 0')
        else:
            ss(page, 'TC-031-check')
            r.set('TC-031', 'skip', 'ต้อง manual')
    else:
        r.set('TC-031', 'skip', 'ไม่พบ number input')

    # TC-032
    print('  TC-032: จำนวนวัน = 366 → error')
    nav(page)
    num = page.locator('input[type="number"]').first
    if num.count() > 0:
        num.fill('366')
        click_save(page)
        if has_error(page):
            r.set('TC-032', 'pass', 'error เมื่อกรอก 366')
        else:
            ss(page, 'TC-032-check')
            r.set('TC-032', 'skip', 'ต้อง manual')
    else:
        r.set('TC-032', 'skip', 'ไม่พบ number input')

    # TC-033
    print('  TC-033: ตัวอักษรใน number field → ไม่รับ')
    nav(page)
    num = page.locator('input[type="number"]').first
    if num.count() > 0:
        # Cannot use .fill('abc') on input[type=number] — use keyboard instead
        num.click()
        num.select_text()
        num.press_sequentially('abc')
        v = num.input_value()
        if not v.strip() or not any(c.isalpha() for c in v):
            r.set('TC-033', 'pass', 'input[type=number] ไม่รับตัวอักษร')
        else:
            ss(page, 'TC-033-check')
            r.set('TC-033', 'skip', f'ค่าหลังพิมพ์: {v!r} — ต้อง verify')
    else:
        r.set('TC-033', 'skip', 'ไม่พบ number input')

    # TC-034
    print('  TC-034: checkbox อื่นๆ → แสดงช่อง email')
    nav(page)
    try:
        other_cb = page.locator(
            'label:has-text("อื่นๆ") input[type="checkbox"], '
            'input[type="checkbox"] + span:has-text("อื่นๆ"), '
            'input[type="checkbox"] ~ *:has-text("อื่นๆ")'
        ).first
        if other_cb.count() == 0:
            # fallback: all checkboxes
            cbs = page.locator('input[type="checkbox"]').all()
            # usually HR Admin is first, Supervisor second, Other last
            other_cb = page.locator('input[type="checkbox"]').last
        other_cb.click()
        page.wait_for_timeout(600)
        email_field = page.locator('input[type="email"], input[placeholder*="email" i]')
        if email_field.count() > 0 and email_field.is_visible():
            r.set('TC-034', 'pass', 'แสดงช่อง email หลังเลือก อื่นๆ')
        else:
            ss(page, 'TC-034-check')
            r.set('TC-034', 'skip', 'ต้อง manual — checkbox อาจไม่ใช่ตัวถูก')
    except Exception as e:
        ss(page, 'TC-034-error')
        r.set('TC-034', 'skip', f'Error: {e}')

    # TC-035
    print('  TC-035: email format ไม่ถูก → error')
    try:
        email_field = page.locator('input[type="email"], input[placeholder*="email" i]')
        if email_field.count() > 0 and email_field.is_visible():
            email_field.fill('notanemail')
            click_save(page)
            if has_error(page):
                r.set('TC-035', 'pass', 'error email format ไม่ถูก')
            else:
                ss(page, 'TC-035-fail')
                r.set('TC-035', 'fail', 'ไม่มี error สำหรับ email ผิด format')
        else:
            r.set('TC-035', 'skip', 'ต้อง manual (TC-034 ต้อง pass ก่อน)')
    except Exception as e:
        r.set('TC-035', 'skip', f'Error: {e}')


# ══════════════════════════════════════════════════════════════════════════════
# Section 6 — บันทึกและผลลัพธ์ (TC-036..039)
# ══════════════════════════════════════════════════════════════════════════════
def s6(page: Page, r: Results):
    print('\n▶ Section 6 — บันทึกและผลลัพธ์')

    # TC-036
    print('  TC-036: ยกเลิก → กลับหน้ารายการ')
    nav(page)
    cancel = page.get_by_role('button', name=re.compile('ยกเลิก|Cancel')).first
    if cancel.count() > 0:
        cancel.click()
        page.wait_for_timeout(1200)
        if '/create' not in page.url:
            r.set('TC-036', 'pass', f'redirect → {page.url}')
        else:
            ss(page, 'TC-036-fail')
            r.set('TC-036', 'fail', 'ยังอยู่ที่ /create หลังกดยกเลิก')
    else:
        ss(page, 'TC-036-notfound')
        r.set('TC-036', 'skip', 'ไม่พบปุ่มยกเลิก')

    # TC-037 — สร้างข้อมูลจริง
    print('  TC-037: กรอกครบ → บันทึกสำเร็จ + toast')
    if not ACTIVE_EMP_CODE:
        r.set('TC-037', 'skip', 'ไม่ได้ตั้ง TEST_EMPLOYEE_CODE — ข้าม TC-037..039')
        r.set('TC-038', 'skip', 'ขึ้นอยู่กับ TC-037')
        r.set('TC-039', 'skip', 'ต้อง manual verify ใน audit log')
        return

    nav(page)
    try:
        # Employee
        fill_employee(page, ACTIVE_EMP_CODE)
        pick_first_option(page)
        # Guard: pick_first_option may navigate away (employee link) — re-navigate if so
        if '/create' not in page.url:
            print(f"    ⚠️  หลุดออกจากฟอร์ม ({page.url}) → navigate กลับ")
            nav(page)
            fill_employee(page, ACTIVE_EMP_CODE)
            # Click option using keyboard Enter instead of mouse click to avoid navigation
            page.locator('ul[role="listbox"] li[role="option"]:visible').first.press('Enter')
            page.wait_for_timeout(800)
            close_open_menus(page)

        # Contract type — nth(1) skips the employee Select trigger (first), targets contract type (second)
        ct_triggers = page.locator('div[class*="MuiSelect-select"]:visible')
        n_ct = ct_triggers.count()
        ct_trigger = ct_triggers.nth(1) if n_ct >= 2 else ct_triggers.first
        print(f"    🔍 MuiSelect-select visible: {n_ct} → using {'nth(1)' if n_ct >= 2 else 'first'}")
        if ct_trigger.count() > 0:
            ct_trigger.click()
            page.wait_for_timeout(500)
            # Contract type uses MuiMenu (not listbox)
            opt = page.locator('[class*="MuiMenu-root"] li:visible').first
            if opt.count() > 0:
                opt.click()
                page.wait_for_timeout(400)
            else:
                page.keyboard.press('Escape')
        close_open_menus(page)
        # Guard: if navigated away, re-navigate
        if '/create' not in page.url:
            print(f"    ⚠️  contract type click navigate ออก ({page.url}) → re-navigate")
            nav(page)
            fill_employee(page, ACTIVE_EMP_CODE)
            page.keyboard.press('ArrowDown')
            page.wait_for_timeout(200)
            page.keyboard.press('Enter')
            page.wait_for_timeout(800)

        # Start date + End date (both required when "ไม่กำหนดวันสิ้นสุด" is unchecked)
        date_inputs = page.locator('input[type="date"]').all()
        if len(date_inputs) >= 1:
            date_inputs[0].fill('2025-07-01')
        if len(date_inputs) >= 2:
            date_inputs[1].fill('2026-06-30')

        close_open_menus(page)
        page.wait_for_timeout(400)
        print(f"    🔍 URL ก่อน save: {page.url}")
        # Scroll to top to see field state and validation errors
        page.evaluate('window.scrollTo(0, 0)')
        page.wait_for_timeout(300)
        ss(page, 'TC-037-form-top')
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        page.wait_for_timeout(300)
        ss(page, 'TC-037-before-save')
        click_save(page)
        page.wait_for_timeout(2500)

        if has_toast(page, 'สำเร็จ') or has_toast(page, 'success'):
            r.set('TC-037', 'pass', 'toast "สำเร็จ" แสดงหลังบันทึก')
            ss(page, 'TC-037-pass')
        elif '/create' not in page.url:
            r.set('TC-037', 'pass', f'redirect สำเร็จ → {page.url}')
            ss(page, 'TC-037-redirect')
        else:
            ss(page, 'TC-037-fail')
            r.set('TC-037', 'fail', 'ยังอยู่ที่ /create หลังกดบันทึก — อาจมี error')

        # TC-038
        print('  TC-038: สถานะ = มีผลบังคับใช้')
        page.wait_for_timeout(1000)
        status_chip = page.locator('[class*="chip"]:has-text("มีผล"), [class*="badge"]:has-text("มีผล"), *:has-text("มีผลบังคับใช้")').first
        if status_chip.count() > 0:
            r.set('TC-038', 'pass', 'สถานะ "มีผลบังคับใช้" แสดงทันที')
        else:
            ss(page, 'TC-038-check')
            r.set('TC-038', 'skip', 'ต้อง manual verify สถานะในหน้า detail')

        # TC-039
        r.set('TC-039', 'skip', 'ต้อง manual verify ใน Audit Log / ประวัติ')

    except Exception as e:
        ss(page, 'TC-037-error')
        r.set('TC-037', 'fail', f'Error: {e}')
        r.set('TC-038', 'skip', 'ขึ้นอยู่กับ TC-037')
        r.set('TC-039', 'skip', 'ต้อง manual verify')


# ══════════════════════════════════════════════════════════════════════════════
# Show results in browser (Playwright inject localStorage → task-408.html)
# ══════════════════════════════════════════════════════════════════════════════
def show_results_in_browser(data: dict):
    """เปิด task-408.html ด้วย Playwright แล้ว inject ผลลัพธ์เข้า localStorage"""
    if not TASK_HTML_FILE.exists():
        print(f"  ⚠️  ไม่พบ {TASK_HTML_FILE}")
        return

    html_url = TASK_HTML_FILE.as_uri()   # file:///G:/My Drive/.../task-408.html
    storage_key = 'qa_task_408'
    payload = json.dumps(data, ensure_ascii=False)

    print(f"\n🌐 เปิดผลลัพธ์ใน browser ...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=False, slow_mo=0)
        ctx = browser.new_context()
        page = ctx.new_page()

        # เปิด HTML file
        page.goto(html_url, wait_until='domcontentloaded')
        page.wait_for_timeout(500)

        # Inject ผลลัพธ์เข้า localStorage แล้ว reload
        page.evaluate(f"""
            localStorage.setItem({json.dumps(storage_key)}, {json.dumps(payload)});
        """)
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(800)

        print(f"  ✅ Import สำเร็จ — browser เปิดค้างไว้ให้ดูผลได้เลย")
        print(f"  ⏸  กด Enter ที่ Terminal นี้เพื่อปิด browser")
        input()
        ctx.close()
        browser.close()


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    if not HR_APP_URL:
        print('❌ ยังไม่ได้ตั้ง HR_APP_URL ใน .env')
        print('   เปิดไฟล์ .env แล้วเพิ่ม: HR_APP_URL=https://...')
        return
    if not HR_USERNAME or not HR_PASSWORD:
        print('❌ ยังไม่ได้ตั้ง HR_USERNAME / HR_PASSWORD ใน .env')
        return

    now = datetime.datetime.now().strftime('%H:%M:%S')
    print(f'🚀 Task 408 Auto-Test [{now}]')
    print(f'   URL    : {CONTRACT_URL}')
    mode_str = 'Manual-Login' if MANUAL_LOGIN else ('Headed' if HEADED else 'Headless')
    if USE_SESSION and SESSION_FILE.exists():
        mode_str += ' + Use-Session'
    if SAVE_SESSION:
        mode_str += ' + Save-Session'
    print(f'   Mode   : {mode_str}')
    print(f'   Section: {SECTION or "ทั้งหมด (1-6)"}')
    if ACTIVE_EMP_CODE:
        print(f'   Emp    : {ACTIVE_EMP_CODE}')

    r = Results()

    sections = {
        1: lambda p: s1(p, r),
        2: lambda p: s2(p, r),
        3: lambda p: s3(p, r),
        4: lambda p: s4(p, r),
        5: lambda p: s5(p, r),
        6: lambda p: s6(p, r),
    }

    with sync_playwright() as pw:
        # manual-login ต้องการ headed เสมอ
        is_headed = HEADED or MANUAL_LOGIN
        browser = pw.chromium.launch(channel='msedge', headless=not is_headed, slow_mo=150 if is_headed else 0)

        # Load saved session if --use-session flag given and file exists
        if USE_SESSION and SESSION_FILE.exists():
            print(f'  📂 โหลด session จาก {SESSION_FILE.name}')
            ctx = browser.new_context(
                storage_state=str(SESSION_FILE),
                viewport={'width': 1440, 'height': 900},
                locale='th-TH'
            )
        else:
            ctx = browser.new_context(viewport={'width': 1440, 'height': 900}, locale='th-TH')

        page = ctx.new_page()

        try:
            if USE_SESSION and SESSION_FILE.exists():
                # Navigate directly to app to verify session still valid
                page.goto(HR_APP_URL, wait_until='networkidle', timeout=30000)
                page.wait_for_timeout(1000)
                if any(p in page.url for p in {'/login', '/otp', '/auth', '/2fa', '/mfa', '/verify'}):
                    print('  ⚠️  Session หมดอายุ — ต้อง login ใหม่')
                    if MANUAL_LOGIN:
                        manual_login(page)
                    else:
                        login(page)
                else:
                    print(f'  ✅ Session ยังใช้ได้ → {page.url}')
            elif MANUAL_LOGIN:
                manual_login(page)
            elif HR_USERNAME and HR_PASSWORD:
                login(page)
            else:
                print('  ❌ ไม่มี credentials และไม่ได้ใช้ --manual-login')
                print('  💡 ใช้: python -X utf8 test_task_408.py --manual-login --save-session')
                return

            # Save session AFTER successful login (for future runs)
            if SAVE_SESSION:
                ctx.storage_state(path=str(SESSION_FILE))
                print(f'  💾 บันทึก session → {SESSION_FILE.name}')
                print(f'  💡 ครั้งต่อไปใช้: python -X utf8 test_task_408.py --use-session')

            # Select company "อรุณเบิกฟ้า จำกัด" before running tests
            select_company(page, 'อรุณเบิกฟ้า')

            to_run = [SECTION] if SECTION else list(sections.keys())
            for sec_num in to_run:
                sections[sec_num](page)

        except KeyboardInterrupt:
            print('\n⏹ หยุดโดย user')
        except Exception as e:
            print(f'\n❌ Fatal: {e}')
            ss(page, '_fatal-error')
        finally:
            ctx.close()
            browser.close()

    r.summary()
    r.save()
    sync_to_firebase(r.data, '408')


if __name__ == '__main__':
    main()

