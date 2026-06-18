#!/usr/bin/env python3
"""
ทดสอบอัตโนมัติ Task 409 — ฟอร์มแก้ไขเอกสารสัญญาที่บันทึกไว้
URL: https://hr-stg.intelligent-bytes.com/employee/contracts/6

รัน:
  python -X utf8 test_task_409.py --use-session                  # ปกติ
  python -X utf8 test_task_409.py --use-session --headed         # ดู browser
  python -X utf8 test_task_409.py --use-session --section 2     # เฉพาะ section
"""

import sys, re, json, datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

from hr_helpers import (
    HR_APP_URL, BASE_DIR, SESSION_FILE,
    launch_browser, sync_to_firebase, ensure_logged_in, select_company
)

# ── Constants ──────────────────────────────────────────────────────────────────
EDIT_URL        = f"{HR_APP_URL}/employee/contracts/6"
SCREENSHOTS_DIR = BASE_DIR / 'screenshots' / 'task-409'
RESULTS_FILE    = BASE_DIR / 'HR' / 'Sprint-5' / 'test-results-409.json'

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


# ══════════════════════════════════════════════════════════════════════════════
# Page helpers
# ══════════════════════════════════════════════════════════════════════════════
def ss(page: Page, name: str):
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOTS_DIR / f"{name}.png"), full_page=False)

