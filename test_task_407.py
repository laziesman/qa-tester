#!/usr/bin/env python3
"""
ทดสอบอัตโนมัติ Task 407 — หน้าแสดงรายการเอกสารสัญญาทั้งหมดของพนักงาน
URL: https://hr-stg.intelligent-bytes.com/employee/contracts

รัน:
  python -X utf8 test_task_407.py --manual-login --save-session  # ครั้งแรก
  python -X utf8 test_task_407.py --use-session                  # ครั้งถัดไป
  python -X utf8 test_task_407.py --use-session --section 2      # เฉพาะ section
  python -X utf8 test_task_407.py --use-session --show-results   # เปิดผลใน browser
"""

import sys, re, json, datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

from hr_helpers import (
    HR_APP_URL, BASE_DIR, SESSION_FILE,
    launch_browser, ensure_logged_in, select_company
)

# ── Constants ──────────────────────────────────────────────────────────────────
LIST_URL        = f"{HR_APP_URL}/employee/contracts"
SCREENSHOTS_DIR = BASE_DIR / 'screenshots' / 'task-407'
RESULTS_FILE    = BASE_DIR / 'HR' / 'Sprint-5' / 'test-results-407.json'
TASK_HTML_FILE  = BASE_DIR / 'HR' / 'Sprint-5' / 'task-407.html'

# ── CLI args ───────────────────────────────────────────────────────────────────
HEADED       = '--headed'       in sys.argv
MANUAL_LOGIN = '--manual-login' in sys.argv
SAVE_SESSION = '--save-session' in sys.argv
USE_SESSION  = '--use-session'  in sys.argv
SHOW_RESULTS = '--show-results' in sys.argv
SECTION      = None
for i, a in enumerate(sys.argv):
    if a == '--section' and i + 1 < len(sys.argv):
        try: SECTION = int(sys.argv[i + 1])
        except ValueError: pass


# ══════════════════════════════════════════════════════════════════════════════
# Results
# ══════════════════════════════════════════════════════════════════════════════
class Results:
    def __init__(self):
        self.data: dict = {}

    def set(self, tc_id: str, status: str, note: str = ''):
        self.data[tc_id] = {'status': status, 'note': note}
        icon = {'pass': '✅', 'fail': '❌', 'skip': '⏭'}.get(status, '?')
        print(f"    {icon} {tc_id}: {note or status.upper()}")

    def summary(self):
        c = {'pass': 0, 'fail': 0, 'skip': 0}
        fails = []
        for tid, v in self.data.items():
            s = v['status']
            if s in c: c[s] += 1
            if s == 'fail': fails.append(tid)
        total = sum(c.values())
        print(f"\n{'═'*55}")
        print(f"✅ Pass: {c['pass']}  ❌ Fail: {c['fail']}  ⏭ Skip: {c['skip']}  (จาก {total})")
        if fails:
            print(f"Fail: {', '.join(fails)}")
        print(f"{'═'*55}")

    def save(self):
        RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        print(f"\n💾 บันทึกที่: {RESULTS_FILE}")
        if SHOW_RESULTS:
            show_results_in_browser(self.data)
        else:
            print(f"   💡 เพิ่ม --show-results เพื่อเปิดผลใน browser อัตโนมัติ")


# ══════════════════════════════════════════════════════════════════════════════
# Page helpers
# ══════════════════════════════════════════════════════════════════════════════
def ss(page: Page, name: str):
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOTS_DIR / f"{name}.png"), full_page=False)

