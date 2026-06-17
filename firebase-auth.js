// firebase-auth.js — auth check + role + readonly mode
// Load AFTER firebase-app-compat, firebase-auth-compat, firebase-sync.js

(function () {
  const CONFIG = {
    apiKey: "AIzaSyC7ULFZaYUqro-sSlqX1qITv9tTm1ybzj0",
    authDomain: "qa-tester-f005d.firebaseapp.com",
    projectId: "qa-tester-f005d",
    storageBucket: "qa-tester-f005d.firebasestorage.app",
    messagingSenderId: "447472890864",
    appId: "1:447472890864:web:fb79980cb0b76803032335"
  };
  if (!firebase.apps.length) firebase.initializeApp(CONFIG);
  const auth = firebase.auth();
  const db   = firebase.firestore();

  window.AUTH = { user: null, role: null };

  window.AUTH.waitForAuth = function () {
    return new Promise((resolve) => {
      const unsub = auth.onAuthStateChanged(async (user) => {
        unsub();
        if (!user) {
          location.href = '/login.html';
          return resolve(null);
        }
        let role = 'readonly';
        try {
          const snap = await db.collection('users').doc(user.uid).get();
          if (snap.exists) role = snap.data().role || 'readonly';
        } catch (e) {}

        window.AUTH.user = user;
        window.AUTH.role = role;

        _injectLogout(user.email);
        if (role === 'readonly') _applyReadonly();

        resolve({ user, role });
      });
    });
  };

  function _injectLogout(email) {
    const onLogout = () => auth.signOut().then(() => { location.href = '/login.html'; });
    const name = email.split('@')[0];
    const roleLabel = window.AUTH.role === 'readonly' ? 'Read-only' : 'Admin';

    // dark topbar (task pages)
    const topbar = document.querySelector('.topbar');
    if (topbar) {
      const wrap = document.createElement('div');
      wrap.style.cssText = 'display:flex;align-items:center;gap:6px;flex-shrink:0;margin-left:auto';

      const chip = document.createElement('span');
      chip.style.cssText = 'font-size:11px;color:rgba(255,255,255,0.45);background:rgba(255,255,255,0.06);border:0.5px solid rgba(255,255,255,0.1);border-radius:999px;padding:3px 10px;white-space:nowrap;display:flex;align-items:center;gap:5px';
      chip.innerHTML = `<span style="width:6px;height:6px;border-radius:50%;background:${window.AUTH.role==='readonly'?'#eab308':'#22c55e'};display:inline-block"></span>${name} · ${roleLabel}`;

      const btn = document.createElement('button');
      btn.textContent = 'ออกจากระบบ';
      btn.style.cssText = 'font-size:11px;padding:3px 10px;border-radius:999px;border:0.5px solid rgba(255,255,255,0.12);background:transparent;color:rgba(255,255,255,0.35);cursor:pointer;white-space:nowrap;transition:color .12s,border-color .12s';
      btn.onmouseenter = () => { btn.style.color='#fff'; btn.style.borderColor='rgba(255,255,255,0.35)'; };
      btn.onmouseleave = () => { btn.style.color='rgba(255,255,255,0.35)'; btn.style.borderColor='rgba(255,255,255,0.12)'; };
      btn.onclick = onLogout;

      wrap.appendChild(chip);
      wrap.appendChild(btn);
      topbar.appendChild(wrap);
      return;
    }

    // light sidebar (index.html — pin to bottom of sidebar)
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
      const wrap = document.createElement('div');
      wrap.style.cssText = 'margin-top:auto;padding:10px 12px;border-top:1px solid var(--line);display:flex;align-items:center;gap:7px';

      const dot = document.createElement('span');
      dot.style.cssText = `width:7px;height:7px;border-radius:50%;background:${window.AUTH.role==='readonly'?'#eab308':'#22c55e'};flex-shrink:0`;

      const info = document.createElement('div');
      info.style.cssText = 'flex:1;overflow:hidden';
      info.innerHTML = `<div style="font-size:12px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${name}</div><div style="font-size:10px;color:var(--faint);margin-top:1px">${roleLabel}</div>`;

      const btn = document.createElement('button');
      btn.title = 'ออกจากระบบ';
      btn.innerHTML = '↩';
      btn.style.cssText = 'width:26px;height:26px;border-radius:7px;border:1px solid var(--line2);background:var(--bg);color:var(--faint);cursor:pointer;font-size:14px;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:.1s';
      btn.onmouseenter = () => { btn.style.background='#fee2e2'; btn.style.color='#ef5350'; btn.style.borderColor='#ef5350'; };
      btn.onmouseleave = () => { btn.style.background='var(--bg)'; btn.style.color='var(--faint)'; btn.style.borderColor='var(--line2)'; };
      btn.onclick = onLogout;

      wrap.appendChild(dot);
      wrap.appendChild(info);
      wrap.appendChild(btn);
      sidebar.appendChild(wrap);
    }
  }

  const BLOCKED_FNS = ['resetAll','resetTask','addTc','addTcDynamic','deleteTc','deleteTcDynamic','setStatus','saveActual','sendToBoard','exportBugJSON'];

  // Capture-phase click blocker — fires before any onclick handler
  document.addEventListener('click', function (e) {
    if (window.AUTH?.role !== 'readonly') return;
    const btn = e.target.closest('button, [onclick]');
    if (!btn) return;
    const fn = btn.getAttribute('onclick') || '';
    if (BLOCKED_FNS.some(f => fn.includes(f))) {
      e.stopImmediatePropagation();
      e.stopPropagation();
      e.preventDefault();
    }
  }, true);

  function _applyReadonly() {
    document.body.classList.add('qa-readonly');

    // CSS — hide edit controls visually
    const style = document.createElement('style');
    style.textContent = `
      .qa-readonly .tbtn           { opacity:0.25 !important; cursor:not-allowed !important; }
      .qa-readonly .add-tc-btn     { display:none !important; }
      .qa-readonly .del-btn        { display:none !important; }
      .qa-readonly .save-btn       { display:none !important; }
      .qa-readonly #send-btn       { display:none !important; }
      .qa-readonly #export-btn     { display:none !important; }
      .qa-readonly .actual-editor  { pointer-events:none !important; opacity:0.6 !important; }
      .qa-readonly button[onclick*="resetAll"]   { display:none !important; }
      .qa-readonly button[onclick*="sendToBoard"]{ display:none !important; }
    `;
    document.head.appendChild(style);

    // Direct DOM hide (belt-and-suspenders)
    setTimeout(() => {
      ['.tbtn', '.add-tc-btn', '.del-btn', '.save-btn', '#send-btn', '#export-btn'].forEach(sel => {
        document.querySelectorAll(sel).forEach(el => el.style.setProperty('display', 'none', 'important'));
      });
      document.querySelectorAll('button').forEach(el => {
        const oc = el.getAttribute('onclick') || '';
        if (BLOCKED_FNS.some(f => oc.includes(f))) {
          el.style.setProperty('display', 'none', 'important');
        }
      });
      document.querySelectorAll('.actual-editor').forEach(el => el.setAttribute('contenteditable', 'false'));
    }, 0);
  }
})();