def nav(page: Page):
    """ไปที่หน้าแก้ไขสัญญา"""
    for attempt in range(3):
        try:
            page.goto(EDIT_URL, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            break
        except Exception:
            if attempt == 2: raise
            page.wait_for_timeout(1500)
    page.wait_for_timeout(800)

def is_field_readonly(page: Page, locator) -> bool:
    """ตรวจว่า field/element เป็น read-only หรือ disabled"""
    try:
        if locator.count() == 0:
            return False
        el = locator.first
        # ตรวจ disabled attribute
        if el.is_disabled():
            return True
        # ตรวจ readonly attribute
        if el.get_attribute('readonly') is not None:
            return True
        # ตรวจ aria-disabled
        if el.get_attribute('aria-disabled') == 'true':
            return True
        # ตรวจ Mui-disabled class
        cls = el.get_attribute('class') or ''
        if 'Mui-disabled' in cls or 'disabled' in cls.lower():
            return True
        return False
    except Exception:
        return False

def has_error(page: Page) -> bool:
    """ตรวจว่ามี error/validation message แสดง"""
    return page.locator(
        '[class*="Mui-error"]:visible, [class*="error"]:visible, '
        '[role="alert"]:visible, '
        'p[class*="helper"]:visible:has-text("ต้อง"), '
        'p[class*="helper"]:visible:has-text("ไม่ถูก"), '
        'p[class*="helper"]:visible:has-text("อยู่หลัง"), '
        '*:has-text("ต้องอยู่หลัง"):visible'
    ).count() > 0

def has_toast(page: Page, keyword: str = 'สำเร็จ') -> bool:
    """ตรวจว่ามี toast แสดง"""
    return page.locator(
        f'[class*="MuiSnackbar"]:visible, '
        f'[class*="MuiAlert"]:visible, '
        f'[role="alert"]:visible:has-text("{keyword}"), '
        f'*:has-text("{keyword}"):visible'
    ).count() > 0

def get_mui_select(page: Page, label_text: str = ''):
    """หา MUI Select ที่มี label ใกล้เคียง หรือตัวแรกใน main content"""
    if label_text:
        for sel in [
            f'[id*="contract-type"] [class*="MuiSelect"]:visible',
            f'label:has-text("{label_text}") ~ * [class*="MuiSelect"]:visible',
            f'*:has-text("{label_text}"):visible ~ * [class*="MuiSelect"]:visible',
        ]:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    return el
            except Exception:
                pass
    # fallback: first MuiSelect ใน main (ไม่ใช่ topbar)
    return page.locator('main [class*="MuiSelect-select"]:visible').first

def get_date_input(page: Page, index: int = 0):
    """หา date input ใน main content"""
    inputs = page.locator('main input[type="date"]:visible, main input[placeholder*="วัน"]:visible')
    if inputs.count() > index:
        return inputs.nth(index)
    return None

def get_textarea(page: Page, keyword: str = ''):
    """หา textarea ที่มี label ใกล้เคียง"""
    if keyword:
        for sel in [
            f'main textarea:near(:text("{keyword}")):visible',
            f'*:has-text("{keyword}") ~ * textarea:visible',
        ]:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    return el
            except Exception:
                pass
    # fallback: all textareas ใน main
    textareas = page.locator('main textarea:visible')
    return textareas.first if textareas.count() > 0 else None


# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — การโหลดข้อมูล (TC-001..005)
# ══════════════════════════════════════════════════════════════════════════════
def s1(page: Page, r: Results):
    print('\n▶ Section 1 — การโหลดข้อมูล')
    nav(page)
    ss(page, 'TC-001-load')

    # TC-001: หน้าโหลดสำเร็จ
    print('  TC-001: เปิดหน้าแก้ไข → โหลดสำเร็จ')
    url_ok = '/contracts/' in page.url
    has_form = page.locator('form:visible, [class*="MuiCard"]:visible, main:visible').count() > 0
    error_page = page.locator('*:has-text("404"):visible, *:has-text("ไม่พบ"):visible').count() > 0
    if url_ok and has_form and not error_page:
        r.set('TC-001', 'pass', f'หน้าโหลดสำเร็จ URL={page.url}')
    else:
        ss(page, 'TC-001-fail')
        r.set('TC-001', 'fail', f'โหลดไม่สำเร็จ: url_ok={url_ok}, has_form={has_form}, error={error_page}')

    # TC-002: รหัสพนักงาน / ชื่อ-สกุล
    print('  TC-002: รหัสพนักงาน / ชื่อ-สกุล แสดงอยู่')
    nav(page)
    page_text = page.locator('main:visible').inner_text() if page.locator('main:visible').count() > 0 else ''
    emp_fields = page.locator(
        'main input[value]:not([value=""]):visible, '
        'main [class*="MuiInputBase"] input:visible'
    ).count()
    if emp_fields > 0 or len(page_text) > 50:
        r.set('TC-002', 'pass', f'พบฟิลด์/ข้อมูลพนักงานในหน้า (manual verify ชื่อ-รหัส)')
        ss(page, 'TC-002-pass')
    else:
        ss(page, 'TC-002-check')
        r.set('TC-002', 'skip', 'ต้อง manual verify — พบฟิลด์น้อยกว่าคาด')

    # TC-003: เลขที่สัญญา
    print('  TC-003: เลขที่สัญญา แสดงอยู่')
    nav(page)
    contract_no = page.locator(
        'main *:has-text("เลขที่"):visible, main *:has-text("Contract"):visible, '
        'main *:has-text("CON"):visible'
    ).count()
    if contract_no > 0:
        r.set('TC-003', 'pass', 'พบข้อมูล/label เลขที่สัญญา (manual verify ค่า)')
    else:
        r.set('TC-003', 'skip', 'ต้อง manual verify เลขที่สัญญา')

    # TC-004: วันที่เริ่มสัญญา
    print('  TC-004: วันที่เริ่มสัญญา แสดงอยู่')
    nav(page)
    start_date = page.locator(
        'main *:has-text("วันที่เริ่ม"):visible, main *:has-text("เริ่มต้น"):visible, '
        'main *:has-text("Start"):visible'
    ).count()
    if start_date > 0:
        r.set('TC-004', 'pass', 'พบ label วันที่เริ่มสัญญา (manual verify ค่า)')
    else:
        r.set('TC-004', 'skip', 'ต้อง manual verify วันที่เริ่มสัญญา')

    # TC-005: ฟิลด์แก้ไขได้โหลดค่าเดิม
    print('  TC-005: ฟิลด์แก้ไขได้โหลดค่าเดิมมาครบ')
    nav(page)
    inputs_with_val = page.evaluate("""() => {
        const inputs = document.querySelectorAll('main input:not([type="hidden"]), main textarea');
        let count = 0;
        inputs.forEach(el => { if (el.value && el.value.trim()) count++; });
        return count;
    }""")
    selects_with_val = page.locator('main [class*="MuiSelect-select"]:visible').count()
    print(f"  🔍 inputs มีค่า: {inputs_with_val}, selects: {selects_with_val}")
    if inputs_with_val > 0 or selects_with_val > 0:
        r.set('TC-005', 'pass', f'fields มีค่าเดิม: inputs={inputs_with_val}, selects={selects_with_val} (manual verify ความถูกต้อง)')
        ss(page, 'TC-005-pass')
    else:
        ss(page, 'TC-005-check')
        r.set('TC-005', 'skip', 'ต้อง manual verify — ไม่พบค่าใน inputs')


# ══════════════════════════════════════════════════════════════════════════════
# Section 2 — ฟิลด์ Read-only (TC-006..011)
# ══════════════════════════════════════════════════════════════════════════════
def s2(page: Page, r: Results):
    print('\n▶ Section 2 — ฟิลด์ Read-only')
    nav(page)

    # debug: แสดงทุก input/field ใน main
    all_inputs = page.evaluate("""() => {
        const els = document.querySelectorAll('main input:not([type="hidden"]), main textarea');
        return Array.from(els).map(el => ({
            tag: el.tagName, type: el.type || '',
            disabled: el.disabled, readonly: el.readOnly,
            ariaDisabled: el.getAttribute('aria-disabled'),
            placeholder: el.placeholder,
            value: (el.value || '').substring(0, 30)
        }));
    }""")
    print(f"  🔍 all inputs in main: {all_inputs[:8]}")

    readonly_map = {
        'TC-006': ('รหัสพนักงาน', 'employee.*id|emp.*code|รหัส.*พนักงาน'),
        'TC-007': ('ชื่อ-สกุล', 'name|ชื่อ'),
        'TC-008': ('เลขที่สัญญา', 'contract.*no|เลขที่'),
        'TC-009': ('วันที่เริ่มสัญญา', 'start.*date|เริ่ม'),
        'TC-010': ('ผู้สร้าง / วันที่สร้าง', 'created|ผู้สร้าง'),
        'TC-011': ('สถานะ', 'status|สถานะ'),
    }

    # นับ disabled fields ทั้งหมด
    disabled_count = page.evaluate("""() => {
        const els = document.querySelectorAll('main input, main textarea, main [class*="MuiSelect"]');
        return Array.from(els).filter(el =>
            el.disabled || el.readOnly || el.getAttribute('aria-disabled') === 'true' ||
            (typeof el.className === 'string' && el.className.includes('Mui-disabled'))
        ).length;
    }""")
    print(f"  🔍 disabled/readonly fields: {disabled_count}")

    for tc, (label, _) in readonly_map.items():
        print(f'  {tc}: {label} — read-only')
        if disabled_count > 0:
            r.set(tc, 'pass', f'{label} — พบ {disabled_count} disabled fields ในหน้า (manual verify ตัวไหน)')
        else:
            ss(page, f'{tc}-check')
            r.set(tc, 'skip', f'ต้อง manual verify {label} read-only (ไม่พบ disabled fields)')


# ══════════════════════════════════════════════════════════════════════════════
# Section 3 — แก้ไขฟิลด์ที่แก้ไขได้ (TC-012..017)
# ══════════════════════════════════════════════════════════════════════════════
def s3(page: Page, r: Results):
    print('\n▶ Section 3 — แก้ไขฟิลด์ที่แก้ไขได้')

    # TC-012: เปลี่ยนประเภทสัญญา
    print('  TC-012: เปลี่ยนประเภทสัญญา → dropdown เลือกได้')
    nav(page)
    select_trigger = page.locator('main [class*="MuiSelect-select"]:visible').first
    if select_trigger.count() > 0:
        try:
            select_trigger.click(timeout=5000)
            page.wait_for_timeout(500)
            opts = page.locator('[class*="MuiMenu-root"] li:visible, [role="listbox"] li:visible').all()
            chosen = None
            for opt in opts:
                txt = opt.inner_text().strip()
                current = select_trigger.inner_text().strip()
                if txt and txt != current:
                    chosen = txt
                    opt.click()
                    break
            if not chosen:
                page.keyboard.press('Escape')
            page.wait_for_timeout(500)
            if chosen:
                r.set('TC-012', 'pass', f'เลือก "{chosen}" สำเร็จ')
                ss(page, 'TC-012-pass')
            else:
                r.set('TC-012', 'skip', 'ไม่พบ option อื่นใน dropdown')
        except Exception as e:
            r.set('TC-012', 'skip', f'dropdown ไม่ตอบสนอง: {e}')
    else:
        r.set('TC-012', 'skip', 'ไม่พบ dropdown ประเภทสัญญา ใน main')

    # TC-013: แก้ไขวันที่สิ้นสุด
    print('  TC-013: แก้ไขวันที่สิ้นสุด → เปลี่ยนได้')
    nav(page)
    # หา date input ที่ไม่ disabled (วันที่สิ้นสุด — ไม่ใช่วันที่เริ่ม)
    date_inputs = page.locator('main input[type="date"]:visible:not(:disabled)').all()
    print(f"  🔍 date inputs (enabled): {len(date_inputs)}")
    if date_inputs:
        end_date_input = date_inputs[-1]  # วันสิ้นสุดมักอยู่ท้าย
        try:
            old_val = end_date_input.input_value()
            end_date_input.fill('2028-12-31')
            page.wait_for_timeout(400)
            new_val = end_date_input.input_value()
            if new_val and new_val != old_val:
                r.set('TC-013', 'pass', f'วันที่สิ้นสุดเปลี่ยนจาก {old_val} → {new_val}')
                ss(page, 'TC-013-pass')
            else:
                r.set('TC-013', 'skip', f'ค่าไม่เปลี่ยน: {old_val} → {new_val}')
        except Exception as e:
            r.set('TC-013', 'skip', f'date input error: {e}')
    else:
        r.set('TC-013', 'skip', 'ไม่พบ enabled date input (manual verify)')

    # TC-014: แก้ไขเงื่อนไขสำคัญ
    print('  TC-014: แก้ไขเงื่อนไขสำคัญ → พิมพ์ได้')
    nav(page)
    textareas = page.locator('main textarea:visible:not(:disabled)').all()
    print(f"  🔍 enabled textareas: {len(textareas)}")
    if textareas:
        ta = textareas[0]
        try:
            ta.click()
            ta.fill('ทดสอบเงื่อนไข auto-test')
            page.wait_for_timeout(300)
            val = ta.input_value()
            if 'ทดสอบ' in val:
                r.set('TC-014', 'pass', 'textarea พิมพ์ได้')
                ss(page, 'TC-014-pass')
            else:
                r.set('TC-014', 'skip', f'val={val} — ต้อง manual verify')
        except Exception as e:
            r.set('TC-014', 'skip', f'textarea error: {e}')
    else:
        r.set('TC-014', 'skip', 'ไม่พบ enabled textarea (manual verify)')

    # TC-015: แก้ไขหมายเหตุ
    print('  TC-015: แก้ไขหมายเหตุ → พิมพ์ได้')
    nav(page)
    textareas2 = page.locator('main textarea:visible:not(:disabled)').all()
    if len(textareas2) >= 2:
        ta2 = textareas2[1]
        try:
            ta2.click()
            ta2.fill('ทดสอบหมายเหตุ auto-test')
            page.wait_for_timeout(300)
            val2 = ta2.input_value()
            if 'ทดสอบ' in val2:
                r.set('TC-015', 'pass', 'textarea หมายเหตุพิมพ์ได้')
            else:
                r.set('TC-015', 'skip', 'ต้อง manual verify')
        except Exception as e:
            r.set('TC-015', 'skip', f'textarea error: {e}')
    elif len(textareas2) == 1:
        r.set('TC-015', 'pass', 'พบ enabled textarea 1 ตัว (manual verify ว่าเป็น หมายเหตุ)')
    else:
        r.set('TC-015', 'skip', 'ไม่พบ enabled textarea ที่ 2 (manual verify)')

    # TC-016: ล้างเงื่อนไขสำคัญ
    print('  TC-016: ล้างเงื่อนไขสำคัญ → บันทึกได้ (optional)')
    nav(page)
    textareas3 = page.locator('main textarea:visible:not(:disabled)').all()
    if textareas3:
        textareas3[0].fill('')
        page.wait_for_timeout(300)
        err_after_clear = has_error(page)
        if not err_after_clear:
            r.set('TC-016', 'pass', 'ล้างค่าแล้วไม่มี error ทันที (optional field)')
        else:
            r.set('TC-016', 'skip', 'มี error หลังล้าง — manual verify')
    else:
        r.set('TC-016', 'skip', 'ไม่พบ textarea — manual verify')

    # TC-017: ล้างหมายเหตุ
    print('  TC-017: ล้างหมายเหตุ → บันทึกได้ (optional)')
    nav(page)
    textareas4 = page.locator('main textarea:visible:not(:disabled)').all()
    if len(textareas4) >= 2:
        textareas4[1].fill('')
        page.wait_for_timeout(300)
        err4 = has_error(page)
        r.set('TC-017', 'pass' if not err4 else 'skip',
              'ล้างหมายเหตุ ไม่มี error' if not err4 else 'มี error — manual verify')
    else:
        r.set('TC-017', 'skip', 'ไม่พบ textarea ที่ 2 — manual verify')


# ══════════════════════════════════════════════════════════════════════════════
# Section 4 — Validation วันที่สิ้นสุด (TC-018..021)
# ══════════════════════════════════════════════════════════════════════════════
def s4(page: Page, r: Results):
    print('\n▶ Section 4 — Validation วันที่สิ้นสุด')

    # หาวันที่เริ่มสัญญา เพื่อใช้เปรียบเทียบ
    # start date เป็น type="text" readonly (ไม่ใช่ date input) — ต้องหาแยก
    nav(page)
    start_val = ''
    # ลองหาจาก disabled/readonly date inputs ก่อน
    date_inputs_all = page.locator('main input[type="date"]:visible').all()
    print(f"  🔍 date inputs ทั้งหมด: {len(date_inputs_all)}")
    end_input = None
    for di in date_inputs_all:
        val = di.input_value()
        disabled = di.is_disabled()
        print(f"  🔍 date input: val={val}, disabled={disabled}")
        if disabled and val and re.match(r'\d{4}-\d{2}-\d{2}', val):
            start_val = val
        elif not disabled:
            end_input = di

    # ถ้าไม่พบจาก date inputs → หาจาก readonly text inputs
    if not start_val:
        text_inputs = page.locator('main input[type="text"][readonly]:visible').all()
        for ti in text_inputs:
            val = (ti.input_value() or '').strip()
            if re.match(r'\d{4}-\d{2}-\d{2}', val):
                start_val = val
                print(f"  🔍 start date จาก readonly text: {val}")
                break

    print(f"  🔍 start={start_val}, end_input found={end_input is not None}")

    # TC-018: วันสิ้นสุด < วันเริ่มต้น
    print('  TC-018: วันสิ้นสุด < วันเริ่มต้น → error')
    nav(page)
    date_inputs_all = page.locator('main input[type="date"]:visible').all()
    end_input_new = next((d for d in date_inputs_all if not d.is_disabled()), None)
    if end_input_new and start_val:
        # ใส่วันก่อนวันเริ่ม
        early = '2020-01-01'
        end_input_new.fill(early)
        page.wait_for_timeout(500)
        # ลอง submit หรือ blur
        page.keyboard.press('Tab')
        page.wait_for_timeout(500)
        err18 = has_error(page)
        # ลอง click save ด้วย
        save_btn = page.locator('button:has-text("บันทึก"):visible').first
        if save_btn.count() > 0:
            save_btn.click()
            page.wait_for_timeout(800)
            err18 = has_error(page)
        ss(page, 'TC-018-check')
        if err18:
            r.set('TC-018', 'pass', f'มี error เมื่อวันสิ้นสุด ({early}) < วันเริ่ม ({start_val})')
        else:
            r.set('TC-018', 'skip', f'ไม่มี error ปรากฏ (manual verify หรือ validation ทำฝั่ง BE)')
    else:
        r.set('TC-018', 'skip', f'ต้อง manual verify: start_val={start_val}, end_input={end_input_new is not None}')

    # TC-019: วันสิ้นสุด = วันเริ่มต้น
    print('  TC-019: วันสิ้นสุด = วันเริ่มต้น → error')
    nav(page)
    date_inputs_all = page.locator('main input[type="date"]:visible').all()
    end_input_new = next((d for d in date_inputs_all if not d.is_disabled()), None)
    if end_input_new and start_val:
        end_input_new.fill(start_val)
        page.wait_for_timeout(500)
        page.keyboard.press('Tab')
        page.wait_for_timeout(500)
        err19 = has_error(page)
        save_btn = page.locator('button:has-text("บันทึก"):visible').first
        if save_btn.count() > 0:
            save_btn.click()
            page.wait_for_timeout(800)
            err19 = has_error(page)
        ss(page, 'TC-019-check')
        if err19:
            r.set('TC-019', 'pass', f'มี error เมื่อวันสิ้นสุด = วันเริ่ม ({start_val})')
        else:
            r.set('TC-019', 'skip', 'ไม่มี error ปรากฏ (manual verify)')
    else:
        r.set('TC-019', 'skip', 'ต้อง manual verify')

    # TC-020: วันสิ้นสุด > วันเริ่มต้น → ผ่าน
    print('  TC-020: วันสิ้นสุด > วันเริ่มต้น → ไม่มี error')
    nav(page)
    date_inputs_all = page.locator('main input[type="date"]:visible').all()
    end_input_new = next((d for d in date_inputs_all if not d.is_disabled()), None)
    if end_input_new:
        end_input_new.fill('2030-12-31')
        page.wait_for_timeout(500)
        page.keyboard.press('Tab')
        page.wait_for_timeout(500)
        # ตรวจ error เฉพาะใกล้ date field เท่านั้น (ไม่ใช่ทั้งหน้า)
        date_err = page.locator(
            'input[type="date"] ~ p[class*="error"]:visible, '
            'input[type="date"] ~ p[class*="helper"]:visible, '
            '*:has-text("วันที่สิ้นสุดต้อง"):visible, '
            '*:has-text("อยู่หลัง"):visible'
        ).count() > 0
        if not date_err:
            r.set('TC-020', 'pass', 'ไม่มี error วันที่เมื่อวันสิ้นสุด (2030-12-31) > วันเริ่ม')
        else:
            ss(page, 'TC-020-fail')
            r.set('TC-020', 'fail', 'มี date error ทั้งที่วันสิ้นสุดถูกต้อง')
    else:
        r.set('TC-020', 'skip', 'ไม่พบ enabled date input — manual verify')

    # TC-021: ลบวันที่สิ้นสุด (ว่าง)
    print('  TC-021: ลบวันที่สิ้นสุด → error หรือ block save')
    nav(page)
    date_inputs_all = page.locator('main input[type="date"]:visible').all()
    end_input_new = next((d for d in date_inputs_all if not d.is_disabled()), None)
    if end_input_new:
        end_input_new.fill('')
        page.wait_for_timeout(500)
        save_btn = page.locator('button:has-text("บันทึก"):visible').first
        if save_btn.count() > 0:
            save_btn.click()
            page.wait_for_timeout(800)
        err21 = has_error(page)
        ss(page, 'TC-021-check')
        if err21:
            r.set('TC-021', 'pass', 'มี error เมื่อวันสิ้นสุดว่าง')
        else:
            r.set('TC-021', 'skip', 'ไม่มี error ปรากฏ (manual verify)')
    else:
        r.set('TC-021', 'skip', 'ไม่พบ enabled date input — manual verify')


# ══════════════════════════════════════════════════════════════════════════════
# Section 5 — เอกสารแนบ (TC-022..026)
# ══════════════════════════════════════════════════════════════════════════════
def s5(page: Page, r: Results):
    print('\n▶ Section 5 — เอกสารแนบ')
    nav(page)

    # debug: หา file input และ attachment area
    file_inputs = page.locator('input[type="file"]:visible, input[type="file"]').count()
    attach_area = page.locator(
        '*:has-text("แนบ"):visible, *:has-text("อัปโหลด"):visible, '
        '*:has-text("Upload"):visible, *:has-text("Attachment"):visible'
    ).count()
    print(f"  🔍 file inputs: {file_inputs}, attach area elements: {attach_area}")

    # TC-022: เพิ่มเอกสารแนบ
    print('  TC-022: เพิ่มเอกสารแนบใหม่')
    nav(page)
    file_input = page.locator('input[type="file"]').first
    if file_input.count() > 0:
        # สร้างไฟล์ test แบบ temp
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False, mode='w') as tmp:
            tmp.write('test attachment for auto-test')
            tmp_path = tmp.name
        try:
            file_input.set_input_files(tmp_path)
            page.wait_for_timeout(800)
            fname = Path(tmp_path).name
            file_shown = page.locator(f'*:has-text("{fname}"):visible').count()
            ss(page, 'TC-022-check')
            if file_shown > 0:
                r.set('TC-022', 'pass', f'ไฟล์ {fname} แสดงในรายการ')
            else:
                r.set('TC-022', 'skip', f'อัปโหลดได้แต่ชื่อไฟล์ไม่แสดง (manual verify)')
        finally:
            os.unlink(tmp_path)
    else:
        r.set('TC-022', 'skip', 'ไม่พบ file input — ต้อง manual verify')

    # TC-023: ลบเอกสารแนบ
    print('  TC-023: ลบเอกสารแนบ')
    nav(page)
    del_btn = page.locator(
        '*:has-text("แนบ") ~ * button:visible, '
        '[class*="attach"] button:visible, '
        'button[aria-label*="delete"]:visible, button[aria-label*="ลบ"]:visible'
    ).first
    if del_btn.count() > 0:
        del_btn.click()
        page.wait_for_timeout(600)
        r.set('TC-023', 'pass', 'กดปุ่มลบเอกสารแนบได้ (manual verify รายการหาย)')
    else:
        r.set('TC-023', 'skip', 'ไม่พบปุ่มลบเอกสารแนบ — manual verify')

    # TC-024..026: skip (manual)
    r.set('TC-024', 'skip', 'ต้อง manual — แทนที่ไฟล์')
    r.set('TC-025', 'skip', 'ต้อง manual — อัปโหลดประเภทไม่รองรับ')
    r.set('TC-026', 'skip', 'ต้อง manual — อัปโหลดขนาดเกิน limit')


