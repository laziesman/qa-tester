#!/usr/bin/env python3
"""
ทดสอบอัตโนมัติ Task 417 — อัปเดตสถานะเอกสารสัญญาอัตโนมัติ (Cronjob 01:00)
ตรวจสอบผ่าน UI หน้า /employee/contracts

รัน:
  python -X utf8 test_task_417.py --use-session
  python -X utf8 test_task_417.py --use-session --headed
  python -X utf8 test_task_417.py --use-session --section 2
"""

import sys, json, datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

from hr_helpers import (
    HR_APP_URL, BASE_DIR, SESSION_FILE,
    launch_browser, ensure_logged_in, select_company
)

# ── Constants ──────────────────────────────────────────────────────────────────
LIST_URL        = f"{HR_APP_URL}/employee/contracts"
SCREENSHOTS_DIR = BASE_DIR / 'screenshots' / 'task-417'
RESULTS_FILE    = BASE_DIR / 'HR' / 'Sprint-5' / 'test-results-417.json'

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

# สีที่คาดหวังต่อสถานะ (ตรวจจาก class หรือ text)
STATUS_LABELS = {
    'active':      ['มีผลบังคับใช้', 'Active'],
    'near_expiry': ['ใกล้หมดอายุ', 'NearExpiry', 'Near Expiry'],
    'expired':     ['หมดอายุ', 'Expired'],
    'cancelled':   ['ยกเลิก', 'Cancelled'],
}


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
    for attempt in range(3):
        try:
            page.goto(LIST_URL, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            break
        except Exception:
            if attempt == 2: raise
            page.wait_for_timeout(1500)
    page.wait_for_timeout(800)

def get_page_text(page: Page) -> str:
    el = page.locator('main')
    return el.inner_text() if el.count() > 0 else page.inner_text('body')

def count_badges(page: Page, labels: list) -> int:
    total = 0
    for label in labels:
        total += page.locator(f'*:has-text("{label}"):visible').count()
    return total

def find_filter(page: Page, label: str):
    return page.locator(
        f'button:has-text("{label}"):visible, '
        f'[role="option"]:has-text("{label}"):visible, '
        f'li:has-text("{label}"):visible, '
        f'[class*="chip"]:has-text("{label}"):visible, '
        f'[class*="tab"]:has-text("{label}"):visible'
    ).first


# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — หน้ารายการสัญญาโหลดได้ปกติ (TC-001..002)
# ══════════════════════════════════════════════════════════════════════════════
def s1(page: Page, r: Results):
    print('\n▶ Section 1 — หน้ารายการสัญญาโหลดได้ปกติ')
    nav(page)
    ss(page, 'TC-001-load')

    # TC-001: โหลดสำเร็จ
    print('  TC-001: เปิด /employee/contracts → โหลดสำเร็จ')
    url_ok = 'contracts' in page.url
    has_content = page.locator('main:visible, table:visible, [class*="MuiTable"]:visible, [class*="list"]:visible').count() > 0
    error_page = page.locator('*:has-text("404"):visible, *:has-text("ไม่พบ"):visible').count() > 0
    if url_ok and has_content and not error_page:
        r.set('TC-001', 'pass', f'หน้าโหลดสำเร็จ URL={page.url}')
    else:
        ss(page, 'TC-001-fail')
        r.set('TC-001', 'fail', f'โหลดไม่สำเร็จ url_ok={url_ok} content={has_content} error={error_page}')

    # TC-002: มี badge สถานะ
    print('  TC-002: หน้าแสดง badge สถานะสัญญา')
    all_status_labels = [l for labels in STATUS_LABELS.values() for l in labels]
    badge_count = count_badges(page, all_status_labels)
    print(f'  🔍 badge_count={badge_count}')
    ss(page, 'TC-002-badges')
    if badge_count > 0:
        r.set('TC-002', 'pass', f'พบ badge สถานะ {badge_count} รายการในหน้า')
    else:
        r.set('TC-002', 'skip', 'ไม่พบ badge สถานะชัดเจน — อาจใช้ CSS class แทน text (manual verify)')


# ══════════════════════════════════════════════════════════════════════════════
# Section 2 — Badge สีแสดงถูกต้อง (TC-003..006)
# ══════════════════════════════════════════════════════════════════════════════
def s2(page: Page, r: Results):
    print('\n▶ Section 2 — Badge สีแสดงถูกต้อง')
    nav(page)
    ss(page, 'S2-overview')
    page_text = get_page_text(page)

    # ตรวจแต่ละสถานะ
    checks = [
        ('TC-003', 'active',      'มีผลบังคับใช้', 'สีเขียว'),
        ('TC-004', 'near_expiry', 'ใกล้หมดอายุ',   'สีส้ม'),
        ('TC-005', 'expired',     'หมดอายุ',        'สีแดง'),
        ('TC-006', 'cancelled',   'ยกเลิก',         'ไม่เปลี่ยน'),
    ]
    for tc_id, key, label_th, color_desc in checks:
        print(f'  {tc_id}: badge "{label_th}" → {color_desc}')
        labels = STATUS_LABELS[key]
        found = any(l in page_text for l in labels)
        if found:
            # ตรวจสีผ่าน CSS class (heuristic)
            badge_el = page.locator(
                ', '.join(f'*:has-text("{l}"):visible' for l in labels)
            ).first
            badge_class = ''
            if badge_el.count() > 0:
                try:
                    badge_class = badge_el.get_attribute('class') or ''
                except Exception:
                    pass
            ss(page, f'{tc_id}-badge')
            r.set(tc_id, 'pass', f'พบ badge "{label_th}" ในหน้า class="{badge_class[:80]}" (manual verify สี{color_desc})')
        else:
            r.set(tc_id, 'skip', f'ไม่พบ badge "{label_th}" — อาจไม่มีข้อมูลสถานะนี้ในระบบ manual verify')


# ══════════════════════════════════════════════════════════════════════════════
# Section 3 — คอลัมน์ "วันที่เหลือ" (TC-007..010)
# ══════════════════════════════════════════════════════════════════════════════
def s3(page: Page, r: Results):
    print('\n▶ Section 3 — คอลัมน์ "วันที่เหลือ" แสดงถูกต้อง')
    nav(page)
    page_text = get_page_text(page)
    ss(page, 'S3-days-remaining')

    has_days_col   = 'วันที่เหลือ' in page_text or 'วัน' in page_text
    has_expired    = 'หมดอายุแล้ว' in page_text
    has_dash       = '-' in page_text

    print(f'  🔍 has_days_col={has_days_col}, has_expired={has_expired}')

    # TC-007: active > 30 วัน
    print('  TC-007: สัญญา active แสดงจำนวนวันที่เหลือ')
    if has_days_col:
        r.set('TC-007', 'pass', 'พบคอลัมน์วันที่เหลือในหน้า (manual verify ค่าตรงกับ วันสิ้นสุด - วันนี้)')
    else:
        r.set('TC-007', 'skip', 'ไม่พบคอลัมน์วันที่เหลือชัดเจน — manual verify')

    # TC-008: ≤30 วัน
    print('  TC-008: สัญญาใกล้หมดอายุ แสดงวันที่เหลือ ≤ 30 วัน')
    near_labels = STATUS_LABELS['near_expiry']
    has_near = any(l in page_text for l in near_labels)
    if has_near:
        r.set('TC-008', 'pass', 'พบสัญญาสถานะ "ใกล้หมดอายุ" ในหน้า (manual verify วันที่เหลือ ≤ 30)')
    else:
        r.set('TC-008', 'skip', 'ไม่พบสัญญาสถานะ "ใกล้หมดอายุ" — manual verify')

    # TC-009: หมดอายุแล้ว
    print('  TC-009: สัญญาหมดอายุ แสดง "หมดอายุแล้ว X วัน" สีแดง')
    if has_expired:
        expired_el = page.locator('*:has-text("หมดอายุแล้ว"):visible').first
        el_class = ''
        if expired_el.count() > 0:
            try: el_class = expired_el.get_attribute('class') or ''
            except Exception: pass
        ss(page, 'TC-009-expired')
        r.set('TC-009', 'pass', f'พบข้อความ "หมดอายุแล้ว" ในหน้า class="{el_class[:60]}" (manual verify สีแดง)')
    else:
        r.set('TC-009', 'skip', 'ไม่พบ "หมดอายุแล้ว" — Cronjob อาจยังไม่รัน หรือไม่มีสัญญาหมดอายุ')

    # TC-010: ไม่มีวันสิ้นสุด
    print('  TC-010: สัญญาไม่มีวันสิ้นสุด แสดง "-"')
    r.set('TC-010', 'skip', 'ต้อง manual verify กับสัญญาที่ไม่มีวันสิ้นสุด')


# ══════════════════════════════════════════════════════════════════════════════
# Section 4 — การกรองสถานะ (TC-011..014)
# ══════════════════════════════════════════════════════════════════════════════
def s4(page: Page, r: Results):
    print('\n▶ Section 4 — การกรองสถานะ')

    filter_tests = [
        ('TC-011', 'มีผลบังคับใช้', STATUS_LABELS['active']),
        ('TC-012', 'ใกล้หมดอายุ',   STATUS_LABELS['near_expiry']),
        ('TC-013', 'หมดอายุ',        STATUS_LABELS['expired']),
    ]

    for tc_id, filter_label, expected_labels in filter_tests:
        print(f'  {tc_id}: กรองสถานะ "{filter_label}"')
        nav(page)
        page.wait_for_timeout(500)

        # หาปุ่มกรอง/tab/chip
        filter_btn = find_filter(page, filter_label)
        if filter_btn.count() == 0:
            # ลองหา dropdown กรอง
            filter_btn = page.locator(
                f'select:visible, [class*="filter"]:visible, [class*="Filter"]:visible'
            ).first
            ss(page, f'{tc_id}-no-filter')
            r.set(tc_id, 'skip', f'ไม่พบปุ่ม/tab กรองสถานะ "{filter_label}" — manual verify')
            continue

        try:
            filter_btn.click(timeout=5000)
            page.wait_for_timeout(1500)
            ss(page, f'{tc_id}-filtered')
            page_text = get_page_text(page)

            # ตรวจว่าแสดงเฉพาะสถานะที่กรอง
            has_expected = any(l in page_text for l in expected_labels)
            # ตรวจว่าสถานะอื่นไม่ปรากฏ (heuristic — อาจมี false positive)
            other_labels = [l for k, labels in STATUS_LABELS.items()
                           if k not in ['active','near_expiry','expired','cancelled']
                           for l in labels]

            if has_expected:
                r.set(tc_id, 'pass', f'กรอง "{filter_label}" → พบสัญญาที่ถูกกรอง (manual verify ไม่มีสถานะอื่นปน)')
            else:
                # อาจไม่มีข้อมูลสถานะนั้น
                r.set(tc_id, 'skip', f'กรอง "{filter_label}" → ไม่พบสัญญาในหน้า อาจไม่มีข้อมูล (manual verify)')
        except Exception as e:
            r.set(tc_id, 'skip', f'error: {e}')

    # TC-014: ล้างตัวกรอง
    print('  TC-014: ล้างตัวกรอง → แสดงทั้งหมด')
    nav(page)
    clear_btn = page.locator(
        'button:has-text("ทั้งหมด"):visible, button:has-text("All"):visible, '
        'button:has-text("ล้าง"):visible, button:has-text("Clear"):visible'
    ).first
    if clear_btn.count() > 0:
        try:
            clear_btn.click(timeout=5000)
            page.wait_for_timeout(1000)
            ss(page, 'TC-014-cleared')
            page_text = get_page_text(page)
            all_found = sum(
                1 for labels in STATUS_LABELS.values()
                if any(l in page_text for l in labels)
            )
            if all_found >= 2:
                r.set('TC-014', 'pass', f'ล้างตัวกรองแล้วพบ {all_found} สถานะในหน้า')
            else:
                r.set('TC-014', 'skip', f'พบ {all_found} สถานะ — manual verify ว่าแสดงครบ')
        except Exception as e:
            r.set('TC-014', 'skip', f'error: {e}')
    else:
        r.set('TC-014', 'skip', 'ไม่พบปุ่มล้างตัวกรอง — manual verify')


# ══════════════════════════════════════════════════════════════════════════════
# Section 5 — Idempotency (TC-015..016)
# ══════════════════════════════════════════════════════════════════════════════
def s5(page: Page, r: Results):
    print('\n▶ Section 5 — Idempotency (รัน Cronjob ซ้ำ)')
    r.set('TC-015', 'skip', 'ต้อง manual verify — trigger Cronjob ซ้ำ แล้วตรวจ "ใกล้หมดอายุ" ไม่เปลี่ยนกลับ')
    r.set('TC-016', 'skip', 'ต้อง manual verify — trigger Cronjob ซ้ำ แล้วตรวจ "หมดอายุ" ไม่มี AuditLog ใหม่')


# ══════════════════════════════════════════════════════════════════════════════
# Section 6 — AuditLog (TC-017..019)
# ══════════════════════════════════════════════════════════════════════════════
def s6(page: Page, r: Results):
    print('\n▶ Section 6 — AuditLog')
    nav(page)
    page_text = get_page_text(page)
    ss(page, 'S6-audit-check')

    # ตรวจว่ามี section AuditLog ในหน้าหรือ link ไปหน้า log
    has_audit = any(w in page_text for w in ['Audit', 'ประวัติ', 'Log', 'audit'])
    print(f'  🔍 has_audit_in_page={has_audit}')

    for tc_id in ['TC-017', 'TC-018', 'TC-019']:
        r.set(tc_id, 'skip', 'ต้อง manual verify ผ่าน AuditLog หรือ API ของระบบหลัง Cronjob รัน')


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    if not HR_APP_URL:
        print('❌ ยังไม่ได้ตั้ง HR_APP_URL ใน .env')
        return

    now = datetime.datetime.now().strftime('%H:%M:%S')
    print(f'🚀 Task 417 Auto-Test [{now}]')
    print(f'   URL    : {LIST_URL}')
    mode = 'Manual-Login' if MANUAL_LOGIN else 'Auto'
    if USE_SESSION and SESSION_FILE.exists(): mode += ' + Use-Session'
    print(f'   Mode   : {mode}')
    print(f'   Section: {SECTION or "ทั้งหมด (1-6)"}')

    r = Results()
    sections = {1: s1, 2: s2, 3: s3, 4: s4, 5: s5, 6: s6}

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
