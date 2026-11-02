#!/usr/bin/env python3
"""Build an offline Zuhyo browser candidate using a local Amu selfhost root.

Usage: python3 scripts/build-browser.py AMU_DIR BROKER_REPO POLICY_REPO STORAGE_REPO OUTPUT_DIR
The output must not exist. This candidate is not a release or route cutover.
"""
import base64
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 6:
    raise SystemExit(__doc__)
amu, broker, policy_repo, storage_repo, out = [Path(x).resolve() for x in sys.argv[1:]]
out.mkdir(parents=True, exist_ok=False)
root = Path(__file__).resolve().parents[1]
pin = json.loads((root / 'appview/slides-mcp-component/client-runtime.pin.json').read_text())
raw = subprocess.run(['git', '-C', str(broker), 'show', pin['revision'] + ':src/kotoba-client-runtime.js'],
                     check=True, capture_output=True).stdout
if hashlib.sha256(raw).hexdigest() != pin['sha256']:
    raise SystemExit('canonical broker digest mismatch')
(out / 'kotoba-client-runtime.js').write_bytes(raw)
storage_pin = json.loads((root / 'browser/storage.pin.json').read_text())
for item in storage_pin['sources']:
    blob = subprocess.run(['git', '-C', str(storage_repo), 'show', storage_pin['revision'] + ':' + item['path']], check=True, capture_output=True).stdout
    if hashlib.sha256(blob).hexdigest() != item['sha256']:
        raise SystemExit('storage adapter digest mismatch')
    (out / Path(item['path']).name).write_bytes(blob)
for name in ('index.html', 'style.css', 'app.js'):
    shutil.copyfile(root / 'browser' / name, out / name)
shutil.copyfile(amu / 'runtime/wasm32-browser-static-host.js', out / 'worker.js')
source = (root / 'src/zuhyo/deck.kotoba').read_text(encoding='utf-8')
source, n = re.subn(r'\A\(ns\s+zuhyo\.deck[\s\S]*?\(:export \[[^\]]*\]\)\)',
                    '(ns zuhyo.deck (:export [main]))', source, count=1)
anchor = '(defn main [] :i64 (test-deck))'
if n != 1 or source.count(anchor) != 1:
    raise SystemExit('unexpected editor source')
source = source[:source.index(anchor)] + (root / 'src/zuhyo/browser-entry.kotoba').read_text(encoding='utf-8')
(out / 'program.kotoba').write_text(source, encoding='utf-8')
spec = importlib.util.spec_from_file_location('mac', amu / 'scripts/seed/check-aiueos-user-macos-native.py')
mac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mac)
compiler = amu / 'seed/bootstrap/aarch64-macos/amu-full-root.macho'
mac.native_run(compiler, out, 'compile', 'program.kotoba', '--target', 'wasm32-browser', '--output', 'program.wasm')
wasm = (out / 'program.wasm').read_bytes()
policy_pin = json.loads((root / 'browser/draft-policy.pin.json').read_text())
parts = []
for item in policy_pin['sources']:
    blob = subprocess.run(['git', '-C', str(policy_repo), 'show', policy_pin['revision'] + ':' + item['path']],
                          check=True, capture_output=True).stdout
    if hashlib.sha256(blob).hexdigest() != item['sha256']:
        raise SystemExit('canonical draft policy digest mismatch')
    parts.append(blob.decode('utf-8'))
policy_ns = '(ns aiueos.draft-policy (:export [classify classify-chunks units]))'
entry_ns = '(ns aiueos.draft-policy-browser\n  (:export [main])\n  (:capabilities [:cli/args :io/write])\n  (:require [aiueos.draft-policy :as policy]))'
if parts[0].count(policy_ns) != 1 or parts[1].count(entry_ns) != 1:
    raise SystemExit('unexpected draft policy namespace')
policy_source = (parts[0].replace(policy_ns, '(ns aiueos.draft-policy-browser (:export [main]))', 1) + '\n'
                 + parts[1].replace(entry_ns, '', 1).replace('policy/classify-chunks', 'classify-chunks').replace('policy/units', 'units'))
(out / 'draft-policy.kotoba').write_text(policy_source, encoding='utf-8')
mac.native_run(compiler, out, 'compile', 'draft-policy.kotoba', '--target', 'wasm32-browser', '--output', 'draft-policy.wasm')
policy_wasm = (out / 'draft-policy.wasm').read_bytes()
# Preserve the already tracked static DID document at its did:web path.
# This document has no verification methods and does not prove key control.
did = (root / 'appview/slides-mcp-component/cljs/public/.well-known/did.json').read_bytes()
did_document = json.loads(did)
if did_document.get('id') != 'did:web:zuhyo.itonami.app' or did_document.get('@context') != ['https://www.w3.org/ns/did/v1']:
    raise SystemExit('unexpected static DID document')
(out / '.well-known').mkdir()
(out / '.well-known/did.json').write_bytes(did)
desc = {'schema': 'kotoba.app.client-runtime.v1', 'target': 'browser', 'profile': 'trusted-page-v1',
        'entry': 'index.html', 'local-state': {'adapter': 'indexeddb', 'schema': 'itonami.zuhyo.candidate.idb-v2', 'version': 2},
        'workers': [{'id': 'zuhyo-worker', 'entry': 'worker.js', 'protocol': 'wasm32-browser-static.v1'}], 'operations': []}
(out / 'client-runtime.json').write_text(json.dumps(desc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
config = ('export const descriptor = ' + json.dumps(desc, ensure_ascii=False) + ';\n'
          + 'export const wasmBase64 = ' + json.dumps(base64.b64encode(wasm).decode()) + ';\n'
          + 'export const wasmSha256 = ' + json.dumps(hashlib.sha256(wasm).hexdigest()) + ';\n'
          + 'export const draftPolicyBase64 = ' + json.dumps(base64.b64encode(policy_wasm).decode()) + ';\n'
          + 'export const draftPolicySha256 = ' + json.dumps(hashlib.sha256(policy_wasm).hexdigest()) + ';\n')
(out / 'bundle.js').write_text(config, encoding='utf-8')
receipt = {'wasmSha256': hashlib.sha256(wasm).hexdigest(), 'compilerSha256': hashlib.sha256(compiler.read_bytes()).hexdigest(),
           'sourceSha256': hashlib.sha256(source.encode()).hexdigest(), 'brokerRevision': pin['revision'], 'brokerSha256': pin['sha256'],
           'workerSha256': hashlib.sha256((out / 'worker.js').read_bytes()).hexdigest(),
           'draftPolicyRevision': policy_pin['revision'], 'draftPolicySourceSha256': hashlib.sha256(policy_source.encode()).hexdigest(),
           'draftPolicyWasmSha256': hashlib.sha256(policy_wasm).hexdigest(),
           'didSha256': hashlib.sha256(did).hexdigest(), 'storageRevision': storage_pin['revision'],
           'transactionalStorageSha256': storage_pin['sources'][0]['sha256'], 'managedStorageSha256': storage_pin['sources'][1]['sha256']}
(out / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('BUILT_ZUHYO_BROWSER_CANDIDATE', out)
