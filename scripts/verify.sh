#!/usr/bin/env bash
# Boot the Umbrel compose stack against a fake Bitcoin node and check the
# dashboard, both pool modes, and the stratum port.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

echo "== app store manifest =="
test -f umbrel-app-store.yml
python3 - << 'PY'
import pathlib, re, sys
text = pathlib.Path("umbrel-app-store.yml").read_text()
match = re.search(r'(?m)^id:\s*"([^"]+)"\s*$', text)
if not match:
    sys.exit("umbrel-app-store.yml is missing an id")
store_id = match.group(1)
if not re.fullmatch(r"[a-z0-9-]+", store_id):
    sys.exit(f"store id {store_id!r} is not a plain id")
apps = list(pathlib.Path(".").glob("*/umbrel-app.yml"))
if not apps:
    sys.exit("no app manifests found")
for manifest in apps:
    folder = manifest.parent.name
    if not folder.startswith(store_id + "-"):
        sys.exit(f"{folder} does not start with {store_id}-")
print(f"store id {store_id} prefixes {len(apps)} app(s)")
PY

echo "== unit tests =="
python3 -m unittest discover -s karpuz-hydrapool/portal/tests -v

echo "== pre-start copies the store checkout over a stale app-data =="
STORE_ROOT="$(mktemp -d)"
APP_STALE="$(mktemp -d)"
DIRECT="$(mktemp -d)"
mkdir -p \
  "${STORE_ROOT}/app-stores/example/karpuz-hydrapool/portal" \
  "${STORE_ROOT}/app-stores/example/karpuz-hydrapool/scripts" \
  "${DIRECT}/portal" \
  "${DIRECT}/scripts" \
  "${APP_STALE}/portal" \
  "${APP_STALE}/data"
printf 'old-ui\n' > "${APP_STALE}/portal/index.html"
printf 'keep-config\n' > "${APP_STALE}/data/config.toml"
printf 'from-store\n' > "${STORE_ROOT}/app-stores/example/karpuz-hydrapool/portal/server.py"
printf '#!/bin/sh\necho from-store\n' > "${STORE_ROOT}/app-stores/example/karpuz-hydrapool/scripts/run-hydrapool.sh"
printf 'from-env\n' > "${DIRECT}/portal/server.py"
printf '#!/bin/sh\necho from-env\n' > "${DIRECT}/scripts/run-hydrapool.sh"
UMBREL_ROOT="${STORE_ROOT}" APP_DATA_DIR="${APP_STALE}" sh "${ROOT}/karpuz-hydrapool/hooks/pre-start"
grep -q from-store "${APP_STALE}/portal/server.py"
test ! -f "${APP_STALE}/portal/index.html"
grep -q from-store "${APP_STALE}/scripts/run-hydrapool.sh"
grep -q keep-config "${APP_STALE}/data/config.toml"
SCRIPT_APP_REPO_DIR="${DIRECT}" UMBREL_ROOT="${STORE_ROOT}" APP_DATA_DIR="${APP_STALE}" sh "${ROOT}/karpuz-hydrapool/hooks/pre-start"
grep -q from-env "${APP_STALE}/portal/server.py"
printf 'still-old\n' > "${APP_STALE}/portal/index.html"
SCRIPT_APP_REPO_DIR="" UMBREL_ROOT="${STORE_ROOT}/missing" APP_DATA_DIR="${APP_STALE}" sh "${ROOT}/karpuz-hydrapool/hooks/pre-start"
grep -q still-old "${APP_STALE}/portal/index.html"
rm -rf "${STORE_ROOT}" "${APP_STALE}" "${DIRECT}"

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
else
  echo "Docker is not available, so the stack was not started."
  exit 1
fi

# Umbrel copies the app into APP_DATA_DIR, then runs compose with a project
# directory that is not that folder. Relative ./portal mounts miss the files.
APP_DATA_DIR="$(mktemp -d)"
PROJECT_DIR="$(mktemp -d)"
cp -a "${ROOT}/karpuz-hydrapool/." "${APP_DATA_DIR}/"
mkdir -p "${APP_DATA_DIR}/data" "${PROJECT_DIR}/portal"
# umbreld removes app_proxy before docker compose up and runs the gateway itself.
python3 - "${APP_DATA_DIR}/docker-compose.yml" << 'PY'
import pathlib, sys
src = pathlib.Path(sys.argv[1])
out = []
skip = False
for line in src.read_text().splitlines(True):
    if line.startswith("  app_proxy:"):
        skip = True
        continue
    if skip:
        if line.startswith("  ") and not line.startswith("   ") and line.rstrip().endswith(":"):
            skip = False
        else:
            continue
    out.append(line)
src.write_text("".join(out))
PY
VERIFY_MOCK_SCRIPT="${ROOT}/testing/mock_bitcoin.py"
ENV_FILE="$(mktemp)"
cat > "${ENV_FILE}" << EOF
APP_DATA_DIR=${APP_DATA_DIR}
VERIFY_MOCK_SCRIPT=${VERIFY_MOCK_SCRIPT}
DEVICE_DOMAIN_NAME=umbrel.local
DEVICE_HOSTNAME=umbrel
APP_BITCOIN_NETWORK=mainnet
APP_BITCOIN_NODE_IP=mock-bitcoin
APP_BITCOIN_RPC_PORT=8332
APP_BITCOIN_RPC_USER=umbrel
APP_BITCOIN_RPC_PASS=test-rpc-password
APP_BITCOIN_ZMQ_HASHBLOCK_PORT=28334
EOF

COMPOSE=(
  "${DOCKER[@]}" compose
  --env-file "${ENV_FILE}"
  --project-directory "${PROJECT_DIR}"
  --project-name hydrapool-verify
  --file "${APP_DATA_DIR}/docker-compose.yml"
  --file "${ROOT}/testing/docker-compose.verify.yml"
)
cleanup() {
  code=$?
  if [ "${code}" -ne 0 ]; then
    "${COMPOSE[@]}" logs --tail 80 || true
  fi
  "${COMPOSE[@]}" down -v --remove-orphans || true
  rm -rf "${APP_DATA_DIR}" "${PROJECT_DIR}" "${ENV_FILE}" 2>/dev/null || sudo rm -rf "${APP_DATA_DIR}" "${PROJECT_DIR}" "${ENV_FILE}" || true
}
trap cleanup EXIT

echo "== docker compose up (project dir is not the app dir) =="
"${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
"${COMPOSE[@]}" up -d

echo "== app files are visible inside the containers =="
"${COMPOSE[@]}" exec -T portal python3 -c "import pathlib; p=pathlib.Path('/opt/portal/server.py'); assert p.is_file(), p"
"${COMPOSE[@]}" exec -T hydrapool sh -c "test -f /opt/umbrel/run-hydrapool.sh && test -s /opt/umbrel/run-hydrapool.sh"
# No config yet. The supervisor must stay up instead of exiting 0.
sleep 3
cid="$("${COMPOSE[@]}" ps -q hydrapool)"
restarts="$("${DOCKER[@]}" inspect -f '{{.RestartCount}}' "${cid}")"
running="$("${DOCKER[@]}" inspect -f '{{.State.Running}}' "${cid}")"
echo "hydrapool running=${running} restarts=${restarts}"
test "${running}" = "true"
test "${restarts}" = "0"
"${COMPOSE[@]}" logs hydrapool | grep -q "waiting for setup"

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
echo "${page}" | grep -q "theme-hashdash"
echo "${page}" | grep -q "experimental software"
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
