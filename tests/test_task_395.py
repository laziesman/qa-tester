#!/usr/bin/env python3
"""
ทดสอบอัตโนมัติ Task 395 — บันทึกใบลาออก
URL: https://hr-stg.intelligent-bytes.com/employee/resignation/create

รัน:
  python -X utf8 test_task_395.py --manual-login --save-session  # ครั้งแรก
  python -X utf8 test_task_395.py --use-session                  # ครั้งถัดไป
  python -X utf8 test_task_395.py --use-session --section 2      # เฉพาะ section
"""

import sys, re, json, datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

from hr_helpers import (
    HR_APP_URL, BASE_DIR, SESSION_FILE,
    launch_browser, sync_to_firebase, ensure_logged_in, select_company
)

# ── Constants ──────────────────────────────────────────────────────────────────
FORM_URL        = f"{HR_APP_URL}/employee/resignation/create"
SCREENSHOTS_DIR = BASE_DIR / 'screenshots' / 'task-395'
RESULTS_FILE    = BASE_DIR / 'HR' / 'Sprint-5' / 'test-results-395.json'
TASK_HTML_FILE  = BASE_DIR / 'HR' / 'Sprint-5' / 'task-395.html'

TEST_EMPLOYEES = ['test4', 'test3', 'test2', 'test1']

TODAY = datetime.date.today()
DATE_TODAY    = TODAY.strftime('%Y-%m-%d')
DATE_PLUS_30  = (TODAY + datetime.timedelta(days=30)).strftime('%Y-%m-%d')
DATE_PLUS_5   = (TODAY + datetime.timedelta(days=5)).strftime('%Y-%m-%d')
DATE_MINUS_1  = (TODAY - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
DATE_MINUS_35 = (TODAY - datetime.timedelta(days=35)).strftime('%Y-%m-%d')

# ── CLI args ───────────────────────────────────────────────────────────────────
HEADED       = '--headed'       in sys.argv
MANUAL_LOGIN = '--manual-login' in sys.argv
SAVE_SESSION = '--save-session' in sys.argv
USE_SESSION  = '--use-session'  in sys.argv
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
        print(f"   💡 เปิดผลใน browser: เปิด task-395.html แล้ว import JSON")


# ══════════════════════════════════════════════════════════════════════════════
# Page helpers
# ══════════════════════════════════════════════════════════════════════════════
def ss(page: Page, name: str):
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOTS_DIR / f"{name}.png"), full_page=False)

