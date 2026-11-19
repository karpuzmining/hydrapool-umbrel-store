#!/usr/bin/env python3
"""Tiny Bitcoin RPC stand-in so Hydrapool can boot in the verification stack.

It is not a node. It answers the RPC calls Hydrapool makes while starting
and holds the ZMQ port open so the subscriber can connect.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PREVIOUS = "00" * 32


def template() -> dict:
    now = int(time.time())
    return {
        "version": 536870912,
        "rules": ["csv", "segwit"],
        "vbavailable": {},
        "vbrequired": 0,
        "previousblockhash": PREVIOUS,
        "transactions": [],
        "coinbaseaux": {"flags": ""},
        "coinbasevalue": 312500000,
        "longpollid": "verify",
        "target": "7fffff0000000000000000000000000000000000000000000000000000000000",
        "mintime": now - 600,
        "mutable": ["time", "transactions", "prevblock"],
        "noncerange": "00000000ffffffff",
        "sigoplimit": 80000,
        "sizelimit": 4000000,
        "weightlimit": 4000000,
        "curtime": now,
        "bits": "207fffff",
        "height": 1,
        "default_witness_commitment": "6a24aa21a9ed" + ("11" * 32),
    }


def result_for(method: str):
    if method == "getblockchaininfo":
        return {"initialblockdownload": False, "blocks": 1, "headers": 1, "chain": "main"}
    if method == "getblocktemplate":
        return template()
    if method == "getdifficulty":
        return 1.0
    if method == "getmininginfo":
        return {"difficulty": 1.0, "blocks": 1}
    if method == "submitblock":
        return None
    if method == "decoderawtransaction":
        return {"txid": PREVIOUS, "vout": []}
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print("[mock-bitcoin]", fmt % args, flush=True)

    def do_GET(self) -> None:  # noqa: N802
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            body = {}
        method = body.get("method", "")
        payload = {
            "result": result_for(method),
            "error": None if method else {"code": -32600, "message": "no method"},
            "id": body.get("id", 0),
        }
        if method and result_for(method) is None and method not in {"submitblock"}:
            payload["error"] = {"code": -32601, "message": f"unknown method {method}"}
            payload["result"] = None
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def hold_zmq() -> None:
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", 28334))
    server.listen(8)
    while True:
        try:
            conn, _addr = server.accept()
        except OSError:
            return
        conn.close()


def main() -> None:
    threading.Thread(target=hold_zmq, daemon=True).start()
    httpd = ThreadingHTTPServer(("0.0.0.0", 8332), Handler)
    print("mock bitcoin RPC on 8332 and ZMQ port 28334", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
