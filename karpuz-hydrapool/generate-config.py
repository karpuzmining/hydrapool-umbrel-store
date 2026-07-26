#!/usr/bin/env python3

import os
import string
from pathlib import Path

template_path = Path(
    os.environ.get(
        "HYDRAPOOL_CONFIG_TEMPLATE",
        "/templates/config.template.toml",
    )
)

output_path = Path(
    os.environ.get(
        "HYDRAPOOL_CONFIG_OUTPUT",
        "/config/config.toml",
    )
)

required_variables = [
    "APP_BITCOIN_NODE_IP",
    "APP_BITCOIN_RPC_PORT",
    "APP_BITCOIN_RPC_USER",
    "APP_BITCOIN_RPC_PASS",
    "APP_BITCOIN_ZMQ_HASHBLOCK_PORT",
    "HYDRAPOOL_BOOTSTRAP_ADDRESS",
    "HYDRAPOOL_NETWORK",
    "HYDRAPOOL_API_AUTH_TOKEN",
]

missing = [
    variable
    for variable in required_variables
    if not os.environ.get(variable)
]

if missing:
    raise SystemExit(
        "Missing required environment variables: "
        + ", ".join(missing)
    )

supported_networks = {"main", "testnet4", "signet"}

if os.environ["HYDRAPOOL_NETWORK"] not in supported_networks:
    raise SystemExit(
        "Unsupported HydraPool network: "
        + os.environ["HYDRAPOOL_NETWORK"]
    )

template = string.Template(template_path.read_text())
rendered = template.substitute(os.environ)

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(rendered)
output_path.chmod(0o600)

print(f"Generated HydraPool configuration at {output_path}")