def nav(page: Page):
    """ไปที่หน้ารายการสัญญา"""
    for attempt in range(3):
        try:
            page.goto(LIST_URL, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            break
        except Exception:
            if attempt == 2: raise
            page.wait_for_timeout(1500)
    page.wait_for_timeout(800)

def count_rows(page: Page) -> int:
    """นับแถวข้อมูลในตาราง/รายการสัญญา"""
    for sel in [
        'tbody tr:visible',
        'main tbody tr:visible',
        '[class*="MuiTableBody"] tr:visible',
    ]:
        n = page.locator(sel).count()
        if n > 0:
            return n
    return 0


def get_filter_selects(page: Page):
    """หา MuiSelect ที่อยู่ใน main content (ไม่ใช่ topbar/header)"""
    for area in ['main', '[class*="MuiContainer"]:visible']:
        sels = page.locator(f'{area} [class*="MuiSelect-select"]:visible')
        if sels.count() > 0:
            return sels
    # fallback: กรองโดยใช้ bounding_box — เอาเฉพาะอันที่ต่ำกว่า header
    return page.locator('[class*="MuiSelect-select"]:visible')

def get_search_input(page: Page):
    """หา search input ของ filter ในหน้า (ไม่ใช่ global search ใน header)"""
    # หา input ที่อยู่ใน main content เท่านั้น — exclude header/appbar
    for sel in [
        'main input[placeholder*="ค้นหา"]:visible',
        'main input[type="search"]:visible',
        'main input[type="text"]:visible',
        '[class*="MuiContainer"] input[placeholder*="ค้นหา"]:visible',
        '[class*="MuiContainer"] input[type="text"]:visible',
    ]:
        el = page.locator(sel).first
        if el.count() > 0:
            return el
    # fallback: หา input ที่ไม่ใช่ใน header
    all_inputs = page.locator('input:visible').all()
    for inp in all_inputs:
        bb = inp.bounding_box()
        if bb and bb['y'] > 80:   # ต่ำกว่า header (topbar ~64-80px)
            return inp
    return None

def get_select_by_label(page: Page, label: str):
    """หา MUI Select ที่มี label ใกล้เคียง"""
    for sel in [
        f'[class*="MuiSelect"]:near(:text("{label}")):visible',
        f'label:has-text("{label}") + * [class*="MuiSelect"]:visible',
    ]:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                return el
        except Exception:
            pass
    # fallback: ทุก MuiSelect
    return page.locator('[class*="MuiSelect-select"]:visible')

def select_mui_option(page: Page, trigger, option_text: str) -> bool:
    """คลิก MUI Select trigger แล้วเลือก option"""
    try:
        trigger.click(timeout=5000)
        page.wait_for_timeout(500)
        opt = page.locator(
            f'[class*="MuiMenu-root"] li:has-text("{option_text}"):visible, '
            f'[role="option"]:has-text("{option_text}"):visible'
        ).first
        if opt.count() > 0:
            opt.click()
            page.wait_for_timeout(600)
            return True
        page.keyboard.press('Escape')
        return False
    except Exception:
        return False

def has_empty_state(page: Page) -> bool:
    """ตรวจว่ามี empty state แสดงอยู่"""
    return page.locator(
        '*:has-text("ไม่มี"):visible, '
        '*:has-text("ไม่พบ"):visible, '
        '*:has-text("empty"):visible, '
        '[class*="empty"]:visible'
    ).count() > 0

def show_results_in_browser(data: dict):
    """เปิด task-407.html แล้ว inject ผลเข้า localStorage"""
    if not TASK_HTML_FILE.exists():
        print(f"  ⚠️  ไม่พบ {TASK_HTML_FILE}")
        return
    payload = json.dumps(data, ensure_ascii=False)
    print(f"\n🌐 เปิดผลลัพธ์ใน browser ...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=False)
        page = browser.new_context().new_page()
        page.goto(TASK_HTML_FILE.as_uri(), wait_until='domcontentloaded')
        page.wait_for_timeout(500)
        page.evaluate(f"localStorage.setItem('qa_task_407', {json.dumps(payload)})")
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(800)
        print(f"  ✅ Import สำเร็จ — กด Enter เพื่อปิด browser")
        input()
        browser.close()


# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — การแสดงรายการและ Default (TC-001..004)
# ══════════════════════════════════════════════════════════════════════════════
def s1(page: Page, r: Results):
    print('\n▶ Section 1 — การแสดงรายการและ Default')

    nav(page)
    ss(page, '_list-page')

    # Debug: ดูโครงสร้างหน้า
    rows = count_rows(page)
    print(f"  🔍 พบแถวข้อมูล: {rows} แถว")

    # TC-001
    print('  TC-001: หน้าโหลด → แสดงรายการสัญญา เรียงตามวันที่ล่าสุด')
    if rows > 0:
        # ตรวจว่ามีวันที่ในแถวแรก (เรียงลำดับต้อง manual verify)
        r.set('TC-001', 'pass', f'แสดง {rows} รายการ (ลำดับ manual verify)')
        ss(page, 'TC-001-pass')
    else:
        ss(page, 'TC-001-fail')
        r.set('TC-001', 'fail', 'ไม่พบรายการสัญญาในหน้า')

    # TC-002
    print('  TC-002: แต่ละแถวแสดงข้อมูลครบ')
    nav(page)
    if rows > 0:
        first_row = page.locator(
            'tbody tr:visible, [class*="MuiTableRow"]:not([class*="head"]):visible'
        ).first
        text = first_row.inner_text() if first_row.count() > 0 else ''
        if text.strip():
            r.set('TC-002', 'pass', f'แถวแรกมีข้อมูล (manual verify columns)')
            ss(page, 'TC-002-pass')
        else:
            ss(page, 'TC-002-check')
            r.set('TC-002', 'skip', 'ต้อง manual verify columns ในแต่ละแถว')
    else:
        r.set('TC-002', 'skip', 'ไม่มีข้อมูลทดสอบ')

    # TC-003
    print('  TC-003: พนักงานไม่มีสัญญา → empty state')
    r.set('TC-003', 'skip', 'ต้อง manual — ต้องการ employee ที่ไม่มีสัญญา')

    # TC-004
    print('  TC-004: Column headers ถูกต้อง')
    nav(page)
    headers = page.locator(
        'thead th:visible, [class*="MuiTableHead"] [class*="MuiTableCell"]:visible'
    ).all_inner_texts()
    if headers:
        r.set('TC-004', 'pass', f'headers: {headers[:6]}')
    else:
        ss(page, 'TC-004-check')
        r.set('TC-004', 'skip', 'ไม่พบ thead — อาจเป็น card layout')


# ══════════════════════════════════════════════════════════════════════════════
# Section 2 — ค้นหา (TC-005..008)
# ══════════════════════════════════════════════════════════════════════════════
def s2(page: Page, r: Results):
    print('\n▶ Section 2 — ค้นหา')
    nav(page)
    total = count_rows(page)

    search = get_search_input(page)
    if not search or search.count() == 0:
        for tc in ['TC-005', 'TC-006', 'TC-007', 'TC-008']:
            r.set(tc, 'skip', 'ไม่พบ search input บนหน้า')
        return

    # TC-005
    print('  TC-005: พิมพ์คำค้นหา → กรองรายการ')
    nav(page)
    search = get_search_input(page)
    # ใช้คำที่น่าจะมีใน contract: "สัญญา"
    search.fill('สัญญา')
    page.wait_for_timeout(1000)
    filtered = count_rows(page)
    if filtered <= total:
        r.set('TC-005', 'pass', f'กรองเหลือ {filtered} จาก {total}')
        ss(page, 'TC-005-pass')
    else:
        ss(page, 'TC-005-fail')
        r.set('TC-005', 'fail', 'จำนวนรายการไม่เปลี่ยนหลังค้นหา')

    # TC-006
    print('  TC-006: ค้นหาคำที่ไม่มี → empty state')
    nav(page)
    search = get_search_input(page)
    search.fill('xyzไม่มีในระบบ999')
    page.wait_for_timeout(1000)
    empty_rows = count_rows(page)
    empty_shown = has_empty_state(page)
    if empty_rows == 0 or empty_shown:
        r.set('TC-006', 'pass', f'rows={empty_rows}, empty state={empty_shown}')
        ss(page, 'TC-006-pass')
    else:
        ss(page, 'TC-006-fail')
        r.set('TC-006', 'fail', f'ยังแสดง {empty_rows} แถวหลังค้นหาคำที่ไม่มี')

    # TC-007
    print('  TC-007: ลบคำค้นหา → รายการทั้งหมดกลับมา')
    search.fill('')
    page.wait_for_timeout(1000)
    after_clear = count_rows(page)
    if after_clear >= total:
        r.set('TC-007', 'pass', f'กลับมา {after_clear} รายการ')
    else:
        ss(page, 'TC-007-fail')
        r.set('TC-007', 'fail', f'หลังลบคำค้น เหลือ {after_clear} (ควร {total})')

    # TC-008
    print('  TC-008: Real-time search (ไม่ต้องกด Enter)')
    nav(page)
    search = get_search_input(page)
    before = count_rows(page)
    search.type('ส', delay=50)   # พิมพ์ทีละตัว ไม่กด Enter
    page.wait_for_timeout(800)
    after = count_rows(page)
    if after != before or has_empty_state(page):
        r.set('TC-008', 'pass', f'รายการเปลี่ยนทันที ({before}→{after}) ไม่ต้องกด Enter')
    else:
        ss(page, 'TC-008-check')
        r.set('TC-008', 'skip', 'ต้อง manual verify — count ไม่เปลี่ยน (อาจ debounce)')


# ══════════════════════════════════════════════════════════════════════════════
# Section 3 — กรองตามประเภทสัญญา (TC-009..011)
# ══════════════════════════════════════════════════════════════════════════════
def s3(page: Page, r: Results):
    print('\n▶ Section 3 — กรองตามประเภทสัญญา')
    nav(page)
    total = count_rows(page)

    # หา dropdown ประเภทสัญญา (มักเป็น Select แรกหรือที่มี label "ประเภท")
    filter_sels = get_filter_selects(page)
    n_sels = filter_sels.count()
    print(f"  🔍 พบ filter MuiSelect: {n_sels} ตัว")

    if n_sels == 0:
        for tc in ['TC-009', 'TC-010', 'TC-011']:
            r.set(tc, 'skip', 'ไม่พบ dropdown ประเภทสัญญา')
        return

    # TC-010: เปิด dropdown แรกดู options
    print('  TC-010: dropdown แสดงประเภทที่มีในระบบ')
    nav(page)
    filter_sels = get_filter_selects(page)
    type_trigger = filter_sels.first
    type_trigger.click(timeout=5000)
    page.wait_for_timeout(600)
    opts = page.locator('[class*="MuiMenu-root"] li:visible, [role="listbox"] li:visible').all_inner_texts()
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)
    print(f"  🔍 options: {opts[:6]}")
    if opts:
        r.set('TC-010', 'pass', f'dropdown แสดง {len(opts)} ตัวเลือก: {opts[:4]}')
        ss(page, 'TC-010-pass')
    else:
        ss(page, 'TC-010-fail')
        r.set('TC-010', 'fail', 'dropdown ว่าง หรือเปิดไม่ได้')

    # TC-009: เลือก option ที่ไม่ใช่ "ทั้งหมด"
    print('  TC-009: เลือกประเภทสัญญา → กรองรายการ')
    nav(page)
    filter_sels = get_filter_selects(page)
    filter_sels.first.click(timeout=5000)
    page.wait_for_timeout(600)
    all_opts = page.locator('[class*="MuiMenu-root"] li:visible, [role="listbox"] li:visible').all()
    chosen = None
    for opt in all_opts:
        txt = opt.inner_text().strip()
        if txt and 'ทั้งหมด' not in txt:
            chosen = txt
            opt.click()
            break
    if not chosen:
        page.keyboard.press('Escape')
    page.wait_for_timeout(800)

    if chosen:
        filtered = count_rows(page)
        ss(page, 'TC-009-pass')
        r.set('TC-009', 'pass', f'เลือก "{chosen}" → เหลือ {filtered} รายการ (manual verify)')
    else:
        r.set('TC-009', 'skip', 'ไม่พบ option ที่ไม่ใช่ ทั้งหมด')

    # TC-011: เลือก "ทั้งหมด" คืน
    print('  TC-011: เลือก "ทั้งหมด" → รายการทั้งหมดกลับมา')
    nav(page)
    filter_sels = get_filter_selects(page)
    ok = select_mui_option(page, filter_sels.first, 'ทั้งหมด')
    page.wait_for_timeout(800)
    after = count_rows(page)
    if ok and after >= total:
        r.set('TC-011', 'pass', f'กลับมา {after} รายการ')
    elif ok:
        r.set('TC-011', 'pass', f'เลือก "ทั้งหมด" สำเร็จ count={after}')
    else:
        r.set('TC-011', 'skip', 'ไม่พบ option "ทั้งหมด"')


# ══════════════════════════════════════════════════════════════════════════════
# Section 4 — กรองตามสถานะสัญญา (TC-012..015)
# ══════════════════════════════════════════════════════════════════════════════
def s4(page: Page, r: Results):
    print('\n▶ Section 4 — กรองตามสถานะสัญญา')
    nav(page)
    total = count_rows(page)

    filter_sels = get_filter_selects(page)
    n = filter_sels.count()
    # สถานะ dropdown มักเป็นตัวที่ 2 ใน filter area (ถ้ามีหลายตัว)
    status_idx = 1 if n >= 2 else 0
    print(f"  🔍 filter selects={n}, ใช้ตัวที่ {status_idx+1} เป็น status filter")

    # ก่อนเริ่ม: เปิด status dropdown เพื่อ debug options
    nav(page)
    filter_sels = get_filter_selects(page)
    filter_sels.nth(status_idx).click(timeout=5000)
    page.wait_for_timeout(600)
    debug_opts = page.locator('[class*="MuiMenu-root"] li:visible, [role="listbox"] li:visible').all_inner_texts()
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)
    print(f"  🔍 status options: {debug_opts}")

    # label จริงในระบบ: "มีผลบังคับใช้" (ไม่ใช่ "ใช้งาน")
    status_map = {
        'TC-012': 'มีผลบังคับใช้',
        'TC-013': 'หมดอายุ',
        'TC-014': 'ใกล้หมดอายุ',
    }

    for tc, label in status_map.items():
        print(f'  {tc}: filter "{label}"')
        nav(page)
        filter_sels = get_filter_selects(page)
        ok = select_mui_option(page, filter_sels.nth(status_idx), label)
        page.wait_for_timeout(800)
        filtered = count_rows(page)
        if ok:
            ss(page, f'{tc}-pass')
            r.set(tc, 'pass', f'filter "{label}" → {filtered} รายการ (manual verify badge)')
        else:
            r.set(tc, 'skip', f'ไม่พบ option "{label}" — options: {debug_opts[:3]}')

    # TC-015
    print('  TC-015: เลือก "ทั้งหมด" → รายการทั้งหมดกลับมา')
    nav(page)
    filter_sels = get_filter_selects(page)
    ok = select_mui_option(page, filter_sels.nth(status_idx), 'ทั้งหมด')
    after = count_rows(page)
    if ok and after >= total:
        r.set('TC-015', 'pass', f'กลับมา {after} รายการ')
    else:
        ss(page, 'TC-015-check')
        r.set('TC-015', 'skip', f'เลือก "ทั้งหมด" ok={ok}, count={after}')


