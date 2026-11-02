import functools, http.server, importlib.util, json, sys, threading, time
from pathlib import Path
amu, site, out, chrome = [Path(x).resolve() for x in sys.argv[1:]]
out.mkdir(parents=True, exist_ok=False); profile=out/'profile';profile.mkdir()
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py'); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(site)))
threading.Thread(target=server.serve_forever,daemon=True).start();pipe=m.Pipe(str(chrome),profile)
try:
 target=pipe.call('Target.createTarget',{'url':f'http://127.0.0.1:{server.server_port}/index.html'})['targetId']
 session=pipe.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId']
 def evaluate(expr):
  x=pipe.call('Runtime.evaluate',{'expression':expr,'returnByValue':True},session)
  if 'exceptionDetails' in x:raise ValueError(x['exceptionDetails'])
  return x.get('result',{}).get('value')
 def wait(expr):
  end=time.time()+60
  while time.time()<end:
   if evaluate(expr): return
   time.sleep(.1)
  raise TimeoutError(str(evaluate("document.getElementById('status').textContent")))
 wait("document.querySelector('[data-k=heading]') !== null")
 for i in range(8):
  v='bench-'+str(i)
  evaluate("(()=>{const x=document.querySelector('[data-k=heading]');x.value="+json.dumps(v)+";x.dispatchEvent(new Event('input',{bubbles:true}));})()")
  wait("localStorage.getItem('itonami.zuhyo.candidate.zs1')?.includes("+json.dumps(v)+")")
 print('PASS 8 synthetic saves')
finally:
 try:(out/'timings.json').write_text(json.dumps(evaluate('window.__timings || []'),indent=2)+'\n')
 finally:pipe.close();server.shutdown();server.server_close()
