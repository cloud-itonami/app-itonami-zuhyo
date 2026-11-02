#!/usr/bin/env python3
"""Verify ZS2 downgrade refusal and ZS1 multiline preservation on loopback.

Usage: python3 scripts/check-multiline-compat.py AMU_DIR NEW_BUILD OLD_BUILD OUTPUT_DIR CHROME
Synthetic data only; old candidate and current candidate share one isolated origin.
"""
import functools, http.server, importlib.util, json, shutil, sys, threading, time
from pathlib import Path

if len(sys.argv) != 6: raise SystemExit(__doc__)
amu,new,old,out,chrome = map(lambda s:Path(s).resolve(),sys.argv[1:])
out.mkdir(parents=True,exist_ok=False); (out/'profile').mkdir()
shutil.copytree(new,out/'new'); shutil.copytree(old,out/'old')
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py')
browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(out)))
threading.Thread(target=server.serve_forever,daemon=True).start();pipe=browser.Pipe(str(chrome),out/'profile')
key='itonami.zuhyo.candidate.zs1'; base=f'http://127.0.0.1:{server.server_port}/'
try:
 target=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];session=pipe.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId']
 pipe.call('Network.enable',{},session);pipe.call('Page.enable',{},session)
 def ev(expr):
  r=pipe.call('Runtime.evaluate',{'expression':expr,'returnByValue':True},session)
  if 'exceptionDetails' in r: raise ValueError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(expr,label):
  until=time.time()+90
  while time.time()<until:
   try:
    if ev(expr): return
   except RuntimeError as e:
    if not any(x in str(e) for x in ('Execution context was destroyed','Cannot find context with specified id','Inspected target navigated or closed')): raise
   time.sleep(.2)
  raise TimeoutError(label+': '+str(ev("document.getElementById('status')?.textContent")))
 def navigate(path):
  pipe.call('Page.navigate',{'url':base+path+'/index.html'},session)
 def input_(key_,text):
  ev("(()=>{const x=document.querySelector('[data-k="+key_+"]');x.value="+json.dumps(text,ensure_ascii=False)+";x.dispatchEvent(new Event('input',{bubbles:true}));})()")
 navigate('new');wait("document.querySelector('[data-k=body]')?.tagName==='TEXTAREA'",'new initial')
 text='最初😀\n第二行';input_('body',text)
 wait("localStorage.getItem("+json.dumps(key)+")?.startsWith('ZS2|') && document.getElementById('status').textContent==='保存しました'",'multiline saved')
 saved=ev('localStorage.getItem('+json.dumps(key)+')')
 navigate('old');wait("document.getElementById('status')?.textContent.includes('開けません')",'old rejects ZS2')
 if ev('localStorage.getItem('+json.dumps(key)+')') != saved or ev("document.querySelector('[data-k=body]') !== null"): raise ValueError('old editor accepted or modified ZS2')
 navigate('new');wait("document.querySelector('[data-k=body]')?.value === "+json.dumps(text,ensure_ascii=False),'new reopens')
 if ev('localStorage.getItem('+json.dumps(key)+')') != saved: raise ValueError('new reopen changed bytes')
 # Prior ZS1 with line breaks remains readable and upgrades on the next edit.
 legacy='ZS1|'+saved[4:];ev('localStorage.setItem('+json.dumps(key)+','+json.dumps(legacy,ensure_ascii=False)+')');navigate('new')
 wait("document.querySelector('[data-k=body]')?.value === "+json.dumps(text,ensure_ascii=False),'legacy multiline')
 input_('heading','編集後');wait("localStorage.getItem("+json.dumps(key)+")?.startsWith('ZS2|') && document.getElementById('status').textContent==='保存しました'",'legacy upgrade')
 if ev("document.querySelector('[data-k=body]')?.value") != text: raise ValueError('legacy line breaks lost')
 # Textarea/input normalization must not silently alter persisted CR bytes.
 current=ev('localStorage.getItem('+json.dumps(key)+')');assert text in current
 cr=current.replace(text,text.replace('\n','\r'),1);ev('localStorage.setItem('+json.dumps(key)+','+json.dumps(cr,ensure_ascii=False)+')');navigate('new')
 wait("document.getElementById('status')?.textContent.includes('開けません')",'CR refusal')
 if ev('localStorage.getItem('+json.dumps(key)+')')!=cr: raise ValueError('CR snapshot overwritten')
 requests=[e['params']['request']['url'] for e in pipe.events if e.get('method')=='Network.requestWillBeSent']
 if not requests or any(not x.startswith(base) for x in requests):raise ValueError('unexpected request')
 (out/'result.json').write_text(json.dumps({'status':'PASS','checks':['ZS2 old editor refuses without write','new editor reopens exact text','ZS1 multiline upgrade','CR normalization refusal','loopback only'],'scope':'synthetic candidate, no real-user migration or release'},ensure_ascii=False,indent=2)+'\n')
 print('PASS_ZUHYO_MULTILINE_COMPAT')
finally:
 pipe.close();server.shutdown();server.server_close()
