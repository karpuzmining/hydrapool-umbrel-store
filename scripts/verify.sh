#!/usr/bin/env bash
# Boot the Umbrel compose stack against a fake Bitcoin node and check the
# dashboard, both pool modes, and the stratum port.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

echo "== unit tests =="
python3 -m unittest discover -s karpuz-hydrapool/portal/tests -v

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
else
  echo "Docker is not available, so the stack was not started."
  exit 1
fi

COMPOSE=("${DOCKER[@]}" compose -f testing/docker-compose.verify.yml -p hydrapool-verify)
cleanup() {
  code=$?
  if [ "${code}" -ne 0 ]; then
    "${COMPOSE[@]}" logs --tail 80 || true
  fi
  "${COMPOSE[@]}" down -v --remove-orphans || true
}
trap cleanup EXIT

echo "== docker compose up =="
"${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
"${COMPOSE[@]}" up -d

echo "== wait for dashboard =="
ready=0
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:8080/healthz" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [ "${ready}" -ne 1 ]; then
  echo "Dashboard did not open on port 8080."
  exit 1
fi

page="$(curl -fsS http://127.0.0.1:8080/)"
echo "${page}" | grep -q "HYDRAPOOL"
echo "dashboard HTML ok"

python3 - << 'PY'
import json
import urllib.error
import urllib.request

MAIN = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
GENESIS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"

def call(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request("http://127.0.0.1:8080" + path, data=data)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()

status, body = call("/api/setup", {"mode": "solo", "payout_address": "not-an-address"})
assert status == 400, body
print("rejected invalid address")

status, body = call("/api/setup", {"mode": "solo", "payout_address": MAIN})
assert status == 200, body
solo = json.loads(body)["setup"]
assert solo["mode"] == "solo"
assert solo["worker_password"] == "x"
assert "test-rpc-password" not in body.decode()
print("solo setup saved")

status, body = call(
    "/api/setup",
    {
        "mode": "pplns",
        "payout_address": MAIN,
        "fee_bps": 100,
        "fee_address": GENESIS,
        "tailscale_host": "umbrel.example.ts.net",
        "difficulty_multiplier": 1.5,
        "pplns_ttl_days": 3,
    },
)
assert status == 200, body
pplns = json.loads(body)["setup"]
assert pplns["tailscale_url"] == "stratum+tcp://umbrel.example.ts.net:34533"
assert pplns["fee_bps"] == 100
assert "token" not in pplns
print("pplns setup saved")

status, body = call("/api/meta")
meta = json.loads(body)
assert meta["lan_url"] == "stratum+tcp://umbrel.local:34533"
assert meta["configured"] is True
assert meta["bitcoin_ready"] is True
print("meta ok", meta["lan_url"])
PY

echo "== config written for both modes (last save is PPLNS) =="
"${COMPOSE[@]}" exec -T portal python3 - << 'PY'
from pathlib import Path
text = Path("/data/config/config.toml").read_text()
assert 'mode = "hydrapool"' in text
assert "fee = 100" in text
assert "solo_address" not in text
assert "donation" not in text
assert "difficulty_multiplier = 1.5" in text
assert "pplns_ttl_days = 3" in text
assert "tcp://mock-bitcoin:28334" in text
assert 'network = "main"' in text
# The RPC password must be present for the pool and absent from this log.
assert "test-rpc-password" in text
print("config.toml has PPLNS fee, node endpoints, and no donation")
PY

echo "== wait for stratum =="
python3 - << 'PY'
import json
import socket
import time

deadline = time.time() + 90
last = "not tried"
while time.time() < deadline:
    try:
        sock = socket.create_connection(("127.0.0.1", 34533), timeout=3)
        sock.settimeout(8)
        message = {"id": 1, "method": "mining.subscribe", "params": ["hydrapool-verify/1.0"]}
        sock.sendall((json.dumps(message) + "\n").encode())
        data = sock.recv(4096)
        sock.close()
    except OSError as exc:
        last = str(exc)
        time.sleep(2)
        continue
    if data and b"mining.notify" in data:
        text = data.decode(errors="replace").strip().splitlines()[0][:240]
        print("stratum accepted connection:", text)
        break
    last = "empty subscribe response"
    time.sleep(2)
else:
    raise SystemExit(f"stratum port 34533 did not accept a subscribe ({last})")
PY

curl -fsS http://127.0.0.1:8080/api/live >/dev/null
echo "live API ok"
echo "verification passed"
