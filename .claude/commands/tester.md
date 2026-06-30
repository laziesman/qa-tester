# Tester — รัน Test Cases บน Browser

## หน้าที่
รับ TC จาก Dev → เปิด browser → รัน test ทีละข้อ → บันทึก Pass/Fail/Skip → ส่งผลให้ Reporter

## Input
รับจาก Dev:
- URL ของ QA page (standalone mode): `https://qa-tester-f005d.web.app/index.html?p={projectId}&s={sprintId}&standalone=1#task={taskId}`
  - ตัวอย่าง: `https://qa-tester-f005d.web.app/index.html?p=hrfi&s=s6&standalone=1#task=455`
  - `p`, `s`, `task` id มาจาก `tasks.json`
- TC ทั้งหมดจาก JSON (รู้ว่าต้องทดสอบอะไรบ้าง)

## Credentials
อ่านจาก `apps.json` key `hrfi` อัตโนมัติ — ห้ามถาม PM

## ขั้นตอน

### 1. เตรียม browser

**ลอง load session ที่บันทึกไว้ก่อนเสมอ:**
```
state_load /home/work/.agent-browser/sessions/hr-session
navigate → https://hr-stg.intelligent-bytes.com/dashboard
```
→ ถ้า URL ยังอยู่ที่ /dashboard (ไม่ redirect ไป /login) → logged in อยู่ → ข้ามไป Tab 2 เลย

- **ถ้า logged in** → เปิด Tab 2 เลย ไม่ต้อง OTP
- **ถ้า redirect ไป /login** → ทำ login flow ด้านล่าง

**Login flow (ทำเมื่อ session หมดเท่านั้น):**
```
1. navigate → https://hr-stg.intelligent-bytes.com/login
2. fill username: admin, password: Admin@1234
3. click เข้าสู่ระบบ → รอหน้า OTP โผล่ (อย่า navigate ออก)
4. รัน bash ทันที:
```
```bash
python3 scripts/get_otp.py
```
```
5. click box แรก (e14) → keyboard_type OTP 6 หลัก
6. snapshot ตรวจปุ่ม ยืนยัน enabled → click ยืนยัน
7. รอ redirect → /dashboard
8. บันทึก session:
```
```
state_save /home/work/.agent-browser/sessions/hr-session
```

> ⚠️ `get_otp.py` ต้องรัน **หลัง** submit login ทันที — OTP ใหม่สร้างตอน submit เท่านั้น
> ⚠️ ใช้ `keyboard_type` ไม่ใช่ `fill` — OTP boxes ต้องการ real key events ถึงจะ enable ปุ่ม ยืนยัน

เปิด Tab 2 — QA page:
```
https://qa-tester-f005d.web.app/index.html?p={projectId}&s={sprintId}&standalone=1#task={taskId}
```
login ด้วย `admin@qa-tester.test / Admin@1234`

### 2. รัน test ทีละ TC
สำหรับแต่ละ TC:

1. **อ่าน precondition** — ตรวจว่าเงื่อนไขครบก่อนเริ่ม
2. **ทำตาม steps** ทีละขั้น ไม่ข้าม
3. **snapshot ก่อนคลิกทุกครั้ง** — เพื่อได้ ref ที่ถูกต้อง
4. **ตรวจ expected result**

#### ถ้า PASS
- ถ่ายรูป screenshot เป็นหลักฐาน
- สลับไป Tab 2 → กด **Pass**

#### ถ้า FAIL
1. **Save snapshot ก่อนออกจาก step ที่ fail** — เพื่อให้ dev เขียน retest .py ได้:
   ```bash
   cp .playwright-cli/$(ls -t .playwright-cli/*.yml | head -1 | xargs basename) \
      screenshots/task-{NUMBER}-TC{ID}-fail-snapshot.yml
   ```
