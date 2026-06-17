// firebase-sync.js — syncs qa_ localStorage keys to Firestore
// Loaded via CDN scripts in each HTML file

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
  const db = firebase.firestore();
  const COL = 'qa_results';

  // Intercept localStorage.setItem — auto-push to Firestore (debounced 800ms)
  const _orig = Storage.prototype.setItem;
  const timers = {};

  Storage.prototype.setItem = function (key, value) {
    _orig.call(this, key, value);
    const m = key.match(/^(qa_task_\d+)/);
    if (!m) return;
    const docId = m[1];
    clearTimeout(timers[docId]);
    timers[docId] = setTimeout(() => _push(docId), 800);
  };

  function _push(docId) {
    const data = {};
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(docId)) data[k] = localStorage.getItem(k);
    }
    db.collection(COL).doc(docId).set(data)
      .catch(e => console.warn('[FS] write error', e));
  }

  // Pull one task's data from Firestore into localStorage
  async function pullDoc(docId) {
    try {
      const snap = await db.collection(COL).doc(docId).get();
      if (snap.exists) {
        Object.entries(snap.data()).forEach(([k, v]) => _orig.call(localStorage, k, v));
        return true;
      }
    } catch (e) {
      console.warn('[FS] pullDoc error', e);
    }
    return false;
  }

  // Pull ALL tasks from Firestore into localStorage (for index.html)
  async function pullAll() {
    try {
      const snaps = await db.collection(COL).get();
      snaps.forEach(doc => {
        Object.entries(doc.data()).forEach(([k, v]) => _orig.call(localStorage, k, v));
      });
    } catch (e) {
      console.warn('[FS] pullAll error', e);
    }
  }

  window.FS = { pullDoc, pullAll };
})();
