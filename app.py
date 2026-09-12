"""Run the simple local website for YouTube Transcript Studio.

This file serves the friendly paste-a-link screen and starts resumable local
pipeline jobs. It uses only Python's standard library, so the app stays easy to
run and does not send transcript text to a third party.
"""

from __future__ import annotations

import json
import mimetypes
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from pipeline import run_pipeline


HOST = "127.0.0.1"
PORT = 8080
EXPORT_ROOT = Path(__file__).resolve().parent / "exports"
JOBS: dict[str, dict] = {}


HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>YouTube Transcript Studio</title>
  <style>
    :root{--ink:#18232d;--muted:#63717d;--paper:#f7f5f0;--card:#fffdf9;--line:#e7e0d5;--orange:#ec6d42;--blue:#2b6e87;--shadow:0 22px 70px #30405216}
    *{box-sizing:border-box}body{margin:0;color:var(--ink);background:radial-gradient(circle at 8% 2%,#ffe7d1 0,transparent 27%),radial-gradient(circle at 94% 10%,#dcebf0 0,transparent 24%),var(--paper);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}
    main{max-width:1120px;margin:0 auto;padding:30px 22px 70px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:64px}.mark{display:flex;gap:12px;align-items:center;font-weight:760;letter-spacing:-.03em}.logo{width:38px;height:38px;border-radius:13px;background:var(--ink);color:#fff;display:grid;place-items:center;box-shadow:5px 5px 0 var(--orange)}.badge{padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:#ffffffa8;color:var(--muted);font-size:12px}
    .hero{max-width:800px}.eyebrow{color:var(--orange);font-weight:800;letter-spacing:.14em;text-transform:uppercase;font-size:12px}.hero h1{font-size:clamp(42px,7vw,76px);line-height:.98;letter-spacing:-.07em;margin:16px 0 22px}.hero p{max-width:650px;color:var(--muted);font-size:18px;margin:0}.panel{margin-top:42px;background:var(--card);border:1px solid var(--line);border-radius:28px;padding:24px;box-shadow:var(--shadow)}label{font-size:12px;font-weight:800;color:var(--muted);display:block;margin-bottom:8px;text-transform:uppercase;letter-spacing:.1em}.row{display:flex;gap:12px}.url{flex:1;border:1px solid #d8d1c5;border-radius:15px;padding:16px 17px;font:inherit;outline:none;background:#fff}.url:focus{border-color:var(--blue);box-shadow:0 0 0 4px #2b6e8714}.button{border:0;border-radius:15px;background:var(--ink);color:#fff;padding:0 22px;font-weight:800;cursor:pointer}.button:hover{background:var(--orange)}.hint{display:flex;gap:9px;flex-wrap:wrap;margin-top:17px;color:var(--muted);font-size:13px}.chip{padding:7px 10px;background:#f0eee9;border-radius:999px}.grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-top:18px}.feature{padding:18px;border:1px solid var(--line);border-radius:19px;background:#ffffff8a}.feature strong{display:block;margin-bottom:4px}.feature span{color:var(--muted);font-size:13px}.job{display:none;margin-top:18px}.job.show{display:block}.job-head{display:flex;justify-content:space-between;gap:20px;align-items:start}.job h2{font-size:18px;margin:0}.status{color:var(--muted);font-size:13px}.bar{height:10px;background:#eee9e0;border-radius:999px;overflow:hidden;margin:18px 0}.bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--orange),#f3b05c);transition:width .3s}.stats{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;color:var(--muted)}.stats b{color:var(--ink)}.links{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}.links a{color:var(--blue);font-weight:750;text-decoration:none;border-bottom:1px solid #2b6e8750;padding-bottom:2px}.error{color:#a53b2b;background:#fff0ec;border-radius:12px;padding:12px;margin-top:14px;display:none}.error.show{display:block}@media(max-width:720px){.top{margin-bottom:42px}.row{display:block}.button{height:52px;width:100%;margin-top:10px}.grid{grid-template-columns:1fr}.hero h1{font-size:51px}}
  </style>
</head>
<body><main>
  <header class="top"><div class="mark"><div class="logo">YT</div><span>Transcript Studio</span></div><div class="badge">local-first · AI-ready</div></header>
  <section class="hero"><div class="eyebrow">Turn any YouTube link into research</div><h1>Paste a link.<br>Get the words.</h1><p>Pull transcripts from one video, a full playlist, or an entire channel. Clean timing noise, split long exports, and make them ready for NotebookLM or your next AI prompt.</p></section>
  <section class="panel"><form id="form"><label for="url">YouTube link</label><div class="row"><input class="url" id="url" required placeholder="https://youtube.com/@channel/videos" autocomplete="url"><button class="button" type="submit">Start extraction</button></div><div class="hint"><span class="chip">video</span><span class="chip">playlist</span><span class="chip">channel</span><span>Nothing leaves this machine.</span></div></form>
    <div class="grid"><div class="feature"><strong>Resumable</strong><span>Interruptions do not throw away completed videos.</span></div><div class="feature"><strong>500k parts</strong><span>Long source packs are split at a hard character limit.</span></div><div class="feature"><strong>AI handoff</strong><span>Every run includes a clean prompt and source map.</span></div></div>
    <div class="job" id="job"><div class="job-head"><div><h2 id="jobTitle">Preparing run</h2><div class="status" id="jobStatus">Starting…</div></div><div class="badge" id="jobKind">waiting</div></div><div class="bar"><i id="bar"></i></div><div class="stats"><span>videos <b id="videos">—</b></span><span>transcripts <b id="transcripts">—</b></span><span>parts <b id="parts">—</b></span><span>status <b id="state">—</b></span></div><div class="links" id="links"></div><div class="error" id="error"></div></div>
  </section>
</main><script>
const $=id=>document.getElementById(id);let timer;
function render(data){$('job').classList.add('show');$('jobTitle').textContent=data.title||'Extraction run';$('jobKind').textContent=data.kind||'working';$('jobStatus').textContent=data.current_title?`${data.current_status||'working'} · ${data.current_title}`:'Preparing source list…';$('videos').textContent=data.total??data.videos??'—';$('transcripts').textContent=data.completed??data.transcripts??'—';$('parts').textContent=data.notebook_parts??'—';$('state').textContent=data.status||'running';let pct=data.total?Math.min(100,Math.round(((data.completed||0)/data.total)*100)):4;$('bar').style.width=pct+'%';if(data.error){$('error').textContent=data.error;$('error').classList.add('show')}if(data.status==='complete'||data.status==='partial'){clearInterval(timer);$('bar').style.width='100%';$('links').innerHTML=`<a href="/api/jobs/${data.id}/prompt" target="_blank">Open AI prompt</a><a href="/api/jobs/${data.id}/parts" target="_blank">List NotebookLM parts</a><a href="/api/jobs/${data.id}/summary" target="_blank">Open run summary</a>`}}
async function poll(id){const r=await fetch('/api/jobs/'+id);const d=await r.json();d.id=id;render(d);if(d.status==='running')timer=setTimeout(()=>poll(id),1200)}
$('form').addEventListener('submit',async e=>{e.preventDefault();$('error').classList.remove('show');const r=await fetch('/api/jobs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({url:$('url').value})});const d=await r.json();if(!r.ok){$('error').textContent=d.error||'Could not start run';$('error').classList.add('show');return}render(d);poll(d.id)});
</script></body></html>'''


def _json(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    raw = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _resume_run(source_url: str) -> Path | None:
    """Find an unfinished export for the same source after an app restart."""

    for run_dir in sorted(EXPORT_ROOT.iterdir(), reverse=True) if EXPORT_ROOT.exists() else []:
        state_path = run_dir / "state.json"
        if not run_dir.is_dir() or not state_path.exists():
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if state.get("source_url") == source_url and state.get("status") != "complete":
            return run_dir
    return None


class Handler(BaseHTTPRequestHandler):
    """Serve the UI and the tiny JSON API."""

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            raw = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if parsed.path.startswith("/api/jobs/"):
            bits = parsed.path.strip("/").split("/")
            job_id = bits[2] if len(bits) > 2 else ""
            job = JOBS.get(job_id)
            if not job:
                _json(self, {"error": "Run not found"}, 404)
                return
            if len(bits) == 3:
                _json(self, job)
                return
            root = Path(job["run_dir"])
            if bits[3] == "summary":
                path = root / "state.json"
                if path.exists():
                    _json(self, json.loads(path.read_text(encoding="utf-8")))
                    return
            if bits[3] == "prompt":
                prompts = sorted(root.glob("AI prompt - YouTube - *.md"))
                if prompts:
                    path = prompts[0]
                    self._file(path, "text/markdown; charset=utf-8")
                    return
            if bits[3] == "parts":
                parts = sorted(path.name for path in (root / "notebooklm").glob("*.md"))
                _json(self, {"parts": parts})
                return
        _json(self, {"error": "Not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/jobs":
            _json(self, {"error": "Not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            source_url = str(payload.get("url", "")).strip()
            if not source_url:
                raise ValueError("Paste a YouTube URL first.")
            existing_dir = _resume_run(source_url)
            job_id = existing_dir.name if existing_dir else uuid.uuid4().hex[:10]
            run_dir = existing_dir or EXPORT_ROOT / job_id
            job = {"id": job_id, "status": "running", "source_url": source_url, "run_dir": str(run_dir)}
            JOBS[job_id] = job

            def work() -> None:
                try:
                    def update(state: dict) -> None:
                        job.update(state)
                    result = run_pipeline(source_url, run_dir, progress=update)
                    job.update(result)
                except Exception as error:
                    job.update({"status": "error", "error": str(error)})
            threading.Thread(target=work, daemon=True).start()
            _json(self, job, 202)
        except Exception as error:
            _json(self, {"error": str(error)}, 400)

    def _file(self, path: Path, content_type: str | None = None) -> None:
        raw = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main() -> None:
    """Start the local web app."""

    EXPORT_ROOT.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"YouTube Transcript Studio: http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
