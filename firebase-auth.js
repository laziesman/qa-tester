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
    const topbar = document.querySelector('.topbar');
    if (!topbar) return;
    const btn = document.createElement('button');
    btn.textContent = email.split('@')[0] + ' ↩';
    btn.title = 'Logout';
    btn.style.cssText = 'font-size:11px;padding:3px 8px;border-radius:4px;border:0.5px solid rgba(255,255,255,0.12);background:transparent;color:rgba(255,255,255,0.3);cursor:pointer;white-space:nowrap;flex-shrink:0';
    btn.onclick = () => auth.signOut().then(() => { location.href = '/login.html'; });
    topbar.appendChild(btn);
  }

  function _applyReadonly() {
    document.body.classList.add('qa-readonly');

    // CSS layer
    const style = document.createElement('style');
    style.textContent = `
      .qa-readonly .tbtn           { pointer-events:none !important; opacity:0.25 !important; }
      .qa-readonly .add-tc-btn     { display:none !important; }
      .qa-readonly .del-btn        { display:none !important; }
      .qa-readonly .save-btn       { display:none !important; }
      .qa-readonly #send-btn       { display:none !important; }
      .qa-readonly #export-btn     { display:none !important; }
      .qa-readonly .actual-editor  { pointer-events:none !important; }
      .qa-readonly .abtn.primary   { pointer-events:none !important; opacity:0.25 !important; }
    `;
    document.head.appendChild(style);

    // JS layer — hide elements directly
    setTimeout(() => {
      ['.tbtn', '.add-tc-btn', '.del-btn', '.save-btn', '#send-btn', '#export-btn'].forEach(sel => {
        document.querySelectorAll(sel).forEach(el => el.style.setProperty('display', 'none', 'important'));
      });
      document.querySelectorAll('button').forEach(el => {
        const fn = el.getAttribute('onclick') || '';
        if (fn.includes('resetAll') || fn.includes('sendToBoard')) {
          el.style.setProperty('display', 'none', 'important');
        }
        if (fn.includes('setStatus') || fn.includes('addTc')) {
          el.style.setProperty('pointer-events', 'none', 'important');
          el.style.setProperty('opacity', '0.25', 'important');
        }
      });
      document.querySelectorAll('.actual-editor').forEach(el => {
        el.setAttribute('contenteditable', 'false');
      });
    }, 0);

    // Function override layer — block calls even if buttons somehow visible
    const noop = () => {};
    ['addTc', 'deleteTc', 'resetAll', 'setStatus', 'saveActual', 'sendToBoard', 'exportBugJSON'].forEach(fn => {
      if (typeof window[fn] === 'function') window[fn] = noop;
    });
  }
})();
