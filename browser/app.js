import { clientRuntimeProblems, clientRuntimeConnectSrc } from './kotoba-client-runtime.js';
import { descriptor, wasmBase64, wasmSha256 } from './bundle.js';

const status = document.getElementById('status');
const mount = document.getElementById('app');
const KEY = 'itonami.zuhyo.candidate.zs1';
const LIMIT = 35000;
const MAX_VIEW = 1000000;
const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });
let bytes, snapshot, persisted;
let pending = Promise.resolve();

function fail(message) { status.textContent = message; }
function parseTree(wire) {
  const data = encoder.encode(wire);
  if (data.length > MAX_VIEW || !wire.startsWith('BV1|') || data[data.length - 1] !== 10) throw Error('view format');
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
    const [tag, css, type, key, value, text, count] = Array.from({ length: 7 }, field);
    if (!tags.has(tag) || !/^(0|[1-9][0-9]?)$/.test(count) || Number(count) > 32 || encoder.encode(key).length > 128) throw Error('view node');
    if ((type && !['text', 'button'].includes(type)) || (tag !== 'input' && value)) throw Error('view attribute');
    const el = document.createElement(tag);
    if (css) el.className = css;
    if (type) el.setAttribute('type', type);
    if (key) el.dataset.k = key;
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
    worker.postMessage({ bytes, fuel: 25000000, allow: [37, 38], args });
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
  } catch (_) {
    fail('保存できませんでした。前の内容を保持しています。');
    try { await draw(snapshot, focus); } catch (_) { /* leave the previous view */ }
  }
}
for (const kind of ['click', 'input']) mount.addEventListener(kind, e => {
  // Capture the target and value before an earlier queued render replaces it.
  const el = e.target.closest('[data-k]');
  if (!el || !mount.contains(el) || (e.type === 'input' && el.tagName !== 'INPUT')) return;
  const key = el.dataset.k, value = e.type === 'input' ? el.value : '';
  const focus = e.type === 'input' ? { key, start: el.selectionStart, end: el.selectionEnd } : null;
  const captured = { key, value, focus, type: e.type };
  pending = pending.then(() => dispatch(captured));
});
async function start() {
  if (clientRuntimeProblems(descriptor, [], location.origin).length || clientRuntimeConnectSrc(descriptor, [], [], location.origin) !== "connect-src 'none'") throw Error('descriptor');
  bytes = Uint8Array.from(atob(wasmBase64), c => c.charCodeAt(0));
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2, '0')).join('');
  if (digest !== wasmSha256) throw Error('artifact digest');
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
