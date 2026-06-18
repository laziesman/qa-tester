# Dev Mode — Tooling & Dashboard

> ใช้ไฟล์นี้เมื่อต้องการแก้ไข UI, template, หรือ infrastructure — ไม่ใช่สำหรับ QA workflow

## Files in Scope
| File | หน้าที่ |
|------|---------|
| `task-template.html` | Base template สำหรับทุก task file — แก้ได้ใน dev mode เท่านั้น |
| `index.html` | Dashboard หลัก — แก้ได้ทั้งไฟล์ใน dev mode |
| `lib/firebase-auth.js` | Firebase authentication |
| `lib/firebase-storage.js` | Firebase storage helpers |
| `lib/firebase-sync.js` | Firestore sync logic |
| `login.html` | Login page |

## Design System (Light Theme)

```
CSS variables (defined in :root):
  --bg:          #ffffff   card / input background
  --canvas:      #f7f8fa   page background
  --panel:       #fbfbfc   sidebar background
  --panel2:      #f1f3f7   hover / metric bg
  --line:        #ececf0   border subtle
  --line2:       #e2e4ea   border stronger
  --text:        #16181d   primary text
  --dim:         #5a606b   secondary text
  --faint:       #9499a3   muted / placeholder
  --accent:      #4f6ef7   blue accent
  --accent-soft: #eef2ff   accent background

  --pass:      #22c55e   --pass-soft:  #dcfce7
  --fail:      #ef5350   --fail-soft:  #fee2e2
  --skip:      #eab308   --skip-soft:  #fef9c3
  --pending:   #cbd5e1

Fonts:
  body:    'Sarabun' (Thai), system-ui
  numbers: 'Space Grotesk'
  mono:    'IBM Plex Mono'

Border-radius: 11-16px cards, 8-9px inputs/buttons
```

## task-template.html — Placeholders

เมื่อแก้ template ต้องให้ placeholders เหล่านี้ยังทำงานได้:
- `{{TASK_NUMBER}}`, `{{TASK_NAME}}`, `{{PROJECT}}`, `{{SPRINT}}`
- `{{BACK_PATH}}`, `{{STORAGE_KEY}}`, `{{TEST_CASES_JS}}`

Section "Test Cases เพิ่มเติม (นอกเหนือ AC)" ต้องอยู่ท้ายสุดเสมอ (prefix `EX-001`, `EX-002`...)

## Firebase Config

Firebase JS SDK loaded from CDN (firebase-compat 9.23.0) ใน `index.html` และ `login.html`
Local scripts อยู่ใน `lib/` — path ใน index.html: `lib/firebase-sync.js`, `lib/firebase-auth.js`, `lib/firebase-storage.js`

## Deployment

```
scripts/deploy.ps1    ← PowerShell deploy script
scripts/Procfile      ← Process definition
firebase.json         ← Firebase Hosting config
.firebaserc           ← Firebase project alias
```