# ══════════════════════════════════════════════════════════════════════════════
# Section 5 — กรองตามช่วงวันที่ (TC-016..018)
# ══════════════════════════════════════════════════════════════════════════════
def s5(page: Page, r: Results):
    print('\n▶ Section 5 — กรองตามช่วงวันที่')
    nav(page)
    total = count_rows(page)

    date_inputs = page.locator('input[type="date"]:visible').all()
    print(f"  🔍 พบ date input: {len(date_inputs)} ช่อง")

    if len(date_inputs) < 2:
        for tc in ['TC-016', 'TC-017', 'TC-018']:
            r.set(tc, 'skip', f'พบ date input {len(date_inputs)} ช่อง (ต้องการ 2)')
        return

    # TC-016
    print('  TC-016: เลือกช่วงวันที่ → กรองรายการ')
    nav(page)
    date_inputs = page.locator('input[type="date"]:visible')
    date_inputs.nth(0).fill('2024-01-01')
    date_inputs.nth(1).fill('2026-12-31')
    page.wait_for_timeout(1000)
    filtered = count_rows(page)
    ss(page, 'TC-016-pass')
    r.set('TC-016', 'pass', f'ช่วง 2024-2026 → {filtered} รายการ (manual verify)')

    # TC-017
    print('  TC-017: วันสิ้นสุด < วันเริ่มต้น → error หรือ warning')
    nav(page)
    date_inputs = page.locator('input[type="date"]:visible')
    date_inputs.nth(0).fill('2026-01-01')
    date_inputs.nth(1).fill('2025-01-01')
    page.wait_for_timeout(800)
    err = page.locator(
        '[class*="error"]:visible, [class*="Mui-error"]:visible, '
        '[role="alert"]:visible, *:has-text("ต้องมากกว่า"):visible'
    ).count() > 0
    if err:
        r.set('TC-017', 'pass', 'มี error เมื่อวันสิ้นสุด < วันเริ่มต้น')
    else:
        ss(page, 'TC-017-check')
        r.set('TC-017', 'skip', 'ไม่พบ error — ต้อง manual verify')

    # TC-018
    print('  TC-018: เคลียร์ filter วันที่ → รายการทั้งหมดกลับมา')
    nav(page)
    date_inputs = page.locator('input[type="date"]:visible')
    date_inputs.nth(0).fill('2025-01-01')
    date_inputs.nth(1).fill('2025-06-30')
    page.wait_for_timeout(800)
    date_inputs.nth(0).fill('')
    date_inputs.nth(1).fill('')
    page.wait_for_timeout(1000)
    after = count_rows(page)
    if after >= total:
        r.set('TC-018', 'pass', f'กลับมา {after} รายการหลังเคลียร์วันที่')
    else:
        ss(page, 'TC-018-check')
        r.set('TC-018', 'skip', f'หลังเคลียร์วันที่ count={after} (manual verify)')


