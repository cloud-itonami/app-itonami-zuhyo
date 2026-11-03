#!/usr/bin/env python3
"""Check that malformed UTF-16 remains unsaved, and valid text saves.

Usage: script AMU BUILD OUT CHROME bunsho|hyokeisan|zuhyo
Synthetic Chrome data only; this does not establish crash durability.
"""
import functools, http.server, importlib.util, json, sys, threading, time
from pathlib import Path

if len(sys.argv) != 6: raise SystemExit(__doc__)
amu, build, out, chrome = map(lambda s: Path(s).resolve(), sys.argv[1:5])
name = sys.argv[5]
fields = {'bunsho': ('b0', 'itonami.bunsho.candidate.bs1'),
          'hyokeisan': ('c0', 'itonami.hyokeisan.candidate.hs1'),
          'zuhyo': ('body', 'itonami.zuhyo.candidate.zs1')}
field, key = fields[name]
draft_key = key + '.session-draft.v1'
out.mkdir(parents=True, exist_ok=False); profile = out / 'profile'; profile.mkdir()
spec = importlib.util.spec_from_file_location('browser', amu / 'scripts/seed/check-wasm32-browser.py')
browser = importlib.util.module_from_spec(spec); spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self, *args): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(build)))
threading.Thread(target=server.serve_forever, daemon=True).start(); pipe = browser.Pipe(str(chrome), profile)
try:
 target = pipe.call('Target.createTarget', {'url': 'about:blank'})['targetId']
 session = pipe.call('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
 pipe.call('Page.enable', {}, session)
 pipe.call('Page.navigate', {'url': f'http://127.0.0.1:{server.server_port}/index.html'}, session)
 def ev(expr):
  result = pipe.call('Runtime.evaluate', {'expression': expr, 'returnByValue': True}, session)
  if 'exceptionDetails' in result: raise ValueError(result['exceptionDetails'])
  return result.get('result', {}).get('value')
 def wait(expr, label):
  end = time.time() + 60
  while time.time() < end:
   try:
    if ev(expr): return
   except RuntimeError as e:
    if not any(x in str(e) for x in ('Execution context was destroyed', 'Cannot find context with specified id')): raise
   time.sleep(.1)
  raise TimeoutError(label + ': ' + str(ev("document.getElementById('status')?.textContent")))
 selector = json.dumps('[data-k=' + field + ']'); saved = json.dumps(key); journal = json.dumps(draft_key)
 wait('document.querySelector(' + selector + ') !== null', 'initial')
 def input_expr(expr):
  ev('(()=>{const e=document.querySelector(' + selector + ');e.value=' + expr + ';e.dispatchEvent(new Event("input",{bubbles:true}))})()')
 input_expr('"baseline"'); wait('localStorage.getItem(' + saved + ')?.includes("baseline")', 'baseline')
 ev('window.__saved=localStorage.getItem(' + saved + ')')
 for unit in (0xd800, 0xdc00):
  invalid = '"A"+String.fromCharCode(' + str(unit) + ')+"B"'
  input_expr(invalid)
  wait('document.getElementById("status").textContent.includes("入力に不正な文字") || localStorage.getItem(' + saved + ')!==window.__saved', 'invalid input')
  if not ev('document.getElementById("status").textContent.includes("入力に不正な文字")'): raise ValueError('invalid input was persisted')
  condition = ('localStorage.getItem(' + saved + ')===window.__saved && document.querySelector(' + selector + ').value===(' + invalid + ') && '
    'JSON.parse(sessionStorage.getItem(' + journal + ')).entries.some(e=>e[0]===' + json.dumps(field) + ' && e[1]===(' + invalid + ')) && '
    '!document.getElementById("retry-save").hidden')
  if not ev(condition): raise ValueError('invalid input lost or persisted')
  ev('document.getElementById("retry-save").click()')
  wait('document.getElementById("status").textContent.includes("入力に不正な文字")', 'invalid retry')
  if not ev(condition): raise ValueError('retry altered invalid input')
 input_expr('"valid 😀 \\uFFFD"')
 wait('localStorage.getItem(' + saved + ')?.includes("valid 😀 \\uFFFD") && document.getElementById("retry-save").hidden', 'corrected valid input')
 if ev('sessionStorage.getItem(' + journal + ')') is not None: raise ValueError('corrected input not cleared')
 report = {'status':'PASS_BROWSER_SCALAR_INPUT','app':name,'checks':['lone-high-and-low-refused','storage-unchanged','draft-and-field-preserved','retry-refused','valid-supplementary-and-replacement-character-saved'], 'scope':'synthetic Chrome; no real user data or crash durability'}
 (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n'); print(report['status'], name, flush=True)
finally:
 pipe.close(); server.shutdown(); server.server_close()
