from __future__ import annotations

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Any
from urllib.parse import urlparse
import uuid

import sys

HOST = "127.0.0.1"
PORT = 5051
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
LOGS_DIR = PROJECT_ROOT / "logs"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from m8_report_builder.report_builder import render_html
from pipeline.pipeline_runner import PipelineRunner
from pipeline.trace_writer import write_trace_artifacts


class ConsoleState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.status = "waiting"
        self.logs: list[str] = []
        self.last_request: dict[str, Any] | None = None
        self.last_run_id: str | None = None
        self.last_report_url: str | None = None
        self.last_error: str | None = None

    def push(self, line: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.logs.append(f"[{stamp}] {line}")
            if len(self.logs) > 500:
                self.logs = self.logs[-500:]

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "running": self.running,
                "status": self.status,
                "logs": "\n".join(self.logs),
                "last_run_id": self.last_run_id,
                "last_report_url": self.last_report_url,
                "last_error": self.last_error,
            }

    def reset(self) -> None:
      with self.lock:
        self.running = False
        self.status = "waiting"
        self.logs = []
        self.last_request = None
        self.last_run_id = None
        self.last_report_url = None
        self.last_error = None


STATE = ConsoleState()


def _reset_console_state() -> None:
  STATE.reset()


def _run_scan(payload: dict[str, Any], run_id: str) -> None:
    institute = str(payload.get("institute_name", "")).strip()
    city = str(payload.get("city", "")).strip()
    debug = bool(payload.get("debug", False))

    STATE.push(f"Scan started for institute='{institute}' city='{city}' run_id='{run_id}'")

    with STATE.lock:
        STATE.running = True
        STATE.status = "running"
        STATE.last_error = None
        STATE.last_request = {"institute_name": institute, "city": city, "debug": debug}

    try:
        raw_input = {
            "entity_name": institute,
            "jurisdiction": city,
            "city": city,
        }

        runner = PipelineRunner()
        run_started_at = datetime.now(timezone.utc).isoformat()
        result = runner.run(
            raw_input=raw_input,
            source_urls=[],
            pipeline_run_id=run_id,
            ai_fields=[],
        )
        run_finished_at = datetime.now(timezone.utc).isoformat()

        output_dir = LOGS_DIR / run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        write_trace_artifacts(
            result=result,
            output_dir=output_dir,
            run_started_at=run_started_at,
            run_finished_at=run_finished_at,
            run_duration_seconds=0.0,
        )
        STATE.push("Trace artifacts written")

        report_html_path = output_dir / "report.html"
        if result.report is not None:
          report_html = render_html(result.report)
          report_html_path.write_text(report_html, encoding="utf-8")
          STATE.push("Rendered HTML report generated")
        else:
          fallback_html = _failed_report_html(run_id=run_id, status=result.status, error=result.error)
          report_html_path.write_text(fallback_html, encoding="utf-8")
          STATE.push("Pipeline did not return report; generated diagnostic HTML report")
        report_url = f"/reports/{run_id}/report.html"

        with STATE.lock:
            STATE.running = False
            STATE.status = result.status
            STATE.last_run_id = run_id
            STATE.last_report_url = report_url
            STATE.last_error = json.dumps(result.error) if result.error else None

        if result.error:
          STATE.push(f"Pipeline error payload: {result.error}")
        STATE.push(f"Scan completed with status='{result.status}'")

    except Exception as exc:  # noqa: BLE001
        with STATE.lock:
            STATE.running = False
            STATE.status = "error"
            STATE.last_error = str(exc)
            STATE.last_run_id = run_id
            STATE.last_report_url = None
        STATE.push(f"Scan failed: {exc}")