2. **Zoom เข้า element ที่มีปัญหาก่อน** แล้วถ่ายรูป → บันทึกไว้ที่ `screenshots/task-{NUMBER}-TC{ID}-fail-{desc}.png`
3. สลับไป Tab 2 → กด **Fail**
4. **บันทึก Actual result + รูป ด้วย 3 ขั้นตอนนี้เสมอ:**

   **ขั้น A — Upload รูปไป imgbb ผ่าน bash:**
   ```bash
   curl -s -X POST "https://api.imgbb.com/1/upload?key=808ea7c6f6cf54e96e94c85ef70a3ac7" \
     -F "image=@/path/to/screenshot.png" \
     | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['display_url'] if d.get('success') else d)"
   ```
   → ได้ URL เช่น `https://i.ibb.co/xxx/filename.png`

   **ขั้น B — เขียนข้อความ + URL ลง localStorage โดยตรง ผ่าน eval:**
   ```javascript
   (() => {
     const raw = localStorage.getItem('qa_task_{NUMBER}');
     const data = JSON.parse(raw);
     data['TC-{ID}'].note = '[Round 1] ข้อความ Actual result<br><img src="{IMGBB_URL}">';
     localStorage.setItem('qa_task_{NUMBER}', JSON.stringify(data));
   })()
   ```
   > ใส่ `[Round 1]` นำหน้า Actual result เสมอ — เพื่อให้ retest append ต่อได้ชัดเจน

   **ขั้น C — Reload หน้า:**
   ```javascript
   location.reload()
   ```
   → Actual result จะแสดงข้อความ + รูปทันที

   > ⚠️ ห้ามใช้ `innerHTML =` หรือ `appendChild` + `dispatchEvent` กับ contenteditable โดยตรง — ไม่ save ครับ ใช้ localStorage write เท่านั้น

   > **Retest (Round 2+):** ถ้า TC เป็น Fail อยู่แล้วและยัง Fail → แค่ append Actual result ใน localStorage แล้วจบ **ห้ามกดปุ่ม Fail ซ้ำ** — กดซ้ำจะ toggle เป็น Pending แทน

#### ถ้า SKIP
- ระบุเหตุผลใน Actual result ก่อนกด Skip

### 3. กฎการใช้ playwright-cli
- **snapshot ก่อนคลิกเสมอ** — ได้ ref ล่าสุดก่อน interact
- **scroll into view** ก่อนคลิก element ที่อาจอยู่นอกหน้าจอ
- **ถ่ายรูปก่อน FAIL เสมอ** — zoom เข้า element ที่มีปัญหาก่อน
- ถ้า element หาไม่เจอ → snapshot ใหม่ อย่า retry ด้วย ref เก่า
- ถ้า dialog/modal เปิด → snapshot ใหม่ก่อนคลิกปุ่มใน dialog

### 4. ถ้าติดปัญหาระหว่างทดสอบ
- **Session หมด** → login ใหม่จาก `.env` เอง
- **Element หาไม่เจอ** → snapshot ใหม่ แล้วลองอีกครั้ง
- **App crash / error ร้ายแรง** → บันทึก FAIL + แจ้ง PM ทันที หยุดรัน TC ถัดไป
- **TC นี้ block TC ถัดไป** → Skip TC ที่ขึ้นกับมัน พร้อมระบุเหตุผล

### 5. ส่ง Bug Report ไป Taiga
หลังรันครบทุก TC — ยังอยู่ใน Tab 2 (QA page):
1. กด **"สรุป Bug Report"** → ตรวจ Fail list ครบถ้วน
2. กด **"📤 ส่งไป Taiga"** → ระบบส่ง comment เข้า Taiga
3. [ถ้า CORS block] → ไฟล์ `bug-report-{NUMBER}.json` จะถูก download อัตโนมัติ → รัน:
   ```bash
   python scripts/send_to_taiga.py bug-report-{NUMBER}.json
   ```
4. Confirm: "✅ ส่ง X bugs ไปที่ task #{NUMBER} แล้วครับ"

### 6. Output summary
```
TASK: {NUMBER}
✅ Pass: {จำนวน} — TC-001, TC-002, ...
❌ Fail: {จำนวน} — TC-006, TC-007, ...
⏭ Skip: {จำนวน} — TC-008 (เหตุผล), ...
```

## กฎ
- รัน TC ตามลำดับเสมอ ห้ามข้าม (ยกเว้น Skip ด้วยเหตุผล)
- ทุก FAIL ต้องมี screenshot + Actual result ก่อนเสมอ
- ห้ามเดาผล — ต้องทดสอบจริงทุกข้อ
- ห้ามแก้โค้ด app หรือ QA page — ทำแค่ทดสอบและบันทึก
