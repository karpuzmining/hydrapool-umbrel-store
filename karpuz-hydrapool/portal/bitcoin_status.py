"""Read Bitcoin Core RPC errors that mean the node is still syncing.

getblocktemplate returns JSON-RPC code -10 while the node is downloading
blocks. getblockchaininfo.verificationprogress is the fraction complete.
"""

from __future__ import annotations

SYNCING_CODE = -10


def interpret(info: dict | None, template_error: dict | None) -> dict:
    code = None
    if isinstance(template_error, dict):
        raw_code = template_error.get("code")
        if isinstance(raw_code, int):
            code = raw_code
    progress = None
    blocks = None
    headers = None
    downloading = False
    if isinstance(info, dict):
        downloading = bool(info.get("initialblockdownload"))
        raw_progress = info.get("verificationprogress")
        if isinstance(raw_progress, (int, float)) and not isinstance(raw_progress, bool):
            progress = float(raw_progress)
        if isinstance(info.get("blocks"), int):
            blocks = info["blocks"]
        if isinstance(info.get("headers"), int):
            headers = info["headers"]
    syncing = code == SYNCING_CODE or downloading
    return {
        "reachable": info is not None or template_error is not None,
        "syncing": syncing,
        "template_error_code": code,
        "verification_progress": progress,
        "blocks": blocks,
        "headers": headers,
        "message": "Bitcoin node syncing" if syncing else "",
    }