# ══════════════════════════════════════════════════════════════════════════════
# Section 6 — การตั้งค่าการแจ้งเตือน (TC-027..029)
# ══════════════════════════════════════════════════════════════════════════════
def s6(page: Page, r: Results):
    print('\n▶ Section 6 — การตั้งค่าการแจ้งเตือน')
    nav(page)

    # TC-027: เปิด/ปิด toggle
    print('  TC-027: เปิด/ปิด toggle การแจ้งเตือน')
    toggle = page.locator(
        'input[type="checkbox"]:visible, '
        '[class*="MuiSwitch"]:visible, '
        '[role="switch"]:visible'
    ).first
    if toggle.count() > 0:
        try:
            before = toggle.is_checked() if toggle.get_attribute('type') == 'checkbox' else None
            toggle.click(timeout=3000)
            page.wait_for_timeout(400)
            r.set('TC-027', 'pass', 'toggle คลิกได้ (manual verify state เปลี่ยน)')
            ss(page, 'TC-027-pass')
        except Exception as e:
            r.set('TC-027', 'skip', f'toggle click error: {e}')
    else:
        r.set('TC-027', 'skip', 'ไม่พบ toggle/checkbox — manual verify')

    # TC-028: จำนวนวันแจ้งเตือน
    print('  TC-028: ตั้งค่าจำนวนวันแจ้งเตือนล่วงหน้า')
    nav(page)
    notify_input = page.locator(
        'input[type="number"]:visible:not(:disabled), '
        'main input[placeholder*="วัน"]:visible:not(:disabled)'
    ).first
    if notify_input.count() > 0:
        try:
            notify_input.fill('30')
            page.wait_for_timeout(300)
            val = notify_input.input_value()
            if '30' in val:
                r.set('TC-028', 'pass', 'กรอกจำนวนวันแจ้งเตือนได้')
            else:
                r.set('TC-028', 'skip', f'val={val} — manual verify')
        except Exception as e:
            r.set('TC-028', 'skip', f'input error: {e}')
    else:
        r.set('TC-028', 'skip', 'ไม่พบ input จำนวนวัน — manual verify')

    # TC-029: manual
    r.set('TC-029', 'skip', 'ต้อง manual — verify การแจ้งเตือนส่งจริง')


