"""Turn a setup form into the config.toml Hydrapool actually reads.

Solo and PPLNS are both standalone Hydrapool mode (`mode = "hydrapool"`).
Hydrapool pays each stratum username from the coinbase. Solo mode records
one payout address and tells every miner to use it. PPLNS mode records the
operator address used before any shares exist, plus an optional fee.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

from addresses import address_is_valid, hostname_is_valid, map_network

SOLO = "solo"
PPLNS = "pplns"
MODES = {SOLO, PPLNS}

DEFAULTS = {
    "fee_bps": 0,
    "fee_address": "",
    "tailscale_host": "",
    "difficulty_multiplier": 1.0,
    "pplns_ttl_days": 7,
    "start_difficulty": 1024,
    "minimum_difficulty": 1,
}


class SetupError(ValueError):
    """The form was incomplete or the values cannot be mined safely."""


def toml_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\b", "\\b")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\f", "\\f")
    )
    return f'"{escaped}"'


def toml_float(value: float) -> str:
    text = f"{value:.8f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    return text


def _as_int(value, default: int, low: int, high: int, label: str) -> int:
    if value is None or value == "":
        value = default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise SetupError(f"{label} must be a whole number.") from exc
    if isinstance(value, bool) or number < low or number > high:
        raise SetupError(f"{label} must be between {low} and {high}.")
    return number


def _as_float(value, default: float, low: float, high: float, label: str) -> float:
    if value is None or value == "":
        value = default
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SetupError(f"{label} must be a number.") from exc
    if number < low or number > high:
        raise SetupError(f"{label} must be between {low} and {high}.")
    return number


def normalize_setup(payload: dict, network: str) -> dict:
    """Validate a setup payload and return the values that get stored."""
    if not isinstance(payload, dict):
        raise SetupError("Setup must be a JSON object.")
    if network not in {"main", "test", "testnet4", "signet", "regtest"}:
        raise SetupError("This Bitcoin network is not supported by Hydrapool.")

    mode = str(payload.get("mode") or "").strip().lower()
    if mode not in MODES:
        raise SetupError("Choose a local solo pool or a PPLNS pool.")

    payout = str(payload.get("payout_address") or "").strip()
    if not address_is_valid(payout, network):
        raise SetupError(
            "Enter a Bitcoin address that matches the node's network. "
            "Legacy, nested segwit, native segwit, and taproot addresses are accepted."
        )

    fee_bps = _as_int(payload.get("fee_bps"), 0, 0, 10_000, "Pool fee")
    fee_address = str(payload.get("fee_address") or "").strip()
    if mode == SOLO:
        # Solo pays one address. A fee would skim that address, so drop it.
        fee_bps = 0
        fee_address = ""
    elif fee_bps == 0:
        fee_address = ""
    elif fee_bps == 10_000:
        raise SetupError("A pool fee of 10000 basis points would take the whole block. Leave something for the miners.")
    elif not address_is_valid(fee_address, network):
        raise SetupError("A pool fee needs a Bitcoin address on this network.")

    tailscale_host = str(payload.get("tailscale_host") or "").strip().lower().rstrip(".")
    if tailscale_host and not hostname_is_valid(tailscale_host):
        raise SetupError(
            "Tailscale host must be a hostname such as umbrel.tailnet-name.ts.net, without a scheme or port."
        )

    start_difficulty = _as_int(
        payload.get("start_difficulty"),
        DEFAULTS["start_difficulty"],
        1,
        1_000_000_000,
        "Starting difficulty",
    )
    minimum_difficulty = _as_int(
        payload.get("minimum_difficulty"),
        DEFAULTS["minimum_difficulty"],
        1,
        1_000_000_000,
        "Minimum difficulty",
    )
    if minimum_difficulty > start_difficulty:
        raise SetupError("Minimum difficulty cannot be higher than the starting difficulty.")

    return {
        "mode": mode,
        "payout_address": payout,
        "fee_bps": fee_bps,
        "fee_address": fee_address,
        "tailscale_host": tailscale_host,
        "difficulty_multiplier": _as_float(
            payload.get("difficulty_multiplier"),
            DEFAULTS["difficulty_multiplier"],
            0.01,
            100.0,
            "PPLNS window multiplier",
        ),
        "pplns_ttl_days": _as_int(
            payload.get("pplns_ttl_days"),
            DEFAULTS["pplns_ttl_days"],
            1,
            30,
            "Share retention",
        ),
        "start_difficulty": start_difficulty,
        "minimum_difficulty": minimum_difficulty,
    }


def password_to_hmac(salt: str, password: str) -> str:
    """Match p2poolv2's password_to_hmac: HMAC-SHA256, salt is the key."""
    return hmac.new(salt.encode(), password.encode(), hashlib.sha256).hexdigest()