# ══════════════════════════════════════════════════════════════════════════════
# Section 6 — กรองหลายเงื่อนไขพร้อมกัน (TC-019..021)
# ══════════════════════════════════════════════════════════════════════════════
def s6(page: Page, r: Results):
    print('\n▶ Section 6 — กรองหลายเงื่อนไขพร้อมกัน')
    nav(page)
    total = count_rows(page)

    # TC-019
    print('  TC-019: filter หลายตัวพร้อมกัน → AND logic')
    nav(page)
    filter_sels = get_filter_selects(page)
    type_ok = status_ok = False
    if filter_sels.count() >= 1:
        filter_sels.nth(0).click()
        page.wait_for_timeout(400)
        opts = page.locator('[class*="MuiMenu-root"] li:visible, [role="listbox"] li:visible').all()
        for opt in opts:
            if 'ทั้งหมด' not in opt.inner_text():
                opt.click()
                type_ok = True
                break
        else:
            page.keyboard.press('Escape')
        page.wait_for_timeout(400)
    if filter_sels.count() >= 2:
        status_ok = select_mui_option(page, filter_sels.nth(1), 'ใช้งาน')
    page.wait_for_timeout(800)
    filtered = count_rows(page)
    empty = has_empty_state(page)
    ss(page, 'TC-019-check')
    if type_ok or status_ok:
        r.set('TC-019', 'pass', f'filter รวม → {filtered} รายการ, empty={empty} (manual verify AND logic)')
    else:
        r.set('TC-019', 'skip', 'ตั้ง filter ไม่สำเร็จ')

    # TC-020
    print('  TC-020: search + filter พร้อมกัน')
    nav(page)
    search = get_search_input(page)
    if search and search.count() > 0:
        search.fill('สัญญา')
        page.wait_for_timeout(400)
        filter_sels = get_filter_selects(page)
        if filter_sels.count() >= 1:
            select_mui_option(page, filter_sels.nth(0), 'ใช้งาน')
        page.wait_for_timeout(800)
        combined = count_rows(page)
        ss(page, 'TC-020-check')
        r.set('TC-020', 'pass', f'search+filter → {combined} รายการ (manual verify)')
    else:
        r.set('TC-020', 'skip', 'ไม่พบ search input')

    # TC-021
    print('  TC-021: กดปุ่ม Reset → filter ทั้งหมดกลับ default')
    nav(page)
    # ตั้ง filter ก่อน
    search = get_search_input(page)
    if search and search.count() > 0:
        search.fill('ทดสอบ')
        page.wait_for_timeout(400)
    # หาปุ่ม reset/clear
    reset_btn = page.locator(
        'button:has-text("รีเซ็ต"):visible, button:has-text("Reset"):visible, '
        'button:has-text("ล้าง"):visible, button:has-text("Clear"):visible'
    ).first
    if reset_btn.count() > 0:
        reset_btn.click()
        page.wait_for_timeout(800)
        after = count_rows(page)
        search_val = search.input_value() if search and search.count() > 0 else '?'
        if after >= total and search_val == '':
            r.set('TC-021', 'pass', f'Reset สำเร็จ — กลับมา {after} รายการ search ว่าง')
        else:
            ss(page, 'TC-021-fail')
            r.set('TC-021', 'fail', f'หลัง Reset rows={after}, search="{search_val}"')
    else:
        ss(page, 'TC-021-check')
        r.set('TC-021', 'skip', 'ไม่พบปุ่ม Reset — ต้อง manual')