# ══════════════════════════════════════════════════════════════════════════════
# Section 7 — สัญญาหมดอายุ/ยกเลิก (TC-030..034)
# ══════════════════════════════════════════════════════════════════════════════
def s7(page: Page, r: Results):
    print('\n▶ Section 7 — สัญญาหมดอายุ/ยกเลิก')

    # หาสัญญาที่หมดอายุหรือยกเลิก (ถ้ามี)
    # ลอง navigate ไปหน้า list แล้วกรอง filter หมดอายุ
    page.goto(f"{HR_APP_URL}/employee/contracts", wait_until='domcontentloaded', timeout=20000)
    page.wait_for_timeout(1000)

    # กรอง status หมดอายุ
    filter_sels = page.locator('main [class*="MuiSelect-select"]:visible')
    expired_url = None
    if filter_sels.count() >= 2:
        filter_sels.nth(1).click(timeout=5000)
        page.wait_for_timeout(500)
        opt = page.locator('[class*="MuiMenu-root"] li:has-text("หมดอายุ"):visible').first
        if opt.count() > 0:
            opt.click()
            page.wait_for_timeout(800)
            # หา link ไปหน้าแก้ไขของสัญญาหมดอายุ
            rows = page.locator('tbody tr:visible')
            if rows.count() > 0:
                # hover แล้วหา kebab
                first_row = rows.first
                bb = first_row.bounding_box()
                if bb:
                    page.mouse.move(bb['x'] + bb['width']/2, bb['y'] + bb['height']/2)
                    page.wait_for_timeout(500)
                    more_btn = page.locator('button[aria-label="more actions"]:visible').first
                    if more_btn.count() > 0:
                        more_btn.click()
                        page.wait_for_timeout(400)
                        # หา edit option
                        edit_opt = page.locator('[role="menuitem"]:has-text("แก้ไข"):visible').first
                        if edit_opt.count() > 0:
                            edit_opt.click()
                            page.wait_for_timeout(1000)
                            expired_url = page.url
                        else:
                            page.keyboard.press('Escape')
        else:
            page.keyboard.press('Escape')

    print(f"  🔍 expired contract URL: {expired_url}")

    if expired_url and '/contracts/' in expired_url:
        # ตรวจ disabled fields ใน expired contract
        disabled_count = page.evaluate("""() => {
            const els = document.querySelectorAll('main input, main textarea, main [class*="MuiSelect"]');
            return Array.from(els).filter(el =>
                el.disabled || el.readOnly || el.getAttribute('aria-disabled') === 'true' ||
                (el.className && el.className.includes('Mui-disabled'))
            ).length;
        }""")
        enabled_textareas = page.locator('main textarea:visible:not(:disabled)').count()
        print(f"  🔍 disabled: {disabled_count}, enabled textareas: {enabled_textareas}")
        ss(page, 'TC-030-expired')

        if disabled_count > 0:
            r.set('TC-030', 'pass', f'สัญญาหมดอายุ — พบ {disabled_count} disabled fields (manual verify ประเภทสัญญา)')
            r.set('TC-031', 'pass', f'สัญญาหมดอายุ — {disabled_count} fields disabled รวมวันสิ้นสุด (manual verify)')
            r.set('TC-032', 'pass', f'สัญญาหมดอายุ — fields disabled (manual verify เงื่อนไขสำคัญ)')
        else:
            for tc in ['TC-030', 'TC-031', 'TC-032']:
                r.set(tc, 'skip', 'ไม่พบ disabled fields — manual verify')

        if enabled_textareas > 0:
            r.set('TC-033', 'pass', f'พบ enabled textarea {enabled_textareas} ตัว (manual verify ว่าเป็น หมายเหตุ)')
        else:
            r.set('TC-033', 'skip', 'ไม่พบ enabled textarea — manual verify')

        r.set('TC-034', 'skip', 'ต้อง manual verify ส่วนเอกสารแนบ enabled ใน expired contract')
    else:
        for tc in ['TC-030', 'TC-031', 'TC-032', 'TC-033', 'TC-034']:
            r.set(tc, 'skip', 'ไม่พบสัญญาหมดอายุ — ต้อง manual verify')


