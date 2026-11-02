#!/usr/bin/env python3
"""Check the browser warning for a failed synthetic edit, not crash durability.
Usage: python3 scripts/check-browser-unload.py AMU_DIR BUILD_DIR OUTPUT_DIR CHROME
"""
import functools,http.server,importlib.util,json,threading,time,sys
from pathlib import Path
amu,build,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:]);out.mkdir(parents=True,exist_ok=False);profile=out/'profile';profile.mkdir()
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(build)));threading.Thread(target=server.serve_forever,daemon=True).start();pipe=browser.Pipe(str(chrome),profile)
try:
 target=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];session=pipe.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId']
 pipe.call('Page.enable',{},session);pipe.call('Network.enable',{},session);pipe.call('Page.navigate',{'url':f'http://127.0.0.1:{server.server_port}/index.html'},session)
 def ev(expr):
  r=pipe.call('Runtime.evaluate',{'expression':expr,'returnByValue':True},session)
  if 'exceptionDetails' in r: raise ValueError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(expr,label):
  end=time.time()+90
  while time.time()<end:
   if ev(expr): return
   time.sleep(.2)
  raise TimeoutError(label+': '+str(ev("document.getElementById('status')?.textContent")))
 wait("document.querySelector('[data-k=title]') !== null",'initial')
 rect=ev("(()=>{const r=document.querySelector('[data-k=title]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
 pipe.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':rect['x'],'y':rect['y'],'button':'left','clickCount':1},session)
 pipe.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':rect['x'],'y':rect['y'],'button':'left','clickCount':1},session)
 ev("document.querySelector('[data-k=title]').select()")
 pipe.call('Input.insertText',{'text':'保存済み'},session)
 wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('保存済み') && document.getElementById('status').textContent === '保存しました'",'baseline save')
 saved=ev("localStorage.getItem('itonami.zuhyo.candidate.zs1')")
 ev("window.testSetter=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw Error('quota')};(()=>{let e=document.querySelector('[data-k=title]');e.value='未保存';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
 wait("document.getElementById('status').textContent.includes('保存できませんでした')",'failed edit')
 if ev("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != saved: raise ValueError('stored value changed')
 pipe.send('Page.reload',{},session);handled=False
 for _ in range(40):
  try:
   pipe.call('Page.handleJavaScriptDialog',{'accept':False},session,timeout=5);handled=True;break
  except RuntimeError: time.sleep(.1)
 if not handled: raise ValueError('beforeunload dialog not observed')
 dialogs=[e for e in pipe.events if e.get('method')=='Page.javascriptDialogOpening' and e.get('params',{}).get('type')=='beforeunload']
 if len(dialogs)!=1: raise ValueError('beforeunload event missing or duplicated')
 if ev("document.querySelector('[data-k=title]')?.value")!='未保存' or ev("localStorage.getItem('itonami.zuhyo.candidate.zs1')")!=saved: raise ValueError('cancelled reload lost state')
 ev("Storage.prototype.setItem=window.testSetter;document.getElementById('retry-save').click()")
 wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('未保存') && document.getElementById('retry-save').hidden",'retry save')
 mark=len(pipe.events);pipe.call('Page.reload',{},session)
 wait("document.querySelector('[data-k=title]')?.value === '未保存'",'clean reload')
 if any(e.get('method')=='Page.javascriptDialogOpening' and e.get('params',{}).get('type')=='beforeunload' for e in pipe.events[mark:]): raise ValueError('clean reload warned')
 requests=[e['params']['request']['url'] for e in pipe.events if e.get('method')=='Network.requestWillBeSent']
 if not requests or any(not u.startswith(f'http://127.0.0.1:{server.server_port}/') for u in requests): raise ValueError('unexpected request')
 (out/'result.json').write_text(json.dumps({'status':'PASS','checks':['activated-dirty-reload-warning','cancel-retains-input','retry','clean-reload-no-warning'],'limitations':['browser may suppress beforeunload','does not provide crash recovery']},indent=2)+'\n');print('PASS_BROWSER_UNLOAD_WARNING')
finally:
 pipe.close();server.shutdown();server.server_close()
