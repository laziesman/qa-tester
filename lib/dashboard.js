const BOARD_HOST = 'https://boards.intelligent-bytes.com/project/'
const PROXY_URL  = 'https://web-production-3a704.up.railway.app'

function boardUrl(taskId, taskObj) {
  if (taskObj && taskObj.url) return taskObj.url
  const p = project()
  return BOARD_HOST + (p.boardSlug || p.id) + '/task/' + taskId
}

// ── Projects (our file-based structure) ──
let PROJECTS = []


// ── Helpers ──
function project() { return PROJECTS.find(p => p.id === curProject) }
function sprint()  { return project().sprints.find(s => s.id === curSprint) }
function task(tid) { return sprint().tasks.find(t => t.id === tid) }

function getTaskData(key)      { try { return JSON.parse(localStorage.getItem(key) || '{}') } catch(e) { return {} } }
function setTaskData(key, data) {
  const val = JSON.stringify(data)
  try {
    localStorage.setItem(key, val)
  } catch(e) {
    if (e.name !== 'QuotaExceededError') { showToast('❌ บันทึกไม่ได้: ' + e.message); return }
    // Auto-cleanup: strip base64 images from all tasks to free space, then retry
    let freed = 0
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (!k || !k.startsWith('qa_task_')) continue
      try {
        const d = JSON.parse(localStorage.getItem(k) || '{}')
        let changed = false
        Object.values(d).forEach(tc => {
          if (tc && tc.note && tc.note.includes('data:image')) {
            freed += tc.note.length
            tc.note = tc.note.replace(/src="data:[^"]+"/g, 'src=""')
            freed -= tc.note.length
            changed = true
          }
        })
        if (changed) localStorage.setItem(k, JSON.stringify(d))
      } catch(e2) {}
    }
    try {
      localStorage.setItem(key, val)
      if (freed > 0) showToast(`⚠ ล้างรูปเก่า ${Math.round(freed/1024)}KB เพื่อเพิ่มพื้นที่`)
    } catch(e3) {
      showToast('❌ พื้นที่เต็ม ไม่สามารถบันทึกได้')
      console.error('[save]', e3)
    }
  }
}

function getProgress(key) {
  const d = getTaskData(key)
  let pass=0, fail=0, skip=0, retest=0
  Object.values(d).forEach(v => { if(v.status==='pass') pass++; else if(v.status==='fail') fail++; else if(v.status==='skip') skip++; else if(v.status==='retest') retest++ })
  const total = Object.keys(d).length
  return { pass, fail, skip, retest, n: total-pass-fail-skip-retest, total }
}

function sprintTally() {
  const acc = {pass:0,fail:0,skip:0,n:0,total:0}
  sprint().tasks.forEach(t => { const c=getProgress(t.storageKey); acc.pass+=c.pass; acc.fail+=c.fail; acc.skip+=c.skip; acc.n+=c.n; acc.total+=c.total })
  return acc
}

function barHTML(c) {
  if (!c.total) return ''
  const seg = (v,col) => v>0 ? `<span style="width:${v/c.total*100}%;background:${col}"></span>` : ''
  return seg(c.pass,'var(--pass)') + seg(c.fail,'var(--fail)') + seg(c.retest,'#f59e0b') + seg(c.skip,'var(--skip)') + seg(c.n,'var(--pending)')
}

function allTcIds() {
  return currentSections.flatMap(s => s.tcs.map(tc => tc.id))
}


