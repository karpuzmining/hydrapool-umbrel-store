#!/usr/bin/env python3
"""Dashboard and setup service for Hydrapool on Umbrel.

The pool process stays stopped until this service writes config.toml.
Umbrel's app proxy only needs this process, so the UI loads even while
Bitcoin or the pool is still starting.
"""

from __future__ import annotations

import base64
import json
import os
import platform
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from addresses import network_label

import bitcoin_status
import configgen
import metrics

ASSET_VERSION = "1.0.4"

STATIC_DIR = Path(__file__).resolve().parent / "static"
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
API_URL = os.environ.get("HYDRAPOOL_API_URL", "http://hydrapool:46884").rstrip("/")
STRATUM_PORT = int(os.environ.get("HYDRAPOOL_STRATUM_PORT", "34533"))
SAMPLE_SECONDS = int(os.environ.get("HYDRAPOOL_SAMPLE_SECONDS", "15"))
HISTORY_SECONDS = 6 * 60 * 60

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.lock = threading.Lock()
        self.samples: list[dict] = []
        self.known: dict[tuple[str, str], dict] = {}
        self.pool_up = False
        self.pool_error = "Waiting for the pool"
        self.bitcoin = {
            "reachable": False,
            "syncing": False,
            "template_error_code": None,
            "verification_progress": None,
            "blocks": None,
            "headers": None,
            "message": "",
        }
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        path = self.data_dir / "history.jsonl"
        if not path.exists():
            return
        cutoff = time.time() - HISTORY_SECONDS
        for line in path.read_text().splitlines():
            try:
                sample = json.loads(line)
            except json.JSONDecodeError:
                continue
            if int(sample.get("t", 0)) < cutoff:
                continue
            self.samples.append(sample)
            self._remember(sample)

    def _remember(self, sample: dict) -> None:
        seen = int(sample["t"])
        for worker in sample.get("workers", []):
            key = (worker["address"], worker["worker"])
            current = self.known.get(key)
            record = {
                "address": worker["address"],
                "worker": worker["worker"],
                "work": int(worker.get("work") or 0),
                "best": int(worker.get("best") or 0),
                "last_share": int(worker.get("last_share") or 0),
                "seen": seen,
            }
            if current is None or record["seen"] >= current["seen"]:
                self.known[key] = record

    def add_sample(self, parsed: dict, stamp: int | None = None) -> None:
        sample = {
            "t": int(stamp if stamp is not None else time.time()),
            "accepted_difficulty": int(parsed["accepted_difficulty"]),
            "accepted": int(parsed["accepted"]),
            "rejected": int(parsed["rejected"]),
            "best_share": int(parsed["best_share"]),
            "workers": parsed["workers"],
        }
        with self.lock:
            if self.samples and int(self.samples[-1]["t"]) == sample["t"]:
                self.samples[-1] = sample
            else:
                self.samples.append(sample)
            cutoff = sample["t"] - HISTORY_SECONDS
            self.samples = [item for item in self.samples if int(item["t"]) >= cutoff]
            self._remember(sample)
            self._flush()

    def _flush(self) -> None:
        path = self.data_dir / "history.jsonl"
        temporary = path.with_suffix(".jsonl.tmp")
        temporary.write_text("".join(json.dumps(sample) + "\n" for sample in self.samples))
        os.replace(temporary, path)

    def snapshot(self) -> dict:
        with self.lock:
            payload = metrics.build_snapshot(
                list(self.samples),
                dict(self.known),
                int(time.time()),
                self.pool_up,
                self.pool_error,
            )
            payload["bitcoin"] = dict(self.bitcoin)
            return payload

    def set_pool(self, up: bool, error: str) -> None:
        with self.lock:
            self.pool_up = up
            self.pool_error = error


def read_metrics_text(secret: dict | None) -> str:
    fixture = os.environ.get("HYDRAPOOL_METRICS_FILE", "").strip()
    if fixture:
        return Path(fixture).read_text()
    if secret is None:
        raise RuntimeError("API credentials are not ready")
    request = urllib.request.Request(API_URL + "/metrics")
    token = base64.b64encode(f"{secret['user']}:{secret['password']}".encode()).decode()
    request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request, timeout=4) as response:
        return response.read().decode()


