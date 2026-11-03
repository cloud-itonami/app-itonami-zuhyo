import { clientRuntimeProblems, clientRuntimeConnectSrc } from './kotoba-client-runtime.js';
import { descriptor, wasmBase64, wasmSha256, draftPolicyBase64, draftPolicySha256 } from './bundle.js';

const status = document.getElementById('status');
const mount = document.getElementById('app');
const retrySave = document.getElementById('retry-save');
const draftNotice = document.getElementById('draft-notice');
const draftPanel = document.getElementById('draft-recovery');
const draftRestore = document.getElementById('draft-restore');
let draftBlocked = false, recoveryRaw = null, recoveryItems = null, lockedControls = [];
let draftReadFailed = false, retryDraftAllowed = false, draftGeneration = 0;
const edits = new Map();
const composing = new Set();
let deferredRender = null;
let editSequence = 0;
const KEY = 'itonami.zuhyo.candidate.zs1';
const DRAFT_KEY = KEY + '.session-draft.v1';
const LIMIT = 35000;
const MAX_VIEW = 1000000;
const BACKUP_PREFIX = KEY + '.preimport.';
const backupFile = document.getElementById('backup-file');
const backupDialog = document.getElementById('backup-dialog');
const backupPreview = document.getElementById('backup-preview');
let proposedBackup = null, proposedBase = null, proposedPersisted = null;
const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });
let bytes, compiledModule, compiledDraftPolicy, snapshot, persisted;
let pending = Promise.resolve();
window.addEventListener('beforeunload', e => {
  if (edits.size || draftBlocked) { e.preventDefault(); e.returnValue = ''; }
});

