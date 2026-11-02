#!/usr/bin/env python3
"""Exercise a storage change by a non-cooperating tab during Wasm dispatch.

Usage: script AMU BUILD OUT CHROME bunsho|hyokeisan|zuhyo
Synthetic Chrome and loopback only. The final check is not atomic CAS.
"""
import functools,http.server,importlib.util,json,sys,threading,time
from pathlib import Path
if len(sys.argv)!=6:raise SystemExit(__doc__)
amu,build,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:5]);name=sys.argv[5]
field,key={'bunsho':('b0','itonami.bunsho.candidate.bs1'),'hyokeisan':('c0','itonami.hyokeisan.candidate.hs1'),'zuhyo':('body','itonami.zuhyo.candidate.zs1')}[name]
out.mkdir(parents=True,exist_ok=False);(out/'profile').mkdir()
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(build)));threading.Thread(target=server.serve_forever,daemon=True).start();p=browser.Pipe(str(chrome),out/'profile');url=f'http://127.0.0.1:{server.server_port}/index.html'
try:
 def tab():
  t=p.call('Target.createTarget',{'url':'about:blank'})['targetId'];s=p.call('Target.attachToTarget',{'targetId':t,'flatten':True})['sessionId'];p.call('Page.enable',{},s);p.call('Page.navigate',{'url':url},s);return s
 a=tab()
 def ev(expr,s=a):
  r=p.call('Runtime.evaluate',{'expression':expr,'returnByValue':True},s)
  if 'exceptionDetails' in r:raise ValueError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(expr,label,s=a):
  end=time.time()+60
  while time.time()<end:
   try:
    if ev(expr,s):return
   except RuntimeError as e:
    if not any(x in str(e) for x in ('Execution context was destroyed','Cannot find context with specified id')):raise
   time.sleep(.1)
  raise TimeoutError(label+': '+str(ev("document.getElementById('status')?.textContent",s)))
 sel=json.dumps('[data-k='+field+']');k=json.dumps(key);j=json.dumps(key+'.session-draft.v1')
 def enter(value):ev('(()=>{let e=document.querySelector('+sel+');e.value='+json.dumps(value)+';e.dispatchEvent(new Event("input",{bubbles:true}))})()')
 wait('document.querySelector('+sel+')!==null','initial');enter('old valid');wait('localStorage.getItem('+k+')?.includes("old valid")','old')
 old=ev('localStorage.getItem('+k+')');enter('current valid');wait('localStorage.getItem('+k+')?.includes("current valid")','current')
 current=ev('localStorage.getItem('+k+')');enter('newest valid');wait('localStorage.getItem('+k+')?.includes("newest valid")','newest')
 newest=ev('localStorage.getItem('+k+')')
 b=tab();wait('document.querySelector('+sel+')!==null','second tab',b)
 ev('''(()=>{const original=Worker.prototype.postMessage;window.__held=false;window.__release=()=>{const [w,d]=window.__pair;window.__pair=null;original.call(w,d)};Worker.prototype.postMessage=function(d){if(!window.__held&&d?.args?.[0]==='step'){window.__held=true;window.__pair=[this,d];return}return original.call(this,d)}})()''')
 enter('pending local');wait('window.__held===true','held worker')
 ev('localStorage.setItem('+k+','+json.dumps(old)+')',b);assert ev('localStorage.getItem('+k+')')==old
 ev('window.__release()')
 wait('document.getElementById("status").textContent.includes("別のタブ") || localStorage.getItem('+k+')?.includes("pending local")','save result')
 actual=ev('localStorage.getItem('+k+')');preserved=actual==old
 result={'status':'PASS_INFLIGHT_STORAGE_REFUSAL' if preserved else 'FAIL_EXTERNAL_WRITE_OVERWRITTEN','otherValidSnapshotPreserved':preserved,'pendingFieldPreserved':ev('document.querySelector('+sel+').value === "pending local"'),'journalPreserved':ev('(JSON.parse(sessionStorage.getItem('+j+')||"{}")?.entries||[]).some(e=>e[0]==='+json.dumps(field)+'&&e[1]==="pending local")'),'retryShown':ev('!document.getElementById("retry-save").hidden'),'scope':'synthetic non-cooperating tab during Wasm step; final check is not atomic CAS'}
 # A fresh tab previews a valid backup, then pauses its confirmation's view
 # worker while the other tab installs a different valid snapshot.
 ev('localStorage.setItem('+k+','+json.dumps(old)+')',b)
 c=tab();wait('document.querySelector('+sel+')!==null','restore tab',c)
 backup=out/'backup.txt';backup.write_text(current,encoding='utf-8')
 p.call('DOM.enable',{},c);document=p.call('DOM.getDocument',{},c)['root']['nodeId']
 file=p.call('DOM.querySelector',{'nodeId':document,'selector':'#backup-file'},c)['nodeId']
 p.call('DOM.setFileInputFiles',{'nodeId':file,'files':[str(backup)]},c)
 wait('document.getElementById("backup-dialog").open','backup preview',c)
 before=ev('Object.keys(localStorage).filter(x=>x.startsWith('+json.dumps(key+'.preimport.')+')).sort()',c)
 ev("""(()=>{const original=Worker.prototype.postMessage;window.__held=false;window.__release=()=>{const [w,d]=window.__pair;window.__pair=null;original.call(w,d)};Worker.prototype.postMessage=function(d){if(!window.__held&&d?.args?.[0]==='view'){window.__held=true;window.__pair=[this,d];return}return original.call(this,d)}})()""",c)
 ev('document.getElementById("backup-confirm").click()',c);wait('window.__held===true','held restore view',c)
 ev('localStorage.setItem('+k+','+json.dumps(newest)+')',b);ev('window.__release()',c)
 wait('document.getElementById("status").textContent.includes("復元できません") || localStorage.getItem('+k+')==='+json.dumps(current),'restore result',c)
 result['restoreOtherSnapshotPreserved']=ev('localStorage.getItem('+k+')',c)==newest
 result['restoreNoStaleBackup']=ev('Object.keys(localStorage).filter(x=>x.startsWith('+json.dumps(key+'.preimport.')+')).sort()',c)==before
 result['status']='PASS_INFLIGHT_STORAGE_REFUSAL' if all(result[x] for x in ['otherValidSnapshotPreserved','pendingFieldPreserved','journalPreserved','retryShown','restoreOtherSnapshotPreserved','restoreNoStaleBackup']) else 'FAIL_EXTERNAL_WRITE_OVERWRITTEN'
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(name,json.dumps(result),flush=True)
 if result['status']!='PASS_INFLIGHT_STORAGE_REFUSAL':raise ValueError('in-flight external write was overwritten or input lost')
finally:p.close();server.shutdown();server.server_close()