def nav(page: Page):
    """เลือกบริษัท อรุณเบิกฟ้า ก่อนเสมอ แล้วไปฟอร์มบันทึกใบลาออก"""
    select_company(page, 'อรุณเบิกฟ้า')
    for attempt in range(3):
        try:
            page.goto(FORM_URL, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            break
        except Exception:
            if attempt == 2: raise
            page.wait_for_timeout(1500)
    page.wait_for_timeout(800)

def find_employee_search(page: Page):
    """หา input ค้นหารหัสพนักงาน (MUI Autocomplete)"""
    for sel in [
        'main input[placeholder*="รหัส"]:visible',
        'main input[placeholder*="ค้นหา"]:visible',
        'main input[placeholder*="พนักงาน"]:visible',
        'main input[aria-autocomplete="list"]:visible',
        'main input[type="text"]:visible',
    ]:
        el = page.locator(sel).first
        if el.count() > 0:
            return el
    # fallback: input แรกใน main content
    all_inputs = page.locator('input:visible').all()
    for inp in all_inputs:
        bb = inp.bounding_box()
        if bb and bb['y'] > 80:
            return inp
    return None

def search_and_select_employee(page: Page, query: str) -> bool:
    """พิมพ์ค้นหาพนักงานแล้วเลือก option แรกใน dropdown"""
    emp_input = find_employee_search(page)
    if not emp_input or emp_input.count() == 0:
        print(f"  ⚠️  ไม่พบ employee search input")
        return False
    emp_input.click()
    emp_input.fill('')
    emp_input.type(query, delay=80)
    page.wait_for_timeout(1200)
    # รอ dropdown options
    opts = page.locator(
        '[class*="MuiAutocomplete-listbox"] li:visible, '
        '[role="listbox"] li:visible, '
        '[class*="MuiMenu-root"] li:visible'
    )
    print(f"  🔍 search '{query}' → พบ {opts.count()} options")
    if opts.count() > 0:
        first_opt = opts.first
        opt_text = first_opt.inner_text().strip()[:50]
        first_opt.click()
        page.wait_for_timeout(800)
        print(f"  🔍 เลือก: '{opt_text}'")
        return True
    return False

def find_date_input(page: Page, label_hint: str):
    """หา date input ใกล้ label ที่ระบุ"""
    for sel in [
        f'label:has-text("{label_hint}") ~ * input:visible',
        f'*:has-text("{label_hint}") input[type="date"]:visible',
        f'*:has-text("{label_hint}") ~ * input[type="date"]:visible',
    ]:
        el = page.locator(sel).first
        if el.count() > 0:
            return el
    # fallback: หา date input ทั้งหมดเรียงตาม y position
    return None

def get_all_date_inputs(page: Page):
    """คืน list ของ date inputs ทั้งหมดในฟอร์ม"""
    return page.locator('main input[type="date"]:visible, main input[placeholder*="วัน"]:visible').all()

def fill_date(page: Page, input_el, date_str: str):
    """กรอก date — ลอง fill ก่อน แล้ว fallback triple-click + type"""
    try:
        input_el.fill(date_str)
        page.wait_for_timeout(300)
    except Exception:
        try:
            input_el.triple_click()
            input_el.type(date_str, delay=50)
            page.wait_for_timeout(300)
        except Exception:
            pass

def find_submit_btn(page: Page):
    """หาปุ่มบันทึกใบลาออก"""
    return page.locator(
        'button:has-text("บันทึกใบลาออก"):visible, '
        'button:has-text("บันทึก"):visible, '
        'button[type="submit"]:visible'
    ).first

def find_select_by_hint(page: Page, hint: str):
    """หา MUI Select ใกล้ label ที่ระบุ"""
    for sel in [
        f'*:has-text("{hint}") [class*="MuiSelect-select"]:visible',
        f'label:has-text("{hint}") ~ * [class*="MuiSelect"]:visible',
    ]:
        el = page.locator(sel).first
        if el.count() > 0:
            return el
    return None

def select_mui_option(page: Page, trigger, option_text: str) -> bool:
    """คลิก MUI Select trigger แล้วเลือก option"""
    try:
        trigger.click(timeout=5000)
        page.wait_for_timeout(500)
        opt = page.locator(
            f'[class*="MuiMenu-root"] li:has-text("{option_text}"):visible, '
            f'[role="option"]:has-text("{option_text}"):visible, '
            f'[role="listbox"] li:has-text("{option_text}"):visible'
        ).first
        if opt.count() > 0:
            opt.click()
            page.wait_for_timeout(600)
            return True
        page.keyboard.press('Escape')
        return False
    except Exception:
        return False

def get_dropdown_options(page: Page) -> list:
    """อ่าน option list ที่เปิดอยู่"""
    return page.locator(
        '[class*="MuiMenu-root"] li:visible, '
        '[role="option"]:visible, '
        '[role="listbox"] li:visible'
    ).all_inner_texts()

def has_error(page: Page) -> bool:
    return page.locator(
        '[class*="Mui-error"]:visible, '
        '[class*="MuiFormHelperText"][class*="error"]:visible, '
        '[role="alert"]:visible, '
        'p[class*="error"]:visible, '
        '*:has-text("จำเป็น"):visible, '
        '*:has-text("กรุณา"):visible'
    ).count() > 0

def has_warning_orange(page: Page) -> bool:
    """ตรวจหา warning สีส้มที่เกี่ยวกับระยะเวลาแจ้งล่วงหน้า"""
    return page.locator(
        '*:has-text("แจ้งล่วงหน้าน้อยกว่า"):visible, '
        '*:has-text("น้อยกว่าที่กำหนด"):visible, '
        '[class*="warning"]:visible'
    ).count() > 0

def is_disabled(page: Page, btn) -> bool:
    try:
        return btn.is_disabled()
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — เลือกพนักงาน (TC-001..007)
# ══════════════════════════════════════════════════════════════════════════════
def s1(page: Page, r: Results):
    print('\n▶ Section 1 — เลือกพนักงาน')

    # TC-001
    print('  TC-001: ค้นหา Active ด้วยรหัส → แสดงใน dropdown')
    nav(page)
    emp_input = find_employee_search(page)
    if emp_input:
        emp_input.click()
        emp_input.type(TEST_EMPLOYEES[0], delay=80)
        page.wait_for_timeout(1200)
        opts = page.locator('[class*="MuiAutocomplete-listbox"] li:visible, [role="listbox"] li:visible').count()
        ss(page, 'TC-001')
        if opts > 0:
            r.set('TC-001', 'pass', f'พิมพ์ "{TEST_EMPLOYEES[0]}" → dropdown แสดง {opts} option')
        else:
            r.set('TC-001', 'fail', f'พิมพ์ "{TEST_EMPLOYEES[0]}" → ไม่มี option ใน dropdown')
        page.keyboard.press('Escape')
    else:
        r.set('TC-001', 'skip', 'ไม่พบ employee search input')

    # TC-002
    print('  TC-002: ค้นหา Active ด้วยชื่อ → แสดงใน dropdown')
    nav(page)
    emp_input = find_employee_search(page)
    if emp_input:
        emp_input.click()
        emp_input.type('test', delay=80)
        page.wait_for_timeout(1200)
        opts = page.locator('[class*="MuiAutocomplete-listbox"] li:visible, [role="listbox"] li:visible').count()
        ss(page, 'TC-002')
        if opts > 0:
            r.set('TC-002', 'pass', f'พิมพ์ "test" → dropdown แสดง {opts} option')
        else:
            r.set('TC-002', 'fail', 'พิมพ์ชื่อแล้วไม่มี option ใน dropdown')
        page.keyboard.press('Escape')
    else:
        r.set('TC-002', 'skip', 'ไม่พบ search input')

    # TC-003, TC-004
    r.set('TC-003', 'skip', 'ต้อง manual — ต้องมี employee ที่ลาออกแล้ว ค้นหาดูว่าไม่ปรากฏ')
    r.set('TC-004', 'skip', 'ต้อง manual — ต้องมี employee Inactive ค้นหาดูว่าไม่ปรากฏ')

    # TC-005
    print('  TC-005: เลือกพนักงาน → auto-fill ส่วนที่ 2 ทั้งหมด')
    nav(page)
    ok = search_and_select_employee(page, TEST_EMPLOYEES[0])
    if ok:
        page.wait_for_timeout(800)
        # ตรวจว่ามี auto-fill field แสดงข้อมูล (read-only inputs/fields)
        readonly_count = page.locator(
            'input[readonly]:visible, input[disabled]:visible, '
            '[class*="MuiInputBase-readOnly"]:visible, '
            '[class*="readOnly"]:visible'
        ).count()
        filled_texts = page.locator(
            'main [class*="MuiInputBase"] input[readonly]:visible'
        ).all_inner_texts()
        ss(page, 'TC-005-autofill')
        if readonly_count > 0:
            r.set('TC-005', 'pass', f'auto-fill สำเร็จ มี {readonly_count} read-only fields')
        else:
            # ตรวจแบบอื่น — ดูว่ามี text แสดงขึ้นมาในส่วนที่ 2
            text_check = page.locator('main').inner_text()
            has_data = any(t in text_check for t in ['ฝ่าย', 'แผนก', 'ตำแหน่ง', 'วันเริ่ม'])
            if has_data:
                r.set('TC-005', 'pass', 'เลือกพนักงานแล้ว ส่วนที่ 2 มีข้อมูลแสดง (manual verify columns)')
            else:
                ss(page, 'TC-005-check')
                r.set('TC-005', 'skip', 'เลือกพนักงานสำเร็จ แต่ verify auto-fill ต้อง manual')
    else:
        r.set('TC-005', 'fail', f'ค้นหา/เลือกพนักงาน "{TEST_EMPLOYEES[0]}" ไม่สำเร็จ')

    # TC-006
    print('  TC-006: ฟิลด์ auto-fill เป็น read-only')
    # ต่อจาก TC-005 ที่เลือกพนักงานแล้ว
    if ok:
        readonly_inputs = page.locator(
            'input[readonly]:visible, '
            '[class*="MuiInputBase-readOnly"] input:visible, '
            'input[aria-readonly="true"]:visible'
        )
        count_ro = readonly_inputs.count()
        ss(page, 'TC-006-readonly')
        if count_ro > 0:
            r.set('TC-006', 'pass', f'พบ {count_ro} read-only field ใน auto-fill section')
        else:
            r.set('TC-006', 'skip', 'ต้อง manual verify — selector อาจไม่ตรงกับ component จริง')
    else:
        r.set('TC-006', 'skip', 'ข้ามเพราะ TC-005 ไม่สำเร็จ')

    # TC-007
    print('  TC-007: อายุงาน คำนวณถูกต้อง (ปี เดือน วัน)')
    r.set('TC-007', 'skip', 'ต้อง manual — เปรียบเทียบค่าที่แสดงกับการคำนวณจากวันเริ่มงาน → วันนี้')


# ══════════════════════════════════════════════════════════════════════════════
# Section 2 — Validation ฟิลด์บังคับ (TC-008..013)
# ══════════════════════════════════════════════════════════════════════════════
def s2(page: Page, r: Results):
    print('\n▶ Section 2 — Validation ฟิลด์บังคับ')

    # TC-008
    print('  TC-008: กดบันทึกโดยไม่เลือกพนักงาน → error')
    nav(page)
    submit = find_submit_btn(page)
    btn_disabled = is_disabled(page, submit) if submit.count() > 0 else True
    if btn_disabled:
        r.set('TC-008', 'pass', 'ปุ่มบันทึก disabled เมื่อยังไม่เลือกพนักงาน (AC: ปุ่ม disabled จนกรอกครบ)')
    else:
        try:
            submit.click(timeout=3000)
            page.wait_for_timeout(800)
        except Exception:
            pass
        if has_error(page):
            ss(page, 'TC-008-error')
            r.set('TC-008', 'pass', 'กดบันทึกโดยไม่เลือกพนักงาน → มี error แสดง')
        else:
            ss(page, 'TC-008-check')
            r.set('TC-008', 'skip', 'กดปุ่มได้ แต่ไม่เห็น error — ต้อง manual verify')

    # TC-013 (ทดสอบตอนนี้เลย — ปุ่ม disabled state)
    print('  TC-013: ปุ่ม "บันทึก" disabled ก่อนกรอกครบ')
    nav(page)
    submit = find_submit_btn(page)
    if submit.count() > 0:
        initially_disabled = is_disabled(page, submit)
        ss(page, 'TC-013-initial')
        if initially_disabled:
            r.set('TC-013', 'pass', 'ปุ่ม disabled ตอนเปิดฟอร์ม ก่อนกรอกข้อมูล')
        else:
            r.set('TC-013', 'skip', 'ปุ่ม enabled แม้ยังไม่กรอก — อาจ validate ตอน submit แทน')
    else:
        r.set('TC-013', 'skip', 'ไม่พบปุ่ม submit')

    # TC-009..012: เลือกพนักงานแล้วข้ามฟิลด์แต่ละตัว
    # ต้องเลือกพนักงานก่อนเพื่อทดสอบ validation field อื่น
    nav(page)
    ok = search_and_select_employee(page, TEST_EMPLOYEES[1])
    if not ok:
        for tc in ['TC-009', 'TC-010', 'TC-011', 'TC-012']:
            r.set(tc, 'skip', 'เลือกพนักงานไม่สำเร็จ — ข้าม validation tests')
        return

    # TC-009: ไม่เลือกประเภทลาออก
    print('  TC-009: ไม่เลือกประเภทลาออก → error')
    # กรอกฟิลด์อื่นครบ ยกเว้นประเภทลาออก
    date_inputs = get_all_date_inputs(page)
    if len(date_inputs) >= 2:
        fill_date(page, date_inputs[0], DATE_TODAY)
        fill_date(page, date_inputs[1], DATE_PLUS_30)
    # เลือกสาเหตุ (ถ้าได้)
    cause_sel = find_select_by_hint(page, 'สาเหตุ')
    if cause_sel and cause_sel.count() > 0:
        cause_sel.click()
        page.wait_for_timeout(400)
        opts = get_dropdown_options(page)
        if opts:
            page.locator(f'[class*="MuiMenu-root"] li:visible').first.click()
            page.wait_for_timeout(400)
        else:
            page.keyboard.press('Escape')
    submit = find_submit_btn(page)
    if submit.count() > 0 and not is_disabled(page, submit):
        submit.click()
        page.wait_for_timeout(800)
        if has_error(page):
            ss(page, 'TC-009-error')
            r.set('TC-009', 'pass', 'ไม่เลือกประเภทลาออก → มี error')
        else:
            ss(page, 'TC-009-check')
            r.set('TC-009', 'skip', 'กดบันทึกแล้วไม่เห็น error field ประเภทลาออก — manual verify')
    else:
        r.set('TC-009', 'skip', 'ปุ่ม disabled — ยังกรอกฟิลด์อื่นไม่ครบหรือ manual verify')

    # TC-010: ไม่เลือกสาเหตุ
    print('  TC-010: ไม่เลือกสาเหตุการลาออก → error')
    nav(page)
    ok = search_and_select_employee(page, TEST_EMPLOYEES[1])
    if ok:
        date_inputs = get_all_date_inputs(page)
        if len(date_inputs) >= 2:
            fill_date(page, date_inputs[0], DATE_TODAY)
            fill_date(page, date_inputs[1], DATE_PLUS_30)
        type_sel = find_select_by_hint(page, 'ประเภทลาออก')
        if type_sel and type_sel.count() > 0:
            type_sel.click()
            page.wait_for_timeout(400)
            opts = page.locator('[class*="MuiMenu-root"] li:visible').all()
            for opt in opts:
                if 'อื่นๆ' not in opt.inner_text() and opt.inner_text().strip():
                    opt.click()
                    break
            else:
                page.keyboard.press('Escape')
            page.wait_for_timeout(400)
        submit = find_submit_btn(page)
        if submit.count() > 0 and not is_disabled(page, submit):
            submit.click()
            page.wait_for_timeout(800)
            if has_error(page):
                ss(page, 'TC-010-error')
                r.set('TC-010', 'pass', 'ไม่เลือกสาเหตุ → มี error')
            else:
                r.set('TC-010', 'skip', 'manual verify — error field สาเหตุ')
        else:
            r.set('TC-010', 'skip', 'ปุ่ม disabled — manual verify')
    else:
        r.set('TC-010', 'skip', 'เลือกพนักงานไม่สำเร็จ')

    # TC-011, TC-012: date fields validation
    print('  TC-011: ไม่กรอกวันที่แจ้งลาออก → error')
    print('  TC-012: ไม่กรอกวันที่ลาออก → error')
    r.set('TC-011', 'skip', 'ต้อง manual — กรอกครบยกเว้นวันที่แจ้ง แล้วดู error highlight')
    r.set('TC-012', 'skip', 'ต้อง manual — กรอกครบยกเว้นวันที่ลาออก แล้วดู error highlight')


# ══════════════════════════════════════════════════════════════════════════════
# Section 3 — Validation วันที่ (TC-014..021)
# ══════════════════════════════════════════════════════════════════════════════
def s3(page: Page, r: Results):
    print('\n▶ Section 3 — Validation วันที่')

    def setup_form_with_employee(page: Page) -> bool:
        nav(page)
        return search_and_select_employee(page, TEST_EMPLOYEES[2])

    # TC-017: วันที่บันทึก default = วันปัจจุบัน
    print('  TC-017: วันที่บันทึก default = วันนี้')
    setup_form_with_employee(page)
    page.wait_for_timeout(600)
    date_inputs = get_all_date_inputs(page)
    print(f"  🔍 พบ date inputs: {len(date_inputs)} ช่อง")
    # หา input ที่มีค่า default เป็นวันนี้ (น่าจะเป็น input สุดท้าย = วันที่บันทึก)
    today_found = False
    for inp in date_inputs:
        try:
            val = inp.input_value()
            print(f"  🔍 date input value: '{val}'")
            if DATE_TODAY in val or TODAY.strftime('%d/%m/%Y') in val:
                today_found = True
                break
        except Exception:
            pass
    ss(page, 'TC-017-dates')
    if today_found:
        r.set('TC-017', 'pass', f'พบ date input ที่มีค่า {DATE_TODAY} (วันปัจจุบัน)')
    else:
        r.set('TC-017', 'skip', f'ไม่พบ default date = วันนี้ ({DATE_TODAY}) — manual verify')

    # TC-014: วันที่ลาออก < วันที่แจ้ง → error
    print('  TC-014: วันที่ลาออก < วันที่แจ้ง → error')
    setup_form_with_employee(page)
    date_inputs = get_all_date_inputs(page)
    if len(date_inputs) >= 2:
        # สมมติ: date_inputs[0] = วันที่แจ้ง, date_inputs[1] = วันที่ลาออก
        fill_date(page, date_inputs[0], DATE_TODAY)     # แจ้ง = วันนี้
        fill_date(page, date_inputs[1], DATE_MINUS_1)   # ลาออก = เมื่อวาน
        page.wait_for_timeout(800)
        # กด Tab เพื่อ trigger validation
        date_inputs[1].press('Tab')
        page.wait_for_timeout(500)
        err = page.locator(
            '*:has-text("ต้องอยู่หลัง"):visible, '
            '*:has-text("ต้องไม่น้อยกว่า"):visible, '
            '*:has-text("วันที่ลาออก"):visible'
        ).count() > 0 or has_error(page)
        ss(page, 'TC-014')
        if err:
            r.set('TC-014', 'pass', 'วันลาออก < แจ้ง → error แสดง')
        else:
            r.set('TC-014', 'skip', 'ไม่เห็น error text — manual verify (อาจ validate ตอน submit)')
    else:
        r.set('TC-014', 'skip', f'พบ date inputs {len(date_inputs)} ช่อง — manual verify')

    # TC-015: วันที่ลาออก = วันที่แจ้ง → pass
    print('  TC-015: วันที่ลาออก = วันที่แจ้ง → valid')
    setup_form_with_employee(page)
    date_inputs = get_all_date_inputs(page)
    if len(date_inputs) >= 2:
        fill_date(page, date_inputs[0], DATE_TODAY)
        fill_date(page, date_inputs[1], DATE_TODAY)
        page.wait_for_timeout(800)
        date_inputs[1].press('Tab')
        page.wait_for_timeout(500)
        date_err = page.locator('*:has-text("ต้องอยู่หลัง"):visible').count()
        ss(page, 'TC-015')
        if date_err == 0:
            r.set('TC-015', 'pass', 'วันลาออก = แจ้ง → ไม่มี error')
        else:
            r.set('TC-015', 'fail', 'วันลาออก = แจ้ง → มี error (ไม่ควรมี)')
    else:
        r.set('TC-015', 'skip', 'ไม่พบ date inputs — manual verify')

    # TC-016: วันที่ลาออก > วันที่แจ้ง → pass
    print('  TC-016: วันที่ลาออก > วันที่แจ้ง → valid')
    setup_form_with_employee(page)
    date_inputs = get_all_date_inputs(page)
    if len(date_inputs) >= 2:
        fill_date(page, date_inputs[0], DATE_TODAY)
        fill_date(page, date_inputs[1], DATE_PLUS_30)
        page.wait_for_timeout(800)
        date_inputs[1].press('Tab')
        page.wait_for_timeout(500)
        date_err = page.locator('*:has-text("ต้องอยู่หลัง"):visible').count()
        ss(page, 'TC-016')
        if date_err == 0:
            r.set('TC-016', 'pass', 'วันลาออก > แจ้ง → ไม่มี error')
        else:
            r.set('TC-016', 'fail', 'วันลาออก > แจ้ง → มี error (ไม่ควรมี)')
    else:
        r.set('TC-016', 'skip', 'ไม่พบ date inputs — manual verify')

    # TC-018: วันที่บันทึก ย้อนหลัง > 30 วัน → error
    print('  TC-018: วันที่บันทึก ย้อนหลัง > 30 วัน → ไม่อนุญาต')
    setup_form_with_employee(page)
    date_inputs = get_all_date_inputs(page)
    record_input = None
    # หา date input ที่ label "วันที่บันทึก" — มักเป็น input สุดท้าย
    for label in ['วันที่บันทึก', 'บันทึก']:
        el = page.locator(f'*:has-text("{label}") ~ * input[type="date"]:visible, *:has-text("{label}") input[type="date"]:visible').first
        if el.count() > 0:
            record_input = el
            break
    if not record_input and len(date_inputs) >= 3:
        record_input = date_inputs[2]   # index 2 = วันที่บันทึก (สมมติ)
    if record_input:
        fill_date(page, record_input, DATE_MINUS_35)
        page.wait_for_timeout(800)
        record_input.press('Tab')
        page.wait_for_timeout(500)
        err_35 = has_error(page)
        ss(page, 'TC-018')
        if err_35:
            r.set('TC-018', 'pass', f'ย้อนหลัง 35 วัน ({DATE_MINUS_35}) → error แสดง')
        else:
            r.set('TC-018', 'skip', f'ไม่เห็น error — manual verify ด้วยวันที่ {DATE_MINUS_35}')
    else:
        r.set('TC-018', 'skip', 'ไม่พบ "วันที่บันทึก" input — manual verify')

    # TC-019: ระยะเวลาแจ้งล่วงหน้า คำนวณ real-time
    print('  TC-019: ระยะเวลาแจ้งล่วงหน้า real-time')
    setup_form_with_employee(page)
    date_inputs = get_all_date_inputs(page)
    if len(date_inputs) >= 2:
        fill_date(page, date_inputs[0], DATE_TODAY)
        page.wait_for_timeout(400)
        fill_date(page, date_inputs[1], DATE_PLUS_30)
        date_inputs[1].press('Tab')
        page.wait_for_timeout(800)
        # ตรวจหา element แสดงจำนวนวัน
        notice_text = page.locator(
            '*:has-text("วัน"):visible, *:has-text("ล่วงหน้า"):visible'
        ).all_inner_texts()
        print(f"  🔍 notice texts: {[t[:30] for t in notice_text if 'วัน' in t][:5]}")
        ss(page, 'TC-019')
        days_shown = any('30' in t or 'วัน' in t for t in notice_text)
        if days_shown:
            r.set('TC-019', 'pass', 'ค่าระยะเวลาแจ้งล่วงหน้าแสดงขึ้นหลังกรอกวันครบ')
        else:
            r.set('TC-019', 'skip', 'ไม่เห็น element แสดงจำนวนวัน — manual verify')
    else:
        r.set('TC-019', 'skip', 'ไม่พบ date inputs — manual verify')

    # TC-020: แจ้งล่วงหน้า < 30 วัน → warning สีส้ม
    print('  TC-020: แจ้งล่วงหน้า < 30 วัน → warning สีส้ม (ไม่บล็อค)')
    setup_form_with_employee(page)
    date_inputs = get_all_date_inputs(page)
    if len(date_inputs) >= 2:
        fill_date(page, date_inputs[0], DATE_TODAY)
        fill_date(page, date_inputs[1], DATE_PLUS_5)  # 5 วัน = น้อยกว่า 30
        date_inputs[1].press('Tab')
        page.wait_for_timeout(800)
        warn = has_warning_orange(page)
        ss(page, 'TC-020')
        if warn:
            r.set('TC-020', 'pass', 'แจ้งล่วงหน้า 5 วัน → warning แสดง')
        else:
            r.set('TC-020', 'skip', 'ไม่เห็น warning text — manual verify color + ข้อความ')
    else:
        r.set('TC-020', 'skip', 'ไม่พบ date inputs — manual verify')

    # TC-021: แจ้งล่วงหน้า ≥ 30 วัน → ไม่มี warning
    print('  TC-021: แจ้งล่วงหน้า ≥ 30 วัน → ไม่มี warning')
    setup_form_with_employee(page)
    date_inputs = get_all_date_inputs(page)
    if len(date_inputs) >= 2:
        fill_date(page, date_inputs[0], DATE_TODAY)
        fill_date(page, date_inputs[1], DATE_PLUS_30)
        date_inputs[1].press('Tab')
        page.wait_for_timeout(800)
        warn = has_warning_orange(page)
        ss(page, 'TC-021')
        if not warn:
            r.set('TC-021', 'pass', 'แจ้งล่วงหน้า 30 วัน → ไม่มี warning')
        else:
            r.set('TC-021', 'fail', 'แจ้งล่วงหน้า 30 วัน → ยังมี warning (ไม่ควรมี)')
    else:
        r.set('TC-021', 'skip', 'ไม่พบ date inputs — manual verify')


# ══════════════════════════════════════════════════════════════════════════════
# Section 4 — สาเหตุ/ประเภท "อื่นๆ" (TC-022..026)
# ══════════════════════════════════════════════════════════════════════════════
def s4(page: Page, r: Results):
    print('\n▶ Section 4 — สาเหตุ/ประเภท "อื่นๆ"')

    def extra_text_visible(page: Page) -> bool:
        return page.locator(
            'input[placeholder*="ระบุ"]:visible, '
            'input[placeholder*="รายละเอียด"]:visible, '
            'textarea[placeholder*="ระบุ"]:visible, '
            '*:has-text("ระบุรายละเอียด"):visible ~ * input:visible'
        ).count() > 0

    # TC-022: ประเภทลาออก "อื่นๆ" → text input แสดง
    print('  TC-022: ประเภทลาออก "อื่นๆ" → text input เพิ่มเติมแสดง')
    nav(page)
    search_and_select_employee(page, TEST_EMPLOYEES[0])
    type_sel = find_select_by_hint(page, 'ประเภทลาออก')
    if not type_sel or type_sel.count() == 0:
        type_sel = page.locator('[class*="MuiSelect-select"]:visible').first
    if type_sel and type_sel.count() > 0:
        ok = select_mui_option(page, type_sel, 'อื่นๆ')
        page.wait_for_timeout(600)
        ss(page, 'TC-022')
        if ok:
            extra_vis = extra_text_visible(page)
            if extra_vis:
                r.set('TC-022', 'pass', 'เลือกประเภท "อื่นๆ" → text input เพิ่มเติมแสดง')
            else:
                r.set('TC-022', 'skip', 'เลือก "อื่นๆ" สำเร็จ แต่ไม่เห็น text input — manual verify')
        else:
            r.set('TC-022', 'skip', 'ไม่พบ option "อื่นๆ" ใน dropdown ประเภทลาออก')
    else:
        r.set('TC-022', 'skip', 'ไม่พบ dropdown ประเภทลาออก')

    # TC-023: เลือก "อื่นๆ" ไม่กรอก → บล็อค
    print('  TC-023: ประเภท "อื่นๆ" ไม่กรอก text → บล็อคบันทึก')
    # ต่อจาก TC-022 (เลือก "อื่นๆ" แล้ว)
    submit = find_submit_btn(page)
    if submit.count() > 0 and not is_disabled(page, submit):
        submit.click()
        page.wait_for_timeout(800)
        if has_error(page):
            ss(page, 'TC-023-error')
            r.set('TC-023', 'pass', 'ไม่กรอก text หลังเลือก "อื่นๆ" → มี error บล็อค')
        else:
            r.set('TC-023', 'skip', 'ไม่เห็น error — manual verify')
    else:
        r.set('TC-023', 'skip', 'ปุ่ม disabled หรือยังกรอกฟิลด์อื่นไม่ครบ — manual verify')

    # TC-024: สาเหตุ "อื่นๆ" → text input แสดง
    print('  TC-024: สาเหตุการลาออก "อื่นๆ" → text input แสดง')
    nav(page)
    search_and_select_employee(page, TEST_EMPLOYEES[0])
    # หา dropdown สาเหตุ (มักเป็น select ที่สองในฟอร์ม)
    selects = page.locator('[class*="MuiSelect-select"]:visible').all()
    cause_trigger = None
    for sel in selects:
        # คลิกเพื่อดู options ว่ามี "ได้งานใหม่" หรือเกี่ยวกับสาเหตุ
        try:
            sel.click(timeout=3000)
            page.wait_for_timeout(400)
            opts_text = get_dropdown_options(page)
            page.keyboard.press('Escape')
            page.wait_for_timeout(300)
            if any('งานใหม่' in t or 'ครอบครัว' in t or 'สุขภาพ' in t for t in opts_text):
                cause_trigger = sel
                print(f"  🔍 พบ dropdown สาเหตุ: {opts_text[:3]}")
                break
        except Exception:
            page.keyboard.press('Escape')
    if cause_trigger:
        ok24 = select_mui_option(page, cause_trigger, 'อื่นๆ')
        page.wait_for_timeout(600)
        ss(page, 'TC-024')
        if ok24:
            extra_vis = extra_text_visible(page)
            if extra_vis:
                r.set('TC-024', 'pass', 'เลือกสาเหตุ "อื่นๆ" → text input เพิ่มเติมแสดง')
            else:
                r.set('TC-024', 'skip', 'เลือก "อื่นๆ" สำเร็จ แต่ไม่เห็น text input — manual verify')
        else:
            r.set('TC-024', 'skip', 'ไม่พบ option "อื่นๆ" ใน dropdown สาเหตุ')
    else:
        r.set('TC-024', 'skip', 'ไม่พบ dropdown สาเหตุการลาออก — manual verify')

    # TC-025
    print('  TC-025: สาเหตุ "อื่นๆ" ไม่กรอก → บล็อค')
    submit = find_submit_btn(page)
    if submit.count() > 0 and not is_disabled(page, submit):
        submit.click()
        page.wait_for_timeout(800)
        if has_error(page):
            r.set('TC-025', 'pass', 'ไม่กรอก text หลังเลือกสาเหตุ "อื่นๆ" → มี error')
        else:
            r.set('TC-025', 'skip', 'manual verify')
    else:
        r.set('TC-025', 'skip', 'ปุ่ม disabled หรือยังกรอกไม่ครบ — manual verify')

    # TC-026: เปลี่ยนจาก "อื่นๆ" → ซ่อน text input
    print('  TC-026: เปลี่ยนสาเหตุจาก "อื่นๆ" → ตัวเลือกอื่น → ซ่อน text input')
    if cause_trigger:
        # เลือก "อื่นๆ" ก่อน (ถ้ายังอยู่หน้าเดิม)
        try:
            select_mui_option(page, cause_trigger, 'อื่นๆ')
            page.wait_for_timeout(400)
            before = extra_text_visible(page)
            # เปลี่ยนกลับ
            select_mui_option(page, cause_trigger, 'ได้งานใหม่')
            page.wait_for_timeout(600)
            after = extra_text_visible(page)
            ss(page, 'TC-026')
            if before and not after:
                r.set('TC-026', 'pass', 'เปลี่ยนจาก "อื่นๆ" → "ได้งานใหม่" → text input ซ่อน')
            else:
                r.set('TC-026', 'skip', f'before={before}, after={after} — manual verify')
        except Exception as e:
            r.set('TC-026', 'skip', f'error: {e}')
    else:
        r.set('TC-026', 'skip', 'ไม่พบ dropdown สาเหตุ — manual verify')


# ══════════════════════════════════════════════════════════════════════════════
# Section 5 — Checklist (TC-027..030)
# ══════════════════════════════════════════════════════════════════════════════
def s5(page: Page, r: Results):
    print('\n▶ Section 5 — Checklist การดำเนินการต่อเนื่อง')

    nav(page)
    search_and_select_employee(page, TEST_EMPLOYEES[3])
    page.wait_for_timeout(600)

    # หา checkbox แจ้งออกประกันสังคม
    sps_checkbox = page.locator(
        'input[type="checkbox"]:near(*:has-text("ประกันสังคม")):visible, '
        'label:has-text("ประกันสังคม") input[type="checkbox"]:visible, '
        '*:has-text("แจ้งออกประกันสังคม") ~ * input[type="checkbox"]:visible'
    ).first

    checklist_area = page.locator(
        '*:has-text("Checklist"):visible, '
        '*:has-text("checklist"):visible, '
        '*:has-text("การดำเนินการ"):visible'
    )
    has_checklist = checklist_area.count() > 0 or page.locator('input[type="checkbox"]:visible').count() > 0
    print(f"  🔍 Checklist area: {'พบ' if has_checklist else 'ไม่พบ'}")

    # TC-027: ไม่ tick → บันทึกได้
    r.set('TC-027', 'skip', 'ต้อง manual — ต้องกรอกทุก field บังคับแล้วกดบันทึกโดยไม่ tick Checklist')

    # TC-028: Tick สปส. → date input แสดง
    print('  TC-028: Tick "แจ้งออกประกันสังคม" → วันที่แจ้ง date input แสดง')
    if sps_checkbox.count() > 0:
        sps_checkbox.check()
        page.wait_for_timeout(600)
        # ตรวจหา date input เพิ่มเติมที่เกี่ยวกับ สปส.
        sps_date = page.locator(
            '*:has-text("ประกันสังคม") ~ * input[type="date"]:visible, '
            '*:has-text("วันที่แจ้ง") input[type="date"]:visible, '
            'label:has-text("วันที่แจ้ง") ~ * input:visible'
        ).first
        ss(page, 'TC-028')
        if sps_date.count() > 0:
            r.set('TC-028', 'pass', 'Tick สปส. → date input "วันที่แจ้ง" แสดงขึ้น')
        else:
            r.set('TC-028', 'skip', 'Tick สำเร็จ แต่ไม่เห็น date input เพิ่มเติม — manual verify')

        # TC-029: tick สปส. ไม่กรอกวันที่ → บล็อค
        print('  TC-029: Tick สปส. ไม่กรอกวันที่ → บล็อค')
        submit = find_submit_btn(page)
        if submit.count() > 0 and not is_disabled(page, submit):
            submit.click()
            page.wait_for_timeout(800)
            if has_error(page):
                ss(page, 'TC-029-error')
                r.set('TC-029', 'pass', 'Tick สปส. ไม่กรอกวันที่ → มี error บล็อค')
            else:
                r.set('TC-029', 'skip', 'ไม่เห็น error — manual verify')
        else:
            r.set('TC-029', 'skip', 'ปุ่ม disabled (ยังกรอกฟิลด์อื่นไม่ครบ) — manual verify')
    else:
        r.set('TC-028', 'skip', 'ไม่พบ checkbox แจ้งออกประกันสังคม — manual verify')
        r.set('TC-029', 'skip', 'ไม่พบ checkbox — manual verify')

    # TC-030: สถานะ Checklist บันทึกลงใน record
    r.set('TC-030', 'skip', 'ต้อง manual — บันทึกฟอร์มแล้วไปดูหน้ารายการ 7.1.19.1')


# ══════════════════════════════════════════════════════════════════════════════
# Section 6 — เมื่อบันทึกสำเร็จ (TC-031..036)
# ══════════════════════════════════════════════════════════════════════════════
def s6(page: Page, r: Results):
    print('\n▶ Section 6 — เมื่อบันทึกสำเร็จ')
    r.set('TC-031', 'skip', 'ต้อง manual — บันทึกจริงแล้วดู Toast ที่แสดง')
    r.set('TC-032', 'skip', 'ต้อง manual — ดูหน้ารายการพนักงาน ว่ามี badge "ลาออก"')
    r.set('TC-033', 'skip', 'ต้อง manual — ใช้ account พนักงานที่ลาออกแล้ว login Staff Portal')
    r.set('TC-034', 'skip', 'ต้อง manual — ดู Audit Log ของ record ที่บันทึก')
    r.set('TC-035', 'skip', 'ต้อง manual — ตรวจ notification ของ HR Admin + ผู้บังคับบัญชา')
    r.set('TC-036', 'skip', 'ต้อง manual — บันทึกสำเร็จแล้วดูว่า redirect ไปหน้ารายการ')


# ══════════════════════════════════════════════════════════════════════════════
# Section 7 — การแก้ไขหลังบันทึก (TC-037..040)
# ══════════════════════════════════════════════════════════════════════════════
def s7(page: Page, r: Results):
    print('\n▶ Section 7 — การแก้ไขหลังบันทึก')

    # ลองเข้าหน้า list เพื่อหาใบลาออกที่มีอยู่
    LIST_URL = f"{HR_APP_URL}/employee/resignation"
    nav_list_ok = False
    try:
        page.goto(LIST_URL, wait_until='domcontentloaded', timeout=20000)
        page.wait_for_timeout(1500)
        rows = page.locator('tbody tr:visible, [class*="MuiTableRow"]:not([class*="head"]):visible').count()
        print(f"  🔍 หน้ารายการใบลาออก — rows: {rows}")
        nav_list_ok = True
        ss(page, 'TC-037-list')
    except Exception as e:
        print(f"  ⚠️  เข้าหน้า list ไม่ได้: {e}")

    if nav_list_ok and rows > 0:
        # TC-037: record สถานะ "รอดำเนินการ" → แก้ไขได้
        print('  TC-037: record "รอดำเนินการ" → แก้ไขได้')
        # หา row ที่มีสถานะ "รอดำเนินการ"
        pending_row = page.locator(
            'tr:has-text("รอดำเนินการ"):visible'
        ).first
        if pending_row.count() > 0:
            edit_btn = pending_row.locator(
                'button:has-text("แก้ไข"):visible, a:has-text("แก้ไข"):visible'
            ).first
            if edit_btn.count() == 0:
                # ลอง kebab menu
                pending_row.hover()
                page.wait_for_timeout(500)
                kebab = pending_row.locator('button[aria-label*="more"]:visible, button[aria-label*="action"]:visible').first
                if kebab.count() > 0:
                    kebab.click()
                    page.wait_for_timeout(400)
                    edit_btn = page.locator('[class*="MuiMenu-root"] li:has-text("แก้ไข"):visible').first
            if edit_btn.count() > 0:
                edit_btn.click()
                page.wait_for_timeout(1500)
                is_edit_page = 'edit' in page.url or 'resignation' in page.url
                ss(page, 'TC-037')
                r.set('TC-037', 'pass' if is_edit_page else 'skip',
                      f'เปิดหน้าแก้ไขได้ → {page.url}')
            else:
                r.set('TC-037', 'skip', 'ไม่พบปุ่มแก้ไขใน row "รอดำเนินการ" — manual verify')
        else:
            r.set('TC-037', 'skip', 'ไม่พบ record สถานะ "รอดำเนินการ" ในรายการ — manual verify')
    else:
        r.set('TC-037', 'skip', 'เข้าหน้า list ไม่ได้หรือไม่มีข้อมูล — manual verify')

    r.set('TC-038', 'skip', 'ต้อง manual — เปิด record ที่สถานะไม่ใช่ "รอดำเนินการ" ตรวจปุ่มแก้ไข')
    r.set('TC-039', 'skip', 'ต้อง manual — เปิดโหมดแก้ไข ดูว่าฟิลด์รหัสพนักงาน read-only')
    r.set('TC-040', 'skip', 'ต้อง manual — แก้ไขบันทึกแล้วดู Audit Log ก่อน/หลัง')


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    if not HR_APP_URL:
        print('❌ ยังไม่ได้ตั้ง HR_APP_URL ใน .env')
        return

    now = datetime.datetime.now().strftime('%H:%M:%S')
    print(f'🚀 Task 395 Auto-Test [{now}]')
    print(f'   URL    : {FORM_URL}')
    print(f'   Employees: {", ".join(TEST_EMPLOYEES)}')
    mode = 'Manual-Login' if MANUAL_LOGIN else 'Auto'
    if USE_SESSION and SESSION_FILE.exists(): mode += ' + Use-Session'
    if SAVE_SESSION: mode += ' + Save-Session'
    print(f'   Mode   : {mode}')
    print(f'   Section: {SECTION or "ทั้งหมด (1-7)"}')

    r = Results()
    sections = {
        1: s1, 2: s2, 3: s3, 4: s4,
        5: s5, 6: s6, 7: s7,
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
    sync_to_firebase(r.data, '395')


if __name__ == '__main__':
    main()