def sample_once(store: Store) -> None:
    secret_path = store.data_dir / "secrets.json"
    secret = None
    if secret_path.exists():
        try:
            secret = json.loads(secret_path.read_text())
        except json.JSONDecodeError:
            secret = None
    try:
        parsed = metrics.parse_exposition(read_metrics_text(secret))
    except (OSError, urllib.error.URLError, RuntimeError, ValueError) as exc:
        store.set_pool(False, "Pool is not answering yet")
        return
    store.set_pool(True, "")
    store.add_sample(parsed)


def refresh_bitcoin(store: Store) -> None:
    info, info_error = bitcoin_rpc("getblockchaininfo", [])
    _template, template_error = bitcoin_rpc(
        "getblocktemplate",
        [{"rules": ["segwit"]}],
    )
    # A missing node should not look like "still syncing".
    if info is None and info_error and info_error.get("code") is None and template_error and template_error.get("code") is None:
        status = bitcoin_status.interpret(None, None)
        status["reachable"] = False
    else:
        status = bitcoin_status.interpret(info, template_error if template_error else None)
    with store.lock:
        store.bitcoin = status


def bitcoin_rpc(method: str, params: list) -> tuple[dict | None, dict | None]:
    env = configgen.read_bitcoin_env()
    if configgen.bitcoin_problem(env):
        return None, {"code": None, "message": "Bitcoin RPC is not configured"}
    url = f"http://{env['ip']}:{int(env['rpc_port'])}"
    payload = json.dumps(
        {"jsonrpc": "1.0", "id": "portal", "method": method, "params": params}
    ).encode()
    request = urllib.request.Request(url, data=payload)
    request.add_header("Content-Type", "application/json")
    credentials = base64.b64encode(f"{env['rpc_user']}:{env['rpc_password']}".encode()).decode()
    request.add_header("Authorization", f"Basic {credentials}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return None, {"code": exc.code, "message": "Bitcoin RPC failed"}
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None, {"code": None, "message": "Bitcoin RPC unreachable"}
    error = body.get("error")
    if error:
        return None, error if isinstance(error, dict) else {"code": None, "message": str(error)}
    result = body.get("result")
    return result if isinstance(result, dict) else None, None


def sampler(store: Store, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            refresh_bitcoin(store)
        except Exception as exc:  # noqa: BLE001
            print(f"[portal] bitcoin status failed: {exc}", flush=True)
        sample_once(store)
        stop.wait(SAMPLE_SECONDS)


def public_setup(setup: dict | None) -> dict | None:
    if not setup:
        return None
    host = setup.get("tailscale_host") or ""
    tailscale_url = f"stratum+tcp://{host}:{STRATUM_PORT}" if host else ""
    return {
        "mode": setup["mode"],
        "payout_address": setup["payout_address"],
        "fee_bps": setup["fee_bps"],
        "fee_address": setup["fee_address"],
        "tailscale_host": host,
        "tailscale_url": tailscale_url,
        "difficulty_multiplier": setup["difficulty_multiplier"],
        "pplns_ttl_days": setup["pplns_ttl_days"],
        "start_difficulty": setup["start_difficulty"],
        "minimum_difficulty": setup["minimum_difficulty"],
        "worker_user": f"{setup['payout_address']}.worker",
        "worker_password": "x",
    }


def load_setup(data_dir: Path) -> dict | None:
    path = data_dir / "setup.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def device_domain() -> str:
    domain = os.environ.get("DEVICE_DOMAIN_NAME", "").strip().lower().rstrip(".") or "umbrel.local"
    if not configgen.hostname_is_valid(domain):
        return "umbrel.local"
    return domain


def meta_payload(data_dir: Path) -> dict:
    env = configgen.read_bitcoin_env()
    problem = configgen.bitcoin_problem(env)
    domain = device_domain()
    hostname = os.environ.get("DEVICE_HOSTNAME", "").strip() or "umbrel"
    setup = load_setup(data_dir)
    return {
        "device_domain": domain,
        "device_hostname": hostname,
        "stratum_port": STRATUM_PORT,
        "lan_url": f"stratum+tcp://{domain}:{STRATUM_PORT}",
        "cpu_arch": platform.machine(),
        "network": env.get("network") or "",
        "network_label": network_label(env["network"]) if env.get("network") else "",
        "network_supported": bool(env.get("network")),
        "bitcoin_ready": problem == "",
        "bitcoin_problem": problem,
        "configured": setup is not None,
        "setup": public_setup(setup),
    }


def save_setup(data_dir: Path, payload: dict) -> dict:
    env = configgen.read_bitcoin_env()
    problem = configgen.bitcoin_problem(env)
    if problem:
        raise configgen.SetupError(problem)
    setup = configgen.normalize_setup(payload, env["network"])
    secret = configgen.load_or_create_api_secret(data_dir)
    rendered = configgen.render_config(setup, env, secret["user"], secret["token"])
    configgen._atomic_write(data_dir / "setup.json", json.dumps(setup, indent=2) + "\n", 0o600)
    configgen._atomic_write(data_dir / "config" / "config.toml", rendered, 0o600)
    return public_setup(setup)


class Handler(BaseHTTPRequestHandler):
    store: Store
    data_dir: Path

    def log_message(self, fmt: str, *args) -> None:
        message = fmt % args
        if "password" in message.lower() or "rpc" in message.lower():
            return
        print(f"[portal] {self.address_string()} {message}", flush=True)

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._do_GET()
        except Exception as exc:  # noqa: BLE001 - keep the dashboard process alive
            print(f"[portal] request failed: {exc}", flush=True)
            if not self.wfile.closed:
                try:
                    self._send(500, b"Portal error", "text/plain; charset=utf-8")
                except Exception:
                    pass

    def _do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._send(200, b"ok", "text/plain; charset=utf-8")
            return
        if path == "/api/meta":
            self._send_json(meta_payload(self.data_dir))
            return
        if path == "/api/live":
            self._send_json(self.store.snapshot())
            return
        if path in ("/", "/index.html"):
            self._send_file(STATIC_DIR / "index.html")
            return
        relative = path.lstrip("/")
        if relative.startswith("api/") or ".." in relative or relative.startswith("/"):
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        candidate = (STATIC_DIR / relative).resolve()
        if STATIC_DIR not in candidate.parents and candidate != STATIC_DIR:
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        if candidate.is_file():
            self._send_file(candidate)
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/api/setup":
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > 100_000:
            self._send_json({"error": "Setup request was empty or too large."}, 400)
            return
        try:
            payload = json.loads(self.rfile.read(length).decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"error": "Setup request was not valid JSON."}, 400)
            return
        try:
            saved = save_setup(self.data_dir, payload)
        except configgen.SetupError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        self._send_json({"ok": True, "setup": saved})

    def _send_file(self, path: Path) -> None:
        body = path.read_bytes()
        version = ASSET_VERSION.encode()
        if path.name == "index.html":
            body = body.replace(b'href="app.css"', b'href="app.css?v=' + version + b'"')
            body = body.replace(b'src="app.js"', b'src="app.js?v=' + version + b'"')
            body = body.replace(b'mascot.svg"', b'mascot.svg?v=' + version + b'"')
        elif path.name == "app.css":
            body = body.replace(
                b'share-tech-mono.woff2"',
                b'share-tech-mono.woff2?v=' + version + b'"',
            )
        self._send(200, body, CONTENT_TYPES.get(path.suffix, "application/octet-stream"))

    def _send_json(self, payload: dict, status: int = 200) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json; charset=utf-8")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def make_server(host: str, port: int, data_dir: Path, start_sampler: bool = True):
    store = Store(data_dir)
    stop = threading.Event()
    if start_sampler:
        threading.Thread(target=sampler, args=(store, stop), daemon=True).start()

    class BoundHandler(Handler):
        pass

    BoundHandler.store = store
    BoundHandler.data_dir = data_dir
    httpd = ThreadingHTTPServer((host, port), BoundHandler)
    httpd.store = store  # type: ignore[attr-defined]
    httpd.stop_sampler = stop  # type: ignore[attr-defined]
    return httpd


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    httpd = make_server("0.0.0.0", 8080, DATA_DIR, start_sampler=True)
    print(f"Hydrapool portal listening on 0.0.0.0:8080, data in {DATA_DIR}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