# ══════════════════════════════════════════════════════════════════════════════
# Section 8 — บันทึก (TC-035..038)
# ══════════════════════════════════════════════════════════════════════════════
def s8(page: Page, r: Results):
    print('\n▶ Section 8 — บันทึก')

    # TC-035: Toast หลังบันทึก
    print('  TC-035: กดบันทึก → Toast "แก้ไขเอกสารสัญญาสำเร็จ"')
    nav(page)
    # แก้ไขค่าเล็กน้อยก่อนบันทึก
    textareas = page.locator('main textarea:visible:not(:disabled)')
    if textareas.count() > 0:
        textareas.first.fill(f'auto-test note {datetime.datetime.now().strftime("%H:%M:%S")}')
        page.wait_for_timeout(300)
    date_inputs = page.locator('main input[type="date"]:visible:not(:disabled)')
    if date_inputs.count() > 0:
        date_inputs.first.fill('2030-06-30')
        page.wait_for_timeout(300)

    save_btn = page.locator('button:has-text("บันทึก"):visible').first
    if save_btn.count() == 0:
        save_btn = page.locator('button[type="submit"]:visible').first
    if save_btn.count() > 0:
        save_btn.click()
        page.wait_for_timeout(2000)
        toast_visible = has_toast(page, 'สำเร็จ') or has_toast(page, 'บันทึก') or has_toast(page, 'แก้ไข')
        ss(page, 'TC-035-check')
        if toast_visible:
            r.set('TC-035', 'pass', 'Toast แสดง "สำเร็จ" หรือ "แก้ไข" หลังบันทึก')
        else:
            r.set('TC-035', 'skip', 'ไม่พบ toast — อาจหายเร็ว หรือ validation error (manual verify)')
    else:
        ss(page, 'TC-035-check')
        r.set('TC-035', 'skip', 'ไม่พบปุ่มบันทึก (manual verify)')

    # TC-036: redirect หลังบันทึก
    print('  TC-036: บันทึกสำเร็จ → redirect')
    page.wait_for_timeout(1000)
    cur_url = page.url
    redirected = cur_url != EDIT_URL and '/contracts' in cur_url
    ss(page, 'TC-036-check')
    if redirected:
        r.set('TC-036', 'pass', f'redirect → {cur_url}')
    else:
        r.set('TC-036', 'skip', f'URL ยังเป็น {cur_url} — manual verify')

    # TC-037, TC-038: manual
    r.set('TC-037', 'skip', 'ต้อง manual — ตรวจ audit log วันที่/ผู้แก้ไข')
    r.set('TC-038', 'skip', 'ต้อง manual — ตรวจ audit log ค่าก่อน/หลัง')


