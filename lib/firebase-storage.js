// firebase-storage.js — imgbb image upload for QA Tester
// Intercepts paste/drop on .actual-editor, uploads to imgbb, inserts URL (syncs cross-device)

(function () {
  const IMGBB_KEY = '808ea7c6f6cf54e96e94c85ef70a3ac7';

  async function _upload(fileOrBlob, filename) {
    const form = new FormData();
    form.append('image', fileOrBlob, filename || 'image.jpg');
    try {
      const res = await fetch(`https://api.imgbb.com/1/upload?key=${IMGBB_KEY}`, {
        method: 'POST', body: form
      });
      const json = await res.json();
      if (json.success) return json.data.display_url || json.data.image?.url || json.data.url;
      console.warn('[imgbb]', json.error);
    } catch(e) { console.warn('[imgbb] upload error', e); }
    return null;
  }

  function _insertImg(editor, url) {
    const img = document.createElement('img');
    img.src = url;
    if (window.openLightbox) img.onclick = () => openLightbox(img.src);
    const sel = window.getSelection();
    if (sel && sel.rangeCount && editor.contains(sel.getRangeAt(0).commonAncestorContainer)) {
      const r = sel.getRangeAt(0);
      r.deleteContents(); r.insertNode(img);
      r.setStartAfter(img); r.collapse(true);
      sel.removeAllRanges(); sel.addRange(r);
    } else {
      editor.appendChild(img);
    }
  }

  // Capture-phase paste — fires before existing handler
  document.addEventListener('paste', async (e) => {
    const editor = e.target.closest('.actual-editor');
    if (!editor) return;
    const imgItem = Array.from(e.clipboardData?.items || []).find(i => i.type.startsWith('image/'));
    if (!imgItem) return;
    e.preventDefault(); e.stopImmediatePropagation();
    if (window.showToast) showToast('⏫ กำลังอัปโหลด...');
    const url = await _upload(imgItem.getAsFile(), `paste_${Date.now()}.jpg`);
    if (!url) { if (window.showToast) showToast('❌ อัปโหลดรูปไม่ได้'); return; }
    _insertImg(editor, url);
    if (window.showToast) showToast('📋 วางรูปแล้ว');
  }, true);

  // Allow drop on actual-editor (required for playwright-cli drop command)
  document.addEventListener('dragover', (e) => {
    if (e.target.closest('.actual-editor')) e.preventDefault();
  }, true);

  // Capture-phase drop — fires before existing handler
  document.addEventListener('drop', async (e) => {
    const editor = e.target.closest('.actual-editor');
    if (!editor) return;
    e.preventDefault(); e.stopImmediatePropagation();

    const _go = async (blobOrUrl, name) => {
      if (window.showToast) showToast('⏫ กำลังอัปโหลด...');
      const url = await _upload(blobOrUrl, name);
      if (url) { _insertImg(editor, url); if (window.showToast) showToast('📎 วางรูปแล้ว'); }
      else if (window.showToast) showToast('❌ อัปโหลดรูปไม่ได้');
    };
    const _direct = (url) => { _insertImg(editor, url); if (window.showToast) showToast('📎 วางรูปแล้ว'); };

    const file = Array.from(e.dataTransfer.files).find(f => f.type.startsWith('image/'));
    if (file) { await _go(file, file.name); return; }

    const item = Array.from(e.dataTransfer.items || []).find(i => i.kind === 'file' && i.type.startsWith('image/'));
    if (item) { const f = item.getAsFile(); await _go(f, f?.name || `img_${Date.now()}.jpg`); return; }

    const html = e.dataTransfer.getData('text/html');
    if (html) {
      const tmp = document.createElement('div'); tmp.innerHTML = html;
      const src = tmp.querySelector('img')?.src;
      if (src) { src.startsWith('data:') ? await _go(src, `img_${Date.now()}.jpg`) : _direct(src); return; }
    }

    const uri = (e.dataTransfer.getData('text/uri-list') || '').split('\n')[0].trim();
    if (uri && /\.(png|jpe?g|gif|webp|svg)/i.test(uri)) _direct(uri);
  }, true);

})();
