"""Read Hydrapool's Prometheus text and turn it into dashboard numbers.

Pool hashrate is difficulty gained over a window, times 2^32, divided by
the seconds in that window. That is the same relationship Bitcoin uses
between difficulty and hashes.
"""

from __future__ import annotations

import re

TWO_32 = float(1 << 32)
LINE_RE = re.compile(
    r"^(?P<name>[A-Za-z_:][A-Za-z0-9_:]*)(?:\{(?P<labels>[^}]*)\})?\s+(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
)
LABEL_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)="((?:\\.|[^"\\])*)"')

IDLE_AFTER_SECONDS = 10 * 60
REMEMBER_SECONDS = 24 * 60 * 60


def _unescape(value: str) -> str:
    return value.replace(r"\"", '"').replace(r"\\", "\\")


def parse_labels(text: str) -> dict[str, str]:
    return {match.group(1): _unescape(match.group(2)) for match in LABEL_RE.finditer(text or "")}


def parse_exposition(text: str) -> dict:
    """Pull the counters the dashboard needs out of /metrics."""
    accepted_difficulty = 0
    accepted = 0
    rejected = 0
    best_share = 0
    workers: list[dict] = []
    indexed: dict[tuple[str, str], dict] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE_RE.match(line)
        if not match:
            continue
        name = match.group("name")
        value = int(float(match.group("value")))
        labels = parse_labels(match.group("labels") or "")
        if name == "accepted_difficulty_total":
            accepted_difficulty = value
        elif name == "shares_accepted_total":
            accepted = value
        elif name == "shares_rejected_total":
            rejected = value
        elif name == "best_share":
            best_share = value
        elif name in {
            "worker_shares_valid_total",
            "worker_best_share",
            "worker_last_share_at",
        }:
            address = labels.get("btcaddress", "")
            worker = labels.get("workername", "") or "unnamed"
            if not address:
                continue
            slot = indexed.setdefault(
                (address, worker),
                {
                    "address": address,
                    "worker": worker,
                    "work": 0,
                    "best": 0,
                    "last_share": 0,
                },
            )
            if name == "worker_shares_valid_total":
                slot["work"] = value
            elif name == "worker_best_share":
                slot["best"] = value
            else:
                slot["last_share"] = value

    workers = list(indexed.values())
    return {
        "accepted_difficulty": accepted_difficulty,
        "accepted": accepted,
        "rejected": rejected,
        "best_share": best_share,
        "workers": workers,
    }


def _gain(end: int, start: int) -> int | None:
    if end < start:
        return None
    return end - start


def hashrate_between(newer: dict, older: dict, field: str = "accepted_difficulty") -> float | None:
    dt = int(newer["t"]) - int(older["t"])
    if dt <= 0:
        return None
    gained = _gain(int(newer[field]), int(older[field]))
    if gained is None:
        return None
    return gained * TWO_32 / dt


def _sample_at_or_before(samples: list[dict], stamp: int) -> dict | None:
    chosen = None
    for sample in samples:
        if int(sample["t"]) <= stamp:
            chosen = sample
        else:
            break
    return chosen


def window_hashrate(samples: list[dict], now: int, window: int) -> tuple[float | None, int]:
    if len(samples) < 2:
        return None, 0
    end = samples[-1]
    start = _sample_at_or_before(samples, int(end["t"]) - window)
    if start is None or start is end:
        start = samples[0]
    span = int(end["t"]) - int(start["t"])
    # A shorter span is a different measurement, not the window that was asked for.
    if span < max(30, int(window * 0.9)):
        return None, span
    rate = hashrate_between(end, start)
    return rate, span


