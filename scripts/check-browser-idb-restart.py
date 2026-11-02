#!/usr/bin/env python3
"""Exercise a clean browser-process restart of the Zuhyo IDB candidate.

Usage: script AMU BUILD NEW_OUTPUT CHROME
Synthetic Chrome only; not crash, power-loss, eviction, other browser or release.
"""
import functools,http.server,importlib.util,json,sys,threading,time
from pathlib import Path
if len(sys.argv)!=5:raise SystemExit(__doc__)
amu,build,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:]);out.mkdir(parents=True,exist_ok=False);(out/'profile').mkdir()
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(build)));threading.Thread(target=server.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{server.server_port}/index.html';pipe=None
try:
 def launch():
  global pipe
  pipe=browser.Pipe(str(chrome),out/'profile');target=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];session=pipe.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId'];pipe.call('Page.enable',{},session);pipe.call('Page.navigate',{'url':url},session);return session
 def ev(x,s,awaited=False):
  r=pipe.call('Runtime.evaluate',{'expression':x,'returnByValue':True,'awaitPromise':awaited},s)
  if 'exceptionDetails' in r:raise ValueError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(x,s,label):
  until=time.time()+75
  while time.time()<until:
   try:
    if ev(x,s):return
   except RuntimeError as e:
    if not any(m in str(e) for m in ('Execution context was destroyed','Cannot find context with specified id')):raise
   time.sleep(.1)
  raise TimeoutError(label+': '+str(ev("document.getElementById('status')?.textContent",s)))
 def waitSaved(text,s):
  until=time.time()+75
  while time.time()<until:
   value=ev('new Promise((resolve,reject)=>{const r=indexedDB.open("itonami.office.zuhyo.v2",1);r.onsuccess=()=>{const d=r.result,t=d.transaction("records","readonly"),g=t.objectStore("records").get("current");g.onsuccess=()=>resolve(g.result?.value??null);g.onerror=()=>reject(Error("read"));t.oncomplete=()=>d.close()};r.onerror=()=>reject(Error("open"))})',s,True)
   if value is not None and text in value and ev('document.getElementById("status").textContent==="保存しました"',s):return
   time.sleep(.1)
  raise TimeoutError('saved text')
 first=launch();wait('document.querySelector("[data-k=heading]")!==null',first,'initial')
 def enter(key,value):ev('(()=>{let e=document.querySelector("[data-k='+key+']");e.value='+json.dumps(value,ensure_ascii=False)+';e.dispatchEvent(new Event("input",{bubbles:true}))})()',first)
 enter('heading','第一😀');waitSaved('第一😀',first)
 enter('notes','発表メモ\n二行目');waitSaved('発表メモ',first)
 ev('document.querySelector("[data-k=add]").click()',first);wait('document.querySelector(".stats")?.textContent==="2 / 2"',first,'second slide')
 enter('heading','第二枚');waitSaved('第二枚',first)
 enter('body','内容\n二行目');waitSaved('内容',first)
 ev('document.querySelector("[data-k=shape-circle]").click()',first);wait('document.querySelector("main.edit.shape-circle")!==null',first,'shape')
 ev('document.querySelector("[data-k=mode]").click()',first);wait('document.querySelector("main.present.shape-circle h1")?.textContent==="第二枚"',first,'presentation')
 waitSaved('第二枚',first);assert ev('localStorage.getItem("itonami.zuhyo.candidate.zs1")',first) is None
 pipe.close();pipe=None
 second=launch();wait('document.querySelector("main.present.shape-circle h1")?.textContent==="第二枚"',second,'restart presentation')
 assert ev('document.querySelector("main.present p")?.textContent',second)=='内容\n二行目'
 ev('document.querySelector("[data-k=prev]").click()',second);wait('document.querySelector("main.present h1")?.textContent==="第一😀"',second,'previous slide')
 ev('document.querySelector("[data-k=mode]").click()',second);wait('document.querySelector("[data-k=notes]")?.value==="発表メモ\\n二行目"',second,'notes')
 assert ev('document.getElementById("storage-conflict").hidden && !document.getElementById("legacy-migration").open',second)
 report={'status':'PASS_ZUHYO_IDB_RESTART_SYNTHETIC','scope':'synthetic Chrome clean process restart; no crash/power-loss, storage eviction, old-client coordination, QEMU or release'};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],flush=True)
finally:
 if pipe:pipe.close()
 server.shutdown();server.server_close()
