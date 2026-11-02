#!/usr/bin/env python3
"""Exercise the local Zuhyo browser candidate on loopback Chrome.
Usage: python3 scripts/check-browser-ui.py AMU_DIR BUILD_DIR OUTPUT_DIR CHROME
"""
import functools
import http.server
import importlib.util
import json
import shutil
import sys
import threading
import time
from pathlib import Path
if len(sys.argv) != 5: raise SystemExit(__doc__)
amu, build, out, chrome = [Path(x).resolve() for x in sys.argv[1:]]
out.mkdir(parents=True, exist_ok=False)
profile = out / 'profile'; profile.mkdir()
site = out / 'site'; shutil.copytree(build, site)
spec = importlib.util.spec_from_file_location('browser', amu / 'scripts/seed/check-wasm32-browser.py')
browser = importlib.util.module_from_spec(spec); spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(out)))
threading.Thread(target=server.serve_forever, daemon=True).start()
pipe = browser.Pipe(str(chrome), profile)
url = f'http://127.0.0.1:{server.server_port}/site/index.html'
try:
    target = pipe.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    session = pipe.call('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
    pipe.call('Network.enable', {}, session); pipe.call('Page.navigate', {'url': url}, session)
    def evaluate(expr):
        result = pipe.call('Runtime.evaluate', {'expression': expr, 'returnByValue': True}, session)
        if 'exceptionDetails' in result: raise ValueError(result['exceptionDetails'])
        return result.get('result', {}).get('value')
    def wait(expr, label, seconds=90):
        end = time.time() + seconds
        while time.time() < end:
            if evaluate(expr): return
            time.sleep(.2)
        raise TimeoutError(label + ': ' + str(evaluate('document.body.innerText')))
    def input_(key, text):
        evaluate("(()=>{let e=document.querySelector('[data-k="+key+"]');e.value="+json.dumps(text,ensure_ascii=False)+";e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("document.querySelector('[data-k=heading]') !== null", 'initial slide')
    if evaluate("document.querySelector('[data-k=heading]').getAttribute('aria-label')") != 'スライドの見出し': raise ValueError('heading lacks accessible name')
    if evaluate("document.querySelector('[data-k=notes]').getAttribute('aria-label')") != '発表者メモ': raise ValueError('notes lack accessible name')
    evaluate("document.querySelector('[data-k=heading]').click()")
    time.sleep(1)
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") is not None: raise ValueError('focusing input wrote state')
    input_('heading', '第一😀')
    wait("document.querySelector('[data-k=heading]')?.value === '第一😀' && document.getElementById('status').textContent === '保存しました'", 'first heading')
    input_('notes', '発表者メモ')
    wait("document.querySelector('[data-k=notes]')?.value === '発表者メモ' && document.getElementById('status').textContent === '保存しました'", 'notes')
    evaluate("document.querySelector('[data-k=add]').click()")
    wait("document.querySelector('.stats')?.textContent === '2 / 2'", 'add slide')
    evaluate("document.querySelector('[data-k=remove]').click()")
    wait("document.querySelector('.stats')?.textContent === '1 / 1'", 'remove slide')
    evaluate("document.querySelector('[data-k=add]').click()")
    wait("document.querySelector('.stats')?.textContent === '2 / 2'", 'add after remove')
    input_('heading', '第二枚')
    wait("document.querySelector('[data-k=heading]')?.value === '第二枚' && document.getElementById('status').textContent === '保存しました'", 'second heading')
    input_('body', '本文の内容')
    wait("document.querySelector('[data-k=body]')?.value === '本文の内容' && document.getElementById('status').textContent === '保存しました'", 'body')
    evaluate("document.querySelector('[data-k=shape-circle]').click()")
    wait("document.querySelector('main.edit.shape-circle') !== null", 'shape')
    evaluate("document.querySelector('[data-k=up]').click()")
    wait("document.querySelector('.stats')?.textContent === '1 / 2'", 'reorder')
    evaluate("document.querySelector('[data-k=mode]').click()")
    wait("document.querySelector('main.present.shape-circle h1')?.textContent === '第二枚'", 'presentation')
    if evaluate("document.querySelector('main.present p')?.textContent") != '本文の内容': raise ValueError('body missing')
    saved = evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")
    if not saved or '第二枚' not in saved or '発表者メモ' not in saved: raise ValueError('deck not saved')
    pipe.call('Page.reload', {}, session)
    wait("document.querySelector('main.present.shape-circle h1')?.textContent === '第二枚'", 'presentation reload')
    evaluate("document.querySelector('[data-k=next]').click()")
    wait("document.querySelector('main.present h1')?.textContent === '第一😀'", 'next slide')
    evaluate("document.querySelector('[data-k=mode]').click()")
    wait("document.querySelector('[data-k=notes]')?.value === '発表者メモ'", 'notes restored')
    saved = evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")
    input_('heading', 'x' * 513)
    wait("document.getElementById('status').textContent.includes('入力が長すぎます')", 'oversized input')
    wait("document.querySelector('[data-k=heading]')?.value === '第一😀'", 'oversized restore')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != saved: raise ValueError('oversize clobbered storage')
    # A downloaded ZS1 can be explicitly reviewed and restored; invalid input
    # and storage failure must never replace the current document.
    download = out / 'downloads'
    download.mkdir()
    pipe.call('Browser.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(download)})
    evaluate("document.querySelector('[data-k=backup-export]').click()")
    end = time.time() + 90
    while time.time() < end and not (download / 'zuhyo-backup.zs1').exists(): time.sleep(.2)
    exported = download / 'zuhyo-backup.zs1'
    if not exported.exists() or exported.read_text() != saved: raise ValueError('backup download mismatch')
    evaluate("(()=>{let e=document.querySelector('[data-k=heading]');e.value='バックアップ前';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('バックアップ前')", 'edit before import')
    prior = evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")
    def select_file(path):
        pipe.call('DOM.enable', {}, session)
        root = pipe.call('DOM.getDocument', {}, session)['root']['nodeId']
        node = pipe.call('DOM.querySelector', {'nodeId': root, 'selector': '#backup-file'}, session)['nodeId']
        pipe.call('DOM.setFileInputFiles', {'nodeId': node, 'files': [str(path)]}, session)
    select_file(exported)
    wait("document.getElementById('backup-dialog').open", 'backup preview')
    if evaluate("document.querySelector('#backup-preview [data-k=heading]')?.value") != '第一😀': raise ValueError('preview mismatch')
    evaluate("document.getElementById('backup-cancel').click()")
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != prior: raise ValueError('cancel changed storage')
    # Reset the input, as the user action does before selecting a file again.
    evaluate("document.getElementById('backup-file').value=''")
    select_file(exported)
    wait("document.getElementById('backup-dialog').open", 'backup preview again')
    evaluate("document.getElementById('backup-confirm').click()")
    wait("document.getElementById('status').textContent === 'バックアップから復元しました。'", 'restore backup')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != saved: raise ValueError('restore mismatch')
    if not evaluate("Object.keys(localStorage).some(k=>k.startsWith('itonami.zuhyo.candidate.zs1.preimport.') && localStorage.getItem(k).includes('バックアップ前'))"): raise ValueError('missing prior backup')
    evaluate("document.querySelector('[data-k=backup-restore]').click()")
    wait("document.getElementById('backup-dialog').open", 'prior backup preview')
    evaluate("document.getElementById('backup-confirm').click()")
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('バックアップ前')", 'restore prior')
    bad = out / 'bad.zs1'
    bad.write_bytes(b'ZS1|bad')
    evaluate("document.getElementById('backup-file').value=''")
    select_file(bad)
    wait("document.getElementById('status').textContent.includes('バックアップを読み込めません')", 'bad backup refusal')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != prior or evaluate("document.getElementById('backup-dialog').open"): raise ValueError('bad import changed state')
    for name, contents in [('utf8.zs1', b'ZS1|\xff'), ('large.zs1', b'ZS1|' + b'x' * 35000), ('unknown.zs1', b'OLD|document')]:
        invalid = out / name
        invalid.write_bytes(contents)
        evaluate("document.getElementById('status').textContent='' ; document.getElementById('backup-file').value=''")
        select_file(invalid)
        wait("document.getElementById('status').textContent.includes('バックアップを読み込めません')", name + ' refusal')
        if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != prior or evaluate("document.getElementById('backup-dialog').open"): raise ValueError(name + ' changed state')
    evaluate("document.getElementById('backup-file').value=''")
    select_file(exported)
    wait("document.getElementById('backup-dialog').open", 'quota backup preview')
    evaluate("window.savedSetItem=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k.includes('.preimport.'))throw Error('quota');return window.savedSetItem.call(this,k,v)};document.getElementById('backup-confirm').click()")
    wait("document.getElementById('status').textContent.includes('復元できませんでした')", 'backup quota refusal')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != prior: raise ValueError('quota import changed state')
    evaluate("Storage.prototype.setItem=window.savedSetItem")
    # Fail the second write after the recovery copy succeeds.
    backup_keys = set(evaluate("Object.keys(localStorage).filter(k=>k.startsWith('itonami.zuhyo.candidate.zs1.preimport.'))"))
    evaluate("document.getElementById('backup-file').value='';document.getElementById('status').textContent=''")
    select_file(exported)
    wait("document.getElementById('backup-dialog').open", 'current-write failure preview')
    evaluate("Storage.prototype.setItem=function(k,v){if(k==='itonami.zuhyo.candidate.zs1')throw Error('quota');return window.savedSetItem.call(this,k,v)};document.getElementById('backup-confirm').click()")
    wait("document.getElementById('status').textContent.includes('復元できませんでした')", 'current-write failure refusal')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != prior: raise ValueError('failed current write changed state')
    after_keys = set(evaluate("Object.keys(localStorage).filter(k=>k.startsWith('itonami.zuhyo.candidate.zs1.preimport.'))"))
    new_keys = after_keys - backup_keys
    if len(new_keys) != 1 or evaluate("localStorage.getItem(" + json.dumps(next(iter(new_keys))) + ")") != prior: raise ValueError('pre-import copy missing after failed current write')
    evaluate("Storage.prototype.setItem=window.savedSetItem;document.getElementById('backup-file').value=''")
    # Return to the original exported fixture through the validated import path.
    select_file(exported)
    wait("document.getElementById('backup-dialog').open", 'return backup preview')
    evaluate("document.getElementById('backup-confirm').click()")
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('第一😀')", 'return to test state')
    second = pipe.call('Target.createTarget', {'url': url})['targetId']
    second_session = pipe.call('Target.attachToTarget', {'targetId': second, 'flatten': True})['sessionId']
    def second_eval(expr):
        result = pipe.call('Runtime.evaluate', {'expression': expr, 'returnByValue': True}, second_session)
        if 'exceptionDetails' in result: raise ValueError(result['exceptionDetails'])
        return result.get('result', {}).get('value')
    end = time.time() + 90
    while time.time() < end and second_eval("document.querySelector('[data-k=heading]')?.value") != '第一😀': time.sleep(.2)
    if second_eval("document.querySelector('[data-k=heading]')?.value") != '第一😀': raise TimeoutError('second tab')
    pipe.call('DOM.enable', {}, second_session)
    second_root = pipe.call('DOM.getDocument', {}, second_session)['root']['nodeId']
    second_file = pipe.call('DOM.querySelector', {'nodeId': second_root, 'selector': '#backup-file'}, second_session)['nodeId']
    pipe.call('DOM.setFileInputFiles', {'nodeId': second_file, 'files': [str(exported)]}, second_session)
    end = time.time() + 90
    while time.time() < end and not second_eval("document.getElementById('backup-dialog').open"): time.sleep(.2)
    if not second_eval("document.getElementById('backup-dialog').open"): raise TimeoutError('second tab backup preview')
    input_('title', '先の変更')
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('先の変更') || document.getElementById('status').textContent.includes('保存できませんでした')", 'first tab write')
    if not evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('先の変更')"):
        raise ValueError('first tab write refused: ' + str(evaluate("document.getElementById('status').textContent")))
    saved_after_edit = evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")
    second_eval("document.getElementById('backup-confirm').click()")
    end = time.time() + 90
    while time.time() < end and not second_eval("document.getElementById('status')?.textContent.includes('復元できませんでした')"): time.sleep(.2)
    if not second_eval("document.getElementById('status')?.textContent.includes('別のタブ')") or evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != saved_after_edit: raise ValueError('conflicting import clobbered state')
    second_eval("(()=>{let e=document.querySelector('[data-k=title]');e.value='後の変更';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    end = time.time() + 90
    while time.time() < end and not second_eval("document.getElementById('status')?.textContent.includes('保存できませんでした')"): time.sleep(.2)
    if not second_eval("document.getElementById('status')?.textContent.includes('保存できませんでした')"): raise TimeoutError('stale tab refusal')
    if not second_eval("document.getElementById('status')?.textContent.includes('別のタブ')"): raise ValueError('conflict reason not shown')
    saved = evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")
    if '先の変更' not in saved or '後の変更' in saved: raise ValueError('stale tab clobbered deck')
    pipe.call('Target.closeTarget', {'targetId': second})
    evaluate("window.savedTimer=window.setTimeout;window.setTimeout=(f,n)=>window.savedTimer(f,n===30000?1:n)")
    input_('heading', '時間切れ')
    wait("document.getElementById('status').textContent.includes('時間内に完了しませんでした')", 'worker timeout')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != saved: raise ValueError('timeout clobbered storage')
    evaluate("window.setTimeout=window.savedTimer")
    pipe.call('Page.reload', {}, session)
    wait("document.querySelector('[data-k=heading]')?.value === '第一😀'", 'reload after timeout')
    evaluate("window.savedWorker=window.Worker;window.Worker=class extends window.savedWorker {postMessage(msg){if(msg.args[0]==='view'){this.terminate();queueMicrotask(()=>this.onerror(new Event('error')))}else super.postMessage(msg)}}")
    input_('heading', '中断')
    wait("document.getElementById('status').textContent.includes('保存できませんでした')", 'worker interruption')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != saved: raise ValueError('interrupted render clobbered storage')
    evaluate("window.Worker=window.savedWorker")
    pipe.call('Page.reload', {}, session)
    wait("document.querySelector('[data-k=heading]')?.value === '第一😀'", 'reload after interruption')
    evaluate("Storage.prototype.setItem = function(){throw new Error('quota')}")
    input_('heading', '失われる変更')
    wait("document.getElementById('status').textContent.includes('保存できませんでした')", 'storage failure')
    wait("document.querySelector('[data-k=heading]')?.value === '第一😀'", 'restore prior view')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != saved: raise ValueError('storage clobbered')
    pipe.call('Page.reload', {}, session)
    wait("document.querySelector('[data-k=heading]')?.value === '第一😀'", 'reload before corruption')
    evaluate("localStorage.setItem('itonami.zuhyo.candidate.zs1','ZS1|bad')")
    pipe.call('Page.reload', {}, session)
    wait("document.getElementById('status').textContent.includes('開けません')", 'corruption refusal')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != 'ZS1|bad': raise ValueError('corrupt state overwritten')
    evaluate("localStorage.removeItem('itonami.zuhyo.candidate.zs1')")
    tampered = out / 'tampered'; shutil.copytree(site, tampered)
    bundle = tampered / 'bundle.js'; content = bundle.read_text()
    content, count = __import__('re').subn(r'(export const wasmSha256 = ")[0-9a-f]{64}(";)', r'\g<1>' + '0' * 64 + r'\g<2>', content)
    if count != 1: raise ValueError('digest mutation anchor')
    bundle.write_text(content)
    pipe.call('Page.navigate', {'url': f'http://127.0.0.1:{server.server_port}/tampered/index.html'}, session)
    wait("document.getElementById('status')?.textContent.includes('開けません')", 'digest refusal')
    if evaluate("document.querySelector('[data-k=heading]') !== null || localStorage.getItem('itonami.zuhyo.candidate.zs1') !== null"):
        raise ValueError('tampered candidate ran or wrote state')
    requests = [e['params']['request']['url'] for e in pipe.events if e.get('method') == 'Network.requestWillBeSent']
    if any(u.split('?', 1)[0].endswith('/favicon.ico') for u in requests): raise ValueError('unversioned favicon request')
    if not requests or any(not u.startswith(f'http://127.0.0.1:{server.server_port}/') for u in requests): raise ValueError('unexpected network request')
    (out / 'result.json').write_text(json.dumps({'status':'PASS','checks':['backup-export-import-cancel-restore','backup-invalid-both-write-failures-conflict','edit','notes','add','remove','shape','reorder','present','reload','navigate','oversized-refusal','concurrent-tab-refusal','worker-timeout','worker-interruption','storage-failure','corrupt-refusal','digest-refusal','loopback-only']},indent=2)+'\n')
    print('PASS_ZUHYO_BROWSER_UI edit, present, save and refusal')
finally:
    pipe.close(); server.shutdown(); server.server_close()