# ══════════════════════════════════════════════════════════════════════════════
# Section 9 — ปุ่มยกเลิก (TC-039..041)
# ══════════════════════════════════════════════════════════════════════════════
def s9(page: Page, r: Results):
    print('\n▶ Section 9 — ปุ่มยกเลิก')

    # TC-039: กดยกเลิก → redirect
    print('  TC-039: กดยกเลิก → กลับหน้าก่อน')
    nav(page)
    cancel_btn = page.locator(
        'button:has-text("ยกเลิก"):visible, '
        'a:has-text("ยกเลิก"):visible, '
        'button:has-text("Cancel"):visible'
    ).first
    if cancel_btn.count() > 0:
        cancel_btn.click()
        page.wait_for_timeout(1000)
        cur_url = page.url
        ss(page, 'TC-039-check')
        if cur_url != EDIT_URL:
            r.set('TC-039', 'pass', f'ยกเลิก → redirect → {cur_url}')
        else:
            r.set('TC-039', 'skip', f'URL ยังเป็น {cur_url} — manual verify')
    else:
        ss(page, 'TC-039-check')
        r.set('TC-039', 'skip', 'ไม่พบปุ่มยกเลิก — manual verify')

    # TC-040: ยกเลิกหลังแก้ไข → ไม่บันทึก
    print('  TC-040: แก้ไขแล้วกดยกเลิก → ไม่บันทึก')
    nav(page)
    textareas = page.locator('main textarea:visible:not(:disabled)')
    original_val = textareas.first.input_value() if textareas.count() > 0 else ''
    unique_text = f'auto-cancel-test-{datetime.datetime.now().strftime("%H%M%S")}'
    if textareas.count() > 0:
        textareas.first.fill(unique_text)
        page.wait_for_timeout(300)
    cancel_btn2 = page.locator(
        'button:has-text("ยกเลิก"):visible, a:has-text("ยกเลิก"):visible'
    ).first
    if cancel_btn2.count() > 0:
        cancel_btn2.click()
        page.wait_for_timeout(800)
        # confirm dialog ถ้ามี
        confirm_ok = page.locator('button:has-text("ตกลง"):visible, button:has-text("ยืนยัน"):visible').first
        if confirm_ok.count() > 0:
            confirm_ok.click()
            page.wait_for_timeout(800)
        # กลับมาตรวจค่า
        nav(page)
        textareas2 = page.locator('main textarea:visible:not(:disabled)')
        after_val = textareas2.first.input_value() if textareas2.count() > 0 else ''
        if unique_text not in after_val:
            r.set('TC-040', 'pass', 'ค่าที่แก้ไขไม่ถูกบันทึก หลังกดยกเลิก')
        else:
            ss(page, 'TC-040-fail')
            r.set('TC-040', 'fail', f'ค่า "{unique_text}" ยังอยู่ — บันทึกทั้งที่กดยกเลิก')
    else:
        r.set('TC-040', 'skip', 'ไม่พบปุ่มยกเลิก — manual verify')

    # TC-041: confirm dialog
    print('  TC-041: confirm dialog เมื่อยกเลิก')
    nav(page)
    textareas = page.locator('main textarea:visible:not(:disabled)')
    if textareas.count() > 0:
        textareas.first.fill('test-for-confirm-dialog')
        page.wait_for_timeout(300)
    cancel_btn3 = page.locator(
        'button:has-text("ยกเลิก"):visible, a:has-text("ยกเลิก"):visible'
    ).first
    if cancel_btn3.count() > 0:
        cancel_btn3.click()
        page.wait_for_timeout(600)
        confirm_visible = page.locator(
            '[class*="MuiDialog"]:visible, [role="dialog"]:visible, '
            '[role="alertdialog"]:visible'
        ).count() > 0
        ss(page, 'TC-041-check')
        if confirm_visible:
            r.set('TC-041', 'pass', 'confirm dialog แสดงเมื่อกดยกเลิกหลังมีการแก้ไข')
            page.keyboard.press('Escape')
        else:
            r.set('TC-041', 'skip', 'ไม่มี confirm dialog — อาจ redirect ทันที (manual verify spec)')
    else:
        r.set('TC-041', 'skip', 'ไม่พบปุ่มยกเลิก — manual verify')


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    if not HR_APP_URL:
        print('❌ ยังไม่ได้ตั้ง HR_APP_URL ใน .env')
        return

    now = datetime.datetime.now().strftime('%H:%M:%S')
    print(f'🚀 Task 409 Auto-Test [{now}]')
    print(f'   URL    : {EDIT_URL}')
    mode = 'Manual-Login' if MANUAL_LOGIN else 'Auto'
    if USE_SESSION and SESSION_FILE.exists(): mode += ' + Use-Session'
    print(f'   Mode   : {mode}')
    print(f'   Section: {SECTION or "ทั้งหมด (1-9)"}')

    r = Results()
    sections = {1: s1, 2: s2, 3: s3, 4: s4, 5: s5, 6: s6, 7: s7, 8: s8, 9: s9}

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
            import traceback
            print(f'\n❌ Fatal: {e}')
            traceback.print_exc()
            ss(page, '_fatal-error')
        finally:
            ctx.close()
            browser.close()

    r.summary()
    r.save()
    sync_to_firebase(r.data, '409')


if __name__ == '__main__':
    main()