async function loadSections(t) {
  function withExtra(sections) {
    try {
      const extra = JSON.parse(localStorage.getItem(t.storageKey + '_tcs') || '[]')
      if (extra.length) return [...sections, { name: 'Test Cases เพิ่มเติม (นอกเหนือ AC)', tcs: extra }]
    } catch(e) {}
    return sections
  }


  // fetch task file and parse SECTIONS (bracket-counting to handle nested arrays)
  try {
    const res = await fetch(t.file)
    const html = await res.text()
    const declIdx = html.search(/const SECTIONS\s*=\s*\[/)
    if (declIdx !== -1) {
      // Extract simple string const declarations before SECTIONS (e.g. UI_URL, TASK_URL)
      // so template literals like `${UI_URL}` inside SECTIONS resolve correctly
      const before = html.slice(0, declIdx)
      const varLines = []
      const varRe = /const\s+(\w+)\s*=\s*('[^']*'|"[^"]*")/g
      let vm
      while ((vm = varRe.exec(before)) !== null) varLines.push(`const ${vm[1]} = ${vm[2]}`)

      const arrStart = html.indexOf('[', declIdx)
      let depth = 0, i = arrStart
      while (i < html.length) {
        if (html[i] === '[') depth++
        else if (html[i] === ']') { depth--; if (depth === 0) break }
        i++
      }
      const arrStr = html.slice(arrStart, i + 1)
      const sections = new Function(varLines.join('\n') + '\nreturn ' + arrStr)()
      return withExtra(sections)
    }
  } catch(e) {}

  // dynamic task: TCs stored in localStorage
  try {
    const tcs = JSON.parse(localStorage.getItem(t.storageKey + '_tcs') || '[]')
    if (tcs.length) return [{ name: '', tcs }]
  } catch(e) {}
  return []
}

// ── State ──
let curProject = ''
let curSprint  = ''
let currentView = 'home', activeTask = null
let currentSections = []
let tcFilter = 'all', allOpen = false

// ── Navigation ──
function go(view, tid) {
  currentView = view
  const ovEl   = document.getElementById('view-overview')
  const dashEl = document.getElementById('view-dash')
  const tcEl   = document.getElementById('view-tc')
  const homBtn = document.getElementById('home-btn')

  if (view === 'home') {
    ovEl.classList.remove('hide')
    dashEl.classList.add('hide')
    tcEl.classList.add('hide')
    homBtn.classList.add('on')
    activeTask = null; currentSections = []
    renderOverview()
  } else if (view === 'dash') {
    ovEl.classList.add('hide')
    dashEl.classList.remove('hide')
    tcEl.classList.add('hide')
    homBtn.classList.remove('on')
    activeTask = null; currentSections = []
    renderDash()
  } else {
    ovEl.classList.add('hide')
    dashEl.classList.add('hide')
    tcEl.classList.remove('hide')
    homBtn.classList.remove('on')
    renderTask(tid)
  }
  document.getElementById('main').scrollTop = 0
  renderSidebar()
}

// ── Selectors ──
function renderSelectors() {
  document.getElementById('sel-project').innerHTML = PROJECTS.map(p => `<option value="${p.id}" ${p.id===curProject?'selected':''}>${p.name}</option>`).join('')
  document.getElementById('sel-sprint').innerHTML = project().sprints.map(s => `<option value="${s.id}" ${s.id===curSprint?'selected':''}>${s.name}</option>`).join('')
}
function onProjectChange() { curProject=document.getElementById('sel-project').value; curSprint=project().sprints[0].id; renderSelectors(); go('dash') }
function onSprintChange()  { curSprint=document.getElementById('sel-sprint').value; go('dash') }

// ── Sidebar ──
function goToTask(pid, sid, tid) {
  curProject = pid; curSprint = sid
  document.getElementById('search').value = ''
  renderSelectors(); go('task', tid)
}

function renderSidebar() {
  const q = document.getElementById('search').value.toLowerCase().trim()

  if (q) {
    // Global search across all projects/sprints
    const results = []
    PROJECTS.forEach(proj => proj.sprints.forEach(spr => spr.tasks.forEach(t => {
      if ((`#${t.id} ${t.title}`).toLowerCase().includes(q))
        results.push({ proj, spr, t })
    })))
    document.getElementById('sb-sprintlabel').textContent = 'ผลการค้นหา'
    document.getElementById('sb-count').textContent = results.length
    document.getElementById('sb-list').innerHTML = results.length ? results.map(({ proj, spr, t }) => {
      const p = getProgress(t.storageKey)
      const sel = currentView==='task' && activeTask===t.id && curProject===proj.id && curSprint===spr.id
      let badge = p.fail>0
        ? `<span class="sb-badge fail">${p.fail} Fail</span>`
        : p.total>0 ? `<span class="sb-badge pass">${p.pass===p.total?'Done':p.pass+'/'+p.total}</span>`
        : `<span class="sb-badge empty">—</span>`
      return `<div class="sb-item" style="flex-direction:column;align-items:stretch;gap:2px" onclick="goToTask('${proj.id}','${spr.id}','${t.id}')">
        <div style="display:flex;align-items:center;gap:6px">
          <span class="sid" style="flex:1">#${t.id}</span>
          ${badge}
          <a class="sb-open" href="index.html?p=${proj.id}&s=${spr.id}&standalone=1#task=${t.id}" target="_blank" rel="noopener" title="เปิด Testcase" onclick="event.stopPropagation()">↗</a>
        </div>
        <div class="sb-title">${t.title}</div>
        <div class="sb-item-meta">${proj.name} › ${spr.name}</div>
      </div>`
    }).join('') : '<div style="padding:12px 8px;font-size:13px;color:var(--faint)">ไม่พบ task ที่ตรงกัน</div>'
    return
  }

  // Normal mode — current sprint only
  document.getElementById('sb-sprintlabel').textContent = sprint().name.toUpperCase() + ' · TASKS'
  const filtered = sprint().tasks
  document.getElementById('sb-count').textContent = filtered.length
  document.getElementById('sb-list').innerHTML = filtered.map(t => {
    const p = getProgress(t.storageKey)
    const sel = currentView==='task' && activeTask===t.id
    let badge = p.fail>0
      ? `<span class="sb-badge fail">${p.fail} Fail</span>`
      : p.total>0 ? `<span class="sb-badge pass">${p.pass===p.total?'Done':p.pass+'/'+p.total}</span>`
      : `<span class="sb-badge empty">—</span>`
    return `<div class="sb-item ${sel?'sel':''}" onclick="go('task','${t.id}')">
      <span class="sid" style="flex:1">#${t.id}</span>
      ${badge}
      <a class="sb-open" href="index.html?p=${curProject}&s=${curSprint}&standalone=1#task=${t.id}" target="_blank" rel="noopener" title="เปิด Testcase" onclick="event.stopPropagation()">↗</a>
    </div>`
  }).join('')
}

// ── Overview ──
function renderOverview() {
  const tot = { pass:0, fail:0, skip:0, n:0, total:0, tasks:0 }
  PROJECTS.forEach(p => p.sprints.forEach(s => s.tasks.forEach(t => {
    const c = getProgress(t.storageKey)
    tot.pass+=c.pass; tot.fail+=c.fail; tot.skip+=c.skip; tot.n+=c.n; tot.total+=c.total
    tot.tasks++
  })))

  const rate = tot.total ? Math.round(tot.pass/tot.total*100) : null
  const rv = document.getElementById('ov-rate')
  rv.textContent = rate !== null ? rate+'%' : '—'
  rv.style.color = rate===null?'var(--text)':rate>=80?'var(--pass)':tot.fail>0?'#d97706':'var(--text)'
  document.getElementById('ov-bar').innerHTML = barHTML(tot)
  document.getElementById('ov-legend').innerHTML = [['pass','Pass'],['fail','Fail'],['skip','Skip'],['n','Pending']].map(([k,l]) => {
    const col = {pass:'var(--pass)',fail:'var(--fail)',skip:'var(--skip)',n:'var(--pending)'}[k]
    return `<div class="lg"><span class="d" style="background:${col}"></span><span class="n num">${tot[k]}</span><span class="t">${l}</span></div>`
  }).join('')
  document.getElementById('ov-total').textContent = tot.total
  document.getElementById('ov-fail').textContent = tot.fail
  document.getElementById('ov-fail').style.color = tot.fail>0?'var(--fail)':'var(--faint)'
  document.getElementById('ov-tasks').textContent = tot.tasks
  document.getElementById('ov-projs').textContent = PROJECTS.length
  document.getElementById('ov-sub').textContent = PROJECTS.length+' projects · '+tot.tasks+' tasks'

  document.getElementById('ov-projects').innerHTML = PROJECTS.map(proj => {
    const projTot = { pass:0, fail:0, skip:0, n:0, total:0 }
    proj.sprints.forEach(s => s.tasks.forEach(t => {
      const c = getProgress(t.storageKey)
      projTot.pass+=c.pass; projTot.fail+=c.fail; projTot.skip+=c.skip; projTot.n+=c.n; projTot.total+=c.total
    }))
    const totalTasks = proj.sprints.reduce((a,s) => a+s.tasks.length, 0)
    const projRate = projTot.total ? Math.round(projTot.pass/projTot.total*100) : null

    const projBadge = projTot.fail>0
      ? `<span class="sb-badge fail">${projTot.fail} Fail</span>`
      : projRate!==null ? `<span class="sb-badge pass">${projRate}%</span>` : ''

    const sprintsHtml = proj.sprints.map(spr => {
      const sprTot = { pass:0, fail:0, skip:0, n:0, total:0 }
      spr.tasks.forEach(t => {
        const c = getProgress(t.storageKey)
        sprTot.pass+=c.pass; sprTot.fail+=c.fail; sprTot.skip+=c.skip; sprTot.n+=c.n; sprTot.total+=c.total
      })
      const sprRate = sprTot.total ? Math.round(sprTot.pass/sprTot.total*100) : null
      const rateCol = sprTot.fail>0?'var(--fail)':sprRate>=80?'var(--pass)':'var(--text)'

      const chips = spr.tasks.map(t => {
        const tc = getProgress(t.storageKey)
        let cls = ''
        if (tc.total===0)          cls = ''
        else if (tc.fail>0)        cls = 'chip-fail'
        else if (tc.pass===tc.total) cls = 'chip-pass'
        else if (tc.n>0)           cls = 'chip-wip'
        else if (tc.skip>0)        cls = 'chip-skip'
        return `<span class="ov-chip ${cls}" onclick="goToTask('${proj.id}','${spr.id}','${t.id}');event.stopPropagation()" title="${t.title}">#${t.id}</span>`
      }).join('')

      return `<div class="ov-sprint-row" onclick="curProject='${proj.id}';curSprint='${spr.id}';renderSelectors();go('dash')">
        <div class="ov-sprint-name">${spr.name}</div>
        <div class="ov-sprint-barwrap">
          <div class="bar" style="height:7px">${barHTML(sprTot)||'<span style="width:100%;background:var(--line2)"></span>'}</div>
          <div class="ov-sprint-mini">
            <span class="ov-mini-stat"><span class="dot" style="background:var(--pass)"></span>${sprTot.pass} pass</span>
            <span class="ov-mini-stat"><span class="dot" style="background:var(--fail)"></span>${sprTot.fail} fail</span>
            <span class="ov-mini-stat"><span class="dot" style="background:var(--pending)"></span>${sprTot.n} pending</span>
            <span class="ov-mini-stat" style="color:var(--faint)">${spr.tasks.length} tasks</span>
          </div>
        </div>
        <div class="ov-sprint-rate" style="color:${rateCol}">${sprRate!==null?sprRate+'%':'—'}</div>
        <button class="ov-sprint-btn">ดู Sprint →</button>
      </div>`
    }).join('')

    return `<div class="ov-proj-card">
      <div class="ov-proj-hd" onclick="toggleOvProject(this)">
        <div class="ov-proj-name">${proj.name}</div>
        <div class="ov-proj-meta">${proj.sprints.length} sprint${proj.sprints.length>1?'s':''} · ${totalTasks} tasks · ${projTot.total} TC</div>
        ${projBadge}
        <div class="ov-expand-btn">▸</div>
      </div>
      <div class="ov-sprints">${sprintsHtml}</div>
    </div>`
  }).join('')

  renderSidebar()
}

function toggleOvProject(hd) {
  const body = hd.nextElementSibling
  const btn  = hd.querySelector('.ov-expand-btn')
  const open = body.classList.toggle('open')
  btn.textContent = open ? '▾' : '▸'
  btn.style.color = open ? 'var(--accent)' : ''
}

// ── Dashboard (Sprint-level) ──
function renderDash() {
  const c = sprintTally()
  const rate = c.total ? Math.round(c.pass/c.total*100) : 0
  document.getElementById('dash-crumb').innerHTML = `<b>${project().name}</b><span class="sep">›</span><b>${sprint().name}</b>`
  document.getElementById('d-eyebrow').textContent = project().name.toUpperCase()
  document.getElementById('d-sprintname').textContent = sprint().name
  document.getElementById('d-tasks').textContent = sprint().tasks.length
  document.getElementById('d-total').textContent = c.total
  const rv = document.getElementById('d-rate')
  rv.innerHTML = rate+'<span style="font-size:.42em;color:var(--faint)">%</span>'
  rv.style.color = rate>=80?'var(--pass)':(c.fail>0?'#d97706':'var(--text)')
  document.getElementById('d-bar').innerHTML = barHTML(c)
  document.getElementById('d-legend').innerHTML =
    [['pass','Pass'],['fail','Fail'],['skip','Skip'],['n','Pending']].map(([k,l]) => {
      const col = {pass:'var(--pass)',fail:'var(--fail)',skip:'var(--skip)',n:'var(--pending)'}[k]
      return `<div class="lg"><span class="d" style="background:${col}"></span><span class="n num">${c[k]}</span><span class="t">${l}</span></div>`
    }).join('')
  const failTasks = sprint().tasks.filter(t=>getProgress(t.storageKey).fail>0).length
  document.getElementById('d-metrics').innerHTML =
    [['Pass rate',rate+'%'],['Test cases',c.total],['Tasks with fail',failTasks+'/'+sprint().tasks.length],['Pending',c.n]]
    .map(([l,v]) => `<div class="metric"><div class="ml">${l}</div><div class="mv num">${v}</div></div>`).join('')
  document.getElementById('d-taskcount').textContent = sprint().tasks.length
  document.getElementById('d-tasklist').innerHTML = sprint().tasks.map(t => {
    const tc = getProgress(t.storageKey)
    const r = tc.total ? Math.round(tc.pass/tc.total*100) : 0
    return `<button class="taskrow ${tc.fail>0?'fail':''}" onclick="go('task','${t.id}')">
      <span class="tid mono">#${t.id}</span>
      <span class="ttitle">${t.title}</span>
      <span class="tbar"><span class="bar" style="height:6px">${barHTML(tc)}</span><span class="meta">${tc.pass}/${tc.total} passed${tc.n?' · '+tc.n+' pending':''}</span></span>
      <span class="tstat" style="color:${tc.fail>0?'var(--fail)':'var(--pass)'}">${tc.fail>0?tc.fail+' Fail':r+'%'}</span>
    </button>`
  }).join('')
  renderSelectors(); renderSidebar()
}

// ── TC View ──
async function renderTask(tid) {
  activeTask = tid
  const t = task(tid)
  document.getElementById('tc-crumb').innerHTML = `<b>${project().name}</b><span class="sep">›</span><b>${sprint().name}</b><span class="sep">›</span>#${t.id}`
  document.getElementById('tc-tid').textContent = '#' + t.id
  document.getElementById('tc-title').textContent = t.title
  document.getElementById('tc-link').href = boardUrl(t.id, t)
  const note = document.getElementById('tc-note')
  note.classList.add('hide')
  tcFilter = 'all'; allOpen = false
  document.querySelectorAll('#tc-filter button').forEach(x => x.classList.toggle('on', x.dataset.f==='all'))
  document.getElementById('toggle-all').textContent = 'Expand all'
  document.getElementById('bug-out').classList.remove('open')
  document.getElementById('export-btn').style.display = 'none'
  document.getElementById('send-btn').style.display = 'none'
  document.getElementById('tc-bar').innerHTML = ''
  document.getElementById('tc-legend').innerHTML = ''
  document.getElementById('tc-list').innerHTML = '<div class="loading-state">กำลังโหลด test cases...</div>'

  const sections = await loadSections(t)
  currentSections = sections
  const isDynamic = !sections.some(s => s.tcs && s.tcs.length && s.tcs[0].id.startsWith('TC-'))

  if (!sections.length) {
    document.getElementById('tc-list').innerHTML =
      `<div class="loading-state" style="display:flex;flex-direction:column;align-items:center;gap:12px;padding:60px 20px">
        <div style="font-size:32px;opacity:.2">📋</div>
        <div style="color:var(--dim);font-size:13px">ยังไม่มี Test Case</div>
        <button onclick="addTcDynamic()" style="font-size:13px;padding:7px 20px;border-radius:999px;background:var(--panel2);color:var(--dim);border:1px solid var(--line2);cursor:pointer;font-family:inherit">+ เพิ่ม Test Case</button>
      </div>`
    return
  }

  document.getElementById('tc-list').innerHTML = sections.map((sec, si) =>
    `<div class="section" id="sec-${si}">
      ${sec.name ? `<div class="section-hd">${sec.name}<span class="count num">${sec.tcs.length} TC</span></div>` : ''}
      ${sec.tcs.map(tc => `
        <div class="tc" id="row-${tc.id}">
          <div class="tc-head">
            <div class="tc-meta">
              <div class="tc-idline">
                <span class="tc-id mono">${tc.id}</span>
                <span class="tc-statustag pass">Pass</span>
                <span class="tc-statustag fail">Fail</span>
                <span class="tc-statustag skip">Skip</span>
                <span class="tc-statustag retest">Retest</span>
              </div>
              <div class="tc-name">${tc.name}</div>
            </div>
            <div class="tc-btns">
              <button class="tbtn" id="p-${tc.id}" onclick="setStatus('${tc.id}','pass')">Pass</button>
              <button class="tbtn" id="f-${tc.id}" onclick="setStatus('${tc.id}','fail')">Fail</button>
              <button class="tbtn" id="s-${tc.id}" onclick="setStatus('${tc.id}','skip')">Skip</button>
              ${(isDynamic || tc.id.startsWith('EX-')) ? `<button class="tbtn del" onclick="deleteTcDynamic('${tc.id}')" title="ลบ TC นี้">✕</button>` : ''}
            </div>
          </div>
          <button class="tc-toggle" onclick="toggleDetail('${tc.id}',this)">▸ ดูรายละเอียด</button>
          <div class="tc-detail" id="detail-${tc.id}">
            ${tc.precondition?`<div class="dlabel">Precondition</div><div class="dval">${tc.precondition}</div>`:''}
            <div class="dlabel">Steps</div><div class="dval">${tc.steps?tc.steps.replace(/\n/g,'<br>'):'<span style="color:var(--faint)">—</span>'}</div>
            <div class="dlabel">Expected</div><div class="dval expected">${tc.expected||'<span style="color:var(--faint)">—</span>'}</div>
            <div class="dlabel">Actual Result (จากผลเทส)</div>
            <div class="actual-editor" id="actual-${tc.id}" contenteditable="true" data-placeholder="พิมพ์หรือ Ctrl+V วางรูปได้เลย..."></div>
            <div class="save-row"><button class="save-btn" onclick="saveActual('${tc.id}')">บันทึก Actual</button></div>
          </div>
        </div>`
      ).join('')}
    </div>`
  ).join('') + `<button class="add-tc-btn-idx" onclick="addTcDynamic()">+ เพิ่ม Test Case</button>`

  sections.forEach(sec => sec.tcs.forEach(tc => setupEditor(tc.id)))
  applyTaskStateToUI(); updateTaskStats(); applyTcFilter()
  renderSelectors(); renderSidebar()
}

function addTcDynamic() {
  const t = task(activeTask)
  const tcsKey = t.storageKey + '_tcs'
  let tcs = []
  try { tcs = JSON.parse(localStorage.getItem(tcsKey) || '[]') } catch(e) {}
  const currentTcs = currentSections.flatMap(s => s.tcs || [])
  const isStatic = currentTcs.some(tc => tc.id.startsWith('TC-'))
  const prefix = isStatic ? 'EX-' : 'TC-'
  const nums = tcs.map(tc => parseInt(tc.id.replace(prefix,''), 10)).filter(n => !isNaN(n))
  const next = nums.length ? Math.max(...nums) + 1 : 1
  const id = prefix + String(next).padStart(3, '0')
  tcs.push({ id, name: id, precondition: '', steps: '', expected: '' })
  localStorage.setItem(tcsKey, JSON.stringify(tcs))
  renderTask(activeTask)
}

function deleteTcDynamic(tcId) {
  if (!confirm('ลบ ' + tcId + '?')) return
  const t = task(activeTask)
  const tcsKey = t.storageKey + '_tcs'
  let tcs = []
  try { tcs = JSON.parse(localStorage.getItem(tcsKey) || '[]') } catch(e) {}
  tcs = tcs.filter(tc => tc.id !== tcId)
  localStorage.setItem(tcsKey, JSON.stringify(tcs))
  const data = getTaskData(t.storageKey)
  delete data[tcId]
  setTaskData(t.storageKey, data)
  renderTask(activeTask)
}

function applyTaskStateToUI() {
  const data = getTaskData(task(activeTask).storageKey)
  allTcIds().forEach(id => {
    const s = data[id]
    if (!s) return
    if (s.status) {
      const row = document.getElementById('row-' + id)
      if (row) row.className = 'tc s-' + s.status
      const map = {pass:'p',fail:'f',skip:'s'}
      Object.entries(map).forEach(([st,k]) => {
        const b = document.getElementById(k+'-'+id)
        if (b) b.className = 'tbtn' + (s.status===st ? ' a'+k : '')
      })
    }
    if (s.note) {
      const ed = document.getElementById('actual-'+id)
      if (ed) {
        const _imgStyle = 'max-width:100%;border-radius:7px;display:block;margin:6px 0;cursor:zoom-in;border:1px solid var(--line2)'
        let _html = s.note
        _html = _html.replace(/\[รูป\]\s*(https?:\/\/[^\s<"'\n]+)/g, `<img src="$1" style="${_imgStyle}" onclick="openLightbox(this.src)">`)
        _html = _html.replace(/(?<!['"=>])(https?:\/\/i\.ibb\.co\/[^\s<"'\n]+)/g, `<img src="$1" style="${_imgStyle}" onclick="openLightbox(this.src)">`)
        ed.innerHTML = _html
      }
    }
  })
}

function updateTaskStats() {
  const c = getProgress(task(activeTask).storageKey)
  document.getElementById('tc-bar').innerHTML = barHTML(c)
  const rate = c.total ? Math.round(c.pass/c.total*100) : 0
  const col = rate>=80?'var(--pass)':(c.fail>0?'#d97706':'var(--text)')
  document.getElementById('tc-legend').innerHTML =
    [['pass','var(--pass)','Pass'],['fail','var(--fail)','Fail'],['retest','#f59e0b','Retest'],['skip','var(--skip)','Skip'],['n','var(--pending)','Pending']].map(([k,clr,l]) =>
      (k==='retest' && !c.retest) ? '' :
      `<div class="lg"><span class="d" style="background:${clr}"></span><span class="n num">${c[k]}</span><span class="t">${l}</span></div>`
    ).join('') +
    `<div class="lg" style="margin-left:8px;border-left:1px solid var(--line2);padding-left:12px"><span class="n num" style="color:var(--dim)">${c.total}</span><span class="t">Total TC</span></div>` +
    `<div class="rate"><span class="v" style="color:${col}">${rate}<span style="font-size:.6em;color:var(--faint)">%</span></span><span class="lb">Pass Rate</span></div>`
  document.getElementById('ab-summary').textContent = `${c.pass}/${c.total} passed · ${c.fail} fail`
}

function setStatus(tcId, st) {
  const key = task(activeTask).storageKey
  const data = getTaskData(key)
  if (!data[tcId]) data[tcId] = {status:null,note:''}
  data[tcId].status = data[tcId].status===st ? null : st
  setTaskData(key, data)
  const row = document.getElementById('row-'+tcId)
  if (row) row.className = 'tc' + (data[tcId].status ? ' s-'+data[tcId].status : '')
  const map = {pass:'p',fail:'f',skip:'s'}
  Object.entries(map).forEach(([full,k]) => {
    const b = document.getElementById(k+'-'+tcId)
    if (b) b.className = 'tbtn' + (data[tcId].status===full ? ' a'+k : '')
  })
  updateTaskStats(); applyTcFilter(); renderSidebar()
}

function toggleDetail(id, el) {
  const open = document.getElementById('detail-'+id).classList.toggle('open')
  el.innerHTML = open ? '▾ Hide details' : '▸ ดูรายละเอียด'
}

function setupEditor(id) {
  const ed = document.getElementById('actual-'+id)
  if (!ed) return
  ed.addEventListener('paste', e => {
    const it = Array.from(e.clipboardData?.items||[]).find(i => i.type.startsWith('image/'))
    if (!it) return
    e.preventDefault()
    const r = new FileReader()
    r.onload = ev => {
      const img = document.createElement('img'); img.src = ev.target.result
      img.onclick = () => openLightbox(img.src)
      insertAtCursor(img); showToast('วางรูปแล้ว')
    }
    r.readAsDataURL(it.getAsFile())
  })
  ed.addEventListener('dragover', e => e.preventDefault())
  ed.addEventListener('drop', e => {
    e.preventDefault()
    const _ins = src => { const _a = s => { const img = document.createElement('img'); img.src = s; img.onclick = () => openLightbox(img.src); ed.appendChild(img); showToast('วางรูปแล้ว') }; if (!src.startsWith('data:') || src.startsWith('data:image/gif')) { _a(src); return }; const tmp = new Image(); tmp.onload = () => { const MAX = 600, cv = document.createElement('canvas'); let w = tmp.width, h = tmp.height; if (w > MAX) { h = Math.round(h * MAX / w); w = MAX } if (h > MAX) { w = Math.round(w * MAX / h); h = MAX } cv.width = w; cv.height = h; cv.getContext('2d').drawImage(tmp, 0, 0, w, h); _a(cv.toDataURL('image/jpeg', 0.4)) }; tmp.src = src }
    const f = Array.from(e.dataTransfer.files).find(x => x.type.startsWith('image/'))
    if (f) { const r = new FileReader(); r.onload = ev => _ins(ev.target.result); r.readAsDataURL(f); return }
    const item = Array.from(e.dataTransfer.items||[]).find(i => i.kind==='file' && i.type.startsWith('image/'))
    if (item) { const r = new FileReader(); r.onload = ev => _ins(ev.target.result); r.readAsDataURL(item.getAsFile()); return }
    const html = e.dataTransfer.getData('text/html')
    if (html) { const tmp = document.createElement('div'); tmp.innerHTML = html; const s = tmp.querySelector('img')?.src; if (s) { _ins(s); return } }
    const uri = (e.dataTransfer.getData('text/uri-list')||'').split('\n')[0].trim()
    if (uri && /\.(png|jpe?g|gif|webp|svg)/i.test(uri)) _ins(uri)
  })
}

function insertAtCursor(node) {
  const sel = window.getSelection()
  if (!sel||!sel.rangeCount) return
  const r = sel.getRangeAt(0); r.deleteContents(); r.insertNode(node)
  r.setStartAfter(node); r.collapse(true); sel.removeAllRanges(); sel.addRange(r)
}

function saveActual(id) {
  const key = task(activeTask).storageKey
  const data = getTaskData(key)
  if (!data[id]) data[id] = {status:null,note:''}
  const ed = document.getElementById('actual-'+id)
  data[id].note = ed ? ed.innerHTML : ''
  setTaskData(key, data)
  showToast('บันทึกแล้ว')
}

function applyTcFilter() {
  currentSections.forEach((sec, si) => {
    const data = getTaskData(task(activeTask).storageKey)
    let shown = 0
    sec.tcs.forEach(tc => {
      const row = document.getElementById('row-'+tc.id)
      const s = data[tc.id]?.status
      let vis = true
      if (tcFilter==='fail') vis = s==='fail'
      else if (tcFilter==='pending') vis = !s
      if (row) row.style.display = vis ? '' : 'none'
      if (vis) shown++
    })
    const el = document.getElementById('sec-'+si)
    if (el) el.style.display = shown ? '' : 'none'
  })
}

function resetTask() {
  if (!confirm('รีเซ็ตผลทดสอบของ task นี้?')) return
  const key = task(activeTask).storageKey
  const data = {}
  allTcIds().forEach(id => data[id] = {status:null,note:''})
  setTaskData(key, data)
  allTcIds().forEach(id => {
    const row = document.getElementById('row-'+id)
    if (row) row.className = 'tc'
    const map = {pass:'p',fail:'f',skip:'s'}
    Object.values(map).forEach(k => { const b=document.getElementById(k+'-'+id); if(b) b.className='tbtn' })
    const ed = document.getElementById('actual-'+id)
    if (ed) ed.innerHTML = ''
  })
  updateTaskStats(); applyTcFilter()
  document.getElementById('bug-out').classList.remove('open')
  document.getElementById('export-btn').style.display = 'none'
  document.getElementById('send-btn').style.display = 'none'
  renderSidebar()
}

function markRetest(id) {
  const key = task(activeTask).storageKey
  const data = getTaskData(key)
  if (!data[id]) data[id] = {status:null,note:''}
  data[id].status = 'retest'
  setTaskData(key, data)
  const row = document.getElementById('row-'+id)
  if (row) row.className = 'tc s-retest'
  ;['p','f','s'].forEach(k => { const b = document.getElementById(k+'-'+id); if(b) b.className='tbtn' })
  updateTaskStats(); applyTcFilter(); renderSidebar(); showBugReport()
}

function unmarkRetest(id) {
  const key = task(activeTask).storageKey
  const data = getTaskData(key)
  if (!data[id]) data[id] = {status:null,note:''}
  data[id].status = 'fail'
  setTaskData(key, data)
  const row = document.getElementById('row-'+id)
  if (row) row.className = 'tc s-fail'
  const fb = document.getElementById('f-'+id); if(fb) fb.className='tbtn af'
  updateTaskStats(); applyTcFilter(); renderSidebar(); showBugReport()
}

function retestPass(id) {
  const key = task(activeTask).storageKey
  const data = getTaskData(key)
  if (!data[id]) data[id] = {status:null,note:''}
  data[id].status = 'pass'
  setTaskData(key, data)
  const row = document.getElementById('row-'+id)
  if (row) row.className = 'tc s-pass'
  const pb = document.getElementById('p-'+id); if(pb) pb.className='tbtn ap'
  ;['f','s'].forEach(k => { const b = document.getElementById(k+'-'+id); if(b) b.className='tbtn' })
  updateTaskStats(); applyTcFilter(); renderSidebar(); showBugReport()
}

function showBugReport() {
  const t = task(activeTask)
  const data = getTaskData(t.storageKey)
  const fails = []; let num = 1
  const retests = []
  currentSections.forEach(sec => sec.tcs.forEach(tc => {
    if (data[tc.id]?.status==='fail') {
      const ed = document.getElementById('actual-'+tc.id)
      fails.push({...tc, section:sec.name, actualHtml:ed?ed.innerHTML.trim():'', num:num++})
    } else if (data[tc.id]?.status==='retest') {
      retests.push({...tc, section:sec.name})
    }
  }))
  const out=document.getElementById('bug-out'), list=document.getElementById('bug-list'), title=document.getElementById('bug-title')
  out.classList.add('open')
  document.getElementById('export-btn').style.display = fails.length ? 'inline-block' : 'none'
  document.getElementById('send-btn').style.display   = fails.length ? 'inline-block' : 'none'
  if (!fails.length && !retests.length) {
    title.textContent=''; list.innerHTML='<div class="no-fail"><span style="width:9px;height:9px;border-radius:3px;background:var(--pass);display:inline-block"></span>ไม่มี Test Case ที่ Fail — ผ่านทั้งหมด</div>'
    out.scrollIntoView({behavior:'smooth',block:'start'}); return
  }
  const parts = []
  if (fails.length) parts.push(fails.length + ' รายการที่ Fail')
  if (retests.length) parts.push(retests.length + ' รายการรอ Retest')
  title.textContent = 'พบ ' + parts.join(' · ')
  const failsHtml = fails.map(f => `<div class="bug-item">
    <div class="bug-id">BUG-${String(f.num).padStart(3,'0')} · ${f.id}</div>
    <div class="bug-name">${f.name}</div>
    ${f.precondition?`<div class="bug-line"><b>Precondition:</b> ${f.precondition}</div>`:''}
    <div class="bug-line"><b>Steps:</b> ${f.steps.replace(/\n/g,'<br>&nbsp;&nbsp;&nbsp;')}</div>
    <div class="bug-line"><b>Expected:</b> ${f.expected}</div>
    <div class="bug-line"><b>Actual result:</b></div>
    <div class="bug-actual">${f.actualHtml||'<span style="color:var(--faint)">ยังไม่ได้ระบุ</span>'}</div>
    <button class="bug-retest-btn" onclick="markRetest('${f.id}')">🔁 Dev แก้แล้ว — Mark Retest</button>
  </div>`).join('')
  const retestsHtml = retests.length ? `
    <div class="bug-title" style="margin-top:16px;color:#b45309">รอ Retest (${retests.length})</div>
    ${retests.map(f => `<div class="bug-item-retest">
      <div class="bug-id" style="color:#b45309">${f.id}<span class="retest-badge">⏳ รอ Retest</span></div>
      <div class="bug-name">${f.name}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
        <button class="bug-retest-btn" style="color:#15803d;border-color:rgba(82,168,105,0.4)" onclick="retestPass('${f.id}')">✅ Retest ผ่าน</button>
        <button class="bug-retest-btn" style="color:#b91c1c;border-color:rgba(239,83,80,0.3)" onclick="unmarkRetest('${f.id}')">❌ Retest ไม่ผ่าน</button>
      </div>
    </div>`).join('')}
  ` : ''
  list.innerHTML = failsHtml + retestsHtml
  out.scrollIntoView({behavior:'smooth',block:'start'})
}

function buildPayload() {
  const t = task(activeTask)
  const data = getTaskData(t.storageKey)
  const fails = []
  currentSections.forEach(sec => sec.tcs.forEach(tc => {
    if (data[tc.id]?.status==='fail') {
      const ed = document.getElementById('actual-'+tc.id)
      const images = []; if (ed) ed.querySelectorAll('img').forEach(i => images.push(i.src))
      fails.push({tc_id:tc.id,name:tc.name,section:sec.name,precondition:tc.precondition||'',steps:tc.steps,expected:tc.expected,actual:ed?ed.innerText.trim():'ยังไม่ได้ระบุ',images})
    }
  }))
  if (!fails.length) { showToast('ไม่มี Fail ที่จะส่ง'); return null }
  const c = getProgress(t.storageKey)
  return {task_url:boardUrl(t.id,t),task_number:t.id,task_name:t.title,project:project().name,sprint:sprint().name,total_pass:c.pass,total_fail:fails.length,total_skip:c.skip,total_tc:c.total,bugs:fails}
}

function exportBugJSON() {
  const p = buildPayload(); if (!p) return
  const blob = new Blob([JSON.stringify(p,null,2)],{type:'application/json'})
  const a = document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='bug-report-'+p.task_number+'.json'; a.click()
  showToast('ดาวน์โหลด bug-report-'+p.task_number+'.json แล้ว')
}

let progressEl = null
function showSending() {
  if (progressEl) progressEl.remove()
  progressEl = document.createElement('div'); progressEl.className='send-progress'
  progressEl.innerHTML='<div class="send-progress-title">กำลังส่ง Bug Report...</div><div class="send-step" id="sp-0">→ ส่งไป proxy...</div>'
  document.body.appendChild(progressEl)
}
function showSendDone(m) { if(!progressEl)return; const s=progressEl.querySelector('#sp-0'); s.className='send-step done'; s.textContent='✓ '+m; setTimeout(()=>{progressEl?.remove();progressEl=null},3000) }
function showSendErr(m)  { if(!progressEl)return; const s=progressEl.querySelector('#sp-0'); s.className='send-step err';  s.textContent='✗ '+m; setTimeout(()=>{progressEl?.remove();progressEl=null},5000) }

async function sendToBoard() {
  const p = buildPayload(); if (!p) return
  showSending()
  try {
    const r = await fetch(`${PROXY_URL}/send`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)})
    const d = await r.json()
    if (d.ok) { showSendDone(`ส่ง ${p.total_fail} bugs สำเร็จ!`); showToast(`ส่ง ${p.total_fail} bugs เข้า Task #${p.task_number} แล้ว`) }
    else       { showSendErr(d.error||'ส่งไม่สำเร็จ'); showToast(d.error||'ส่งไม่สำเร็จ') }
  } catch(e) { showSendErr('เปิด proxy ก่อน'); showToast('ไม่พบ proxy — รัน: python proxy.py'); console.error(e) }
}

function openLightbox(src) {
  const o=document.createElement('div'); o.className='lb-overlay'
  const img=document.createElement('img'); img.src=src
  const c=document.createElement('button'); c.className='lb-close'; c.textContent='✕'
  o.appendChild(img); o.appendChild(c); document.body.appendChild(o)
  const rm=()=>o.remove()
  c.onclick=e=>{e.stopPropagation();rm()}; o.onclick=rm; img.onclick=e=>e.stopPropagation()
  document.addEventListener('keydown',function esc(e){if(e.key==='Escape'){rm();document.removeEventListener('keydown',esc)}})
}

function showToast(m) {
  const t=document.createElement('div'); t.className='toast'; t.textContent=m
  document.body.appendChild(t); setTimeout(()=>t.remove(),2200)
}

// ── Event listeners ──
document.getElementById('sel-project').addEventListener('change', onProjectChange)
document.getElementById('sel-sprint').addEventListener('change', onSprintChange)
document.getElementById('back-btn').onclick = () => go('home')
document.getElementById('search').addEventListener('input', renderSidebar)
document.getElementById('tc-filter').addEventListener('click', e => {
  const b = e.target.closest('button[data-f]'); if (!b) return
  tcFilter = b.dataset.f
  document.querySelectorAll('#tc-filter button').forEach(x => x.classList.toggle('on', x===b))
  applyTcFilter()
})
document.getElementById('toggle-all').addEventListener('click', e => {
  allOpen = !allOpen
  document.querySelectorAll('.tc-detail').forEach(d => d.classList.toggle('open', allOpen))
  document.querySelectorAll('.tc-toggle').forEach(t => t.innerHTML = allOpen ? '▾ Hide details' : '▸ ดูรายละเอียด')
  e.target.textContent = allOpen ? 'Collapse all' : 'Expand all'
})
document.getElementById('bug-list').addEventListener('click',e=>{if(e.target.tagName==='IMG')openLightbox(e.target.src)})

// ── Init ──
;(async function() {
  // โหลด PROJECTS จาก tasks.json
  try {
    const res = await fetch('/tasks.json?v=' + Date.now())
    const data = await res.json()
    if (!Array.isArray(data)) throw new Error('invalid tasks.json')
    PROJECTS = data
  } catch(e) {
    document.body.innerHTML = '<div style="padding:40px;font-family:sans-serif;color:#b91c1c">❌ โหลด tasks.json ไม่ได้ — ตรวจสอบไฟล์และ deploy ใหม่</div>'
    console.error('[init] failed to load tasks.json', e)
    return
  }
  // set default project/sprint หลัง PROJECTS โหลดแล้ว
  curProject = PROJECTS[0].id
  curSprint  = PROJECTS[0].sprints[0].id
  if (window.AUTH) await window.AUTH.waitForAuth()
  if (window.FS) await window.FS.pullAll()
  const params = new URLSearchParams(location.search)
  const hashStr = location.hash.slice(1)               // e.g. "task=403"
  const hashTask = hashStr.startsWith('task=') ? hashStr.replace('task=','') : hashStr

  // standalone mode
  if (params.get('standalone') === '1') {
    document.querySelector('.app').classList.add('standalone')
  }

  // set project / sprint from URL params
  const pParam = params.get('p'), sParam = params.get('s')
  if (pParam) {
    const proj = PROJECTS.find(p => p.id === pParam)
    if (proj) {
      curProject = proj.id
      const spr = sParam ? proj.sprints.find(s => s.id === sParam) : proj.sprints[0]
      if (spr) curSprint = spr.id
    }
  }

  renderSelectors()

  // navigate to task from hash
  if (hashTask) {
    const found = sprint().tasks.find(t => t.id === hashTask)
    if (found) { go('task', found.id); return }
  }
  go('home')
})()

// Prevent browser from navigating when files are dropped outside an editor
document.addEventListener('dragover', e => e.preventDefault())
document.addEventListener('drop', e => e.preventDefault())