def load_or_create_api_secret(data_dir: Path) -> dict:
    """Create the local API password the dashboard uses to read metrics.

    The password stays in the app data directory. It is not a pool wallet
    and it is not the Umbrel account password.
    """
    path = data_dir / "secrets.json"
    if path.exists():
        stored = json.loads(path.read_text())
        if stored.get("user") and stored.get("password") and stored.get("token"):
            _write_password_file(data_dir, stored["password"])
            return stored

    password = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    stored = {
        "user": "hydrapool",
        "password": password,
        "token": f"{salt}${password_to_hmac(salt, password)}",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(stored), 0o600)
    _write_password_file(data_dir, password)
    return stored


def _write_password_file(data_dir: Path, password: str) -> None:
    # The Hydrapool healthcheck reads this file. It is not published.
    _atomic_write(data_dir / "hydrapool" / "api.password", password, 0o600)


def _atomic_write(path: Path, text: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text)
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def bitcoin_endpoint(env: dict) -> tuple[str, str]:
    """Build RPC and ZMQ URLs from Umbrel's bitcoin app variables."""
    host = str(env.get("ip") or "").strip()
    rpc_port = str(env.get("rpc_port") or "").strip()
    zmq_port = str(env.get("zmq_port") or "").strip()
    if not hostname_is_valid(host):
        raise SetupError("Bitcoin node address from Umbrel is missing or not usable.")
    if not rpc_port.isdigit() or not 1 <= int(rpc_port) <= 65535:
        raise SetupError("Bitcoin RPC port from Umbrel is missing or not usable.")
    if not zmq_port.isdigit() or not 1 <= int(zmq_port) <= 65535:
        raise SetupError("Bitcoin ZMQ port from Umbrel is missing or not usable.")
    user = str(env.get("rpc_user") or "")
    password = str(env.get("rpc_password") or "")
    if not user or not password:
        raise SetupError("Bitcoin RPC credentials from Umbrel are missing.")
    if any(ord(char) < 32 for char in user + password):
        raise SetupError("Bitcoin RPC credentials contain unsupported control characters.")
    return f"http://{host}:{int(rpc_port)}", f"tcp://{host}:{int(zmq_port)}"


def render_config(setup: dict, env: dict, api_user: str, api_token: str) -> str:
    network = env["network"]
    rpc_url, zmq_url = bitcoin_endpoint(env)
    fee_lines = ""
    if setup["fee_bps"] > 0:
        fee_lines = (
            f"fee_address = {toml_string(setup['fee_address'])}\n"
            f"fee = {int(setup['fee_bps'])}\n"
        )
    solo_line = ""
    if setup["mode"] == SOLO:
        solo_line = f"solo_address = {toml_string(setup['payout_address'])}\n"

    # Donation is intentionally omitted. Nothing is paid to a baked-in address.
    return f"""# Generated by the Hydrapool Umbrel setup screen. Do not edit by hand;
# the next save from the dashboard replaces this file.

[store]
path = "/data/hydrapool/store.db"
background_task_frequency_hours = 24
pplns_ttl_days = {int(setup["pplns_ttl_days"])}

[stratum]
hostname = "0.0.0.0"
port = 3333
start_difficulty = {int(setup["start_difficulty"])}
minimum_difficulty = {int(setup["minimum_difficulty"])}
{solo_line}bootstrap_address = {toml_string(setup["payout_address"])}
{fee_lines}zmqpubhashblock = {toml_string(zmq_url)}
network = {toml_string(network)}
version_mask = "1fffe000"
difficulty_multiplier = {toml_float(float(setup["difficulty_multiplier"]))}
ignore_difficulty = false
pool_signature = "hydrapool"
max_connections = 100
mode = "hydrapool"
wait_for_chain_sync = false

[bitcoinrpc]
url = {toml_string(rpc_url)}
username = {toml_string(str(env["rpc_user"]))}
password = {toml_string(str(env["rpc_password"]))}

[logging]
level = "info"
stats_dir = "/data/hydrapool/stats"
console = true

[api]
hostname = "0.0.0.0"
port = 46884
auth_user = {toml_string(api_user)}
auth_token = {toml_string(api_token)}
"""


def read_bitcoin_env() -> dict:
    raw_network = os.environ.get("APP_BITCOIN_NETWORK", "")
    network = map_network(raw_network)
    return {
        "network_raw": raw_network.strip(),
        "network": network,
        "ip": os.environ.get("APP_BITCOIN_NODE_IP", "").strip(),
        "rpc_port": os.environ.get("APP_BITCOIN_RPC_PORT", "").strip(),
        "rpc_user": os.environ.get("APP_BITCOIN_RPC_USER", ""),
        "rpc_password": os.environ.get("APP_BITCOIN_RPC_PASS", ""),
        "zmq_port": os.environ.get("APP_BITCOIN_ZMQ_HASHBLOCK_PORT", "").strip(),
    }


def bitcoin_problem(env: dict) -> str:
    if not env.get("network"):
        if env.get("network_raw"):
            return f"Hydrapool cannot mine the {env['network_raw']} chain."
        return "Install and start the Bitcoin Node app. Hydrapool reads its RPC and ZMQ settings from Umbrel."
    try:
        bitcoin_endpoint(env)
    except SetupError as exc:
        return str(exc)
    return ""
