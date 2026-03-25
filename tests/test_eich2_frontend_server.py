from __future__ import annotations

import json
import threading
from urllib.request import Request, urlopen

from eich2_frontend_server import EICH2Handler, STATE, _home_page, _reset_console_state
from http.server import ThreadingHTTPServer


def _start_test_server() -> tuple[ThreadingHTTPServer, int, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), EICH2Handler)
    port = int(server.server_address[1])
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return server, port, worker


def test_home_page_has_reset_button_and_neutral_defaults() -> None:
    html = _home_page()

    assert 'id="resetBtn"' in html
    assert 'class="status waiting">WAITING<' in html
    assert 'Last report: Not available yet' in html


def test_home_page_does_not_fetch_status_on_load_and_polls_via_helper() -> None:
    html = _home_page()

    assert '\n    fetchStatus();\n' not in html
    assert 'function startPolling()' in html
    assert 'setInterval(fetchStatus, 1200)' in html
    assert html.count('startPolling();') >= 2


def test_reset_console_state_helper_clears_fields() -> None:
    with STATE.lock:
        STATE.running = True
        STATE.status = 'error'
        STATE.logs = ['x']
        STATE.last_request = {'institute_name': 'X'}
        STATE.last_run_id = 'run-1'
        STATE.last_report_url = '/reports/run-1/report.html'
        STATE.last_error = 'boom'

    _reset_console_state()
    snap = STATE.snapshot()

    assert snap['running'] is False
    assert snap['status'] == 'waiting'
    assert snap['logs'] == ''
    assert snap['last_run_id'] is None
    assert snap['last_report_url'] is None
    assert snap['last_error'] is None


def test_reset_endpoint_clears_console_state() -> None:
    with STATE.lock:
        STATE.running = True
        STATE.status = 'error'
        STATE.logs = ['line-1']
        STATE.last_request = {'institute_name': 'Test'}
        STATE.last_run_id = 'run-old'
        STATE.last_report_url = '/reports/run-old/report.html'
        STATE.last_error = 'old error'

    server, port, _worker = _start_test_server()
    try:
        req = Request(
            f'http://127.0.0.1:{port}/reset',
            data=b'{}',
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode('utf-8'))

        assert payload['ok'] is True
        snap = STATE.snapshot()
        assert snap['running'] is False
        assert snap['status'] == 'waiting'
        assert snap['logs'] == ''
        assert snap['last_run_id'] is None
        assert snap['last_report_url'] is None
        assert snap['last_error'] is None
    finally:
        server.shutdown()
        server.server_close()
        _reset_console_state()
