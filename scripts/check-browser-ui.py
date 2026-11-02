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
    second = pipe.call('Target.createTarget', {'url': url})['targetId']
    second_session = pipe.call('Target.attachToTarget', {'targetId': second, 'flatten': True})['sessionId']
    def second_eval(expr):
        result = pipe.call('Runtime.evaluate', {'expression': expr, 'returnByValue': True}, second_session)
        if 'exceptionDetails' in result: raise ValueError(result['exceptionDetails'])
        return result.get('result', {}).get('value')
    end = time.time() + 90
    while time.time() < end and second_eval("document.querySelector('[data-k=heading]')?.value") != '第一😀': time.sleep(.2)
    if second_eval("document.querySelector('[data-k=heading]')?.value") != '第一😀': raise TimeoutError('second tab')
    input_('title', '先の変更')
    wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes('先の変更')", 'first tab write')
    second_eval("(()=>{let e=document.querySelector('[data-k=title]');e.value='後の変更';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    end = time.time() + 90
    while time.time() < end and not second_eval("document.getElementById('status')?.textContent.includes('保存できませんでした')"): time.sleep(.2)
    if not second_eval("document.getElementById('status')?.textContent.includes('保存できませんでした')"): raise TimeoutError('stale tab refusal')
    saved = evaluate("localStorage.getItem('itonami.zuhyo.candidate.zs1')")
    if '先の変更' not in saved or '後の変更' in saved: raise ValueError('stale tab clobbered deck')
    pipe.call('Target.closeTarget', {'targetId': second})
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
    if not requests or any(not u.startswith(f'http://127.0.0.1:{server.server_port}/') for u in requests): raise ValueError('unexpected network request')
    (out / 'result.json').write_text(json.dumps({'status':'PASS','checks':['edit','notes','add','remove','shape','reorder','present','reload','navigate','oversized-refusal','concurrent-tab-refusal','worker-interruption','storage-failure','corrupt-refusal','digest-refusal','loopback-only']},indent=2)+'\n')
    print('PASS_ZUHYO_BROWSER_UI edit, present, save and refusal')
finally:
    pipe.close(); server.shutdown(); server.server_close()
