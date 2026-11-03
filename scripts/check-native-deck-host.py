#!/usr/bin/env python3
"""Link the real deck module into a native host and check browser source identity.

Usage: script AMU_DIR KOTOBA_DIR BROWSER_BUILD OUTPUT_DIR
Synthetic macOS Arm only. This is not OS GUI/QEMU or durable persistence.
"""
import hashlib,importlib.util,json,re,sys,types
from native_deck_source import stage
from pathlib import Path
if len(sys.argv)!=5:raise SystemExit(__doc__)
amu,kotoba,build,out=map(lambda x:Path(x).resolve(),sys.argv[1:]);root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('native_gate',kotoba/'lib/kotoba.hata/scripts/native_gate.py');ng=importlib.util.module_from_spec(spec);spec.loader.exec_module(ng)
args=types.SimpleNamespace(compiler=amu/'seed/bootstrap/aarch64-macos/amu-full-root.macho',compiler_sha256='2c551579c06a0228029bb06bae177e93126ecbbc37d636d693c471dbac8d1536',packager=amu/'seed/bootstrap/aarch64-macos/kotoba-packager-root.macho',packager_sha256='e95284408f091c8979ef74ece57116a4df2250e61e42074da5dc95ca30264142',output=out)
gate=ng.NativeGate(args)
if not gate.darwin:raise ValueError('test qualifies macOS Arm only')
source=(root/'src/zuhyo/deck.kotoba').read_text();driver=(root/'tests/native_deck_host.kotoba').read_bytes()
normalized,n=re.subn(r'\A\(ns\s+zuhyo\.deck[\s\S]*?\(:export \[[^\]]*\]\)\)','(ns zuhyo.deck (:export [main]))',source,count=1)
anchor='(defn main [] :i64 (test-deck))'
if n!=1 or normalized.count(anchor)!=1:raise ValueError('unexpected source graph')
staged=(normalized[:normalized.index(anchor)]+(root/'src/zuhyo/browser-entry.kotoba').read_text()).encode()
receipt=json.loads((build/'build-receipt.json').read_text());sha=lambda b:hashlib.sha256(b).hexdigest()
if staged!=(build/'program.kotoba').read_bytes() or sha(staged)!=receipt['sourceSha256'] or (root/'browser/app.js').read_bytes()!=(build/'app.js').read_bytes():raise ValueError('stale browser candidate')
# The native host build changes only the module export declaration. The
# existing public amu run route requires main as the sole original export.
host_source=stage(root)
if host_source[len(host_source.split('\n',1)[0]):] != source[len(source.split('\n',1)[0]):]:raise ValueError('model body changed')
files={'zuhyo/deck.kotoba':host_source.encode(),'zuhyo/native_deck_host.kotoba':driver}
image=gate.build('host','zuhyo/native_deck_host.kotoba',files);gate.run('linked-model',image)
needle=b'(string=? target "body") (set-selected s :body value)'
if files['zuhyo/deck.kotoba'].count(needle)!=1:raise ValueError('mutation anchor')
mutant=dict(files);mutant['zuhyo/deck.kotoba']=mutant['zuhyo/deck.kotoba'].replace(needle,b'(string=? target "body") (set-selected s :notes value)')
broken=gate.build('mutant','zuhyo/native_deck_host.kotoba',mutant);gate.run('mutation-detected',broken,expected=1)
gate.finish('PASS_ZUHYO_LINKED_HOST',observerSHA256=sha(Path(__file__).read_bytes()),stagerSHA256=sha((root/'scripts/native_deck_source.py').read_bytes()),nativeGateSHA256=sha((kotoba/'lib/kotoba.hata/scripts/native_gate.py').read_bytes()),browserBuild=receipt,normalizedSourceSha256=sha(staged),originalSourceSha256=sha(source.encode()),hostSourceSha256=sha(host_source.encode()),scope='macOS Arm native with synthetic data; no Itonami OS GUI, QEMU, durable storage or release')