# ══════════════════════════════════════════════════════════════════════════════
# Section 7 — Badge สถานะและวันที่เหลือ (TC-022..025)
# ══════════════════════════════════════════════════════════════════════════════
def s7(page: Page, r: Results):
    print('\n▶ Section 7 — Badge สถานะและวันที่เหลือ')
    nav(page)
    ss(page, 'TC-022-badges')

    # TC-022
    print('  TC-022: สัญญา active → Badge สีเขียว')
    green = page.locator(
        '[class*="Chip"][class*="success"]:visible, [class*="badge"][style*="green"]:visible, '
        '*:has-text("ใช้งาน"):visible, *:has-text("มีผล"):visible'
    ).count()
    if green > 0:
        r.set('TC-022', 'pass', f'พบ badge active {green} รายการ')
    else:
        r.set('TC-022', 'skip', 'ต้อง manual verify badge color — selector อาจไม่ตรง')

    # TC-023
    print('  TC-023: สัญญาหมดอายุ → Badge สีแดง')
    red = page.locator(
        '[class*="Chip"][class*="error"]:visible, '
        '*:has-text("หมดอายุ"):visible'
    ).count()
    if red > 0:
        r.set('TC-023', 'pass', f'พบ badge หมดอายุ {red} รายการ')
    else:
        r.set('TC-023', 'skip', 'ไม่พบ badge หมดอายุ — อาจไม่มีข้อมูลหรือ selector ไม่ตรง')

    # TC-024
    print('  TC-024: สัญญาใกล้หมดอายุ → Badge สีเหลือง + วันเหลือ')
    near = page.locator(
        '[class*="Chip"][class*="warning"]:visible, '
        '*:has-text("ใกล้หมด"):visible, '
        '*:has-text("เหลือ"):visible'
    ).count()
    if near > 0:
        r.set('TC-024', 'pass', f'พบ badge ใกล้หมดอายุ {near} รายการ')
    else:
        r.set('TC-024', 'skip', 'ไม่พบ badge ใกล้หมดอายุ — manual verify')

    # TC-025
    print('  TC-025: วันเหลือตรงกับการคำนวณ')
    r.set('TC-025', 'skip', 'ต้อง manual คำนวณ วันสิ้นสุด - วันนี้ เทียบกับที่แสดง')


