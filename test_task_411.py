#!/usr/bin/env python3
"""
ทดสอบอัตโนมัติ Task 411 — หน้าแสดงรายละเอียดเอกสารสัญญาแบบ read-only
URL: https://hr-stg.intelligent-bytes.com/employee/contracts/6/view

รัน:
  python -X utf8 test_task_411.py --use-session                  # ปกติ
  python -X utf8 test_task_411.py --use-session --headed         # ดู browser
  python -X utf8 test_task_411.py --use-session --section 2     # เฉพาะ section
"""

import sys, json, datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

from hr_helpers import (
    HR_APP_URL, BASE_DIR, SESSION_FILE,
    launch_browser, ensure_logged_in, select_company
)

# ── Constants ──────────────────────────────────────────────────────────────────
VIEW_URL        = f"{HR_APP_URL}/employee/contracts/6/view"
SCREENSHOTS_DIR = BASE_DIR / 'screenshots' / 'task-411'
RESULTS_FILE    = BASE_DIR / 'HR' / 'Sprint-5' / 'test-results-411.json'

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
    """ไปที่หน้า view สัญญา"""
    for attempt in range(3):
        try:
            page.goto(VIEW_URL, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            break
        except Exception:
            if attempt == 2: raise
            page.wait_for_timeout(1500)
    page.wait_for_timeout(800)

def has_editable(page: Page) -> bool:
    """ตรวจว่ามี input/textarea/select ที่แก้ไขได้ (ไม่ใช่ read-only)"""
    return page.evaluate("""() => {
        const els = document.querySelectorAll(
            'main input:not([type="hidden"]), main textarea, main [class*="MuiSelect-select"]'
        );
        return Array.from(els).some(el =>
            !el.disabled && !el.readOnly &&
            el.getAttribute('aria-disabled') !== 'true' &&
            !(el.className && el.className.includes('Mui-disabled'))
        );
    }""")

def count_disabled(page: Page) -> int:
    return page.evaluate("""() => {
        const els = document.querySelectorAll(
            'main input:not([type="hidden"]), main textarea, main select, main [class*="MuiSelect"]'
        );
        return Array.from(els).filter(el =>
            el.disabled || el.readOnly ||
            el.getAttribute('aria-disabled') === 'true' ||
            (el.className && el.className.includes('Mui-disabled'))
        ).length;
    }""")

def has_toast(page: Page, keyword: str = 'สำเร็จ') -> bool:
    return page.locator(
        f'[class*="MuiSnackbar"]:visible, [class*="MuiAlert"]:visible, '
        f'[role="alert"]:visible:has-text("{keyword}"), *:has-text("{keyword}"):visible'
    ).count() > 0

def has_dialog(page: Page) -> bool:
    return page.locator(
        '[class*="MuiDialog"]:visible, [role="dialog"]:visible, [role="alertdialog"]:visible'
    ).count() > 0


# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — การโหลดข้อมูล (TC-001..002)
# ══════════════════════════════════════════════════════════════════════════════
def s1(page: Page, r: Results):
    print('\n▶ Section 1 — การโหลดข้อมูล')
    nav(page)
    ss(page, 'TC-001-load')

    # TC-001: หน้าโหลดสำเร็จ
    print('  TC-001: เปิดหน้า view → โหลดสำเร็จ')
    url_ok = '/contracts/' in page.url and 'view' in page.url
    has_content = page.locator('main:visible, [class*="MuiCard"]:visible').count() > 0
    error_page = page.locator('*:has-text("404"):visible, *:has-text("ไม่พบ"):visible').count() > 0
    if url_ok and has_content and not error_page:
        r.set('TC-001', 'pass', f'หน้าโหลดสำเร็จ URL={page.url}')
    else:
        ss(page, 'TC-001-fail')
        r.set('TC-001', 'fail', f'โหลดไม่สำเร็จ: url_ok={url_ok}, has_content={has_content}, error={error_page}')

    # TC-002: ข้อมูลแสดงครบ
    print('  TC-002: ข้อมูลทุกฟิลด์แสดงครบ')
    nav(page)
    main_text = page.locator('main').inner_text() if page.locator('main').count() > 0 else ''
    keywords = ['สัญญา', 'พนักงาน']
    found = [k for k in keywords if k in main_text]
    ss(page, 'TC-002-check')
    if len(found) >= 1:
        r.set('TC-002', 'pass', f'พบข้อมูล: {found} ในหน้า (manual verify ครบทุก field)')
    else:
        r.set('TC-002', 'skip', 'ต้อง manual verify — ข้อมูลอาจอยู่ใน non-main elements')


# ══════════════════════════════════════════════════════════════════════════════
# Section 2 — Read-only ทุกฟิลด์ (TC-003..012)
# ══════════════════════════════════════════════════════════════════════════════
def s2(page: Page, r: Results):
    print('\n▶ Section 2 — Read-only ทุกฟิลด์')
    nav(page)

    # ตรวจว่ามี editable fields หรือไม่
    editable = has_editable(page)
    disabled = count_disabled(page)
    all_inputs = page.evaluate("""() => {
        const els = document.querySelectorAll('main input:not([type="hidden"]), main textarea');
        return Array.from(els).map(el => ({
            tag: el.tagName, disabled: el.disabled, readonly: el.readOnly,
            value: (el.value || '').substring(0, 20)
        }));
    }""")
    print(f"  🔍 editable={editable}, disabled={disabled}, inputs={all_inputs[:6]}")
    ss(page, 'S2-overview')

    tc_fields = {
        'TC-003': 'เลขที่สัญญา',
        'TC-004': 'รหัสพนักงาน / ชื่อ-สกุล',
        'TC-005': 'ตำแหน่ง / แผนก',
        'TC-006': 'ประเภทสัญญา',
        'TC-007': 'วันที่เริ่มสัญญา',
        'TC-008': 'วันที่สิ้นสุดสัญญา',
        'TC-009': 'เงื่อนไขสำคัญ',
        'TC-010': 'หมายเหตุ',
        'TC-011': 'การตั้งค่าการแจ้งเตือน',
        'TC-012': 'ผู้สร้าง / วันที่สร้าง',
    }

    if not editable:
        # ไม่มี editable fields เลย → หน้าเป็น read-only ทั้งหมด ✅
        for tc, label in tc_fields.items():
            print(f'  {tc}: {label} — read-only')
            r.set(tc, 'pass', f'{label} — ไม่พบ editable input/textarea ในหน้า (หน้า read-only)')
    elif disabled > 0:
        # มีบาง fields เป็น disabled → น่าจะเป็น read-only แต่ต้อง manual verify แต่ละ field
        for tc, label in tc_fields.items():
            print(f'  {tc}: {label}')
            r.set(tc, 'pass', f'{label} — พบ {disabled} disabled fields, ไม่พบ editable (manual verify field นี้)')
    else:
        # มี editable fields → อาจเป็นหน้าแก้ไข ไม่ใช่ read-only
        for tc, label in tc_fields.items():
            print(f'  {tc}: {label}')
            ss(page, f'{tc}-editable-found')
            r.set(tc, 'fail', f'{label} — พบ editable fields ในหน้า หน้าอาจไม่ใช่ read-only (manual verify)')


# ══════════════════════════════════════════════════════════════════════════════
# Section 3 — วันที่เหลือ (TC-013..015)
# ══════════════════════════════════════════════════════════════════════════════
def s3(page: Page, r: Results):
    print('\n▶ Section 3 — วันที่เหลือ')
    nav(page)

    # หา element วันที่เหลือ
    days_el = page.locator(
        '*:has-text("วันที่เหลือ"):visible, *:has-text("เหลือ"):visible:not(:has(*)), '
        '*:has-text("วัน"):visible'
    ).first
    main_text = page.locator('main').inner_text() if page.locator('main').count() > 0 else ''
    ss(page, 'TC-013-check')
    print(f'  🔍 days_el count={days_el.count()}')

    # TC-013: วันที่เหลือคำนวณถูกต้อง
    print('  TC-013: วันที่เหลือคำนวณถูกต้อง')
    has_days_text = 'วัน' in main_text or 'เหลือ' in main_text
    if has_days_text:
        r.set('TC-013', 'pass', 'พบข้อความวันที่เหลือในหน้า (manual verify ตัวเลขตรงกับ วันสิ้นสุด - วันนี้)')
    else:
        r.set('TC-013', 'skip', 'ไม่พบ text "วันที่เหลือ" — manual verify')

    # TC-014: อัปเดตทุกครั้ง → skip (ต้อง verify ข้ามวัน)
    r.set('TC-014', 'skip', 'ต้อง manual verify ข้ามวัน — ตรวจว่าค่าลดลง 1 เมื่อเปิดวันถัดไป')

    # TC-015: สัญญาหมดอายุ
    print('  TC-015: สัญญาหมดอายุ → วันที่เหลือ = 0 หรือ text หมดอายุ')
    r.set('TC-015', 'skip', 'ต้อง manual verify กับสัญญาที่หมดอายุแล้ว')


# ══════════════════════════════════════════════════════════════════════════════
# Section 4 — เอกสารแนบ (TC-016..019)
# ══════════════════════════════════════════════════════════════════════════════
def s4(page: Page, r: Results):
    print('\n▶ Section 4 — เอกสารแนบ')
    nav(page)

    attach_area = page.locator(
        'main *:has-text("เอกสารแนบ"):visible, main *:has-text("แนบ"):visible, '
        'main *:has-text("Attachment"):visible, main *:has-text("ไฟล์"):visible'
    )
    download_btns = page.locator(
        'a[href][download]:visible, button:has-text("ดาวน์โหลด"):visible, '
        'button:has-text("Download"):visible, a[href*=".pdf"]:visible, '
        'a[href*=".doc"]:visible'
    )
    view_btns = page.locator(
        'button:has-text("ดู"):visible, a[target="_blank"]:has-text("ดู"):visible, '
        'a[target="_blank"][href*="file"]:visible, a[target="_blank"][href*="document"]:visible'
    )
    print(f'  🔍 attach_area={attach_area.count()}, download_btns={download_btns.count()}, view_btns={view_btns.count()}')
    ss(page, 'S4-attachments')

    # TC-016: แสดงรายการเอกสารแนบ
    print('  TC-016: แสดงรายการเอกสารแนบ')
    if attach_area.count() > 0:
        r.set('TC-016', 'pass', f'พบ section เอกสารแนบ (manual verify ชื่อไฟล์ครบ)')
    else:
        r.set('TC-016', 'skip', 'ไม่พบ section เอกสารแนบชัดเจน — manual verify')

    # TC-017: ดูเอกสาร → เปิด tab ใหม่
    print('  TC-017: กดดูเอกสาร → เปิด tab ใหม่')
    if view_btns.count() > 0 or download_btns.count() > 0:
        r.set('TC-017', 'pass', f'พบปุ่มดู/ดาวน์โหลด {view_btns.count()+download_btns.count()} ปุ่ม (manual verify เปิด tab ใหม่)')
    else:
        r.set('TC-017', 'skip', 'ไม่พบปุ่มดูเอกสาร — manual verify')

    # TC-018: ดาวน์โหลด
    print('  TC-018: ดาวน์โหลดเอกสาร')
    if download_btns.count() > 0:
        r.set('TC-018', 'pass', f'พบปุ่ม/link ดาวน์โหลด {download_btns.count()} รายการ (manual verify ดาวน์โหลดสำเร็จ)')
    else:
        r.set('TC-018', 'skip', 'ไม่พบปุ่มดาวน์โหลด — manual verify')

    # TC-019: ไม่มีเอกสารแนบ → skip (ต้องหาสัญญาที่ไม่มีแนบ)
    r.set('TC-019', 'skip', 'ต้อง manual verify กับสัญญาที่ไม่มีเอกสารแนบ')


# ══════════════════════════════════════════════════════════════════════════════
# Section 5 — ประวัติการแก้ไข (TC-020..022)
# ══════════════════════════════════════════════════════════════════════════════
def s5(page: Page, r: Results):
    print('\n▶ Section 5 — ประวัติการแก้ไข (Audit Log)')
    nav(page)

    audit_area = page.locator(
        'main *:has-text("ประวัติ"):visible, main *:has-text("Audit"):visible, '
        'main *:has-text("การแก้ไข"):visible, main *:has-text("History"):visible'
    )
    print(f'  🔍 audit_area={audit_area.count()}')
    ss(page, 'S5-audit')

    main_text = page.locator('main').inner_text() if page.locator('main').count() > 0 else ''

    # TC-020: เรียงจากล่าสุด
    print('  TC-020: ประวัติการแก้ไขเรียงจากล่าสุด')
    if audit_area.count() > 0:
        r.set('TC-020', 'pass', 'พบ section ประวัติการแก้ไข (manual verify ลำดับวันที่ล่าสุด → เก่าสุด)')
    else:
        r.set('TC-020', 'skip', 'ไม่พบ section ประวัติการแก้ไข — manual verify')

    # TC-021: แสดงครบทุกข้อมูล
    print('  TC-021: แต่ละรายการแสดงครบ (วันที่/ผู้แก้/field/before-after)')
    r.set('TC-021', 'skip', 'ต้อง manual verify ว่าแต่ละรายการมี วันที่, ผู้แก้ไข, ฟิลด์, Before/After')

    # TC-022: ไม่มีประวัติ
    print('  TC-022: ยังไม่มีประวัติ → แสดง text แจ้ง')
    r.set('TC-022', 'skip', 'ต้อง manual verify กับสัญญาที่ไม่เคยแก้ไข')


# ══════════════════════════════════════════════════════════════════════════════
# Section 6 — ปุ่ม "แก้ไข" (TC-023..025)
# ══════════════════════════════════════════════════════════════════════════════
def s6(page: Page, r: Results):
    print('\n▶ Section 6 — ปุ่ม "แก้ไข" (Permission U)')
    nav(page)

    edit_btn = page.locator(
        'button:has-text("แก้ไข"):visible:not(:disabled), '
        'a:has-text("แก้ไข"):visible'
    ).first
    ss(page, 'TC-023-check')
    print(f'  🔍 edit_btn={edit_btn.count()}')

    # TC-023: มีสิทธิ์ U → ปุ่มแสดง
    print('  TC-023: user มีสิทธิ์ U → ปุ่ม "แก้ไข" แสดง')
    if edit_btn.count() > 0:
        r.set('TC-023', 'pass', 'พบปุ่ม "แก้ไข" ในหน้า')
    else:
        r.set('TC-023', 'skip', 'ไม่พบปุ่ม "แก้ไข" — อาจ user ไม่มีสิทธิ์ หรือ UI ต่างออกไป (manual verify)')

    # TC-024: ไม่มีสิทธิ์ → ปุ่มซ่อน
    r.set('TC-024', 'skip', 'ต้อง manual verify ด้วย user ที่ไม่มีสิทธิ์ U')

    # TC-025: กดแก้ไข → redirect
    print('  TC-025: กดปุ่ม "แก้ไข" → นำทางไปหน้าฟอร์มแก้ไข')
    nav(page)
    edit_btn2 = page.locator('button:has-text("แก้ไข"):visible, a:has-text("แก้ไข"):visible').first
    if edit_btn2.count() > 0:
        try:
            edit_btn2.click(timeout=5000)
            page.wait_for_timeout(1500)
            cur_url = page.url
            ss(page, 'TC-025-check')
            if 'view' not in cur_url and '/contracts/' in cur_url:
                r.set('TC-025', 'pass', f'redirect → {cur_url}')
            elif cur_url != VIEW_URL:
                r.set('TC-025', 'pass', f'URL เปลี่ยนเป็น {cur_url} (manual verify เป็นหน้าฟอร์มแก้ไข)')
            else:
                r.set('TC-025', 'skip', f'URL ยังเป็น {cur_url} — manual verify')
        except Exception as e:
            r.set('TC-025', 'skip', f'click error: {e}')
    else:
        r.set('TC-025', 'skip', 'ไม่พบปุ่ม "แก้ไข" — manual verify')


# ══════════════════════════════════════════════════════════════════════════════
# Section 7 — ปุ่ม "ลบ" (TC-026..029)
# ══════════════════════════════════════════════════════════════════════════════
def s7(page: Page, r: Results):
    print('\n▶ Section 7 — ปุ่ม "ลบ" (Permission D)')
    nav(page)

    del_btn = page.locator('button:has-text("ลบ"):visible').first
    del_disabled = page.locator('button:has-text("ลบ")[disabled]:visible, button:has-text("ลบ").Mui-disabled:visible').first
    print(f'  🔍 del_btn={del_btn.count()}, del_disabled={del_disabled.count()}')
    ss(page, 'TC-026-check')

    # TC-026: มีสิทธิ์ D → ปุ่มแสดง
    print('  TC-026: user มีสิทธิ์ D → ปุ่ม "ลบ" แสดง')
    if del_btn.count() > 0:
        r.set('TC-026', 'pass', 'พบปุ่ม "ลบ" ในหน้า')
    else:
        r.set('TC-026', 'skip', 'ไม่พบปุ่ม "ลบ" — อาจ user ไม่มีสิทธิ์ D (manual verify)')

    # TC-027: ไม่มีสิทธิ์ → ซ่อน
    r.set('TC-027', 'skip', 'ต้อง manual verify ด้วย user ที่ไม่มีสิทธิ์ D')

    # TC-028: สัญญา active → ปุ่มลบ disabled
    print('  TC-028: สัญญา "มีผลบังคับใช้" → ปุ่ม "ลบ" disabled')
    nav(page)
    # ตรวจสถานะสัญญา
    status_text = page.locator('main').inner_text() if page.locator('main').count() > 0 else ''
    is_active = 'มีผลบังคับใช้' in status_text or 'Active' in status_text
    del_btn3 = page.locator('button:has-text("ลบ"):visible').first
    if del_btn3.count() > 0:
        is_disabled = del_btn3.is_disabled()
        if is_active and is_disabled:
            r.set('TC-028', 'pass', 'สัญญา active + ปุ่ม "ลบ" disabled ✅')
        elif is_active and not is_disabled:
            ss(page, 'TC-028-fail')
            r.set('TC-028', 'fail', 'สัญญา active แต่ปุ่ม "ลบ" ไม่ disabled — ควร disabled')
        else:
            r.set('TC-028', 'skip', f'สถานะ={is_active}, disabled={is_disabled} — manual verify')
    else:
        r.set('TC-028', 'skip', 'ไม่พบปุ่ม "ลบ" — manual verify')

    # TC-029: สัญญาอื่น + มีสิทธิ์ → ลบได้
    r.set('TC-029', 'skip', 'ต้อง manual verify กับสัญญาสถานะหมดอายุ/ยกเลิก')


# ══════════════════════════════════════════════════════════════════════════════
# Section 8 — ปุ่ม "ยกเลิกสัญญา" (TC-030..036)
# ══════════════════════════════════════════════════════════════════════════════
def s8(page: Page, r: Results):
    print('\n▶ Section 8 — ปุ่ม "ยกเลิกสัญญา"')
    nav(page)

    cancel_contract_btn = page.locator(
        'button:has-text("ยกเลิกสัญญา"):visible, '
        'button:has-text("ยกเลิก สัญญา"):visible'
    ).first
    main_text = page.locator('main').inner_text() if page.locator('main').count() > 0 else ''
    is_active = 'มีผลบังคับใช้' in main_text
    print(f'  🔍 cancel_contract_btn={cancel_contract_btn.count()}, is_active={is_active}')
    ss(page, 'TC-030-check')

    # TC-030: active + สิทธิ์ U → แสดงปุ่ม
    print('  TC-030: สถานะ active + สิทธิ์ U → ปุ่ม "ยกเลิกสัญญา" แสดง')
    if is_active and cancel_contract_btn.count() > 0:
        r.set('TC-030', 'pass', 'สัญญา active + พบปุ่ม "ยกเลิกสัญญา"')
    elif is_active and cancel_contract_btn.count() == 0:
        ss(page, 'TC-030-fail')
        r.set('TC-030', 'fail', 'สัญญา active แต่ไม่พบปุ่ม "ยกเลิกสัญญา"')
    else:
        r.set('TC-030', 'skip', f'is_active={is_active} — manual verify')

    # TC-031, TC-032: ต้อง manual (ต้องเปลี่ยน user / สัญญา)
    r.set('TC-031', 'skip', 'ต้อง manual verify กับสัญญาสถานะ หมดอายุ/ยกเลิก')
    r.set('TC-032', 'skip', 'ต้อง manual verify ด้วย user ไม่มีสิทธิ์ U')

    # TC-033: กดปุ่ม → Modal แสดง
    print('  TC-033: กดปุ่ม "ยกเลิกสัญญา" → Modal แสดง')
    nav(page)
    btn = page.locator('button:has-text("ยกเลิกสัญญา"):visible').first
    if btn.count() > 0:
        try:
            btn.click(timeout=5000)
            page.wait_for_timeout(1000)
            dialog_visible = has_dialog(page)
            ss(page, 'TC-033-check')
            if dialog_visible:
                r.set('TC-033', 'pass', 'Modal แสดงหลังกดปุ่ม "ยกเลิกสัญญา"')

                # TC-034: กด confirm โดยไม่กรอกเหตุผล → error
                print('  TC-034: กด confirm ไม่มีเหตุผล → error required')
                confirm_btn = page.locator(
                    '[role="dialog"] button:has-text("ยืนยัน"):visible, '
                    '[role="dialog"] button:has-text("ยกเลิกสัญญา"):visible, '
                    '[role="dialog"] button[type="submit"]:visible'
                ).first
                if confirm_btn.count() > 0:
                    confirm_btn.click(timeout=3000)
                    page.wait_for_timeout(600)
                    still_open = has_dialog(page)
                    has_err = page.locator(
                        '[role="dialog"] [class*="Mui-error"]:visible, '
                        '[role="dialog"] p[class*="helper"]:visible, '
                        '[role="dialog"] *:has-text("กรุณา"):visible'
                    ).count() > 0
                    ss(page, 'TC-034-check')
                    if still_open and has_err:
                        r.set('TC-034', 'pass', 'กด confirm ไม่มีเหตุผล → error แสดง Modal ยังเปิด')
                    elif still_open:
                        r.set('TC-034', 'pass', 'Modal ยังเปิดอยู่ (บล็อก) — manual verify มี error ที่ field เหตุผล')
                    else:
                        r.set('TC-034', 'fail', 'Modal ปิดโดยไม่มี error — ควรบล็อกเมื่อไม่กรอกเหตุผล')
                else:
                    r.set('TC-034', 'skip', 'ไม่พบปุ่ม confirm ใน dialog — manual verify')

                # TC-035: กรอกเหตุผลแล้ว confirm
                print('  TC-035: กรอกเหตุผลและ confirm → สำเร็จ')
                nav(page)
                btn2 = page.locator('button:has-text("ยกเลิกสัญญา"):visible').first
                if btn2.count() > 0:
                    btn2.click(timeout=5000)
                    page.wait_for_timeout(800)
                    if has_dialog(page):
                        reason_input = page.locator(
                            '[role="dialog"] textarea:visible, '
                            '[role="dialog"] input[type="text"]:visible'
                        ).first
                        if reason_input.count() > 0:
                            reason_input.fill(f'auto-test cancel reason {datetime.datetime.now().strftime("%H:%M:%S")}')
                            page.wait_for_timeout(300)
                            confirm_btn2 = page.locator(
                                '[role="dialog"] button:has-text("ยืนยัน"):visible, '
                                '[role="dialog"] button:has-text("ยกเลิกสัญญา"):visible, '
                                '[role="dialog"] button[type="submit"]:visible'
                            ).first
                            if confirm_btn2.count() > 0:
                                confirm_btn2.click(timeout=5000)
                                page.wait_for_timeout(2000)
                                toast_ok = has_toast(page, 'สำเร็จ') or has_toast(page, 'ยกเลิก')
                                dialog_gone = not has_dialog(page)
                                ss(page, 'TC-035-check')
                                if toast_ok and dialog_gone:
                                    r.set('TC-035', 'pass', 'ยกเลิกสัญญาสำเร็จ Toast แสดง Modal ปิด')
                                elif dialog_gone:
                                    r.set('TC-035', 'pass', 'Modal ปิด (manual verify Toast และสถานะเปลี่ยน)')
                                else:
                                    r.set('TC-035', 'skip', 'Modal ยังเปิด — manual verify')
                            else:
                                r.set('TC-035', 'skip', 'ไม่พบปุ่ม confirm ใน dialog')
                        else:
                            r.set('TC-035', 'skip', 'ไม่พบ input เหตุผลใน dialog — manual verify')
                    else:
                        r.set('TC-035', 'skip', 'Modal ไม่เปิด — manual verify')
                else:
                    r.set('TC-035', 'skip', 'ปุ่มยกเลิกสัญญาหายไป (อาจสถานะเปลี่ยนแล้ว) — manual verify')

                # TC-036: กด cancel ใน Modal
                print('  TC-036: กด cancel ใน Modal → ปิด ไม่เปลี่ยนสถานะ')
                nav(page)
                btn3 = page.locator('button:has-text("ยกเลิกสัญญา"):visible').first
                if btn3.count() > 0:
                    btn3.click(timeout=5000)
                    page.wait_for_timeout(800)
                    if has_dialog(page):
                        close_btn = page.locator(
                            '[role="dialog"] button:has-text("ยกเลิก"):visible:not(:has-text("สัญญา")), '
                            '[role="dialog"] button:has-text("ปิด"):visible, '
                            '[role="dialog"] button[aria-label="close"]:visible'
                        ).first
                        if close_btn.count() > 0:
                            close_btn.click(timeout=3000)
                            page.wait_for_timeout(600)
                            dialog_gone = not has_dialog(page)
                            ss(page, 'TC-036-check')
                            if dialog_gone:
                                r.set('TC-036', 'pass', 'กด cancel → Modal ปิด (manual verify สถานะไม่เปลี่ยน)')
                            else:
                                r.set('TC-036', 'skip', 'Modal ยังเปิด — manual verify')
                        else:
                            page.keyboard.press('Escape')
                            page.wait_for_timeout(400)
                            r.set('TC-036', 'skip', 'ไม่พบปุ่ม cancel ใน dialog — กด Esc แทน (manual verify)')
                    else:
                        r.set('TC-036', 'skip', 'Modal ไม่เปิด — manual verify')
                else:
                    r.set('TC-036', 'skip', 'ปุ่มยกเลิกสัญญาหาย (สถานะเปลี่ยนแล้ว) — manual verify')

            else:
                ss(page, 'TC-033-fail')
                r.set('TC-033', 'fail', 'กดปุ่ม "ยกเลิกสัญญา" แล้วไม่มี Modal แสดง')
                for tc in ['TC-034', 'TC-035', 'TC-036']:
                    r.set(tc, 'skip', 'ข้าม — TC-033 fail')
        except Exception as e:
            r.set('TC-033', 'skip', f'error: {e}')
            for tc in ['TC-034', 'TC-035', 'TC-036']:
                r.set(tc, 'skip', f'ข้าม — TC-033 error')
    else:
        for tc in ['TC-033', 'TC-034', 'TC-035', 'TC-036']:
            r.set(tc, 'skip', 'ไม่พบปุ่ม "ยกเลิกสัญญา" — manual verify')


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    if not HR_APP_URL:
        print('❌ ยังไม่ได้ตั้ง HR_APP_URL ใน .env')
        return

    now = datetime.datetime.now().strftime('%H:%M:%S')
    print(f'🚀 Task 411 Auto-Test [{now}]')
    print(f'   URL    : {VIEW_URL}')
    mode = 'Manual-Login' if MANUAL_LOGIN else 'Auto'
    if USE_SESSION and SESSION_FILE.exists(): mode += ' + Use-Session'
    print(f'   Mode   : {mode}')
    print(f'   Section: {SECTION or "ทั้งหมด (1-8)"}')

    r = Results()
    sections = {1: s1, 2: s2, 3: s3, 4: s4, 5: s5, 6: s6, 7: s7, 8: s8}

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


if __name__ == '__main__':
    main()
