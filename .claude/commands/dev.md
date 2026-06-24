# Dev — สร้าง HTML + Deploy

## หน้าที่
รับ TC JSON จาก TC Writer → สร้าง task HTML → update tasks.json → deploy ขึ้นเว็บ → ส่งต่อให้ Tester

## Input
รับ TC JSON จาก TC Writer:
```json
{
  "task": "457",
  "title": "4.1.7.4 API employee-shift-assignments",
  "project": "HR",
  "sprint": "Sprint 6",
  "sections": [...]
}
```

## ขั้นตอน

### 1. เตรียม folder
- ตรวจว่ามี `{PROJECT}/Sprint-{N}/` อยู่แล้วไหม
- ถ้าไม่มี → สร้างใหม่อัตโนมัติ

### 2. สร้าง task HTML
- อ่าน `task-template.html` เป็น base
- แทนค่า placeholders ทุกตัว:

| Placeholder | ค่า |
|---|---|
| `{{TASK_NUMBER}}` | task number (เช่น `457`) |
| `{{TASK_NAME}}` | title จาก JSON |
| `{{PROJECT}}` | project (เช่น `HR`) |
| `{{SPRINT}}` | sprint (เช่น `Sprint 6`) |
| `{{BACK_PATH}}` | `../../index.html` |
| `{{STORAGE_KEY}}` | `qa_task_{NUMBER}` |
| `{{TEST_CASES_JS}}` | แปลง sections JSON → JS SECTIONS array |

- แปลง JSON sections → JS format:
```javascript
const SECTIONS = [
  {
    name: "ส่วนที่ 1 — {ชื่อ section}",
    tcs: [
      {
        id: "TC-001",
        name: "...",
        precondition: "...",
        steps: "1. ...\n2. ...",
        expected: "..."
      }
    ]
  }
]
```

- บันทึกไฟล์เป็น `{PROJECT}/Sprint-{N}/task-{NUMBER}.html`

### 3. อัปเดต tasks.json
เพิ่ม task entry ใน `tasks.json` (ไม่ต้องแตะ index.html):
```json
{ "id": "{NUMBER}", "title": "{TITLE}", "file": "{PROJECT}/Sprint-{N}/task-{NUMBER}.html", "storageKey": "qa_task_{NUMBER}" }
```
- ถ้ายังไม่มี project → เพิ่ม project + sprint + task
- ถ้ายังไม่มี sprint → เพิ่ม sprint + task
- ถ้ามี task อยู่แล้ว → update

### 4. Deploy
```bash
# Git push — ต้องใช้ PowerShell (credentials อยู่ใน Windows)
git add {PROJECT}/Sprint-{N}/task-{NUMBER}.html tasks.json
git commit -m "Add task-{NUMBER}: {TASK_NAME}"
powershell.exe -Command "cd 'G:\My Drive\work\Claude\Tester\qa-tester'; git push"

# Firebase deploy
powershell.exe -Command "cd 'G:\My Drive\work\Claude\Tester\qa-tester'; firebase deploy --only hosting"
```

### 5. Output
แจ้งผลและส่งต่อให้ Tester:
```
✅ task-{NUMBER} ออนไลน์แล้ว — https://qa-tester-f005d.web.app
📄 file: {PROJECT}/Sprint-{N}/task-{NUMBER}.html
🔢 TC ทั้งหมด: {จำนวน} TC
```

## กฎ
- ห้ามแก้ `task-template.html` โดยตรง — อ่านอย่างเดียว
- ห้ามแก้ `index.html` เลย — ไม่มีความจำเป็นอีกแล้ว
- แก้เฉพาะ `tasks.json` เมื่อเพิ่ม task ใหม่
- ห้ามแก้ `lib/*.js` หรือ CSS
- git push ต้องใช้ PowerShell เสมอ — ไม่ใช่ WSL bash
