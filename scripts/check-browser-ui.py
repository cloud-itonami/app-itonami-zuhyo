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
    def reload_page():
        evaluate("window.__reloadMarker = true")
        pipe.call('Page.reload', {}, session)
        wait("window.__reloadMarker !== true", 'new document after reload')
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
    notes_text = '発表者メモ\n二行目😀'
    if not evaluate("document.querySelector('[data-k=notes]')?.tagName === 'TEXTAREA' && document.querySelector('[data-k=body]')?.tagName === 'TEXTAREA'"): raise ValueError('multiline controls missing')
    input_('notes', notes_text)
    wait("document.querySelector('[data-k=notes]')?.value === "+json.dumps(notes_text,ensure_ascii=False)+" && document.getElementById('status').textContent === '保存しました'", 'multiline notes')
    evaluate("document.querySelector('[data-k=add]').click()")
    wait("document.querySelector('.stats')?.textContent === '2 / 2'", 'add slide')
    evaluate("document.querySelector('[data-k=remove]').click()")
    wait("document.querySelector('.stats')?.textContent === '1 / 1'", 'remove slide')
    evaluate("document.querySelector('[data-k=add]').click()")
    wait("document.querySelector('.stats')?.textContent === '2 / 2'", 'add after remove')
    input_('heading', '第二枚')
    wait("document.querySelector('[data-k=heading]')?.value === '第二枚' && document.getElementById('status').textContent === '保存しました'", 'second heading')
    body_text = '本文の内容\n二行目😀'
    input_('body', body_text)
    wait("document.querySelector('[data-k=body]')?.value === "+json.dumps(body_text,ensure_ascii=False)+" && document.getElementById('status').textContent === '保存しました'", 'multiline body')
    evaluate("document.querySelector('[data-k=shape-circle]').click()")
    wait("document.querySelector('main.edit.shape-circle') !== null", 'shape')
    evaluate("document.querySelector('[data-k=up]').click()")
    wait("document.querySelector('.stats')?.textContent === '1 / 2'", 'reorder')
    evaluate("document.querySelector('[data-k=mode]').click()")
    wait("document.querySelector('main.present.shape-circle h1')?.textContent === '第二枚'", 'presentation')
    if evaluate("document.querySelector('.deck input, .deck textarea, [data-k=add], [data-k=remove], [data-k=up], [data-k=down], [data-k=backup-import]') !== null"): raise ValueError('editing controls visible in presentation')
    if evaluate("document.querySelector('.bar .deck-title')?.textContent") != '無題のプレゼン': raise ValueError('presentation title missing')
    if evaluate("document.querySelector('main.present p')?.textContent") != body_text or evaluate("getComputedStyle(document.querySelector('main.present p')).whiteSpace") != 'pre-wrap': raise ValueError('multiline presentation missing')
    saved = evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")
    if not saved or not saved.startswith('ZS2|') or '第二枚' not in saved or notes_text not in saved: raise ValueError('deck not saved')
    reload_page()
    wait("document.querySelector('main.present.shape-circle h1')?.textContent === '第二枚'", 'presentation reload')
    evaluate("document.querySelector('[data-k=next]').click()")
    wait("document.querySelector('main.present h1')?.textContent === '第一😀'", 'next slide')
    evaluate("document.querySelector('[data-k=mode]').click()")
    wait("document.querySelector('[data-k=notes]')?.value === "+json.dumps(notes_text,ensure_ascii=False), 'multiline notes restored')
    saved = evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")
    # Simulate composition while an earlier field's view is in flight.
    original_other = evaluate("document.querySelector('[data-k=body]').value")
    evaluate("window.originalWorker=window.Worker;window.imeDelay=false;window.Worker=class extends window.originalWorker {postMessage(m,...rest){if(m.args[0]==='view'&&!window.imeDelay){window.imeDelay=true;setTimeout(()=>super.postMessage(m,...rest),1500)}else super.postMessage(m,...rest)}}")
    input_('body', 'IME補助')
    wait("window.imeDelay === true", 'pending view before composition')
    evaluate("(()=>{let e=document.querySelector('[data-k=heading]');window.imeNode=e;e.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));e.value='仮変換';e.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:true,inputType:'insertCompositionText',data:'仮変換'}));})()")
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('IME補助')", 'other field save during composition')
    if not evaluate("window.imeNode === document.querySelector('[data-k=heading]')") or evaluate("document.querySelector('[data-k=heading]').value") != '仮変換': raise ValueError('composition node or text replaced')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('仮変換')"): raise ValueError('incomplete composition saved')
    evaluate("(()=>{let e=document.querySelector('[data-k=heading]');e.value='日本語';e.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'日本語'}));e.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:false,inputType:'insertText',data:'日本語'}));})()")
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('日本語') && document.getElementById('status').textContent === '保存しました'", 'completed composition save')
    evaluate("window.Worker=window.originalWorker")
    input_('heading', '第一😀');input_('body', original_other)
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1') === "+json.dumps(saved,ensure_ascii=False)+" && document.getElementById('status').textContent === '保存しました'", 'restore after composition')
    input_('heading', 'x' * 513)
    wait("document.getElementById('status').textContent.includes('入力が長すぎます')", 'oversized input')
    if evaluate("document.querySelector('[data-k=heading]')?.value.length") != 513 or evaluate("document.getElementById('retry-save').hidden"): raise ValueError('oversized input discarded')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != saved: raise ValueError('oversize clobbered storage')
    input_('heading','第一😀');wait("document.getElementById('retry-save').hidden && localStorage.getItem('itonami.zuhyo.candidate.zs1') === " + json.dumps(saved,ensure_ascii=False) + " && document.getElementById('status').textContent === '保存しました'", 'correct oversized input')
    # A downloaded ZS1 can be explicitly reviewed and restored; invalid input
    # and storage failure must never replace the current document.
    download = out / 'downloads'
    download.mkdir()
    pipe.call('Browser.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(download)})
    evaluate("document.querySelector('[data-k=backup-export]').click()")
    end = time.time() + 90
    while time.time() < end and not (download / 'zuhyo-backup.zs2').exists(): time.sleep(.2)
    exported = download / 'zuhyo-backup.zs2'
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
    if second_eval("document.querySelector('[data-k=title]')?.value") != '後の変更' or second_eval("document.getElementById('retry-save').hidden"): raise ValueError('conflict discarded input')
    second_eval("document.getElementById('status').textContent='';document.getElementById('retry-save').click()")
    end = time.time() + 90
    while time.time() < end and not second_eval("document.getElementById('status')?.textContent.includes('別のタブ')"): time.sleep(.2)
    if not second_eval("document.getElementById('status')?.textContent.includes('別のタブ')") or second_eval("document.querySelector('[data-k=title]')?.value") != '後の変更': raise ValueError('conflict retry lost input')
    saved = evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")
    if '先の変更' not in saved or '後の変更' in saved: raise ValueError('stale tab clobbered deck')
    pipe.call('Target.closeTarget', {'targetId': second})
    evaluate("window.savedTimer=window.setTimeout;window.setTimeout=(f,n)=>window.savedTimer(f,n===30000?1:n)")
    input_('heading', '時間切れ')
    wait("document.getElementById('status').textContent.includes('時間内に完了しませんでした')", 'worker timeout')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != saved: raise ValueError('timeout clobbered storage')
    if evaluate("document.querySelector('[data-k=heading]')?.value") != '時間切れ' or evaluate("document.getElementById('retry-save').hidden"): raise ValueError('timeout discarded input')
    evaluate("document.querySelector('[data-k=backup-export]').click()")
    if not evaluate("document.getElementById('status').textContent.includes('未保存')"): raise ValueError('backup allowed with unsaved input')
    evaluate("window.setTimeout=window.savedTimer;document.getElementById('retry-save').click()")
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('時間切れ') && document.getElementById('retry-save').hidden", 'timeout retry')
    input_('heading','第一😀');wait("localStorage.getItem('itonami.zuhyo.candidate.zs1') === " + json.dumps(saved,ensure_ascii=False), 'restore timeout fixture')
    background=pipe.call('Target.createTarget', {'url':'about:blank'})['targetId']
    wait("document.visibilityState === 'hidden'", 'hidden tab')
    # Explicitly stall the Worker: background timer throttling may otherwise
    # let a fast Worker win the deliberately shortened timeout race.
    evaluate("window.hiddenWorker=window.Worker;window.Worker=class extends window.hiddenWorker {postMessage(msg,...rest){if(msg.args[0]!=='step')super.postMessage(msg,...rest)}};window.savedTimer=window.setTimeout;window.setTimeout=(f,n)=>window.savedTimer(f,n===30000?1:n)")
    input_('heading','背景入力');wait("document.getElementById('status').textContent.includes('時間内に完了しませんでした')", 'hidden timeout')
    pipe.call('Page.bringToFront', {}, session);wait("document.visibilityState === 'visible'", 'return to tab')
    if evaluate("document.querySelector('[data-k=heading]')?.value") != '背景入力' or evaluate("document.getElementById('retry-save').hidden") or evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != saved: raise ValueError('hidden timeout discarded input')
    pipe.call('Target.closeTarget', {'targetId':background})
    evaluate("window.Worker=window.hiddenWorker;window.setTimeout=window.savedTimer;document.getElementById('retry-save').click()")
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('背景入力') && document.getElementById('retry-save').hidden", 'hidden retry')
    input_('heading','第一😀');wait("localStorage.getItem('itonami.zuhyo.candidate.zs1') === " + json.dumps(saved,ensure_ascii=False), 'restore hidden fixture')
    reload_page()
    wait("document.querySelector('[data-k=heading]')?.value === '第一😀'", 'reload after timeout')
    evaluate("window.savedWorker=window.Worker;window.Worker=class extends window.savedWorker {postMessage(msg){if(msg.args[0]==='view'){this.terminate();queueMicrotask(()=>this.onerror(new Event('error')))}else super.postMessage(msg)}}")
    input_('heading', '中断')
    wait("document.getElementById('status').textContent.includes('保存できませんでした')", 'worker interruption')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != saved: raise ValueError('interrupted render clobbered storage')
    if evaluate("document.querySelector('[data-k=heading]')?.value") != '中断' or evaluate("document.getElementById('retry-save').hidden"): raise ValueError('interrupted input discarded')
    evaluate("window.Worker=window.savedWorker;document.getElementById('retry-save').click()")
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('中断') && document.getElementById('retry-save').hidden", 'interruption retry')
    input_('heading','第一😀');wait("localStorage.getItem('itonami.zuhyo.candidate.zs1') === " + json.dumps(saved,ensure_ascii=False), 'restore interruption fixture')
    reload_page()
    wait("document.querySelector('[data-k=heading]')?.value === '第一😀'", 'reload after interruption')
    evaluate("window.quotaSetter=Storage.prototype.setItem;Storage.prototype.setItem = function(){throw new Error('quota')}")
    input_('heading', '未保存の変更')
    wait("document.getElementById('status').textContent.includes('保存できませんでした')", 'storage failure')
    if evaluate("document.querySelector('[data-k=heading]')?.value") != '未保存の変更' or evaluate("document.getElementById('retry-save').hidden"): raise ValueError('quota discarded input')
    if evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')") != saved: raise ValueError('storage clobbered')
    evaluate("Storage.prototype.setItem=window.quotaSetter;document.getElementById('retry-save').click()")
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('未保存の変更') && document.getElementById('retry-save').hidden", 'quota retry')
    input_('heading','第一😀');wait("localStorage.getItem('itonami.zuhyo.candidate.zs1') === " + json.dumps(saved,ensure_ascii=False), 'restore quota fixture')
    old_body=evaluate("document.querySelector('[data-k=body]').value")
    evaluate("window.partialSetter=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(v.includes('未保存見出し'))throw Error('quota');return window.partialSetter.call(this,k,v)};(()=>{for(const [k,v] of [['heading','未保存見出し'],['body','追加本文']]){let e=document.querySelector('[data-k='+k+']');e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));}})()")
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('追加本文')", 'other field save')
    if evaluate("document.querySelector('[data-k=heading]')?.value") != '未保存見出し' or evaluate("document.getElementById('retry-save').hidden"): raise ValueError('successful redraw erased failed edit')
    evaluate("Storage.prototype.setItem=window.partialSetter;document.getElementById('retry-save').click()")
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('未保存見出し') && localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('追加本文') && document.getElementById('retry-save').hidden", 'multiple edits retry')
    input_('heading','第一😀');input_('body',old_body);wait("localStorage.getItem('itonami.zuhyo.candidate.zs1') === " + json.dumps(saved,ensure_ascii=False), 'restore multi fixture')
    reload_page()
    wait("document.querySelector('[data-k=heading]')?.value === '第一😀'", 'reload before corruption')
    evaluate("localStorage.setItem('itonami.zuhyo.candidate.zs1','ZS1|bad')")
    reload_page()
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
    (out / 'result.json').write_text(json.dumps({'status':'PASS','checks':['backup-export-import-cancel-restore','backup-invalid-both-write-failures-conflict','edit','multiline-notes-presentation-reload','add','remove','shape','reorder','present','reload','navigate','synthetic-composition-with-concurrent-redraw','oversized-refusal','concurrent-tab-refusal','worker-timeout-retry','hidden-timeout-retry','worker-interruption-retry','storage-failure-retry','multiple-unsaved-fields','corrupt-refusal','digest-refusal','loopback-only']},indent=2)+'\n')
    print('PASS_ZUHYO_BROWSER_UI edit, present, save and refusal')
finally:
    pipe.close(); server.shutdown(); server.server_close()
