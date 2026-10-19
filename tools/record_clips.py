"""Record one clip per scenario from the briefing map.

Serves the project over HTTP and exposes a recorder page that drives the map
through every approach and scenario, captures the canvas with a title bar
burned in, and posts each recording back here to be written to clips/.

    python tools/record_clips.py          # then open http://localhost:8731/_recorder

Recordings land in clips/ as .webm; convert_clips.py turns them into .mp4.
"""
import http.server, socketserver, os, re, sys, threading, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'clips')
PORT = int(os.environ.get('CLIP_PORT', '8731'))

RECORDER = r"""<!doctype html><html><head><meta charset="utf-8"><title>Recording clips</title>
<style>body{margin:0;font:14px system-ui;background:#101c26;color:#dfe9f0}
#bar{padding:10px 16px;background:#0b1620;font-variant-numeric:tabular-nums}
#log{padding:8px 16px;max-height:34vh;overflow:auto;font:12px ui-monospace,Consolas,monospace;white-space:pre-wrap}
iframe{border:0;width:1180px;height:760px;background:#fff}
canvas{display:none}</style></head><body>
<div id="bar">starting…</div><div id="log"></div>
<iframe id="f" src="index.html"></iframe><canvas id="out"></canvas>
<script>
const SETTLE=2600, DURATION=9000, FPS=25, HEAD=66;
function keepAwake(){try{const a=new (window.AudioContext||window.webkitAudioContext)();
const o=a.createOscillator(),g=a.createGain();g.gain.value=0.0001;
o.connect(g);g.connect(a.destination);o.start();return a}catch(e){return null}}
const bar=document.getElementById('bar'), log=document.getElementById('log');
const say=t=>{log.textContent+=t+'\n';log.scrollTop=1e9;bar.textContent=t};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const slug=s=>s.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,46);

function compose(src,out,title,sub){
  const ctx=out.getContext('2d');
  ctx.fillStyle='#102c44';ctx.fillRect(0,0,out.width,HEAD);
  ctx.fillStyle='#fff';ctx.font='700 21px system-ui';ctx.fillText(title,18,29);
  ctx.fillStyle='#b9d1e3';ctx.font='14px system-ui';ctx.fillText(sub,18,52);
  ctx.drawImage(src,0,0,src.width,src.height,0,HEAD,out.width,out.height-HEAD);
}

async function record(src,out,title,sub,name){
  const stream=out.captureStream(FPS);
  const mt=['video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm']
            .find(t=>MediaRecorder.isTypeSupported(t));
  const rec=new MediaRecorder(stream,{mimeType:mt,videoBitsPerSecond:2200000});
  const parts=[];rec.ondataavailable=e=>e.data.size&&parts.push(e.data);
  let raf;const tick=()=>{compose(src,out,title,sub);raf=requestAnimationFrame(tick)};
  tick();rec.start();
  await sleep(DURATION);
  await new Promise(r=>{rec.onstop=r;rec.stop()});
  cancelAnimationFrame(raf);
  const blob=new Blob(parts,{type:'video/webm'});
  await fetch('/save?name='+encodeURIComponent(name),{method:'POST',body:blob});
  return blob.size;
}

(async()=>{
  const ac=keepAwake();
  if(ac&&ac.state==='suspended')document.addEventListener('click',()=>ac.resume(),{once:true});
  const f=document.getElementById('f');
  await new Promise(r=>f.addEventListener('load',r,{once:true}));
  await sleep(1800);
  const w=f.contentWindow, doc=f.contentDocument;
  const origin=doc.getElementById('origin'), scen=doc.getElementById('scenario');
  const src=doc.querySelector('canvas'), out=document.getElementById('out');
  const jobs=[];
  for(const o of [...origin.options]){
    origin.value=o.value;origin.onchange();await sleep(120);
    for(const s of [...scen.options]) jobs.push([o.value,o.textContent,s.value,s.textContent]);
  }
  const q=new URLSearchParams(location.search);
  const from=+(q.get('from')||1), to=+(q.get('to')||jobs.length);
  say('scenarios '+from+'-'+to+' of '+jobs.length);
  let n=0;
  for(const [ov,otext,sv,stext] of jobs){
    n++;
    if(n<from||n>to)continue;
    origin.value=ov;origin.onchange();await sleep(150);
    scen.value=sv;scen.onchange();
    await sleep(SETTLE);
    out.width=src.width/ (w.devicePixelRatio||1);
    out.height=src.height/(w.devicePixelRatio||1)+HEAD;
    const name=String(n).padStart(2,'0')+'-'+slug(otext)+'--'+slug(stext)+'.webm';
    say('['+n+'/'+jobs.length+'] '+name);
    const size=await record(src,out,otext.replace(/^\d+\s*·\s*/,''),stext,name);
    say('      saved '+(size/1024|0)+' KB'+(size<4000?'   <-- EMPTY, page was throttled':''));
    await sleep(400);
  }
  await fetch('/done',{method:'POST'});
  say('ALL DONE — '+jobs.length+' clips');
})().catch(e=>say('ERROR: '+e.message+'\n'+e.stack));
</script></body></html>"""

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.split('?')[0] in ('/_recorder', '/_recorder.html'):
            b = RECORDER.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        return super().do_GET()

    def do_POST(self):
        path, _, qs = self.path.partition('?')
        if path == '/done':
            print('RECORDER REPORTS DONE', flush=True)
            self.send_response(204); self.end_headers(); return
        if path != '/save':
            self.send_error(404); return
        name = urllib.parse.parse_qs(qs).get('name', ['clip.webm'])[0]
        name = re.sub(r'[^A-Za-z0-9._-]', '_', name)
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, name), 'wb') as fh:
            fh.write(body)
        print('saved %s (%d KB)' % (name, len(body) // 1024), flush=True)
        self.send_response(204); self.end_headers()

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    with socketserver.ThreadingTCPServer(('127.0.0.1', PORT), H) as srv:
        srv.allow_reuse_address = True
        print('serving %s on http://localhost:%d  (recorder at /_recorder)' % (ROOT, PORT), flush=True)
        srv.serve_forever()
