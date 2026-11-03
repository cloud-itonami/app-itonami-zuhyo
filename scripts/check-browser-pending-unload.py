#!/usr/bin/env python3
"""Verify an in-flight Zuhyo slide addition warns on reload and persists.

Usage: script AMU BUILD NEW_OUTPUT CHROME add
Uses synthetic loopback Chrome only; beforeunload may be suppressed by browsers.
"""
import functools, http.server, importlib.util, sys, threading, time
from pathlib import Path
amu, build, out, chrome, button = sys.argv[1:]
out = Path(out); out.mkdir(parents=True, exist_ok=False); (out/'profile').mkdir()
spec=importlib.util.spec_from_file_location('browser',Path(amu)/'scripts/seed/check-wasm32-browser.py'); browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=build));threading.Thread(target=server.serve_forever,daemon=True).start();p=browser.Pipe(chrome,out/'profile')
try:
 t=p.call('Target.createTarget',{'url':'about:blank'})['targetId'];s=p.call('Target.attachToTarget',{'targetId':t,'flatten':True})['sessionId'];p.call('Page.enable',{},s);p.call('Page.navigate',{'url':f'http://127.0.0.1:{server.server_port}/index.html'},s)
 def ev(x):
  r=p.call('Runtime.evaluate',{'expression':x,'returnByValue':True},s)
  if 'exceptionDetails' in r: raise ValueError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(x):
  end=time.time()+40
  while time.time()<end:
   if ev(x): return
   time.sleep(.1)
  raise ValueError('timeout: '+x)
 wait('document.querySelector("[data-k='+button+']") !== null')
 assert not ev('(()=>{let e=new Event("beforeunload",{cancelable:true});dispatchEvent(e);return e.defaultPrevented})()')
 ev('''(()=>{let original=Worker.prototype.postMessage;window.__held=false;window.__release=()=>original.call(...window.__pair);Worker.prototype.postMessage=function(d){if(!window.__held&&d?.args?.[0]==='step'){window.__held=true;window.__pair=[this,d];return}return original.call(this,d)}})()''')
 rect=ev('(()=>{let r=document.querySelector("[data-k='+button+']").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()')
 for typ in ('mousePressed','mouseReleased'):p.call('Input.dispatchMouseEvent',{'type':typ,'x':rect['x'],'y':rect['y'],'button':'left','clickCount':1},s)
 wait('window.__held')
 warning=ev('(()=>{let e=new Event("beforeunload",{cancelable:true});dispatchEvent(e);return e.defaultPrevented})()')
 print('held-warning',warning,flush=True)
 if not warning: raise ValueError('in-flight action is not protected')
 p.send('Page.reload',{},s)
 for i in range(30):
  try:p.call('Page.handleJavaScriptDialog',{'accept':False},s,timeout=2);break
  except RuntimeError:time.sleep(.1)
 else:raise ValueError('reload warning missing')
 ev('window.__release()');wait('document.getElementById("status").textContent === "保存しました"')
 assert not ev('(()=>{let e=new Event("beforeunload",{cancelable:true});dispatchEvent(e);return e.defaultPrevented})()')
 assert ev('document.querySelector(".stats").textContent.trim()') == '2 / 2'
 ev('window.__old=true');p.call('Page.reload',{},s)
 wait('window.__old!==true && document.querySelector(".stats")?.textContent.trim()==="2 / 2"')
 print('PASS_HELD_ACTION_WARNING_AND_CLEAN',flush=True)
finally:p.close();server.shutdown();server.server_close()
