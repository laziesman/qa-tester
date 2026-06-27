// firebase-sync.js — syncs qa_ localStorage keys to Firestore
// Images stay local only; Firestore stores text/status only

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

  // Strip base64 images before sending to Firestore (avoid 1MB doc limit)
  function _stripImages(jsonStr) {
    try {
      const d = JSON.parse(jsonStr);
      Object.values(d).forEach(tc => {
        if (tc && tc.note) tc.note = tc.note.replace(/src="data:[^"]+"/g, 'src=""');
      });
      return JSON.stringify(d);
    } catch(e) { return jsonStr; }
  }

  function _push(docId) {
    const data = {};
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(docId)) data[k] = _stripImages(localStorage.getItem(k));
    }
    db.collection(COL).doc(docId).set(data)
      .catch(e => console.warn('[FS] write error', e));
  }

  // Merge Firestore value into localStorage — preserve local base64 images
  function _mergeKey(k, remoteVal) {
    const localVal = localStorage.getItem(k);
    if (!localVal) { _orig.call(localStorage, k, remoteVal); return; }
    try {
      const local  = JSON.parse(localVal);
      const remote = JSON.parse(remoteVal);
      Object.keys(remote).forEach(tcId => {
        if (!local[tcId]) { local[tcId] = remote[tcId]; return; }
        const localNote = local[tcId].note || '';
        // Keep local note if it has images; otherwise take remote note
        local[tcId] = {
          ...remote[tcId],
          note: (localNote.includes('data:image') || localNote.includes('<img')) ? localNote : (remote[tcId].note || localNote)
        };
      });
      _orig.call(localStorage, k, JSON.stringify(local));
    } catch(e) {
      _orig.call(localStorage, k, remoteVal);
    }
  }

  async function pullDoc(docId) {
    try {
      const snap = await db.collection(COL).doc(docId).get();
      if (snap.exists) {
        Object.entries(snap.data()).forEach(([k, v]) => _mergeKey(k, v));
        return true;
      }
    } catch (e) {
      console.warn('[FS] pullDoc error', e);
    }
    return false;
  }

  async function pullAll() {
    try {
      const snaps = await db.collection(COL).get();
      snaps.forEach(doc => {
        Object.entries(doc.data()).forEach(([k, v]) => _mergeKey(k, v));
      });
    } catch (e) {
      console.warn('[FS] pullAll error', e);
    }
  }

  window.FS = { pullDoc, pullAll };
})();
