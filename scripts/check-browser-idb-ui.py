#!/usr/bin/env python3
"""Exercise Zuhyo's experimental IDB UI and explicit legacy migration.

Usage: script AMU BUILD NEW_OUTPUT CHROME
Synthetic Chrome loopback only. No real user data, old-client coordination,
crash/power-loss, OS/QEMU or release qualification.
"""
import functools,http.server,importlib.util,json,sys,threading,time
from pathlib import Path
if len(sys.argv)!=5:raise SystemExit(__doc__)
amu,build,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:]);out.mkdir(parents=True,exist_ok=False);(out/'profile').mkdir();(out/'downloads').mkdir()
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(build)));threading.Thread(target=server.serve_forever,daemon=True).start();server2=None;pipe=browser.Pipe(str(chrome),out/'profile');port=server.server_port
try:
 def tab(host='127.0.0.1',seed=None,target_port=None):
  t=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];s=pipe.call('Target.attachToTarget',{'targetId':t,'flatten':True})['sessionId'];pipe.call('Page.enable',{},s)
  if seed:pipe.call('Page.addScriptToEvaluateOnNewDocument',{'source':seed},s)
  pipe.call('Page.navigate',{'url':f'http://{host}:{target_port or port}/index.html'},s);return s
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
 def state(s,key='current'):
  return ev('''new Promise((resolve,reject)=>{const r=indexedDB.open("itonami.office.zuhyo.v2",1);r.onsuccess=()=>{const d=r.result,t=d.transaction("records","readonly"),g=t.objectStore("records").get('''+json.dumps(key)+''');g.onsuccess=()=>resolve(g.result||null);g.onerror=()=>reject(Error("get"));t.oncomplete=()=>d.close()};r.onerror=()=>reject(Error("open"))})''',s,True)
 def enter(s,value):ev('(()=>{let e=document.querySelector("[data-k=body]");e.value='+json.dumps(value,ensure_ascii=False)+';e.dispatchEvent(new Event("input",{bubbles:true}))})()',s)
 def click(s,selector):
  rect=ev('(()=>{let r=document.querySelector('+json.dumps(selector)+').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()',s);pipe.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':rect['x'],'y':rect['y'],'button':'left','clickCount':1},s);pipe.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':rect['x'],'y':rect['y'],'button':'left','clickCount':1},s)
 pipe.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(out/'downloads')})
 a=tab();wait('document.querySelector("[data-k=body]")!==null',a,'initial');assert state(a) is None
 enter(a,'最初😀');wait('document.getElementById("status").textContent==="保存しました"',a,'first save');first=state(a);assert first['revision']==1 and '最初😀' in first['value'] and first['legacyAnchor'] is None
 assert ev('localStorage.getItem("itonami.zuhyo.candidate.zs1")',a) is None
 ev('window.__old=true',a);pipe.call('Page.reload',{},a);wait('window.__old!==true && document.querySelector("[data-k=body]")?.value==="最初😀"',a,'reload')
 b=tab();wait('document.querySelector("[data-k=body]")?.value==="最初😀"',b,'second tab')
 enter(a,'先行');wait('document.getElementById("status").textContent==="保存しました" && document.querySelector("[data-k=body]")?.value==="先行"',a,'winner');winner=state(a);assert winner['revision']==2
 enter(b,'保留');wait('document.getElementById("status").textContent.includes("別のタブ")',b,'stale refusal');assert state(b)==winner and ev('document.querySelector("[data-k=body]").value',b)=='保留'
 assert ev('JSON.parse(sessionStorage.getItem("itonami.zuhyo.candidate.zs1.session-draft.v1")).entries[0][1]',b)=='保留'
 stale_raw=ev('sessionStorage.getItem("itonami.zuhyo.candidate.zs1.session-draft.v1")',b)
 ev('window.__old=true',b);pipe.send('Page.reload',{},b)
 for _ in range(40):
  try:pipe.call('Page.handleJavaScriptDialog',{'accept':True},b,timeout=5);break
  except RuntimeError:
   try:
    if ev('window.__old!==true',b):break
   except RuntimeError:pass
   time.sleep(.1)
 else:raise ValueError('stale draft reload did not proceed')
 wait('window.__old!==true && !document.getElementById("draft-recovery").hidden && document.getElementById("draft-preview").textContent.includes("保留")',b,'stale revision draft preview')
 assert ev('document.getElementById("draft-restore").disabled',b) and ev('sessionStorage.getItem("itonami.zuhyo.candidate.zs1.session-draft.v1")',b)==stale_raw and state(b)==winner
 # Explicit preview and confirmation before transactional backup/restore.
 backup=out/'first.zs1';backup.write_text(first['value']);pipe.call('DOM.enable',{},a);root=pipe.call('DOM.getDocument',{},a)['root']['nodeId'];node=pipe.call('DOM.querySelector',{'nodeId':root,'selector':'#backup-file'},a)['nodeId'];pipe.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(backup)]},a)
 wait('document.getElementById("backup-dialog").open',a,'backup preview');assert state(a)==winner
 click(a,'#backup-confirm');wait('document.getElementById("status").textContent.includes("復元しました")',a,'backup restore');restored=state(a);assert restored['revision']==3 and restored['value']==first['value']
 preserved=state(a,'backup:'+str(winner['revision']).zfill(16));assert preserved==winner
 # Abort the current-state put. No state advances, pending input remains in
 # both the field and session journal, and a retry can commit after recovery.
 ev('window.__put=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(){throw Error("injected quota")}',a)
 enter(a,'失敗後の入力');wait('document.getElementById("status").textContent.includes("保存できません")',a,'injected save abort')
 assert state(a)==restored and ev('document.querySelector("[data-k=body]").value',a)=='失敗後の入力'
 assert ev('JSON.parse(sessionStorage.getItem("itonami.zuhyo.candidate.zs1.session-draft.v1")).entries[0][1]',a)=='失敗後の入力'
 # A same-tab reload first asks before discarding unsaved in-memory input;
 # its versioned journal must offer recovery against the same IDB revision.
 ev('window.__old=true',a);pipe.send('Page.reload',{},a)
 for _ in range(40):
  try:pipe.call('Page.handleJavaScriptDialog',{'accept':True},a,timeout=5);break
  except RuntimeError:time.sleep(.1)
 else:raise ValueError('beforeunload dialog missing')
 wait('window.__old!==true && !document.getElementById("draft-recovery").hidden && !document.getElementById("draft-restore").disabled',a,'draft recovery')
 ev('document.getElementById("draft-restore").click()',a);wait('document.getElementById("draft-recovery").hidden && document.querySelector("[data-k=body]")?.value==="失敗後の入力"',a,'draft restored')
 ev('document.getElementById("retry-save").click()',a)
 wait('document.getElementById("status").textContent==="保存しました" && document.getElementById("retry-save").hidden',a,'save retry');retried=state(a);assert retried['revision']==4 and '失敗後の入力' in retried['value']
 # Legacy session journals have no IDB revision: preview/export is retained,
 # but automatic restoration must stay disabled rather than guessing.
 old_draft={'version':1,'program':json.loads((build/'build-receipt.json').read_text())['wasmSha256'],'base':retried['value'],'baseState':retried['value'],'entries':[['body','旧下書き']]}
 ev('sessionStorage.setItem("itonami.zuhyo.candidate.zs1.session-draft.v1",'+json.dumps(json.dumps(old_draft,ensure_ascii=False))+');window.__old=true',a);pipe.call('Page.reload',{},a)
 wait('window.__old!==true && !document.getElementById("draft-recovery").hidden && document.getElementById("draft-preview").textContent.includes("旧下書き")',a,'legacy draft preview')
 assert ev('document.getElementById("draft-restore").disabled',a) and state(a)==retried
 pipe.send('Runtime.evaluate',{'expression':'document.getElementById("draft-discard").click()'},a)
 for _ in range(40):
  try:pipe.call('Page.handleJavaScriptDialog',{'accept':True},a,timeout=5);break
  except RuntimeError:time.sleep(.1)
 else:raise ValueError('draft discard confirmation missing')
 wait('document.getElementById("draft-recovery").hidden',a,'legacy draft discard')
 # A backup and a replacement are one transaction; failure of the put must
 # leave the previous state and must not retain a newly queued backup.
 ev('document.getElementById("backup-file").value=""',a);root=pipe.call('DOM.getDocument',{},a)['root']['nodeId'];node=pipe.call('DOM.querySelector',{'nodeId':root,'selector':'#backup-file'},a)['nodeId'];pipe.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(backup)]},a)
 wait('document.getElementById("backup-dialog").open',a,'restore failure preview')
 ev('window.__put=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(){throw Error("injected quota")}',a);click(a,'#backup-confirm')
 wait('document.getElementById("status").textContent.includes("復元できません")',a,'restore transaction abort');ev('IDBObjectStore.prototype.put=window.__put',a)
 assert state(a)==retried and state(a,'backup:'+str(retried['revision']).zfill(16)) is None and state(a,'backup:'+str(winner['revision']).zfill(16))==winner
 # If an old writer changes localStorage while the atomic backup/restore
 # commits, the UI must report that the new store changed, not claim failure.
 ev('document.getElementById("backup-file").value=""',a);pipe.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(backup)]},a);wait('document.getElementById("backup-dialog").open',a,'postcommit backup preview')
 ev('window.__put=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(...args){const r=window.__put.apply(this,args);localStorage.setItem("itonami.zuhyo.candidate.zs1",'+json.dumps(first['value'],ensure_ascii=False)+');return r}',a)
 click(a,'#backup-confirm');wait('!document.getElementById("storage-conflict").hidden && document.getElementById("status").textContent.includes("新しい保存先は更新されました")',a,'postcommit backup warning')
 assert state(a)['value']==first['value'] and state(a,'backup:'+str(retried['revision']).zfill(16))==retried and ev('localStorage.getItem("itonami.zuhyo.candidate.zs1")',a)==first['value']
 # A fresh new-store tab can open after removing the synthetic divergent old
 # value; an in-flight old write during a normal edit is also reported.
 ev('localStorage.removeItem("itonami.zuhyo.candidate.zs1")',a);normal=tab();wait('document.querySelector("[data-k=body]")?.value==="最初😀"',normal,'postcommit normal tab')
 ev('window.__put=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(...args){const r=window.__put.apply(this,args);localStorage.setItem("itonami.zuhyo.candidate.zs1",'+json.dumps(winner['value'],ensure_ascii=False)+');return r}',normal)
 enter(normal,'保存直後に旧版変更');wait('!document.getElementById("storage-conflict").hidden && document.getElementById("status").textContent.includes("新しい保存先は更新されました")',normal,'postcommit edit warning')
 assert '保存直後に旧版変更' in state(normal)['value'] and ev('localStorage.getItem("itonami.zuhyo.candidate.zs1")',normal)==winner['value']
 assert ev('JSON.parse(sessionStorage.getItem("itonami.zuhyo.candidate.zs1.session-draft.v1")).entries.some(e=>e[1]==="保存直後に旧版変更")',normal)
 # A different origin gets a synthetic old snapshot. No IDB state is written
 # before the user activates the preview confirmation button.
 seed='if(!sessionStorage.getItem("__seeded")){localStorage.setItem("itonami.zuhyo.candidate.zs1",'+json.dumps(first['value'],ensure_ascii=False)+');localStorage.setItem("itonami.zuhyo.candidate.zs1.preimport.1700000000000.00000000-0000-0000-0000-000000000001",'+json.dumps(winner['value'],ensure_ascii=False)+');sessionStorage.setItem("__seeded","1")}';m=tab('localhost',seed)
 wait('document.getElementById("legacy-migration").open',m,'migration preview');assert ev('document.getElementById("legacy-migration").textContent.includes("全スライド")',m);assert state(m) is None and ev('localStorage.getItem("itonami.zuhyo.candidate.zs1")',m)==first['value']
 ev('document.getElementById("legacy-migration-confirm").click()',m);assert ev('document.getElementById("legacy-migration").open',m) and state(m) is None
 click(m,'#legacy-migration-confirm');wait('document.getElementById("status").textContent.includes("移行しました")',m,'migration confirm');migrated=state(m);assert migrated['revision']==1 and migrated['legacyAnchor']==first['value'] and ev('localStorage.getItem("itonami.zuhyo.candidate.zs1")',m)==first['value']
 legacy_backup='itonami.zuhyo.candidate.zs1.preimport.1700000000000.00000000-0000-0000-0000-000000000001'
 assert ev('localStorage.getItem('+json.dumps(legacy_backup)+')',m)==winner['value']
 ev('document.querySelector("[data-k=backup-restore]").click()',m);wait('document.getElementById("backup-dialog").open',m,'old backup preview');assert state(m)==migrated
 ev('document.getElementById("backup-cancel").click()',m);wait('!document.getElementById("backup-dialog").open',m,'old backup cancel');assert ev('localStorage.getItem('+json.dumps(legacy_backup)+')',m)==winner['value']
 # A legacy change arrives while the new editor has an unfinished IME
 # composition. The current DOM value must be journaled before freezing.
 ev('(()=>{const e=document.querySelector("[data-k=body]");e.dispatchEvent(new CompositionEvent("compositionstart",{bubbles:true}));e.value="未確定最新"})()',m)
 old=tab('localhost');wait('document.querySelector("[data-k=body]")!==null',old,'old writer page');ev('localStorage.setItem("itonami.zuhyo.candidate.zs1",'+json.dumps(winner['value'],ensure_ascii=False)+')',old)
 wait('!document.getElementById("storage-conflict").hidden && document.getElementById("app").inert',m,'legacy divergence');assert state(m)==migrated and ev('localStorage.getItem("itonami.zuhyo.candidate.zs1")',m)==winner['value']
 assert ev('document.querySelector("[data-k=body]").value',m)=='未確定最新' and ev('JSON.parse(sessionStorage.getItem("itonami.zuhyo.candidate.zs1.session-draft.v1")).entries.some(e=>e[0]==="body" && e[1]==="未確定最新")',m)
 # A late composition input may still arrive after the freeze; retain it in
 # the journal without trying to commit either storage branch.
 ev('(()=>{const e=document.querySelector("[data-k=body]");e.value="凍結後の入力";e.dispatchEvent(new InputEvent("input",{bubbles:true,isComposing:true}))})()',m)
 assert ev('JSON.parse(sessionStorage.getItem("itonami.zuhyo.candidate.zs1.session-draft.v1")).entries.some(e=>e[0]==="body" && e[1]==="凍結後の入力")',m) and state(m)==migrated
 pending_raw=ev('sessionStorage.getItem("itonami.zuhyo.candidate.zs1.session-draft.v1")',m)
 ev('document.getElementById("export-current-conflict").click();document.getElementById("export-legacy-conflict").click();document.getElementById("export-pending-conflict").click()',m)
 current_file=out/'downloads/zuhyo-current-recovery.txt';legacy_file=out/'downloads/zuhyo-legacy-recovery.txt';pending_file=out/'downloads/zuhyo-unsaved-recovery.json';deadline=time.time()+30
 while time.time()<deadline and not (current_file.exists() and legacy_file.exists() and pending_file.exists()):time.sleep(.1)
 assert current_file.read_text()==migrated['value'] and legacy_file.read_text()==winner['value'] and pending_file.read_text()==pending_raw
 # A separate origin proves that cancel and invalid legacy data do not create
 # a new record or remove/overwrite the old snapshot.
 server2=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(build)));threading.Thread(target=server2.serve_forever,daemon=True).start()
 c=tab(seed=seed,target_port=server2.server_port);wait('document.getElementById("legacy-migration").open',c,'cancel preview')
 ev('document.getElementById("legacy-migration-cancel").focus()',c)
 pipe.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Enter','code':'Enter','text':'\r','unmodifiedText':'\r','windowsVirtualKeyCode':13,'nativeVirtualKeyCode':13},c)
 pipe.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'nativeVirtualKeyCode':13},c)
 wait('!document.getElementById("storage-conflict").hidden',c,'migration cancelled');assert state(c) is None and ev('localStorage.getItem("itonami.zuhyo.candidate.zs1")',c)==first['value']
 ev('localStorage.setItem("itonami.zuhyo.candidate.zs1","invalid snapshot")',c)
 invalid=tab(target_port=server2.server_port);wait('!document.getElementById("storage-conflict").hidden',invalid,'invalid legacy refusal');assert state(invalid) is None and ev('localStorage.getItem("itonami.zuhyo.candidate.zs1")',invalid)=='invalid snapshot'
 # Even invalid UTF-16 must be exportable without Blob's replacement of lone
 # surrogates; the recovery file uses an escaped JSON string envelope.
 ev('localStorage.setItem("itonami.zuhyo.candidate.zs1",String.fromCharCode(0xd800))',c)
 malformed=tab(target_port=server2.server_port);wait('!document.getElementById("storage-conflict").hidden',malformed,'invalid UTF16 refusal')
 ev('document.getElementById("export-legacy-conflict").click()',malformed);encoded=out/'downloads/zuhyo-legacy-recovery.txt.json';deadline=time.time()+30
 while time.time()<deadline and not encoded.exists():time.sleep(.1)
 payload=json.loads(encoded.read_text());assert payload=={'encoding':'json-string-utf16','value':chr(0xd800)} and state(malformed) is None
 # If the old tab changes the value while the preview is open, confirming
 # must not copy the stale preview or overwrite the changed legacy value.
 ev('localStorage.setItem("itonami.zuhyo.candidate.zs1",'+json.dumps(first['value'],ensure_ascii=False)+')',c)
 race=tab(target_port=server2.server_port);wait('document.getElementById("legacy-migration").open',race,'stale migration preview')
 ev('localStorage.setItem("itonami.zuhyo.candidate.zs1",'+json.dumps(winner['value'],ensure_ascii=False)+')',c)
 wait('!document.getElementById("storage-conflict").hidden',race,'migration divergence')
 click(race,'#legacy-migration-confirm');wait('!document.getElementById("legacy-migration").open',race,'stale migration refusal')
 assert state(race) is None and ev('localStorage.getItem("itonami.zuhyo.candidate.zs1")',race)==winner['value']
 # Failed initial IDB put must leave the chosen old value intact and create
 # no current record. The failure is injected only into this synthetic tab.
 failed=tab(target_port=server2.server_port);wait('document.getElementById("legacy-migration").open',failed,'failed migration preview')
 ev('window.__put=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(){throw Error("injected quota")}',failed)
 click(failed,'#legacy-migration-confirm');wait('!document.getElementById("storage-conflict").hidden && !document.getElementById("legacy-migration").open',failed,'migration transaction abort')
 assert state(failed) is None and ev('localStorage.getItem("itonami.zuhyo.candidate.zs1")',failed)==winner['value']
 # A legacy change during the IDB put leaves both branches intact and locks
 # the UI; the coordinator reports the post-commit divergence.
 post=tab(target_port=server2.server_port);wait('document.getElementById("legacy-migration").open',post,'postcommit preview')
 ev('window.__put=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(...args){const r=window.__put.apply(this,args);localStorage.setItem("itonami.zuhyo.candidate.zs1",'+json.dumps(first['value'],ensure_ascii=False)+');return r}',post)
 click(post,'#legacy-migration-confirm');wait('!document.getElementById("storage-conflict").hidden && !document.getElementById("legacy-migration").open',post,'postcommit legacy divergence')
 poststate=state(post);assert poststate['value']==winner['value'] and poststate['legacyAnchor']==winner['value'] and ev('localStorage.getItem("itonami.zuhyo.candidate.zs1")',post)==first['value'] and ev('document.getElementById("app").inert',post)
 report={'status':'PASS_ZUHYO_IDB_UI_SYNTHETIC','checks':['new-document-save-reload','stale-tab-conflict-preserves-draft','stale-revision-draft-preview-only','backup-preview-and-atomic-restore','save-abort-reload-recover-draft-and-retry','legacy-session-draft-preview-only','restore-abort-rolls-back-backup','postcommit-restore-truthful-warning','postcommit-save-truthful-warning','legacy-preview-explicit-trusted-confirm','legacy-copy-and-old-backup-preserved','old-backup-preview','old-writer-divergence-freezes','unfinished-and-late-composition-journaled','both-divergent-branches-and-unsaved-draft-export','migration-keyboard-cancel-preserves','invalid-legacy-refusal','invalid-utf16-legacy-export','migration-preview-race-refusal','migration-transaction-abort','migration-postcommit-divergence-preserved'],'scope':'synthetic Chrome loopback; no real user data, atomic cross-store coordination, crash/power-loss, QEMU or release'}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],flush=True)
finally:
 pipe.close();server.shutdown();server.server_close()
 if server2:server2.shutdown();server2.server_close()
