#!/usr/bin/env python3
"""Compare bytes-per-Worker and precompiled-module browser candidates.

Usage: python3 scripts/measure-worker-latency.py AMU_DIR OLD_BUILD NEW_BUILD OUTPUT_DIR CHROME
Builds must contain the same program.wasm and worker.js. This local,
instrumented, synthetic measurement is not a performance qualification.
"""
import hashlib
import json
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 6:
    raise SystemExit(__doc__)
amu, old, new, out, chrome = [Path(x).resolve() for x in sys.argv[1:]]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for name in ('program.wasm', 'worker.js'):
    if sha(old / name) != sha(new / name): raise SystemExit(name + ' differs')
out.mkdir(parents=True, exist_ok=False)
worker_anchor = '    const { argv, fs } = inputs(msg.args, msg.files);'
worker_start = '''      memory = instance.exports.memory;
      if (jspi)'''
app_anchor = '''  return new Promise((resolve, reject) => {
    const worker = new Worker('./worker.js');
    const timer = setTimeout(() => { worker.terminate(); reject(Error('worker timeout')); }, 30000);
    worker.onmessage = ({ data }) => {
      clearTimeout(timer); worker.terminate();'''
app_replacement = '''  return new Promise((resolve, reject) => {
    const t = performance.now(), op = args[0]; window.__timings ||= [];
    const worker = new Worker('./worker.js');
    const mark = phase => window.__timings.push({op, phase, ms: Math.round(performance.now()-t)});
    const timer = setTimeout(() => { mark('timeout'); worker.terminate(); reject(Error('worker timeout')); }, 30000);
    worker.onmessage = ({ data }) => {
      if (data.progress) { mark(data.progress); return; }
      mark('complete'); clearTimeout(timer); worker.terminate();'''
for label, source in [('bytes', old), ('module', new)]:
    dest = out / label
    shutil.copytree(source, dest)
    worker = dest / 'worker.js'; s = worker.read_text()
    if s.count(worker_anchor) != 1 or s.count(worker_start) != 1: raise ValueError('worker anchors changed')
    s = s.replace(worker_anchor, "    self.postMessage({ progress: 'worker-start' });\n" + worker_anchor)
    s = s.replace(worker_start, "      memory = instance.exports.memory;\n      self.postMessage({ progress: 'wasm-start' });\n      if (jspi)")
    worker.write_text(s)
    app = dest / 'app.js'; s = app.read_text()
    if s.count(app_anchor) != 1: raise ValueError('app anchor changed')
    app.write_text(s.replace(app_anchor, app_replacement))
rows = []
runner = Path(__file__).with_name('worker-latency-run.py')
for index, label in enumerate(('bytes', 'module', 'bytes', 'module')):
    target = out / ('run-' + str(index))
    subprocess.run([sys.executable, str(runner), str(amu), str(out / label), str(target), str(chrome)], check=True)
    events = json.loads((target / 'timings.json').read_text())
    summary = {'label': label}
    for op in ('init', 'step', 'view'):
        values = [v['ms'] for v in events if v['op'] == op and v['phase'] == 'complete']
        summary[op] = {'count': len(values), 'medianMs': statistics.median(values) if values else None,
                       'maxMs': max(values) if values else None}
    summary['timeouts'] = sum(v['phase'] == 'timeout' for v in events)
    rows.append(summary)
receipt = {'wasmSha256': sha(old / 'program.wasm'), 'workerSha256': sha(old / 'worker.js'), 'runs': rows}
(out / 'summary.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
