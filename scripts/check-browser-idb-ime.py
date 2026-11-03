#!/usr/bin/env python3
"""Exercise synthetic CDP IME input on an isolated loopback browser candidate.

Usage: python3 scripts/check-browser-ime.py AMU_DIR BUILD_DIR OUTPUT_DIR CHROME
This does not qualify an OS IME or production release.
"""
import functools,http.server,importlib.util,json,threading,time,sys
from pathlib import Path
amu,build,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:])
out.mkdir(parents=True,exist_ok=False);profile=out/'profile';profile.mkdir()
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(build)));threading.Thread(target=server.serve_forever,daemon=True).start();pipe=browser.Pipe(str(chrome),profile)
try:
 target=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];session=pipe.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId']
 pipe.call('Network.enable',{},session)
 pipe.call('Page.navigate',{'url':f'http://127.0.0.1:{server.server_port}/index.html'},session)
 def ev(expr,awaited=False):
  r=pipe.call('Runtime.evaluate',{'expression':expr,'returnByValue':True,'awaitPromise':awaited},session)
  if 'exceptionDetails' in r: raise ValueError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(expr,label):
  end=time.time()+90
  while time.time()<end:
   if ev(expr): return
   time.sleep(.2)
  raise TimeoutError(label+': '+str(ev("document.getElementById('status')?.textContent")))
 def read_saved():
  return ev('new Promise((resolve,reject)=>{const r=indexedDB.open("itonami.office.zuhyo.v2",1);r.onsuccess=()=>{const d=r.result,t=d.transaction("records","readonly"),g=t.objectStore("records").get("current");g.onsuccess=()=>resolve(g.result?.value??null);g.onerror=()=>reject(Error("read"));t.oncomplete=()=>d.close()};r.onerror=()=>reject(Error("open"))})',True)
 def wait_saved(text,label):
  end=time.time()+90
  while time.time()<end:
   value=read_saved()
   if value is not None and text in value and ev("document.getElementById('status').textContent==='保存しました'"):return value
   time.sleep(.2)
  raise TimeoutError(label)
 wait("document.querySelector('[data-k=title]') !== null",'initial')
 ev("(()=>{let e=document.querySelector('[data-k=title]');window.imeEvents=[];for(const t of ['compositionstart','compositionupdate','compositionend','beforeinput','input'])e.addEventListener(t,x=>window.imeEvents.push({type:x.type,composing:!!x.isComposing,trusted:x.isTrusted}));e.focus();e.select();})()")
 pipe.call('Input.imeSetComposition',{'text':'日本','selectionStart':2,'selectionEnd':2},session)
 wait("document.querySelector('[data-k=title]')?.value.includes('日本')",'composition text')
 time.sleep(1)
 mid={'value':ev("document.querySelector('[data-k=title]').value"),'stored':read_saved(),'events':ev('window.imeEvents')}
 if mid['stored'] is not None: raise ValueError('uncommitted composition saved')
 pipe.call('Input.insertText',{'text':'日本語'},session)
 wait_saved('日本語','committed IME')
 # Exercise the multiline editor with CDP composition and an actual Enter key.
 ev("document.querySelector('[data-k=body]').focus();document.querySelector('[data-k=body]').select()")
 pipe.call('Input.imeSetComposition',{'text':'本文','selectionStart':2,'selectionEnd':2},session)
 wait("document.querySelector('[data-k=body]')?.value==='本文'",'textarea composition')
 if '本文' in read_saved(): raise ValueError('uncommitted textarea composition saved')
 pipe.call('Input.insertText',{'text':'本文'},session)
 wait_saved('本文','textarea IME commit')
 ev("document.querySelector('[data-k=body]').focus();document.querySelector('[data-k=body]').setSelectionRange(2,2)")
 pipe.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Enter','code':'Enter','text':'\r','unmodifiedText':'\r','windowsVirtualKeyCode':13,'nativeVirtualKeyCode':13},session)
 pipe.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'nativeVirtualKeyCode':13},session)
 wait("document.querySelector('[data-k=body]')?.value === '本文\\n'",'textarea enter')
 wait_saved('本文\n','textarea enter saved')
 pipe.call('Input.insertText',{'text':'二行目'},session)
 wait("document.querySelector('[data-k=body]')?.value==='本文\\n二行目'",'textarea multiline')
 if not wait_saved('二行目','textarea multiline saved').startswith('ZS2|'):raise ValueError('multiline snapshot missing')
 result={'status':'PASS_IDB_CDP_SYNTHETIC_IME','mid':mid,'final':{'value':ev("document.querySelector('[data-k=title]').value"),'events':ev('window.imeEvents')},'limitations':['CDP-generated browser events; not a physical OS IME test','loopback local candidate; not a release']}
 if result['final']['value'] != '日本語': raise ValueError('composition commit mismatch')
 requests=[e['params']['request']['url'] for e in pipe.events if e.get('method')=='Network.requestWillBeSent']
 if not requests or any(not u.startswith(f'http://127.0.0.1:{server.server_port}/') for u in requests): raise ValueError('unexpected network request')
 (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
finally:
 pipe.close();server.shutdown();server.server_close()
