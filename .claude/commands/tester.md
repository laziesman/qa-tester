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
อ่านจาก `.env` อัตโนมัติ:
- `HR_APP_URL` — URL ของ app ที่ทดสอบ
- `HR_USERNAME` / `HR_PASSWORD` — login credentials
- ถ้า session หมด → login ใหม่เองจาก credentials ใน `.env` ห้ามถาม PM

## ขั้นตอน

### 1. เตรียม browser
เปิด 2 tabs ควบคู่กัน:
- **Tab 1** — App ที่ทดสอบ (hr-stg)
- **Tab 2** — QA page (standalone URL) สำหรับบันทึกผล
  ```
  https://qa-tester-f005d.web.app/index.html?p={projectId}&s={sprintId}&standalone=1#task={taskId}
  ```
  login ด้วย `admin@qa-tester.test / Admin@1234` ถ้ายังไม่ได้ login

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
1. **Zoom เข้า element ที่มีปัญหาก่อน** แล้วถ่ายรูป → บันทึกไว้ที่ `screenshots/task-{NUMBER}-TC{ID}-fail-{desc}.png`
2. สลับไป Tab 2 → กด **Fail**
3. **บันทึก Actual result + รูป ด้วย 3 ขั้นตอนนี้เสมอ:**

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
     data['TC-{ID}'].note = 'ข้อความ Actual result<br><img src="{IMGBB_URL}">';
     localStorage.setItem('qa_task_{NUMBER}', JSON.stringify(data));
   })()
   ```

   **ขั้น C — Reload หน้า:**
   ```javascript
   location.reload()
   ```
   → Actual result จะแสดงข้อความ + รูปทันที

   > ⚠️ ห้ามใช้ `innerHTML =` หรือ `appendChild` + `dispatchEvent` กับ contenteditable โดยตรง — ไม่ save ครับ ใช้ localStorage write เท่านั้น

#### ถ้า SKIP
- ระบุเหตุผลใน Actual result ก่อนกด Skip

### 3. กฎการใช้ agent-browser
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
