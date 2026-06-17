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

        console.log('[AUTH] role=', role, 'calling _applyReadonly:', role === 'readonly');
        _injectLogout(user.email);
        if (role === 'readonly') _applyReadonly();

        resolve({ user, role });
      });
    });
  };

  function _injectLogout(email) {
    const topbar = document.querySelector('.topbar');
    if (!topbar) return;
    const btn = document.createElement('button');
    btn.textContent = email.split('@')[0] + ' ↩';
    btn.title = 'Logout';
    btn.style.cssText = 'font-size:11px;padding:3px 8px;border-radius:4px;border:0.5px solid rgba(255,255,255,0.12);background:transparent;color:rgba(255,255,255,0.3);cursor:pointer;white-space:nowrap;flex-shrink:0';
    btn.onclick = () => auth.signOut().then(() => { location.href = '/login.html'; });
    topbar.appendChild(btn);
  }

  const BLOCKED_FNS = ['resetAll','resetTask','addTc','deleteTc','setStatus','saveActual','sendToBoard','exportBugJSON'];

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
    console.log('[AUTH] _applyReadonly() called, body=', document.body);
    document.body.classList.add('qa-readonly');
    console.log('[AUTH] qa-readonly class added:', document.body.classList.contains('qa-readonly'));

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