def worker_hashrate(samples: list[dict], address: str, worker: str, window: int) -> float | None:
    if len(samples) < 2:
        return None
    end = samples[-1]
    start = _sample_at_or_before(samples, int(end["t"]) - window) or samples[0]
    span = int(end["t"]) - int(start["t"])
    if span < 30:
        return None

    def work_of(sample: dict) -> int | None:
        for item in sample.get("workers", []):
            if item["address"] == address and item["worker"] == worker:
                return int(item["work"])
        return None

    end_work = work_of(end)
    start_work = work_of(start)
    if end_work is None:
        return 0.0
    if start_work is None:
        start_work = 0
    gained = _gain(end_work, start_work)
    if gained is None:
        return None
    # `work` is already difficulty * 2^32, which is hashes.
    return gained / span


def _downsample(points: list[dict], limit: int) -> list[dict]:
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    chosen = []
    last = -1
    for index in range(limit):
        pick = round(index * step)
        if pick == last:
            continue
        chosen.append(points[pick])
        last = pick
    return chosen


def rolling_history(samples: list[dict], window: int = 300, limit: int = 480) -> list[dict]:
    """Trailing-window hashrate at each stored sample, thinned for the chart."""
    points = []
    for index, sample in enumerate(samples):
        start = _sample_at_or_before(samples[: index + 1], int(sample["t"]) - window)
        if start is None or start is sample:
            continue
        rate = hashrate_between(sample, start)
        if rate is None:
            continue
        points.append({"t": int(sample["t"]), "hashrate": rate})
    return _downsample(points, limit)


def build_snapshot(samples: list[dict], known: dict, now: int, pool_up: bool, pool_error: str) -> dict:
    rate_windows = (60, 300, 900, 3600, 86400)
    measured = {window: window_hashrate(samples, now, window) for window in rate_windows}
    rate_5m, span_5m = measured[300]
    _rate_1h, _span_1h = measured[3600]
    latest = samples[-1] if samples else None
    active_keys = set()
    if latest:
        active_keys = {(item["address"], item["worker"]) for item in latest.get("workers", [])}

    rows = []
    for key, record in known.items():
        address, worker = key
        last_share = int(record.get("last_share") or 0)
        seen = int(record.get("seen") or last_share or 0)
        if now - seen > REMEMBER_SECONDS and (address, worker) not in active_keys:
            continue
        active = (address, worker) in active_keys
        rate = worker_hashrate(samples, address, worker, 300) if active else 0.0
        rows.append(
            {
                "address": address,
                "worker": worker,
                "hashrate_5m": rate or 0.0,
                "best_share": int(record.get("best") or 0),
                "last_share": last_share,
                "active": active,
                "idle": not active or (last_share > 0 and now - last_share > IDLE_AFTER_SECONDS),
            }
        )

    rows.sort(key=lambda row: (-row["hashrate_5m"], row["address"], row["worker"]))
    active_rows = [row for row in rows if row["active"] and not row["idle"]]
    users: dict[str, dict] = {}
    for row in rows:
        bucket = users.setdefault(
            row["address"],
            {"address": row["address"], "hashrate_5m": 0.0, "workers": [], "active": False},
        )
        bucket["workers"].append(row)
        bucket["hashrate_5m"] += row["hashrate_5m"]
        bucket["active"] = bucket["active"] or (row["active"] and not row["idle"])

    user_rows = sorted(users.values(), key=lambda item: (-item["hashrate_5m"], item["address"]))
    history = rolling_history(samples)
    history_span = 0
    if len(samples) >= 2:
        history_span = int(samples[-1]["t"]) - int(samples[0]["t"])

    return {
        "pool_up": pool_up,
        "pool_error": pool_error,
        "hashrate_5m": rate_5m,
        "hashrate_1h": measured[3600][0],
        "hashrates": {str(window): measured[window][0] for window in rate_windows},
        "history_span": history_span,
        "warming_up": span_5m < 60,
        "active_users": len({row["address"] for row in active_rows}),
        "active_workers": len(active_rows),
        "accepted": int(latest["accepted"]) if latest else 0,
        "rejected": int(latest["rejected"]) if latest else 0,
        "best_share": int(latest["best_share"]) if latest else 0,
        "history": history,
        "users": user_rows,
        "generated_at": now,
    }