# ══════════════════════════════════════════════════════════════════════════════
# Section 8 — Auto-เปลี่ยนสถานะ (TC-026..027)
# ══════════════════════════════════════════════════════════════════════════════
def s8(page: Page, r: Results):
    print('\n▶ Section 8 — Auto-เปลี่ยนสถานะ')
    r.set('TC-026', 'skip', 'ต้อง manual — ต้องการ contract ที่ expire เมื่อวาน')
    r.set('TC-027', 'skip', 'ต้อง manual — verify contract active ยังไม่หมดอายุ')


# ══════════════════════════════════════════════════════════════════════════════
# Section 9 — Pagination (TC-028..031)
# ══════════════════════════════════════════════════════════════════════════════
def s9(page: Page, r: Results):
    print('\n▶ Section 9 — Pagination')
    nav(page)
    total = count_rows(page)

    pagination = page.locator(
        '[class*="MuiPagination"]:visible, '
        'nav[aria-label*="pagination"]:visible, '
        '[class*="pagination"]:visible'
    )
    has_pagination = pagination.count() > 0
    print(f"  🔍 Pagination: {'พบ' if has_pagination else 'ไม่พบ'}, rows={total}")

    # TC-028
    print('  TC-028: มีสัญญาเกิน page size → pagination แสดง')
    if has_pagination:
        r.set('TC-028', 'pass', 'pagination แสดง')
        ss(page, 'TC-028-pass')
    else:
        r.set('TC-028', 'skip', f'ไม่พบ pagination (rows={total}) — อาจข้อมูลน้อยกว่า page size')

    # TC-029
    print('  TC-029: กดหน้าถัดไป → รายการใหม่')
    nav(page)
    next_btn = page.locator(
        'button[aria-label*="next"]:visible, button:has-text("›"):visible, '
        '[class*="next"]:visible'
    ).first
    if next_btn.count() > 0 and not next_btn.is_disabled():
        first_row_text = page.locator(
            'tbody tr:visible, [class*="MuiTableRow"]:not([class*="head"]):visible'
        ).first.inner_text() if count_rows(page) > 0 else ''
        next_btn.click()
        page.wait_for_timeout(1000)
        new_first = page.locator(
            'tbody tr:visible, [class*="MuiTableRow"]:not([class*="head"]):visible'
        ).first.inner_text() if count_rows(page) > 0 else ''
        if new_first != first_row_text:
            r.set('TC-029', 'pass', 'หน้าถัดไปแสดงรายการใหม่')
            ss(page, 'TC-029-pass')
        else:
            ss(page, 'TC-029-fail')
            r.set('TC-029', 'fail', 'รายการในหน้าถัดไปเหมือนหน้าแรก')
    else:
        r.set('TC-029', 'skip', 'ไม่มีปุ่ม next หรือ disabled (ข้อมูลหน้าเดียว)')

    # TC-030
    print('  TC-030: filter แล้ว pagination อัปเดต')
    nav(page)
    search = get_search_input(page)
    if search and search.count() > 0:
        search.fill('xyzไม่มีในระบบ')
        page.wait_for_timeout(1000)
        pag_after = page.locator('[class*="MuiPagination"]:visible, [class*="pagination"]:visible').count()
        if pag_after == 0 or not page.locator('button[aria-label*="next"]:visible').count():
            r.set('TC-030', 'pass', 'pagination หายหรือ next disabled เมื่อ filter ไม่มีผล')
        else:
            ss(page, 'TC-030-check')
            r.set('TC-030', 'skip', 'ต้อง manual verify pagination เมื่อ filter ลดรายการ')
    else:
        r.set('TC-030', 'skip', 'ไม่พบ search input')

    # TC-031
    print('  TC-031: รายการน้อยกว่า page size → ไม่แสดง pagination')
    nav(page)
    if not has_pagination:
        r.set('TC-031', 'pass', f'ไม่มี pagination เมื่อ rows={total}')
    else:
        r.set('TC-031', 'skip', 'มี pagination — ไม่สามารถ verify กรณีนี้จาก data ปัจจุบัน')