class EICH2Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self._write_html(200, _home_page())
            return
        if path == "/health":
            self._write_text(200, "ok")
            return
        if path == "/status":
            self._write_json(200, STATE.snapshot())
            return
        if path == "/open-last-report":
            snap = STATE.snapshot()
            if snap["last_report_url"]:
                self.send_response(302)
                self.send_header("Location", snap["last_report_url"])
                self.end_headers()
                return
            self._write_text(404, "No report available")
            return
        if path.startswith("/reports/"):
            self._serve_report_file(path)
            return
        self._write_text(404, "Not Found")

    def do_POST(self) -> None:  # noqa: N802
      parsed = urlparse(self.path)
      path = parsed.path
      if path == "/scan":
        self._handle_scan()
        return
      if path == "/rerun":
        self._handle_rerun()
        return
      if path == "/reset":
        self._handle_reset()
        return
      self._write_text(404, "Not Found")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _handle_scan(self) -> None:
        with STATE.lock:
            if STATE.running:
                self._write_json(409, {"ok": False, "message": "Scan already running"})
                return

        payload = self._read_json_body()
        institute = str(payload.get("institute_name", "")).strip()
        city = str(payload.get("city", "")).strip()
        if not institute:
            self._write_json(400, {"ok": False, "message": "Institute name is required"})
            return
        if not city:
            self._write_json(400, {"ok": False, "message": "City is required"})
            return

        run_id = f"run-local-{uuid.uuid4().hex[:8]}"
        thread = threading.Thread(target=_run_scan, args=(payload, run_id), daemon=True)
        thread.start()
        self._write_json(202, {"ok": True, "run_id": run_id})

    def _handle_rerun(self) -> None:
        with STATE.lock:
            if STATE.running:
                self._write_json(409, {"ok": False, "message": "Scan already running"})
                return
            payload = dict(STATE.last_request or {})

        if not payload:
            self._write_json(400, {"ok": False, "message": "No previous request available"})
            return

        run_id = f"run-local-{uuid.uuid4().hex[:8]}"
        thread = threading.Thread(target=_run_scan, args=(payload, run_id), daemon=True)
        thread.start()
        self._write_json(202, {"ok": True, "run_id": run_id})

    def _handle_reset(self) -> None:
        _reset_console_state()
        self._write_json(200, {"ok": True})

    def _serve_report_file(self, path: str) -> None:
        rel = path[len("/reports/") :]
        target = (LOGS_DIR / rel).resolve()
        if not str(target).startswith(str(LOGS_DIR.resolve())):
            self._write_text(400, "Invalid path")
            return
        if not target.exists() or not target.is_file():
            self._write_text(404, "Report not found")
            return
        payload = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json_body(self) -> dict[str, Any]:
        raw_len = self.headers.get("Content-Length", "0")
        try:
            size = int(raw_len)
        except ValueError:
            size = 0
        body = self.rfile.read(size) if size > 0 else b"{}"
        try:
            obj = json.loads(body.decode("utf-8"))
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _write_json(self, status: int, data: dict[str, Any]) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _write_html(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _write_text(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _home_page() -> str:
    return """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>EICH 2 Local Testing Console</title>
  <style>
    body { font-family: Segoe UI, Arial, sans-serif; background: #eef1f5; margin: 0; padding: 24px; color: #1f2937; }
    .page { max-width: 1100px; margin: 0 auto; display: grid; grid-template-columns: 1fr; gap: 16px; }
    .panel { background: #fff; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,.08); padding: 20px; }
    .header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
    .header h1 { margin: 0; font-size: 24px; }
    .status { font-weight: 700; border-radius: 999px; padding: 6px 12px; font-size: 12px; }
    .status.waiting { background: #e5e7eb; color: #374151; }
    .status.running { background: #dbeafe; color: #1d4ed8; }
    .status.success { background: #d1fae5; color: #065f46; }
    .status.partial { background: #fef3c7; color: #92400e; }
    .status.quarantined, .status.error { background: #fee2e2; color: #991b1b; }
    .grid { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 12px; margin-top: 14px; }
    label { display: block; font-size: 12px; color: #6b7280; margin-bottom: 6px; }
    input, select { width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 14px; }
    .row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }
    button { border: none; padding: 10px 14px; border-radius: 8px; font-weight: 600; cursor: pointer; }
    .primary { background: #1d4ed8; color: #fff; }
    .neutral { background: #f3f4f6; color: #111827; }
    .console { background: #0b1020; color: #d1d5db; border-radius: 10px; padding: 14px; min-height: 300px; max-height: 460px; overflow: auto; white-space: pre-wrap; font-family: Consolas, monospace; font-size: 12px; }
    .small { color: #6b7280; font-size: 12px; margin-top: 8px; }
    @media (max-width: 860px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class=\"page\">
    <div class=\"panel\">
      <div class=\"header\">
        <h1>EICH 2 Local Testing Console</h1>
        <span id=\"runStatus\" class=\"status waiting\">WAITING</span>
      </div>

      <div class=\"grid\">
        <div>
          <label for=\"institute\">Institute Name</label>
          <input id=\"institute\" type=\"text\" placeholder=\"Enter institute name\" />
        </div>
        <div>
          <label for=\"city\">City</label>
          <select id=\"city\">
            <option value=\"\">Select city</option>
            <option>Chennai</option><option>Mumbai</option><option>Delhi</option>
            <option>Bengaluru</option><option>Hyderabad</option><option>Kolkata</option>
          </select>
        </div>
        <div>
          <label for=\"debug\">Debug Mode</label>
          <select id=\"debug\"><option value=\"false\">Off</option><option value=\"true\">On</option></select>
        </div>
      </div>

      <div class=\"row\">
        <button id=\"scanBtn\" class=\"primary\">Scan</button>
        <button id=\"clearBtn\" class=\"neutral\">Clear Screen</button>
        <button id=\"openBtn\" class=\"neutral\">Open Last Report</button>
        <button id=\"rerunBtn\" class=\"neutral\">Rerun Last</button>
        <button id="resetBtn" class="neutral">Reset Session</button>
      </div>

      <div id=\"reportMeta\" class=\"small\">Last report: Not available yet</div>
    </div>

    <div class=\"panel\">
      <h3 style=\"margin:0 0 10px 0;\">Updator Screen</h3>
      <div id=\"console\" class=\"console\"></div>
    </div>
  </div>

  <script>
    const el = {
      institute: document.getElementById('institute'),
      city: document.getElementById('city'),
      debug: document.getElementById('debug'),
      status: document.getElementById('runStatus'),
      console: document.getElementById('console'),
      reportMeta: document.getElementById('reportMeta'),
      scanBtn: document.getElementById('scanBtn'),
      clearBtn: document.getElementById('clearBtn'),
      openBtn: document.getElementById('openBtn'),
      rerunBtn: document.getElementById('rerunBtn'),
      resetBtn: document.getElementById('resetBtn'),
    };

    const uiState = {
      userTriggeredScan: false,
      pollTimer: null,
    };

    function setStatus(status) {
      const s = (status || 'waiting').toLowerCase();
      el.status.textContent = s.toUpperCase();
      el.status.className = 'status ' + s;
    }

    function setNeutralUI(resetConsole) {
      setStatus('waiting');
      el.reportMeta.textContent = 'Last report: Not available yet';
      if (resetConsole) {
        el.console.textContent = '';
      }
    }

    function startPolling() {
      if (uiState.pollTimer !== null) {
        return;
      }
      uiState.pollTimer = setInterval(fetchStatus, 1200);
    }

    function stopPolling() {
      if (uiState.pollTimer !== null) {
        clearInterval(uiState.pollTimer);
        uiState.pollTimer = null;
      }
    }

    function friendlyError(rawError) {
      const text = String(rawError || '');
      if (text.toLowerCase().includes('entity_records cannot be empty')) {
        return 'No data source found for this institute. Please refine institute/city and retry.';
      }
      return 'Last error: ' + text;
    }

    async function fetchStatus() {
      if (!uiState.userTriggeredScan) {
        setNeutralUI(false);
        return;
      }
      const res = await fetch('/status');
      const data = await res.json();
      setStatus(data.status);
      el.console.textContent = data.logs || '';
      if (data.last_error) {
        el.reportMeta.textContent = friendlyError(data.last_error);
      } else if (data.last_report_url) {
        el.reportMeta.textContent = 'Last report: ' + data.last_report_url + ' (Run: ' + (data.last_run_id || '-') + ')';
      } else {
        el.reportMeta.textContent = 'Last report: Not available yet';
      }
      el.console.scrollTop = el.console.scrollHeight;
    }

    async function startScan() {
      const payload = {
        institute_name: el.institute.value.trim(),
        city: el.city.value,
        debug: el.debug.value === 'true',
      };
      const res = await fetch('/scan', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        alert(data.message || 'Unable to start scan');
        return;
      }
      uiState.userTriggeredScan = true;
      startPolling();
      await fetchStatus();
    }

    async function rerunLast() {
      const res = await fetch('/rerun', {method: 'POST'});
      const data = await res.json();
      if (!res.ok) {
        alert(data.message || 'Unable to rerun');
        return;
      }
      uiState.userTriggeredScan = true;
      startPolling();
      await fetchStatus();
    }

    async function resetSession() {
      const res = await fetch('/reset', {method: 'POST'});
      const data = await res.json();
      if (!res.ok || !data.ok) {
        alert(data.message || 'Unable to reset session');
        return;
      }
      stopPolling();
      uiState.userTriggeredScan = false;
      setNeutralUI(true);
    }

    el.scanBtn.addEventListener('click', startScan);
    el.rerunBtn.addEventListener('click', rerunLast);
    el.clearBtn.addEventListener('click', () => { el.console.textContent = ''; });
    el.openBtn.addEventListener('click', () => { window.open('/open-last-report', '_blank'); });
    el.resetBtn.addEventListener('click', resetSession);

    setNeutralUI(false);
  </script>
</body>
</html>"""


def _failed_report_html(run_id: str, status: str, error: dict[str, Any] | None) -> str:
    pretty_error = json.dumps(error or {}, indent=2)
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>EICH 2 Diagnostic Report</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; background: #f4f6f8; margin: 0; padding: 24px; }}
    .card {{ max-width: 980px; margin: 0 auto; background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,.08); }}
    h1 {{ margin-top: 0; }}
    .badge {{ display: inline-block; background: #fee2e2; color: #991b1b; border-radius: 999px; padding: 4px 10px; font-weight: 700; font-size: 12px; }}
    pre {{ background: #0b1020; color: #d1d5db; padding: 12px; border-radius: 8px; overflow: auto; }}
  </style>
</head>
<body>
  <div class=\"card\">
    <h1>EICH 2 Diagnostic Report</h1>
    <p><span class=\"badge\">{status.upper()}</span></p>
    <p>Run ID: <strong>{run_id}</strong></p>
    <p>The pipeline did not return a final HTML report for this run. See error payload below.</p>
    <pre>{pretty_error}</pre>
  </div>
</body>
</html>"""


def main() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), EICH2Handler)
    print(f"EICH 2 local console server started: http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
