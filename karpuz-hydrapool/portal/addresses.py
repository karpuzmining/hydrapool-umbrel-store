"""Bitcoin address checks for the networks Hydrapool can mine.

The pool pays the address inside a miner's stratum username, so a bad
address has to be rejected before it is written into config.toml.
"""

from __future__ import annotations

import hashlib
import re

BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

# Umbrel's APP_BITCOIN_NETWORK values, plus the names Hydrapool itself uses.
NETWORK_ALIASES = {
    "main": "main",
    "mainnet": "main",
    "bitcoin": "main",
    "test": "test",
    "testnet": "test",
    "testnet3": "test",
    "testnet4": "testnet4",
    "signet": "signet",
    "regtest": "regtest",
}

NETWORK_LABELS = {
    "main": "mainnet",
    "test": "testnet",
    "testnet4": "testnet4",
    "signet": "signet",
    "regtest": "regtest",
}

# Human-readable parts accepted by Bitcoin Core / rust-bitcoin for each chain.
HRPS = {
    "main": ("bc",),
    "test": ("tb",),
    "testnet4": ("tb",),
    "signet": ("tb",),
    "regtest": ("bcrt",),
}

# Base58 version bytes: pubkey-hash, then script-hash.
BASE58_VERSIONS = {
    "main": (0x00, 0x05),
    "test": (0x6F, 0xC4),
    "testnet4": (0x6F, 0xC4),
    "signet": (0x6F, 0xC4),
    "regtest": (0x6F, 0xC4),
}

_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$"
)


def map_network(raw: str) -> str | None:
    key = (raw or "").strip().lower()
    return NETWORK_ALIASES.get(key)


def network_label(network: str) -> str:
    return NETWORK_LABELS.get(network, network or "unknown")


def _bech32_polymod(values: list[int]) -> int:
    generator = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    checksum = 1
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ value
        for index in range(5):
            if (top >> index) & 1:
                checksum ^= generator[index]
    return checksum


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(char) >> 5 for char in hrp] + [0] + [ord(char) & 31 for char in hrp]


def _convertbits(data: list[int], from_bits: int, to_bits: int, pad: bool) -> list[int] | None:
    acc = 0
    bits = 0
    result: list[int] = []
    max_value = (1 << to_bits) - 1
    max_acc = (1 << (from_bits + to_bits - 1)) - 1
    for value in data:
        if value < 0 or value >> from_bits:
            return None
        acc = ((acc << from_bits) | value) & max_acc
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            result.append((acc >> bits) & max_value)
    if pad:
        if bits:
            result.append((acc << (to_bits - bits)) & max_value)
    elif bits >= from_bits or ((acc << (to_bits - bits)) & max_value):
        return None
    return result


def _decode_segwit(address: str) -> tuple[str, int, bytes] | None:
    if address.lower() != address and address.upper() != address:
        return None
    address = address.lower()
    separator = address.rfind("1")
    if separator < 1 or separator + 7 > len(address) or len(address) > 90:
        return None
    hrp = address[:separator]
    data: list[int] = []
    for char in address[separator + 1 :]:
        index = BECH32_CHARSET.find(char)
        if index == -1:
            return None
        data.append(index)
    if len(data) < 7:
        return None
    spec_constant = _bech32_polymod(_hrp_expand(hrp) + data)
    if spec_constant == 1:
        bech32m = False
    elif spec_constant == 0x2BC830A3:
        bech32m = True
    else:
        return None
    payload = data[:-6]
    version = payload[0]
    if version < 0 or version > 16:
        return None
    if version == 0 and bech32m:
        return None
    if version != 0 and not bech32m:
        return None
    program = _convertbits(payload[1:], 5, 8, False)
    if program is None:
        return None
    program_bytes = bytes(program)
    if not 2 <= len(program_bytes) <= 40:
        return None
    if version == 0 and len(program_bytes) not in (20, 32):
        return None
    if version == 1 and len(program_bytes) != 32:
        return None
    return hrp, version, program_bytes


def _b58decode(text: str) -> bytes | None:
    if not text or any(char not in BASE58_ALPHABET for char in text):
        return None
    number = 0
    for char in text:
        number = number * 58 + BASE58_ALPHABET.index(char)
    pad = 0
    for char in text:
        if char != "1":
            break
        pad += 1
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * pad + body


def _valid_base58(address: str, versions: tuple[int, int]) -> bool:
    raw = _b58decode(address)
    if raw is None or len(raw) != 25:
        return False
    payload, checksum = raw[:-4], raw[-4:]
    digest = hashlib.sha256(hashlib.sha256(payload).digest()).digest()
    return checksum == digest[:4] and payload[0] in versions


def address_is_valid(address: str, network: str) -> bool:
    """Return True when address can receive a coinbase payout on network."""
    if network not in HRPS or not address or len(address) > 90:
        return False
    text = address.strip()
    if any(char.isspace() for char in text):
        return False
    decoded = _decode_segwit(text)
    if decoded is not None:
        hrp, _version, _program = decoded
        return hrp in HRPS[network]
    return _valid_base58(text, BASE58_VERSIONS[network])


def hostname_is_valid(host: str) -> bool:
    """Tailnet MagicDNS names and plain hostnames. No scheme and no port."""
    if not host:
        return False
    lowered = host.strip().lower().rstrip(".")
    if lowered != host.strip().lower() or "://" in lowered or "/" in lowered:
        return False
    if lowered.startswith(".") or ".." in lowered:
        return False
    return _HOST_RE.match(lowered) is not None