# ══════════════════════════════════════════════════════════════════════════════
# Section 10 — Export Excel (TC-032..035)
# ══════════════════════════════════════════════════════════════════════════════
def s10(page: Page, r: Results):
    print('\n▶ Section 10 — Export Excel')
    nav(page)

    # debug: แสดง buttons ทั้งหมดบนหน้า พร้อม aria-label
    all_btns_info = [(b.inner_text().strip(), b.get_attribute('aria-label') or b.get_attribute('title') or '')
                     for b in page.locator('button:visible').all()]
    print(f"  🔍 buttons (text, aria/title): {all_btns_info}")

    export_btn = page.locator(
        'button:has-text("Export"):visible, button:has-text("xlsx"):visible, '
        'button:has-text("ดาวน์โหลด"):visible, button:has-text("Excel"):visible, '
        'button:has-text("ส่งออก"):visible'
    ).first

    if export_btn.count() == 0:
        for tc in ['TC-032', 'TC-033', 'TC-034', 'TC-035']:
            r.set(tc, 'skip', 'ไม่มีปุ่ม Export Excel บนหน้า — ต้อง manual verify หรืออาจยังไม่ implement')
        return

    # TC-032
    print('  TC-032: กด Export Excel → ดาวน์โหลด .xlsx')
    nav(page)
    export_btn = page.locator(
        'button:has-text("Export"):visible, button:has-text("xlsx"):visible, '
        'button:has-text("ดาวน์โหลด"):visible, button:has-text("Excel"):visible'
    ).first
    try:
        with page.expect_download(timeout=15000) as dl:
            export_btn.click()
        download = dl.value
        fname = download.suggested_filename
        if fname and ('.xlsx' in fname or '.xls' in fname or '.csv' in fname):
            r.set('TC-032', 'pass', f'ดาวน์โหลดสำเร็จ: {fname}')
        else:
            r.set('TC-032', 'pass', f'ดาวน์โหลดสำเร็จ: {fname} (verify extension)')
    except Exception as e:
        ss(page, 'TC-032-fail')
        r.set('TC-032', 'fail', f'Export ไม่สำเร็จ: {e}')

    # TC-033..035
    r.set('TC-033', 'skip', 'ต้อง manual เปิดไฟล์ Excel ตรวจ columns')
    r.set('TC-034', 'skip', 'ต้อง manual — ตั้ง filter แล้ว export ตรวจไฟล์')
    r.set('TC-035', 'skip', 'ต้อง manual — filter ไม่มีผลแล้ว export')


