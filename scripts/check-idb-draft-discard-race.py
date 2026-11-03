#!/usr/bin/env python3
"""Check that a pending IDB read cannot revive a discarded draft.

Usage: script AMU BUILD NEW_OUTPUT CHROME
Synthetic Chrome only; no real user data, OS IME, crash or release.
"""
import functools,http.server,importlib.util,json,sys,threading,time
from pathlib import Path
if len(sys.argv)!=5:raise SystemExit(__doc__)
amu,build,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:]);out.mkdir(parents=True,exist_ok=False);(out/'profile').mkdir()
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(build)));threading.Thread(target=server.serve_forever,daemon=True).start();pipe=browser.Pipe(str(chrome),out/'profile');url=f'http://127.0.0.1:{server.server_port}/index.html'
try:
 def tab():
  t=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];s=pipe.call('Target.attachToTarget',{'targetId':t,'flatten':True})['sessionId'];pipe.call('Page.enable',{},s);pipe.call('Page.navigate',{'url':url},s);return s
 def ev(x,s,awaited=False):
  r=pipe.call('Runtime.evaluate',{'expression':x,'returnByValue':True,'awaitPromise':awaited},s)
  if 'exceptionDetails' in r:raise ValueError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(x,s,label):
  end=time.time()+75
  while time.time()<end:
   try:
    if ev(x,s):return
   except RuntimeError as e:
    if not any(m in str(e) for m in ('Execution context was destroyed','Cannot find context with specified id')):raise
   time.sleep(.1)
  raise TimeoutError(label+': '+str(ev("document.getElementById('status')?.textContent",s)))
 def dialog(s):
  for _ in range(40):
   try:pipe.call('Page.handleJavaScriptDialog',{'accept':True},s,timeout=5);return
   except RuntimeError:time.sleep(.1)
  raise ValueError('expected dialog not seen')
 a=tab();wait('document.querySelector("[data-k=body]")!==null',a,'initial')
 rect=ev('(()=>{let r=document.querySelector("[data-k=body]").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()',a)
 pipe.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':rect['x'],'y':rect['y'],'button':'left','clickCount':1},a);pipe.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':rect['x'],'y':rect['y'],'button':'left','clickCount':1},a)
 ev('(()=>{let e=document.querySelector("[data-k=body]");e.value="保存済み";e.dispatchEvent(new Event("input",{bubbles:true}))})()',a);wait('document.getElementById("status").textContent==="保存しました"',a,'base save')
 ev('window.__put=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(){throw Error("test failure")};(()=>{let e=document.querySelector("[data-k=body]");e.value="破棄予定";e.dispatchEvent(new Event("input",{bubbles:true}))})()',a)
 wait('document.getElementById("status").textContent.includes("保存できません")',a,'failed save')
 ev('window.__old=true',a);pipe.send('Page.reload',{},a);dialog(a)
 wait('window.__old!==true && !document.getElementById("draft-recovery").hidden && !document.getElementById("draft-restore").disabled',a,'recoverable draft')
 b=tab();wait('document.querySelector("[data-k=body]")!==null',b,'blocker page')
 ev('''new Promise((resolve,reject)=>{const r=indexedDB.open("itonami.office.zuhyo.v2",1);r.onsuccess=()=>{const d=r.result,t=d.transaction("records","readwrite"),s=t.objectStore("records");window.__release=false;function hold(){if(window.__release)return;const g=s.get("current");g.onsuccess=()=>{if(!window.__held){window.__held=true;resolve(true)}hold()};g.onerror=()=>reject(Error("hold"))}t.oncomplete=()=>d.close();t.onabort=()=>reject(Error("abort"));hold()};r.onerror=()=>reject(Error("open"))})''',b,True)
 ev('window.__tx=IDBDatabase.prototype.transaction;IDBDatabase.prototype.transaction=function(...args){if(args[1]==="readonly")window.__readStarted=true;return window.__tx.apply(this,args)};document.getElementById("draft-restore").click()',a)
 wait('window.__readStarted===true',a,'restore read queued')
 pipe.send('Runtime.evaluate',{'expression':'document.getElementById("draft-discard").click()'},a);dialog(a)
 wait('document.getElementById("draft-recovery").hidden',a,'discard')
 ev('window.__release=true',b);time.sleep(1)
 assert ev('document.getElementById("draft-recovery").hidden && document.querySelector("[data-k=body]").value==="保存済み" && sessionStorage.getItem("itonami.zuhyo.candidate.zs1.session-draft.v1")===null',a)
 report={'status':'PASS_IDB_DRAFT_DISCARD_RACE','scope':'synthetic same-origin Chrome with blocked IndexedDB transaction; no OS, crash or release'};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],flush=True)
finally:pipe.close();server.shutdown();server.server_close()
