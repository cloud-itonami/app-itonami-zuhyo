#!/usr/bin/env python3
"""Check the bounded deck model and reorder mutant using Amu and Chrome.
Usage: python3 scripts/check-deck-wasm.py AMU_DIR OUTPUT_DIR CHROME
"""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
if len(sys.argv) != 4: raise SystemExit(__doc__)
amu, out, chrome = [Path(x).resolve() for x in sys.argv[1:]]
out.mkdir(parents=True, exist_ok=False)
source = (Path(__file__).resolve().parents[1] / 'src/zuhyo/deck.kotoba').read_text()
anchor = '(document-vector-assoc (document-vector-assoc v i (dat v j)) j (dat v i))) j)'
if source.count(anchor) != 1: raise ValueError('mutation anchor changed')
version_anchor = '(if (needs-zs2? s) "ZS2|" "ZS1|")'
if source.count(version_anchor) != 1: raise ValueError('snapshot version anchor changed')
spec = importlib.util.spec_from_file_location('mac', amu / 'scripts/seed/check-aiueos-user-macos-native.py')
mac = importlib.util.module_from_spec(spec); spec.loader.exec_module(mac)
compiler = amu / 'seed/bootstrap/aarch64-macos/amu-full-root.macho'
results = {}
for name, text, expected in [('deck', source, 0), ('mutant', source.replace(anchor, anchor[:-2] + 'i)'), 1), ('version-mutant', source.replace(version_anchor, '"ZS1|"'), 1)]:
    src = out / (name + '.kotoba'); src.write_text(text)
    run = subprocess.run([str(amu / 'bin/amu'), 'run', str(src)], capture_output=True, text=True, check=True, timeout=120)
    if run.stdout.strip() != str(expected): raise ValueError('native ' + name + ': ' + run.stdout)
    mac.native_run(compiler, out, 'compile', src.name, '--target', 'wasm32-browser', '--output', name + '.wasm')
    dest = out / (name + '-browser')
    subprocess.run([sys.executable, str(amu / 'scripts/seed/check-wasm32-browser.py'), '--browser', str(chrome),
                    '--app', str(out / (name + '.wasm')), '--output', str(dest)], check=True)
    report = json.loads((dest / 'app.json').read_text()).get('report', '')
    if not re.search(rf'\{{:status :ok :result {expected}(?:\s|\}})', report): raise ValueError(name + ': ' + report)
    results[name] = {'result': expected, 'wasmSha256': hashlib.sha256((out / (name + '.wasm')).read_bytes()).hexdigest()}
(out / 'receipt.json').write_text(json.dumps({'sourceSha256': hashlib.sha256(source.encode()).hexdigest(),
    'compilerSha256': hashlib.sha256(compiler.read_bytes()).hexdigest(), 'results': results}, indent=2) + '\n')
print('PASS_ZUHYO_MODEL native, Wasm, reorder and snapshot-version mutants')
