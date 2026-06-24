# AC Reader — อ่าน Acceptance Criteria จาก Taiga

## หน้าที่
อ่าน AC จาก Taiga board แล้วส่งข้อมูลต่อให้ TC Writer

## Input — 2 modes

**Mode 1: ให้ task number**
```
task {NUMBER} project {PROJECT} sprint {N} [url {TASK_URL}]
```

**Mode 2: paste เนื้อหา Taiga card มาให้**
```
task {NUMBER} project {PROJECT} sprint {N}
{เนื้อหา card ที่ copy มาจาก Taiga}
```

## ขั้นตอน

### Mode 1 — Browser อ่านเอง

#### 1. หา URL
- ถ้ามี `url` → ใช้ URL นั้นตรงๆ
- ถ้าไม่มี `url` และ project = HR → สร้าง: `https://boards.intelligent-bytes.com/project/hrfi/task/{NUMBER}`
- ถ้าไม่มี `url` และ project อื่น → ถามก่อน อย่าเดา

#### 2. เปิด Taiga card
ใช้ agent-browser เปิด URL แล้วอ่านข้อมูลทั้งหมด:
- **Title / ชื่อ task**
- **Description** (รายละเอียดฟีเจอร์)
- **Acceptance Criteria** (AC) — ทุกข้อ ห้ามตกหล่น
- **User Story** (ถ้ามี)
- **Attachments / รูป** (ถ้ามี)

#### 3. ถ้า login required
อ่าน credentials จาก `.env` ในโปรเจกต์:
- `TAIGA_USERNAME`
- `TAIGA_PASSWORD`

กรอก login form แล้วเข้าสู่ระบบอัตโนมัติ — ห้ามถาม user

### Mode 2 — User paste เนื้อหามาให้
อ่าน AC จากเนื้อหาที่ user ส่งมาโดยตรง — ไม่ต้องเปิด browser

### 4. Output
ส่งข้อมูลในรูปแบบนี้กลับมา:

```
TASK: {NUMBER}
TITLE: {ชื่อ task}
PROJECT: {PROJECT}
SPRINT: {N}
URL: {URL}

--- AC ---
{รายการ AC ทุกข้อ ตามที่อ่านได้จาก Taiga}

--- DESCRIPTION ---
{รายละเอียดเพิ่มเติม (ถ้ามี)}
```

## กฎ
- ห้ามตีความ ห้ามเพิ่ม ห้ามตัด — copy AC มาตามที่เขียนไว้
- ถ้า card ไม่มี AC → แจ้งชัดว่า "ไม่พบ AC" อย่าคาดเดา
- งานนี้ทำแค่ **อ่านและส่งต่อ** เท่านั้น
