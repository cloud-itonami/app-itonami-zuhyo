import { clientRuntimeProblems, clientRuntimeConnectSrc } from './kotoba-client-runtime.js';
import { descriptor, wasmBase64, wasmSha256 } from './bundle.js';

const status = document.getElementById('status');
const mount = document.getElementById('app');
const KEY = 'itonami.zuhyo.candidate.zs1';
const LIMIT = 35000;
const MAX_VIEW = 1000000;
const BACKUP_PREFIX = KEY + '.preimport.';
const backupFile = document.getElementById('backup-file');
const backupDialog = document.getElementById('backup-dialog');
const backupPreview = document.getElementById('backup-preview');
let proposedBackup = null;
const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });
let bytes, compiledModule, snapshot, persisted;
let pending = Promise.resolve();

function fail(message) { status.textContent = message; }
function parseTree(wire) {
  const data = encoder.encode(wire);
  if (data.length > MAX_VIEW || !wire.startsWith('BV2|') || data[data.length - 1] !== 10) throw Error('view format');
  let pos = 4, nodes = 0;
  function field() {
    const start = pos;
    while (pos < data.length && data[pos] >= 48 && data[pos] <= 57 && pos - start < 7) pos++;
    if (pos === start || data[pos] !== 58 || (pos - start > 1 && data[start] === 48)) throw Error('field length');
    const n = Number(decoder.decode(data.slice(start, pos++)));
    if (!Number.isSafeInteger(n) || n > MAX_VIEW || pos + n > data.length) throw Error('field bounds');
    const text = decoder.decode(data.slice(pos, pos + n)); pos += n; return text;
  }
  const tags = new Set(['div', 'header', 'main', 'footer', 'input', 'button', 'span', 'h1', 'h2', 'p', 'ul', 'li']);
  function node(depth) {
    if (++nodes > 512 || depth > 12) throw Error('view bounds');
    const [tag, css, type, key, value, text, label, count] = Array.from({ length: 8 }, field);
    if (!tags.has(tag) || !/^(0|[1-9][0-9]?)$/.test(count) || Number(count) > 32 || encoder.encode(key).length > 128) throw Error('view node');
    if ((type && !['text', 'button'].includes(type)) || (tag !== 'input' && value)) throw Error('view attribute');
    const el = document.createElement(tag);
    if (css) el.className = css;
    if (type) el.setAttribute('type', type);
    if (key) el.dataset.k = key;
    if (label) el.setAttribute('aria-label', label);
    if (tag === 'input') el.value = value;
    if (text) el.textContent = text;
    for (let i = 0; i < Number(count); i++) el.append(node(depth + 1));
    return el;
  }
  const tree = node(0);
  if (pos !== data.length - 1) throw Error('view trailing data');
  return tree;
}
function run(args) {
  return new Promise((resolve, reject) => {
    const worker = new Worker('./worker.js');
    const timer = setTimeout(() => { worker.terminate(); reject(Error('worker timeout')); }, 30000);
    worker.onmessage = ({ data }) => {
      clearTimeout(timer); worker.terminate();
      if (data.exit !== 0 || data.wasmTrap || !/^\{:status :ok :result 0(?:\s|\})/.test(data.report || '')) reject(Error('program refused'));
      else resolve(data.output);
    };
    worker.onerror = () => { clearTimeout(timer); worker.terminate(); reject(Error('worker failed')); };
    worker.postMessage({ module: compiledModule, fuel: 25000000, allow: [37, 38], args });
  });
}
async function draw(state, focus) {
  const tree = parseTree(await run(['view', state]));
  mount.replaceChildren(tree);
  if (focus) {
    const found = [...mount.querySelectorAll('[data-k]')].find(el => el.dataset.k === focus.key);
    if (found) { found.focus(); if (typeof found.setSelectionRange === 'function' && focus.start !== null) found.setSelectionRange(focus.start, focus.end); }
  }
}
async function dispatch(event) {
  const { key, value, focus } = event;
  if (encoder.encode(key).length > 128 || encoder.encode(value).length > 512) {
    fail('入力が長すぎます。');
    try { await draw(snapshot, focus); } catch (_) {}
    return;
  }
  try {
    if (!navigator.locks) throw Error('local locking unavailable');
    await navigator.locks.request(KEY, async () => {
      if (localStorage.getItem(KEY) !== persisted) throw Error('concurrent change');
      const output = await run(['step', snapshot, key, event.type, value]);
      if (!output.endsWith('\n')) throw Error('snapshot terminator');
      const next = output.slice(0, -1);
      if (encoder.encode(next).length > LIMIT) throw Error('snapshot bounds');
      const tree = parseTree(await run(['view', next]));
      localStorage.setItem(KEY, next);
      persisted = next;
      snapshot = next;
      mount.replaceChildren(tree);
      if (focus) {
        const found = [...mount.querySelectorAll('[data-k]')].find(node => node.dataset.k === focus.key);
        if (found) { found.focus(); if (focus.start !== null) found.setSelectionRange(focus.start, focus.end); }
      }
      fail('保存しました');
    });
  } catch (error) {
    const reason = error?.message === 'worker timeout' ? '処理が時間内に完了しませんでした。' :
      error?.message === 'concurrent change' ? '別のタブで変更されています。再読込してください。' : '';
    fail('保存できませんでした。' + reason + '前の内容を保持しています。');
    try { await draw(snapshot, focus); } catch (_) { /* leave the previous view */ }
  }
}
for (const kind of ['click', 'input']) mount.addEventListener(kind, e => {
  // Capture the target and value before an earlier queued render replaces it.
  const el = e.target.closest('[data-k]');
  if (!el || !mount.contains(el) || (e.type === 'input' && el.tagName !== 'INPUT')
      || (e.type === 'click' && el.tagName !== 'BUTTON')) return;
  const key = el.dataset.k, value = e.type === 'input' ? el.value : '';
  if (e.type === 'click' && key === 'backup-import') { backupFile.value = ''; backupFile.click(); return; }
  if (e.type === 'click' && key === 'backup-export') { pending = pending.then(exportBackup); return; }
  if (e.type === 'click' && key === 'backup-restore') { pending = pending.then(restoreBackup); return; }
  const focus = e.type === 'input' ? { key, start: el.selectionStart, end: el.selectionEnd } : null;
  const captured = { key, value, focus, type: e.type };
  pending = pending.then(() => dispatch(captured));
});
function exportBackup() {
  if (typeof snapshot !== 'string') return;
  const url = URL.createObjectURL(new Blob([snapshot], { type: 'application/octet-stream' }));
  const link = document.createElement('a');
  link.href = url; link.download = 'zuhyo-backup.zs1'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  fail('バックアップのダウンロードを開始しました。');
}
async function previewBackup(candidate, label) {
  if (typeof candidate !== 'string' || !candidate.startsWith('ZS1|') || encoder.encode(candidate).length > LIMIT) throw Error('invalid backup');
  const tree = parseTree(await run(['view', candidate]));
  proposedBackup = candidate;
  document.getElementById('backup-label').textContent = label;
  backupPreview.replaceChildren(tree);
  backupDialog.showModal();
}
backupFile.addEventListener('change', () => {
  const file = backupFile.files[0];
  if (!file) return;
  pending = pending.then(async () => {
    try {
      if (file.size > LIMIT) throw Error('backup too large');
      await previewBackup(decoder.decode(await file.arrayBuffer()), file.name);
    } catch (_) { fail('バックアップを読み込めません。現在のスライドは変更していません。'); }
  });
});
async function restoreBackup() {
  try {
    let latest = '';
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith(BACKUP_PREFIX) && /^\d{13}\.[0-9a-f-]{36}$/.test(key.slice(BACKUP_PREFIX.length)) && key > latest) latest = key;
    }
    if (!latest) { fail('読み込み前のバックアップはありません。'); return; }
    await previewBackup(localStorage.getItem(latest), 'このブラウザに保存された読み込み前のスライド');
  } catch (_) { fail('バックアップを読み込めません。現在のスライドは変更していません。'); }
}
document.getElementById('backup-cancel').addEventListener('click', () => backupDialog.close());
backupDialog.addEventListener('close', () => { proposedBackup = null; backupPreview.replaceChildren(); });
document.getElementById('backup-confirm').addEventListener('click', () => {
  const next = proposedBackup;
  if (next === null) return;
  backupDialog.close();
  pending = pending.then(async () => {
    try {
      if (!navigator.locks) throw Error('local locking unavailable');
      await navigator.locks.request(KEY, async () => {
        if (localStorage.getItem(KEY) !== persisted) throw Error('concurrent change');
        const tree = parseTree(await run(['view', next]));
        let stamp = Date.now();
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          const suffix = key && key.startsWith(BACKUP_PREFIX) ? key.slice(BACKUP_PREFIX.length) : '';
          if (/^\d{13}\.[0-9a-f-]{36}$/.test(suffix)) stamp = Math.max(stamp, Number(suffix.slice(0, 13)) + 1);
        }
        if (stamp > 9999999999999) throw Error('backup timestamp bounds');
        const backupKey = BACKUP_PREFIX + String(stamp).padStart(13, '0') + '.' + crypto.randomUUID();
        localStorage.setItem(backupKey, snapshot);
        localStorage.setItem(KEY, next);
        persisted = next; snapshot = next;
        mount.replaceChildren(tree);
        fail('バックアップから復元しました。');
      });
    } catch (error) {
      const reason = error?.message === 'concurrent change' ? '別のタブで変更されています。再読込してください。' : '';
      fail('復元できませんでした。' + reason + '前の内容を保持しています。');
    }
  });
});
async function start() {
  if (clientRuntimeProblems(descriptor, [], location.origin).length || clientRuntimeConnectSrc(descriptor, [], [], location.origin) !== "connect-src 'none'") throw Error('descriptor');
  bytes = Uint8Array.from(atob(wasmBase64), c => c.charCodeAt(0));
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2, '0')).join('');
  if (digest !== wasmSha256) throw Error('artifact digest');
  compiledModule = await WebAssembly.compile(bytes);
  const saved = localStorage.getItem(KEY);
  persisted = saved;
  if (saved !== null) {
    if (encoder.encode(saved).length > LIMIT) throw Error('saved state size');
    snapshot = saved;
    await draw(snapshot);
    fail('保存済みのスライドを開きました');
  } else {
    const output = await run(['init']);
    if (!output.endsWith('\n')) throw Error('init');
    snapshot = output.slice(0, -1);
    await draw(snapshot);
    fail('新しいスライド');
  }
}
start().catch(() => fail('スライドを開けません。保存済みの内容は変更していません。'));
