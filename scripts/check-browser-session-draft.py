#!/usr/bin/env python3
"""Check same-tab session draft recovery with synthetic data in Chrome.

Usage: python3 scripts/check-browser-session-draft.py AMU_DIR BUILD_DIR OUTPUT_DIR CHROME
This does not establish closed-tab, browser-crash, OS, or power-loss durability.
"""
import functools,http.server,importlib.util,json,threading,time,sys
from pathlib import Path
amu,build,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:]);out.mkdir(parents=True,exist_ok=False);profile=out/'profile';profile.mkdir();downloads=out/'downloads';downloads.mkdir();program_sha=json.loads((build/'build-receipt.json').read_text())['wasmSha256']
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(build)));threading.Thread(target=server.serve_forever,daemon=True).start();pipe=browser.Pipe(str(chrome),profile);url=f'http://127.0.0.1:{server.server_port}/index.html'
try:
 target=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];session=pipe.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId'];pipe.call('Page.enable',{},session);pipe.call('Network.enable',{},session);pipe.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(downloads)});pipe.call('Page.navigate',{'url':url},session)
 def evaluate(expr,which=session):
  r=pipe.call('Runtime.evaluate',{'expression':expr,'returnByValue':True},which)
  if 'exceptionDetails' in r: raise ValueError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(expr,label,which=session):
  end=time.time()+90
  while time.time()<end:
   try:
    if evaluate(expr,which): return
   except RuntimeError as error:
    if not any(message in str(error) for message in ('Inspected target navigated or closed', 'Execution context was destroyed', 'Cannot find context with specified id')): raise
   time.sleep(.2)
  raise TimeoutError(label+': '+str(evaluate("document.getElementById('status')?.textContent",which)))
 def activate(which=session):
  pipe.call('Page.bringToFront',{},which)
  rect=evaluate("(()=>{const r=document.querySelector('[data-k=title]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()",which)
  pipe.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':rect['x'],'y':rect['y'],'button':'left','clickCount':1},which);pipe.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':rect['x'],'y':rect['y'],'button':'left','clickCount':1},which)
 def type_(value,which=session):
  evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value="+json.dumps(value,ensure_ascii=False)+";e.dispatchEvent(new Event('input',{bubbles:true}));})()",which)
 def dialog(accept,kind):
  for _ in range(40):
   try: pipe.call('Page.handleJavaScriptDialog',{'accept':accept},session,timeout=5);break
   except RuntimeError: time.sleep(.1)
  else: raise ValueError(kind+' dialog not observed')
  if not any(e.get('method')=='Page.javascriptDialogOpening' and e.get('params',{}).get('type')==kind for e in pipe.events): raise ValueError(kind+' event missing')
 def reload_accept():
  evaluate('window.__oldDocument=true');pipe.send('Page.reload',{},session);dialog(True,'beforeunload');wait('window.__oldDocument !== true','new document');wait("document.querySelector('[data-k=title]') !== null",'reloaded UI')
 wait("document.querySelector('[data-k=title]') !== null",'initial')

 # A failed journal read must freeze editing until a successful retry; it must
 # neither overwrite a retained record nor discard it without inspection.
 evaluate("sessionStorage.setItem('itonami.zuhyo.candidate.zs1.session-draft.v1','{retained')")
 injected=pipe.call('Page.addScriptToEvaluateOnNewDocument',{'source':"window.__draftGet=Storage.prototype.getItem;Storage.prototype.getItem=function(k){if(this===sessionStorage && k==='itonami.zuhyo.candidate.zs1.session-draft.v1')throw Error('read denied');return window.__draftGet.call(this,k)}"},session)['identifier']
 evaluate('window.__oldDocument=true');pipe.call('Page.reload',{},session);wait('window.__oldDocument !== true','new document for read failure');wait("document.querySelector('[data-k=title]') !== null",'UI after read failure')
 if not evaluate("document.getElementById('app').inert && [...document.querySelectorAll('#app input,#app button')].every(e=>e.disabled) && !document.getElementById('draft-recovery').hidden && document.getElementById('draft-retry-read') && !document.getElementById('draft-retry-read').hidden && document.getElementById('draft-discard').disabled && document.getElementById('draft-download').disabled"): raise ValueError('failed journal read did not freeze editor')
 evaluate("document.getElementById('draft-retry-read').click()")
 if not evaluate("document.getElementById('app').inert && document.getElementById('draft-discard').disabled"): raise ValueError('failed retry unlocked editor')
 pipe.call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':injected},session);evaluate("Storage.prototype.getItem=window.__draftGet;document.getElementById('draft-retry-read').click()")
 wait("!document.getElementById('draft-recovery').hidden && document.getElementById('draft-retry-read').hidden && !document.getElementById('draft-discard').disabled",'retained record offered after retry')
 if evaluate("sessionStorage.getItem('itonami.zuhyo.candidate.zs1.session-draft.v1')")!='{retained' or not evaluate("document.getElementById('app').inert && document.getElementById('draft-restore').disabled"): raise ValueError('retained record was altered or applied')
 pipe.send('Runtime.evaluate',{'expression':"document.getElementById('draft-discard').click()"},session);dialog(True,'confirm');wait("document.getElementById('draft-recovery').hidden && !document.getElementById('app').inert",'discard retained record')
 # A read failure with no journal also stays locked until absence is verified.
 injected=pipe.call('Page.addScriptToEvaluateOnNewDocument',{'source':"window.__draftGet=Storage.prototype.getItem;Storage.prototype.getItem=function(k){if(this===sessionStorage && k==='itonami.zuhyo.candidate.zs1.session-draft.v1')throw Error('read denied');return window.__draftGet.call(this,k)}"},session)['identifier']
 evaluate('window.__oldDocument=true');pipe.call('Page.reload',{},session);wait('window.__oldDocument !== true','new document for empty read failure');wait("document.querySelector('[data-k=title]') !== null",'UI after empty read failure')
 if not evaluate("document.getElementById('app').inert && !document.getElementById('draft-retry-read').hidden"): raise ValueError('empty journal read failure unlocked editor')
 pipe.call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':injected},session);evaluate("Storage.prototype.getItem=window.__draftGet;document.getElementById('draft-retry-read').click()")
 wait("document.getElementById('draft-recovery').hidden && !document.getElementById('app').inert",'empty journal read verified')
 activate();evaluate("document.querySelector('[data-k=title]').select()");pipe.call('Input.insertText',{'text':'保存済み'},session)

 wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('保存済み') && document.getElementById('status').textContent === '保存しました'",'baseline')
 saved=evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")
 evaluate("window.localSetter=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(this===localStorage && k==='itonami.zuhyo.candidate.zs1')throw Error('quota');return window.localSetter.call(this,k,v)}")
 type_('未保存A');wait("document.getElementById('status').textContent.includes('保存できませんでした')",'failed save')
 if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")!=saved or not evaluate("sessionStorage.getItem('itonami.zuhyo.candidate.zs1.session-draft.v1')?.includes('未保存A')"): raise ValueError('journal not created safely')
 reload_accept();wait("!document.getElementById('draft-recovery').hidden",'recoverable draft')
 if evaluate("document.getElementById('draft-restore').disabled") or not evaluate("document.getElementById('app').inert && [...document.querySelectorAll('#app input,#app button')].every(e=>e.disabled)"): raise ValueError('matching draft not offered safely')
 if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")!=saved: raise ValueError('recovery auto-saved')
 evaluate("document.getElementById('draft-restore').click()")
 if evaluate("document.querySelector('[data-k=title]').value")!='未保存A' or evaluate("document.querySelector('[data-k=title]').disabled") or evaluate("document.getElementById('retry-save').hidden"): raise ValueError('matching draft not restored')
 evaluate("document.getElementById('retry-save').click()")
 wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('未保存A') && document.getElementById('retry-save').hidden",'restored save')
 if evaluate("sessionStorage.getItem('itonami.zuhyo.candidate.zs1.session-draft.v1')") is not None: raise ValueError('saved draft not cleared')
 evaluate("window.localSetter=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(this===localStorage && k==='itonami.zuhyo.candidate.zs1')throw Error('quota');return window.localSetter.call(this,k,v)}")
 type_('衝突下書き');wait("document.getElementById('status').textContent.includes('保存できませんでした')",'conflicting draft')
 raw=evaluate("sessionStorage.getItem('itonami.zuhyo.candidate.zs1.session-draft.v1')")
 other=pipe.call('Target.createTarget',{'url':url})['targetId'];second=pipe.call('Target.attachToTarget',{'targetId':other,'flatten':True})['sessionId'];pipe.call('Page.enable',{},second);wait("document.querySelector('[data-k=title]') !== null",'other tab',second)
 if evaluate("sessionStorage.getItem('itonami.zuhyo.candidate.zs1.session-draft.v1')",second) is not None: raise ValueError('test tab inherited draft')
 type_('他タブ保存',second);wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('他タブ保存')",'other tab saved',second)
 other_saved=evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')");activate();reload_accept();wait("!document.getElementById('draft-recovery').hidden",'stale draft')
 if not evaluate("document.getElementById('draft-restore').disabled") or not evaluate("document.getElementById('app').inert"): raise ValueError('stale draft could overwrite')
 if evaluate("sessionStorage.getItem('itonami.zuhyo.candidate.zs1.session-draft.v1')")!=raw or evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")!=other_saved: raise ValueError('stale draft altered')
 evaluate("document.getElementById('draft-download').click()")
 f=downloads/'zuhyo-unsaved-draft.json';end=time.time()+90
 while time.time()<end and not f.exists(): time.sleep(.2)
 if not f.exists() or f.read_text()!=raw: raise ValueError('stale export mismatch')
 pipe.send('Runtime.evaluate',{'expression':"document.getElementById('draft-discard').click()"},session);dialog(True,'confirm')
 wait("document.getElementById('draft-recovery').hidden && !document.getElementById('app').inert",'explicit discard')
 if evaluate("sessionStorage.getItem('itonami.zuhyo.candidate.zs1.session-draft.v1')") is not None or evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")!=other_saved: raise ValueError('discard affected saved state')
 pipe.call('Target.closeTarget',{'targetId':other})
 # A malformed retained record is never silently discarded or applied.
 evaluate("sessionStorage.setItem('itonami.zuhyo.candidate.zs1.session-draft.v1','{bad')")
 evaluate('window.__oldDocument=true');pipe.call('Page.reload',{},session);wait('window.__oldDocument !== true','new document for malformed draft');wait("!document.getElementById('draft-recovery').hidden",'malformed draft')
 if not evaluate("document.getElementById('draft-restore').disabled && document.getElementById('app').inert") or evaluate("sessionStorage.getItem('itonami.zuhyo.candidate.zs1.session-draft.v1')")!='{bad' or evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")!=other_saved: raise ValueError('malformed draft overwritten or applied')
 pipe.send('Runtime.evaluate',{'expression':"document.getElementById('draft-discard').click()"},session);dialog(True,'confirm');wait("document.getElementById('draft-recovery').hidden",'discard malformed draft')
 # The saved snapshot can change after the recovery panel appears.
 evaluate("sessionStorage.setItem('itonami.zuhyo.candidate.zs1.session-draft.v1',JSON.stringify({version:1,program:"+json.dumps(program_sha)+",base:localStorage.getItem('itonami.zuhyo.candidate.zs1'),baseState:localStorage.getItem('itonami.zuhyo.candidate.zs1'),entries:[['title','表示中の下書き']]}));window.__oldDocument=true")
 pipe.call('Page.reload',{},session);wait('window.__oldDocument !== true','new document for recovery race');wait("!document.getElementById('draft-recovery').hidden && !document.getElementById('draft-restore').disabled",'matching panel before race')
 race_raw=evaluate("sessionStorage.getItem('itonami.zuhyo.candidate.zs1.session-draft.v1')")
 racer=pipe.call('Target.createTarget',{'url':url})['targetId'];racer_session=pipe.call('Target.attachToTarget',{'targetId':racer,'flatten':True})['sessionId'];wait("document.querySelector('[data-k=title]') !== null",'racing tab',racer_session)
 type_('後から保存',racer_session);wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('後から保存')",'racing save',racer_session)
 race_saved=evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')");activate();evaluate("document.getElementById('draft-restore').click()")
 if not evaluate("document.getElementById('draft-restore').disabled && document.getElementById('app').inert") or evaluate("sessionStorage.getItem('itonami.zuhyo.candidate.zs1.session-draft.v1')")!=race_raw or evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")!=race_saved: raise ValueError('recovery race not refused')
 pipe.send('Runtime.evaluate',{'expression':"document.getElementById('draft-discard').click()"},session);dialog(True,'confirm');wait("document.getElementById('draft-recovery').hidden",'discard raced draft');pipe.call('Target.closeTarget',{'targetId':racer})
 evaluate('window.__oldDocument=true');pipe.call('Page.reload',{},session);wait('window.__oldDocument !== true','reload after race');wait("document.querySelector('[data-k=title]')?.value === '後から保存'",'latest saved after race');other_saved=race_saved
 # A session journal failure is visible, with the typed input and saved state preserved.
 evaluate("window.bothSetter=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw Error('quota')}")
 type_('一時失敗');wait("document.getElementById('status').textContent.includes('保存できませんでした')",'session storage failure')
 if evaluate("document.getElementById('draft-notice').hidden") or evaluate("document.querySelector('[data-k=title]').value")!='一時失敗' or evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")!=other_saved: raise ValueError('journal failure not reported safely')
 evaluate("Storage.prototype.setItem=window.bothSetter;document.getElementById('retry-save').click()")
 wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('一時失敗') && document.getElementById('draft-notice').hidden && document.getElementById('retry-save').hidden",'retry after journal failure')
 # If the saved snapshot succeeds but journal cleanup fails, warn and quarantine the leftover on reload.
 evaluate("window.originalRemove=Storage.prototype.removeItem;Storage.prototype.removeItem=function(k){if(this===sessionStorage && k==='itonami.zuhyo.candidate.zs1.session-draft.v1')throw Error('quota');return window.originalRemove.call(this,k)}")
 type_('保存成功');wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('保存成功') && document.getElementById('draft-notice').textContent.includes('削除できません')",'draft cleanup failure')
 cleanup_saved=evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')");cleanup_raw=evaluate("sessionStorage.getItem('itonami.zuhyo.candidate.zs1.session-draft.v1')")
 if not cleanup_raw or not evaluate("document.getElementById('retry-save').hidden"): raise ValueError('cleanup failure not surfaced after saved edit')
 evaluate("Storage.prototype.removeItem=window.originalRemove;window.__oldDocument=true");pipe.call('Page.reload',{},session);wait('window.__oldDocument !== true','new document after cleanup failure');wait("!document.getElementById('draft-recovery').hidden",'quarantine leftover')
 if not evaluate("document.getElementById('draft-restore').disabled") or evaluate("sessionStorage.getItem('itonami.zuhyo.candidate.zs1.session-draft.v1')")!=cleanup_raw or evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")!=cleanup_saved: raise ValueError('stale leftover not quarantined')
 pipe.send('Runtime.evaluate',{'expression':"document.getElementById('draft-discard').click()"},session);dialog(True,'confirm');wait("document.getElementById('draft-recovery').hidden",'discard leftover')
 # A journal from different Wasm must not be applied even when saved bytes match.
 evaluate("sessionStorage.setItem('itonami.zuhyo.candidate.zs1.session-draft.v1',JSON.stringify({version:1,program:'0'.repeat(64),base:localStorage.getItem('itonami.zuhyo.candidate.zs1'),baseState:localStorage.getItem('itonami.zuhyo.candidate.zs1'),entries:[['title','異なる版']]}));window.__oldDocument=true")
 pipe.call('Page.reload',{},session);wait('window.__oldDocument !== true','new document for program mismatch');wait("!document.getElementById('draft-recovery').hidden",'program mismatch')
 if not evaluate("document.getElementById('draft-restore').disabled") or evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")!=cleanup_saved: raise ValueError('different program journal accepted')
 pipe.send('Runtime.evaluate',{'expression':"document.getElementById('draft-discard').click()"},session);dialog(True,'confirm');wait("document.getElementById('draft-recovery').hidden",'discard different-program draft')
 # A new unsaved document must match the exact initialized state, not just a null storage key.
 evaluate("localStorage.removeItem('itonami.zuhyo.candidate.zs1');sessionStorage.setItem('itonami.zuhyo.candidate.zs1.session-draft.v1',JSON.stringify({version:1,program:"+json.dumps(program_sha)+",base:null,baseState:'別の初期状態',entries:[['title','未保存新規']]}));window.__oldDocument=true")
 pipe.call('Page.reload',{},session);wait('window.__oldDocument !== true','new document for initial-state mismatch');wait("!document.getElementById('draft-recovery').hidden",'initial-state mismatch')
 if not evaluate("document.getElementById('draft-restore').disabled") or evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") is not None: raise ValueError('different initialized state accepted')
 pipe.send('Runtime.evaluate',{'expression':"document.getElementById('draft-discard').click()"},session);dialog(True,'confirm');wait("document.getElementById('draft-recovery').hidden",'discard mismatched initial draft')
 requests=[e['params']['request']['url'] for e in pipe.events if e.get('method')=='Network.requestWillBeSent']
 if not requests or any(not u.startswith(f'http://127.0.0.1:{server.server_port}/') for u in requests): raise ValueError('unexpected request')
 (out/'result.json').write_text(json.dumps({'status':'PASS','checks':['same-tab-reload','explicit-recovery-and-retry','stale-draft-refusal','raw-export','explicit-discard','malformed-draft-refusal','recovery-selection-race-refusal','journal-quota-and-retry','journal-cleanup-failure','initial-state-mismatch','program-digest-mismatch','journal-read-failure-retry','empty-journal-read-retry','loopback-only'],'limitations':['sessionStorage only','not crash or closed-tab durability','synthetic data']},indent=2)+'\n');print('PASS_BROWSER_SESSION_DRAFT')
finally:
 pipe.close();server.shutdown();server.server_close()
