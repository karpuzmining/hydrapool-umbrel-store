#!/usr/bin/env python3
"""Render the dashboard with sample shares and save screenshots.

The numbers are synthetic so the layout can be reviewed without a miner.
They are not a live pool.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTAL = ROOT / "karpuz-hydrapool" / "portal"
OUT = Path("/opt/cursor/artifacts")
ADDRESS_A = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
ADDRESS_B = "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0"
ADDRESS_C = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
TWO_32 = 1 << 32


def seed(data: Path) -> Path:
    now = int(time.time())
    # Rough home-miner rates: 1.2 TH/s, 480 GH/s, and an idle 200 GH/s.
    rates = {
        ("a", ADDRESS_A, "bitaxe-kitchen"): 1.2e12,
        ("b", ADDRESS_B, "s19-garage"): 480e9,
        ("c", ADDRESS_C, "shed"): 200e9,
    }
    work = {key: 0 for key in rates}
    difficulty = 0
    samples = []
    for step in range(0, 6 * 60 * 60, 60):
        stamp = now - (6 * 60 * 60 - step)
        workers = []
        for key, rate in rates.items():
            _tag, address, name = key
            if name == "shed" and stamp > now - 20 * 60:
                continue
            gained = int(rate * 60 / TWO_32)
            difficulty += gained
            work[key] += gained * TWO_32
            workers.append(
                {
                    "address": address,
                    "worker": name,
                    "work": work[key],
                    "best": 1_200_000 if name != "shed" else 40_000,
                    "last_share": stamp if name != "shed" else now - 20 * 60,
                }
            )
        samples.append(
            {
                "t": stamp,
                "accepted_difficulty": difficulty,
                "accepted": step // 60,
                "rejected": 2,
                "best_share": 1_200_000,
                "workers": workers,
            }
        )
    (data / "history.jsonl").write_text("".join(json.dumps(sample) + "\n" for sample in samples))
    setup = {
        "mode": "pplns",
        "payout_address": ADDRESS_A,
        "fee_bps": 100,
        "fee_address": ADDRESS_A,
        "tailscale_host": "umbrel.example.ts.net",
        "difficulty_multiplier": 1.0,
        "pplns_ttl_days": 7,
        "start_difficulty": 1024,
        "minimum_difficulty": 1,
    }
    (data / "setup.json").write_text(json.dumps(setup, indent=2) + "\n")
    latest = samples[-1]
    lines = [
        f"accepted_difficulty_total {latest['accepted_difficulty']}",
        f"shares_accepted_total {latest['accepted']}",
        "shares_rejected_total 2",
        "best_share 1200000",
    ]
    for worker in latest["workers"]:
        lines.append(
            f'worker_shares_valid_total{{btcaddress="{worker["address"]}",workername="{worker["worker"]}"}} {worker["work"]}'
        )
        lines.append(
            f'worker_best_share{{btcaddress="{worker["address"]}",workername="{worker["worker"]}"}} {worker["best"]}'
        )
        lines.append(
            f'worker_last_share_at{{btcaddress="{worker["address"]}",workername="{worker["worker"]}"}} {worker["last_share"]}'
        )
    metrics = data / "metrics.txt"
    metrics.write_text("\n".join(lines) + "\n")
    return metrics


def shoot(url: str, name: str, width: int, height: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / name
    subprocess.run(
        [
            "timeout",
            "25",
            "google-chrome",
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--window-size={width},{height}",
            f"--screenshot={target}",
            url,
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not target.exists() or target.stat().st_size < 1000:
        raise SystemExit(f"screenshot failed: {target}")
    print(target, target.stat().st_size)


def main() -> None:
    data = Path(tempfile.mkdtemp(prefix="hydrapool-shot-"))
    metrics = seed(data)
    os.environ.update(
        {
            "DATA_DIR": str(data),
            "HYDRAPOOL_METRICS_FILE": str(metrics),
            "HYDRAPOOL_SAMPLE_SECONDS": "3600",
            "APP_BITCOIN_NETWORK": "mainnet",
            "APP_BITCOIN_NODE_IP": "10.21.21.8",
            "APP_BITCOIN_RPC_PORT": "8332",
            "APP_BITCOIN_RPC_USER": "umbrel",
            "APP_BITCOIN_RPC_PASS": "screenshot-only",
            "APP_BITCOIN_ZMQ_HASHBLOCK_PORT": "28334",
            "DEVICE_DOMAIN_NAME": "umbrel.local",
            "DEVICE_HOSTNAME": "umbrel",
        }
    )
    import sys

    sys.path.insert(0, str(PORTAL))
    import server

    httpd = server.make_server("127.0.0.1", 8091, data, start_sampler=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(1.2)
    base = "http://127.0.0.1:8091"
    shoot(f"{base}/?tab=overview", "overview-desktop.png", 1440, 1100)
    shoot(f"{base}/?tab=connect", "connect-desktop.png", 1440, 1100)
    shoot(f"{base}/?tab=setup", "setup-desktop.png", 1440, 1200)
    shoot(f"{base}/?tab=miners", "miners-desktop.png", 1440, 900)
    shoot(f"{base}/?tab=overview", "overview-mobile.png", 390, 1200)
    shoot(f"{base}/?tab=setup", "setup-mobile.png", 390, 1400)
    httpd.shutdown()


if __name__ == "__main__":
    main()