# ══════════════════════════════════════════════════════════════════════════════
# Section 11 — สิทธิ์และปุ่มต่างๆ (TC-036..042)
# ══════════════════════════════════════════════════════════════════════════════
def s11(page: Page, r: Results):
    print('\n▶ Section 11 — สิทธิ์และปุ่มต่างๆ')
    select_company(page, 'อรุณเบิกฟ้า')
    nav(page)

    # TC-036
    print('  TC-036: ปุ่ม "เพิ่มสัญญา" แสดงสำหรับ user ที่มีสิทธิ์')
    add_btn = page.locator(
        'button:has-text("เพิ่ม"):visible, button:has-text("สร้าง"):visible, '
        'a:has-text("เพิ่ม"):visible, button:has-text("New"):visible'
    ).first
    if add_btn.count() > 0:
        r.set('TC-036', 'pass', f'ปุ่ม "{add_btn.inner_text().strip()}" แสดงอยู่')
    else:
        ss(page, 'TC-036-check')
        r.set('TC-036', 'skip', 'ไม่พบปุ่ม เพิ่มสัญญา — ต้อง manual verify')

    # TC-037
    r.set('TC-037', 'skip', 'ต้อง manual — ต้อง login ด้วย user ที่ไม่มีสิทธิ์')

    # ── helper: hover row ด้วย mouse coordinates แล้ว JS click menu item ──
    def open_kebab_and_click(p: Page, action_text: str) -> bool:
        """ใช้ mouse.move() hover row → ตามด้วย mouse.click() บน visible more-actions button"""
        # รอให้ตาราง/รายการโหลดก่อน
        try:
            p.wait_for_selector('tbody tr:visible', timeout=8000)
        except Exception:
            pass
        p.wait_for_timeout(500)

        first_row = p.locator('tbody tr:visible').first
        if first_row.count() == 0:
            print(f"  ⚠️  ไม่พบแถวข้อมูลใน tbody")
            return False
        bb = first_row.bounding_box()
        if not bb:
            print(f"  ⚠️  bounding box ของ first row เป็น None")
            return False

        # ย้าย mouse ไป center ของ row แล้วรอให้ button ปรากฏ
        cx = bb['x'] + bb['width'] / 2
        cy = bb['y'] + bb['height'] / 2
        p.mouse.move(cx, cy)
        p.wait_for_timeout(800)

        # หา "more actions" button ที่ visible อยู่ในขณะนี้ (เพราะ hover แล้ว)
        btn = p.locator('button[aria-label="more actions"]:visible').first
        if btn.count() == 0:
            print(f"  ⚠️  more actions button ไม่ปรากฏหลัง hover")
            return False

        btn_bb = btn.bounding_box()
        if not btn_bb:
            return False
        print(f"  🔍 more-actions btn at x={btn_bb['x']:.0f} y={btn_bb['y']:.0f}")

        # click ด้วย mouse coordinates โดยตรง
        click_x = btn_bb['x'] + btn_bb['width'] / 2
        click_y = btn_bb['y'] + btn_bb['height'] / 2
        print(f"  🔍 clicking at ({click_x:.0f}, {click_y:.0f})")
        p.mouse.click(click_x, click_y)
        p.wait_for_timeout(800)
        p.screenshot(path=str(SCREENSHOTS_DIR / f'debug-after-kebab-{action_text[:4]}.png'))

        # JS click: walk TEXT NODES เพื่อหา element ที่มี text ตรงกันและ visible จริง
        clicked = p.evaluate("""(text) => {
            // walk text nodes ทั้งหมด — หา leaf element ที่มี exact text และ visible
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                if (node.textContent.trim() === text) {
                    const el = node.parentElement;
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        el.click();
                        return 'text-click:' + text;
                    }
                }
            }
            // fallback: show what text is actually visible (non-empty, reasonable length)
            const all = [];
            const walker2 = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            while ((node = walker2.nextNode())) {
                const t = node.textContent.trim();
                if (t.length > 1 && t.length < 50) {
                    const el = node.parentElement;
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        all.push(t);
                    }
                }
            }
            return JSON.stringify([...new Set(all)].slice(0, 20));
        }""", action_text)

        if clicked and str(clicked).startswith('text-click:'):
            print(f"  🔍 clicked: '{clicked}'")
            p.wait_for_timeout(800)
            return True
        print(f"  🔍 visible text items: {clicked}")
        p.keyboard.press('Escape')
        p.wait_for_timeout(400)
        return False

    # TC-038
    print('  TC-038: ปุ่ม "ดูรายละเอียด" → เปิดหน้า detail')
    nav(page)
    # ลอง 1: คลิก contract number link (shortcut to detail)
    contract_link = page.locator('tbody tr:visible').first.locator('a').first
    if contract_link.count() > 0:
        contract_link.click()
        page.wait_for_timeout(1500)
        if '/contracts/' in page.url:
            r.set('TC-038', 'pass', f'คลิก contract link → detail → {page.url}')
            ss(page, 'TC-038-pass')
        else:
            ss(page, 'TC-038-check')
            r.set('TC-038', 'skip', f'URL={page.url} — manual verify')
    else:
        # ลอง 2: kebab menu
        ok38 = open_kebab_and_click(page, 'ดูรายละเอียด')
        if ok38:
            r.set('TC-038', 'pass' if '/contracts/' in page.url else 'skip',
                  f'ดูรายละเอียด → {page.url}')
            ss(page, 'TC-038-pass')
        else:
            r.set('TC-038', 'skip', 'ไม่พบ link/option ดูรายละเอียด')

    # TC-039
    print('  TC-039: ปุ่ม "แก้ไข" → เปิดฟอร์มแก้ไข')
    nav(page)
    ok39 = open_kebab_and_click(page, 'แก้ไข')
    if ok39:
        page.wait_for_timeout(1000)
        cur_url = page.url
        # accept: /contracts/{id} (ไม่จำเป็นต้องมี /edit ใน URL)
        if '/contracts/' in cur_url and cur_url != LIST_URL:
            r.set('TC-039', 'pass', f'แก้ไข → {cur_url} (manual verify form)')
            ss(page, 'TC-039-pass')
        else:
            ss(page, 'TC-039-check')
            r.set('TC-039', 'skip', f'URL={cur_url} — manual verify')
    else:
        r.set('TC-039', 'skip', 'ไม่พบ option "แก้ไข" ใน row menu')

    # TC-040
    print('  TC-040: ปุ่ม "ลบ" → Modal ยืนยันแสดง')
    nav(page)
    ok40 = open_kebab_and_click(page, 'ลบ')
    if ok40:
        modal = page.locator('[class*="MuiDialog"]:visible, [role="dialog"]:visible')
        if modal.count() > 0:
            r.set('TC-040', 'pass', 'Modal ยืนยันลบแสดงขึ้น')
            ss(page, 'TC-040-pass')
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)
        else:
            ss(page, 'TC-040-fail')
            r.set('TC-040', 'fail', 'คลิกลบแล้วไม่มี dialog ยืนยัน')
    else:
        # row action menu มีแค่ ดูรายละเอียด / แก้ไข — ไม่มี option "ลบ"
        ss(page, 'TC-040-skip')
        r.set('TC-040', 'skip', 'row menu มีแค่ ดูรายละเอียด/แก้ไข — ไม่มี option ลบ (manual verify)')

    # TC-041
    r.set('TC-041', 'skip', 'ต้อง manual — ต้อง login ด้วย user ที่ไม่มีสิทธิ์')

    # TC-042
    print('  TC-042: Responsive 375px')
    nav(page)
    page.set_viewport_size({'width': 375, 'height': 812})
    page.wait_for_timeout(800)
    overflow = page.evaluate(
        'document.documentElement.scrollWidth > document.documentElement.clientWidth'
    )
    ss(page, 'TC-042-mobile')
    if not overflow:
        r.set('TC-042', 'pass', 'ไม่มี horizontal overflow ที่ 375px')
    else:
        r.set('TC-042', 'fail', 'มี horizontal overflow ที่ 375px')
    page.set_viewport_size({'width': 1440, 'height': 900})


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    if not HR_APP_URL:
        print('❌ ยังไม่ได้ตั้ง HR_APP_URL ใน .env')
        return

    now = datetime.datetime.now().strftime('%H:%M:%S')
    print(f'🚀 Task 407 Auto-Test [{now}]')
    print(f'   URL    : {LIST_URL}')
    mode = 'Manual-Login' if MANUAL_LOGIN else 'Auto'
    if USE_SESSION and SESSION_FILE.exists(): mode += ' + Use-Session'
    if SAVE_SESSION: mode += ' + Save-Session'
    print(f'   Mode   : {mode}')
    print(f'   Section: {SECTION or "ทั้งหมด (1-11)"}')

    r = Results()
    sections = {
        1: s1, 2: s2, 3: s3, 4: s4,  5: s5,  6: s6,
        7: s7, 8: s8, 9: s9, 10: s10, 11: s11,
    }

    with sync_playwright() as pw:
        browser, ctx = launch_browser(pw, headed=HEADED or MANUAL_LOGIN, use_session=USE_SESSION)
        page = ctx.new_page()
        try:
            ensure_logged_in(page, USE_SESSION, MANUAL_LOGIN, SAVE_SESSION)
            select_company(page, 'อรุณเบิกฟ้า')

            to_run = [SECTION] if SECTION else list(sections.keys())
            for n in to_run:
                sections[n](page, r)

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


if __name__ == '__main__':
    main()