function fail(message) { status.textContent = message; }
function draftWarning(message) { draftNotice.textContent = message; draftNotice.hidden = !message; }
function writeDraft() {
  if (draftBlocked) return;
  try {
    if (!edits.size) sessionStorage.removeItem(DRAFT_KEY);
    else {
      const raw = JSON.stringify({ version: 1, program: wasmSha256, base: persisted, baseState: snapshot, entries: [...edits].map(([key, edit]) => [key, edit.value]) });
      if (raw.length > 1000000) throw Error('draft bounds');
      sessionStorage.setItem(DRAFT_KEY, raw);
    }
    draftWarning('');
  } catch (_) { draftWarning(edits.size ? '未保存入力の再読込用コピーを記録できません。画面の入力を別に控えてください。' : '保存済みですが、再読込用コピーを削除できません。次回確認してください。'); }
}
function unlockDraftMount() {
  for (const [el, disabled] of lockedControls) el.disabled = disabled;
  lockedControls = [];
  mount.inert = false;
}
function scalarString(s) {
  if (typeof s !== 'string') return false;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      if (++i >= s.length) return false;
      const d = s.charCodeAt(i);
      if (d < 0xdc00 || d > 0xdfff) return false;
    } else if (c >= 0xdc00 && c <= 0xdfff) return false;
  }
  return true;
}
async function offerDraft(raw, allowRestore) {
  const generation = ++draftGeneration;
  recoveryRaw = raw; recoveryItems = null; draftBlocked = true; mount.inert = true;
  document.getElementById('draft-retry-read').hidden = true;
  document.getElementById('draft-download').disabled = false;
  document.getElementById('draft-discard').disabled = false;
  lockedControls = [...mount.querySelectorAll('input,textarea,button')].map(el => [el, el.disabled]);
  for (const [el] of lockedControls) el.disabled = true;
  draftRestore.disabled = true;
  document.getElementById('draft-message').textContent = '未保存データを確認しています。';
  document.getElementById('draft-preview').textContent = '';
  draftPanel.hidden = false;
  let data = null;
  try { if (raw.length <= 1000000) data = JSON.parse(raw); } catch (_) {}
  const inputs = [...mount.querySelectorAll('input[data-k],textarea[data-k]')].map(el => el.dataset.k);
  // JSON shape and Unicode are transport checks. The Wasm policy decides
  // bounds, duplicates, snapshot equality and whether restoration is safe.
  const shaped = data && data.version === 1 && scalarString(data.program) &&
    (data.base === null || scalarString(data.base)) && scalarString(data.baseState) &&
    Array.isArray(data.entries) && data.entries.length <= 33 &&
    data.entries.every(entry => Array.isArray(entry) && entry.length === 2 && scalarString(entry[0]) && scalarString(entry[1])) &&
    (persisted === null || scalarString(persisted)) && scalarString(snapshot) && inputs.every(scalarString) && inputs.length <= 512;
  let verdict = 0;
  if (shaped && compiledDraftPolicy) {
    const wire = inputs.map(key => encoder.encode(key).length + ':' + key).join('');
    const args = ['classify', String(raw.length), String(LIMIT), allowRestore ? '1' : '0', wasmSha256,
      persisted === null ? 'null' : 'string', persisted ?? '', snapshot, data.program,
      data.base === null ? 'null' : 'string', data.base ?? '', data.baseState, String(data.entries.length),
      ...data.entries.flat(), String(inputs.length), wire];
    try {
      const result = await run(args, compiledDraftPolicy);
      if (/^[012]\n$/.test(result)) verdict = Number(result[0]);
    } catch (_) {}
  }
  if (generation !== draftGeneration || !draftBlocked || recoveryRaw !== raw) return;
  const valid = verdict > 0, matches = verdict === 2;
  if (valid) recoveryItems = data.entries;
  draftRestore.disabled = !matches;
  document.getElementById('draft-message').textContent = matches
    ? '前回の未保存入力です。内容を確認して画面に戻し、再保存してください。'
    : '保存済み内容との対応を確認できません。書き出して内容を控えてから、破棄するか判断してください。';
  document.getElementById('draft-preview').textContent = valid
    ? data.entries.map(([key, value]) => key + ': ' + (value.length > 4096 ? value.slice(0, 4096) + '…' : value)).join('\n\n')
    : '形式を確認できないため、内容のプレビューは表示できません。';
  draftPanel.hidden = false;
}
function inspectDraft(allowRestore) {
  let raw;
  try { raw = sessionStorage.getItem(DRAFT_KEY); }
  catch (_) {
    if (!draftReadFailed) {
      draftBlocked = true; mount.inert = true;
      lockedControls = [...mount.querySelectorAll('input,textarea,button')].map(el => [el, el.disabled]);
      for (const [el] of lockedControls) el.disabled = true;
    }
    draftReadFailed = true; retryDraftAllowed = allowRestore;
    recoveryRaw = null; recoveryItems = null; draftRestore.disabled = true;
    document.getElementById('draft-download').disabled = true;
    document.getElementById('draft-discard').disabled = true;
    document.getElementById('draft-message').textContent = '未保存データを確認できないため、編集を停止しています。確認を再試行してください。';
    document.getElementById('draft-preview').textContent = '';
    document.getElementById('draft-retry-read').hidden = false;
    draftPanel.hidden = false;
    draftWarning('再読込用の未保存データを確認できません。');
    return;
  }
  if (draftReadFailed) { draftReadFailed = false; draftBlocked = false; unlockDraftMount(); }
  draftWarning('');
  if (raw !== null) offerDraft(raw, allowRestore);
  else { draftPanel.hidden = true; document.getElementById('draft-retry-read').hidden = true; }
}
document.getElementById('draft-retry-read').addEventListener('click', () => {
  if (draftReadFailed) inspectDraft(retryDraftAllowed);
});
document.getElementById('draft-download').addEventListener('click', () => {
  if (recoveryRaw === null) return;
  const url = URL.createObjectURL(new Blob([recoveryRaw], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = 'zuhyo-unsaved-draft.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
});
document.getElementById('draft-discard').addEventListener('click', () => {
  if (!draftBlocked || draftReadFailed || !window.confirm('このタブの未保存データを破棄しますか？')) return;
  try { sessionStorage.removeItem(DRAFT_KEY); }
  catch (_) { draftWarning('未保存データを破棄できません。'); return; }
  draftGeneration++; draftBlocked = false; recoveryRaw = null; recoveryItems = null; draftPanel.hidden = true; unlockDraftMount();
  try {
    fail(localStorage.getItem(KEY) === persisted ? '未保存データを破棄しました。' : '未保存データを破棄しました。別のタブの変更を開くため再読込してください。');
  } catch (_) { fail('未保存データを破棄しました。保存済み内容を確認できません。'); }
});
draftRestore.addEventListener('click', () => {
  if (!draftBlocked || draftRestore.disabled || !recoveryItems) return;
  try {
    if (localStorage.getItem(KEY) !== persisted) throw Error('concurrent change');
  } catch (_) {
    draftRestore.disabled = true;
    document.getElementById('draft-message').textContent = '保存済み内容が変わったか確認できません。書き出して内容を控えてください。';
    return;
  }
  for (const [key, value] of recoveryItems) edits.set(key, { value, sequence: ++editSequence, failed: true });
  draftBlocked = false; recoveryRaw = null; recoveryItems = null; draftPanel.hidden = true; unlockDraftMount();
  for (const el of mount.querySelectorAll('input[data-k],textarea[data-k]')) if (edits.has(el.dataset.k)) el.value = edits.get(el.dataset.k).value;
  refreshRetry();
  fail('未保存入力を画面に戻しました。内容を確認して再保存してください。');
});
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
  const tags = new Set(['div', 'header', 'main', 'footer', 'input', 'textarea', 'button', 'span', 'h1', 'h2', 'p', 'ul', 'li']);
  function node(depth) {
    if (++nodes > 512 || depth > 12) throw Error('view bounds');
    const [tag, css, type, key, value, text, label, count] = Array.from({ length: 8 }, field);
    if (!tags.has(tag) || !/^(0|[1-9][0-9]?)$/.test(count) || Number(count) > 32 || encoder.encode(key).length > 128) throw Error('view node');
    if ((type && !['text', 'button'].includes(type)) || (!['input', 'textarea'].includes(tag) && value) || (tag === 'textarea' && type)) throw Error('view attribute');
    const el = document.createElement(tag);
    if (css) el.className = css;
    if (type) el.setAttribute('type', type);
    if (key) el.dataset.k = key;
    if (label) el.setAttribute('aria-label', label);
    if (tag === 'input' || tag === 'textarea') {
      el.value = value;
      if (el.value !== value) throw Error('input normalization');
    }
    if (text) el.textContent = text;
    for (let i = 0; i < Number(count); i++) el.append(node(depth + 1));
    return el;
  }
  const tree = node(0);
  if (pos !== data.length - 1) throw Error('view trailing data');
  return tree;
}
function run(args, module = compiledModule) {
  return new Promise((resolve, reject) => {
    const worker = new Worker('./worker.js');
    const timer = setTimeout(() => { worker.terminate(); reject(Error('worker timeout')); }, 30000);
    worker.onmessage = ({ data }) => {
      clearTimeout(timer); worker.terminate();
      if (data.exit !== 0 || data.wasmTrap || !/^\{:status :ok :result 0(?:\s|\})/.test(data.report || '')) reject(Error('program refused'));
      else resolve(data.output);
    };
    worker.onerror = () => { clearTimeout(timer); worker.terminate(); reject(Error('worker failed')); };
    worker.postMessage({ module, fuel: 25000000, allow: [37, 38], args });
  });
}
function refreshRetry() { retrySave.hidden = ![...edits.values()].some(edit => edit.failed); }
function render(tree, focus) {
  if (composing.size) { deferredRender = { tree, focus }; return; }
  deferredRender = null;
  mount.replaceChildren(tree);
  for (const node of mount.querySelectorAll('input[data-k],textarea[data-k]')) {
    const edit = edits.get(node.dataset.k);
    if (edit) node.value = edit.value;
  }
  if (focus) {
    const found = [...mount.querySelectorAll('[data-k]')].find(el => el.dataset.k === focus.key);
    if (found) { found.focus(); if (typeof found.setSelectionRange === 'function' && focus.start !== null) found.setSelectionRange(focus.start, focus.end); }
  }
}
async function draw(state, focus) { render(parseTree(await run(['view', state])), focus); }
function failEdit(event, reason) {
  const edit = edits.get(event.key);
  if (event.type === 'input' && edit?.sequence === event.sequence) edit.failed = true;
  refreshRetry();
  fail(reason + (edits.size ? '未保存の入力は画面に残っています。再読込すると失われます。' : '保存済みの内容を保持しています。'));
}
async function dispatch(event) {
  const { key, value, focus } = event;
  if (draftBlocked) { fail('前回の未保存データを確認してください。'); return; }
  if (event.type === 'input' && edits.get(key)?.sequence !== event.sequence) return;
  if (event.type === 'click' && edits.size) { fail('未保存の入力を再保存または修正してください。'); return; }
  // TextEncoder replaces lone UTF-16 surrogates. Refuse before encoding so
  // the original unsaved input and session journal remain available.
  if (!scalarString(key) || !scalarString(value)) {
    failEdit(event, '入力に不正な文字があります。');
    return;
  }
  if (encoder.encode(key).length > 128 || encoder.encode(value).length > 512) {
    failEdit(event, '入力が長すぎます。');
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
      // Recheck after the asynchronous worker. Web Locks protect cooperating
      // writers; localStorage itself has no atomic compare-and-swap.
      if (localStorage.getItem(KEY) !== persisted) throw Error('concurrent change');
      localStorage.setItem(KEY, next);
      persisted = next;
      snapshot = next;
      if (event.type === 'input' && edits.get(key)?.sequence === event.sequence) edits.delete(key);
      writeDraft();
      render(tree, focus);
      refreshRetry();
      fail(edits.size ? '保存待ちの入力があります。' : '保存しました');
    });
  } catch (error) {
    const reason = error?.message === 'worker timeout' ? '処理が時間内に完了しませんでした。' :
      error?.message === 'concurrent change' ? '別のタブで変更されています。入力をコピーしてから再読込してください。' : '';
    failEdit(event, '保存できませんでした。' + reason);
  }
}
function captureInput(el) {
  const key = el.dataset.k, value = el.value, sequence = ++editSequence;
  edits.set(key, { value, sequence, failed: false });
  writeDraft();
  refreshRetry();
  return { key, value, sequence, focus: { key, start: el.selectionStart, end: el.selectionEnd }, type: 'input' };
}
mount.addEventListener('compositionstart', e => {
  const el = e.target.closest('input[data-k],textarea[data-k]');
  if (!el || !mount.contains(el) || draftBlocked) return;
  composing.add(el.dataset.k);
  captureInput(el);
});
mount.addEventListener('compositionend', e => {
  const el = e.target.closest('input[data-k],textarea[data-k]');
  if (!el || !mount.contains(el) || !composing.has(el.dataset.k)) return;
  const captured = captureInput(el);
  composing.delete(el.dataset.k);
  pending = pending.then(() => dispatch(captured));
  // Let the browser deliver any final non-composing input before replacing DOM.
  if (!composing.size && deferredRender) {
    deferredRender.focus = captured.focus;
    setTimeout(() => { if (!composing.size && deferredRender) render(deferredRender.tree, deferredRender.focus); }, 0);
  }
});
for (const kind of ['click', 'input']) mount.addEventListener(kind, e => {
  // Capture the target and value before an earlier queued render replaces it.
  const el = e.target.closest('[data-k]');
  if (!el || !mount.contains(el) || draftBlocked || (e.type === 'input' && !['INPUT', 'TEXTAREA'].includes(el.tagName))
      || (e.type === 'click' && el.tagName !== 'BUTTON')) return;
  const key = el.dataset.k, value = e.type === 'input' ? el.value : '';
  if (e.type === 'input') {
    if (e.isComposing) composing.add(key);
    const captured = captureInput(el);
    if (!composing.has(key)) pending = pending.then(() => dispatch(captured));
    return;
  }
  if (e.type === 'click' && key.startsWith('backup-') && edits.size) { fail('未保存の入力を再保存または修正してください。'); return; }
  if (e.type === 'click' && key === 'backup-import') { backupFile.value = ''; backupFile.click(); return; }
  if (e.type === 'click' && key === 'backup-export') { pending = pending.then(exportBackup); return; }
  if (e.type === 'click' && key === 'backup-restore') { pending = pending.then(restoreBackup); return; }
  const captured = { key, value, focus: null, type: e.type, sequence: 0 };
  pending = pending.then(() => dispatch(captured));
});
retrySave.addEventListener('click', () => {
  if (draftBlocked) return;
  for (const [key, edit] of edits) {
    if (edit.failed) {
      edit.failed = false;
      pending = pending.then(() => dispatch({ key, value: edit.value, sequence: edit.sequence, focus: null, type: 'input' }));
    }
  }
  refreshRetry();
});
function exportBackup() {
  if (edits.size) { fail('未保存の入力を再保存または修正してください。'); return; }
  if (typeof snapshot !== 'string') return;
  const url = URL.createObjectURL(new Blob([snapshot], { type: 'application/octet-stream' }));
  const link = document.createElement('a');
  link.href = url; link.download = snapshot.startsWith('ZS2|') ? 'zuhyo-backup.zs2' : 'zuhyo-backup.zs1'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  fail('バックアップのダウンロードを開始しました。');
}
async function previewBackup(candidate, label) {
  const base = snapshot, basePersisted = persisted;
  if (typeof candidate !== 'string' || !candidate.startsWith('ZS1|') && !candidate.startsWith('ZS2|') || encoder.encode(candidate).length > LIMIT) throw Error('invalid backup');
  const protectedState = await run(['protect', candidate]);
  if (!protectedState.endsWith('\n')) throw Error('protect refusal');
  candidate = protectedState.slice(0, -1);
  const tree = parseTree(await run(['view', candidate]));
  if (edits.size || snapshot !== base || persisted !== basePersisted) throw Error('preview changed');
  proposedBackup = candidate; proposedBase = base; proposedPersisted = basePersisted;
  document.getElementById('backup-label').textContent = label;
  backupPreview.replaceChildren(tree);
  backupDialog.showModal();
}
backupFile.addEventListener('change', () => {
  const file = backupFile.files[0];
  if (!file) return;
  pending = pending.then(async () => {
    try {
      if (edits.size) throw Error('unsaved input');
      if (file.size > LIMIT) throw Error('backup too large');
      await previewBackup(decoder.decode(await file.arrayBuffer()), file.name);
    } catch (_) { fail('バックアップを読み込めません。現在のスライドは変更していません。'); }
  });
});
async function restoreBackup() {
  try {
    if (edits.size) { fail('未保存の入力を再保存または修正してください。'); return; }
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
backupDialog.addEventListener('close', () => { proposedBackup = null; proposedBase = null; proposedPersisted = null; backupPreview.replaceChildren(); });
document.getElementById('backup-confirm').addEventListener('click', () => {
  const next = proposedBackup, base = proposedBase, basePersisted = proposedPersisted;
  if (next === null) return;
  backupDialog.close();
  pending = pending.then(async () => {
    try {
      if (!navigator.locks) throw Error('local locking unavailable');
      await navigator.locks.request(KEY, async () => {
        if (snapshot !== base || persisted !== basePersisted || localStorage.getItem(KEY) !== persisted) throw Error('concurrent change');
        const tree = parseTree(await run(['view', next]));
        if (edits.size) throw Error('unsaved input');
        let stamp = Date.now();
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          const suffix = key && key.startsWith(BACKUP_PREFIX) ? key.slice(BACKUP_PREFIX.length) : '';
          if (/^\d{13}\.[0-9a-f-]{36}$/.test(suffix)) stamp = Math.max(stamp, Number(suffix.slice(0, 13)) + 1);
        }
        if (stamp > 9999999999999) throw Error('backup timestamp bounds');
        const backupKey = BACKUP_PREFIX + String(stamp).padStart(13, '0') + '.' + crypto.randomUUID();
        if (localStorage.getItem(KEY) !== persisted) throw Error('concurrent change');
        localStorage.setItem(backupKey, snapshot);
        if (localStorage.getItem(KEY) !== persisted) throw Error('concurrent change');
        localStorage.setItem(KEY, next);
        persisted = next; snapshot = next;
        mount.replaceChildren(tree);
        fail('バックアップから復元しました。');
      });
    } catch (error) {
      const reason = error?.message === 'concurrent change' ? '別のタブで変更されています。再読込してください。' :
        error?.message === 'unsaved input' ? '未保存の入力を再保存または修正してください。' : '';
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
  const policyBytes = Uint8Array.from(atob(draftPolicyBase64), c => c.charCodeAt(0));
  const policyDigest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', policyBytes))].map(x => x.toString(16).padStart(2, '0')).join('');
  if (policyDigest !== draftPolicySha256) throw Error('draft policy digest');
  compiledDraftPolicy = await WebAssembly.compile(policyBytes);
  const saved = localStorage.getItem(KEY);
  persisted = saved;
  if (saved !== null) {
    if (encoder.encode(saved).length > LIMIT) throw Error('saved state size');
    snapshot = saved;
    if (saved.startsWith('ZS1|') && /[\r\n]/.test(saved)) {
      const output = await run(['protect', saved]);
      if (!output.endsWith('\n')) throw Error('protect refusal');
      const next = output.slice(0, -1);
      const tree = parseTree(await run(['view', next]));
      if (next !== saved) {
        if (!navigator.locks) throw Error('local locking unavailable');
        await navigator.locks.request(KEY, async () => {
          if (localStorage.getItem(KEY) !== saved) throw Error('concurrent change');
          localStorage.setItem(KEY, next);
          persisted = next; snapshot = next;
        });
      }
      render(tree);
    } else await draw(snapshot);
    fail('保存済みのスライドを開きました');
    inspectDraft(true);
  } else {
    const output = await run(['init']);
    if (!output.endsWith('\n')) throw Error('init');
    snapshot = output.slice(0, -1);
    await draw(snapshot);
    fail('新しいスライド');
    inspectDraft(true);
  }
}
start().catch(() => { fail('スライドを開けません。保存済みの内容は変更していません。'); inspectDraft(false); });
