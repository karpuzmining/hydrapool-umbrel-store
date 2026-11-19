import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import addresses  # noqa: E402
import bitcoin_status  # noqa: E402
import configgen  # noqa: E402
import metrics  # noqa: E402
import server  # noqa: E402

MAIN_BECH32 = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
TEST_BECH32 = "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx"
TAPROOT = "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0"
GENESIS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"

BITCOIN_ENV = {
    "APP_BITCOIN_NETWORK": "mainnet",
    "APP_BITCOIN_NODE_IP": "10.21.21.8",
    "APP_BITCOIN_RPC_PORT": "8332",
    "APP_BITCOIN_RPC_USER": "umbrel",
    "APP_BITCOIN_RPC_PASS": 'test-rpc-password-"quoted"',
    "APP_BITCOIN_ZMQ_HASHBLOCK_PORT": "28334",
    "DEVICE_DOMAIN_NAME": "umbrel.local",
    "DEVICE_HOSTNAME": "umbrel",
}


class AddressTests(unittest.TestCase):
    def test_mainnet_vectors(self):
        self.assertTrue(addresses.address_is_valid(MAIN_BECH32, "main"))
        self.assertTrue(addresses.address_is_valid(TAPROOT, "main"))
        self.assertTrue(addresses.address_is_valid(GENESIS, "main"))

    def test_rejects_wrong_network_and_checksum(self):
        self.assertFalse(addresses.address_is_valid(TEST_BECH32, "main"))
        self.assertTrue(addresses.address_is_valid(TEST_BECH32, "testnet4"))
        self.assertTrue(addresses.address_is_valid(TEST_BECH32, "signet"))
        broken = MAIN_BECH32[:-1] + ("p" if MAIN_BECH32[-1] != "p" else "q")
        self.assertFalse(addresses.address_is_valid(broken, "main"))
        self.assertFalse(addresses.address_is_valid("not-an-address", "main"))

    def test_network_aliases(self):
        self.assertEqual(addresses.map_network("mainnet"), "main")
        self.assertEqual(addresses.map_network("testnet4"), "testnet4")
        self.assertIsNone(addresses.map_network("liquid"))

    def test_tailscale_host(self):
        self.assertTrue(addresses.hostname_is_valid("umbrel.tailnet-name.ts.net"))
        self.assertFalse(addresses.hostname_is_valid("http://umbrel.local"))
        self.assertFalse(addresses.hostname_is_valid("umbrel.local:3333"))
        self.assertFalse(addresses.hostname_is_valid(""))


class BitcoinStatusTests(unittest.TestCase):
    def test_template_error_minus_ten_is_syncing(self):
        status = bitcoin_status.interpret(
            {
                "initialblockdownload": True,
                "verificationprogress": 0.42,
                "blocks": 100,
                "headers": 200,
            },
            {"code": -10, "message": "Bitcoin is downloading blocks..."},
        )
        self.assertTrue(status["syncing"])
        self.assertEqual(status["message"], "Bitcoin node syncing")
        self.assertEqual(status["template_error_code"], -10)
        self.assertAlmostEqual(status["verification_progress"], 0.42)

    def test_ready_node_is_not_syncing(self):
        status = bitcoin_status.interpret(
            {"initialblockdownload": False, "verificationprogress": 1, "blocks": 10, "headers": 10},
            None,
        )
        self.assertFalse(status["syncing"])
        self.assertEqual(status["message"], "")


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "network": "main",
            "ip": "10.21.21.8",
            "rpc_port": "8332",
            "rpc_user": "umbrel",
            "rpc_password": 'test-rpc-password-"quoted"',
            "zmq_port": "28334",
        }

    def test_solo_config_pays_one_address_and_has_no_fee_or_donation(self):
        setup = configgen.normalize_setup(
            {"mode": "solo", "payout_address": MAIN_BECH32, "fee_bps": 250},
            "main",
        )
        text = configgen.render_config(setup, self.env, "hydrapool", "salt$token")
        self.assertIn('solo_address = "%s"' % MAIN_BECH32, text)
        self.assertIn('bootstrap_address = "%s"' % MAIN_BECH32, text)
        self.assertIn('mode = "hydrapool"', text)
        self.assertIn("ignore_difficulty = false", text)
        self.assertNotIn("fee_address", text)
        self.assertNotIn("donation", text)
        self.assertIn('password = "test-rpc-password-\\"quoted\\""', text)
        self.assertIn("tcp://10.21.21.8:28334", text)
        self.assertEqual(setup["fee_bps"], 0)

    def test_pplns_config_keeps_fee_and_tailnet_host(self):
        setup = configgen.normalize_setup(
            {
                "mode": "pplns",
                "payout_address": MAIN_BECH32,
                "fee_bps": 100,
                "fee_address": GENESIS,
                "tailscale_host": "Umbrel.Tailnet.ts.net.",
                "difficulty_multiplier": 1.5,
                "pplns_ttl_days": 3,
            },
            "main",
        )
        self.assertEqual(setup["tailscale_host"], "umbrel.tailnet.ts.net")
        self.assertEqual(setup["fee_bps"], 100)
        text = configgen.render_config(setup, self.env, "hydrapool", "salt$token")
        self.assertNotIn("solo_address", text)
        self.assertIn('fee_address = "%s"' % GENESIS, text)
        self.assertIn("fee = 100", text)
        self.assertIn("difficulty_multiplier = 1.5", text)
        self.assertIn("pplns_ttl_days = 3", text)

    def test_rejects_bad_address_full_fee_and_bad_host(self):
        with self.assertRaises(configgen.SetupError):
            configgen.normalize_setup({"mode": "pplns", "payout_address": TEST_BECH32}, "main")
        with self.assertRaises(configgen.SetupError):
            configgen.normalize_setup(
                {
                    "mode": "pplns",
                    "payout_address": MAIN_BECH32,
                    "fee_bps": 10000,
                    "fee_address": GENESIS,
                },
                "main",
            )
        with self.assertRaises(configgen.SetupError):
            configgen.normalize_setup(
                {
                    "mode": "pplns",
                    "payout_address": MAIN_BECH32,
                    "tailscale_host": "stratum+tcp://umbrel.local",
                },
                "main",
            )

    def test_hmac_matches_pool_format(self):
        salt = "0123456789abcdef0123456789abcdef"
        digest = configgen.password_to_hmac(salt, "testpassword123")
        self.assertEqual(digest, "e6eb13e97ec482011d014112984f4b4e2ff82c25117f07bf4b616257df1923b7")
        self.assertEqual(len(digest), 64)


class MetricsTests(unittest.TestCase):
    def test_hashrate_window(self):
        # One difficulty every 300 seconds is 2^32 / 300 hashes per second.
        samples = [
            {"t": 1_000, "accepted_difficulty": 0, "workers": []},
            {"t": 1_300, "accepted_difficulty": 1, "workers": []},
        ]
        rate, span = metrics.window_hashrate(samples, 1_300, 300)
        self.assertEqual(span, 300)
        self.assertAlmostEqual(rate, (1 << 32) / 300)

    def test_parse_workers_and_snapshot(self):
        text = """
# HELP accepted_difficulty_total Total difficulty of accepted shares
accepted_difficulty_total 10
shares_accepted_total 4
shares_rejected_total 1
best_share 80
worker_shares_valid_total{btcaddress="bc1quser",workername="rig"} 42949672960
worker_best_share{btcaddress="bc1quser",workername="rig"} 80
worker_last_share_at{btcaddress="bc1quser",workername="rig"} 2000
"""
        parsed = metrics.parse_exposition(text)
        self.assertEqual(parsed["accepted_difficulty"], 10)
        self.assertEqual(parsed["workers"][0]["worker"], "rig")
        self.assertEqual(parsed["workers"][0]["work"], 42949672960)
        samples = [
            {
                "t": 1700,
                "accepted_difficulty": 0,
                "accepted": 0,
                "rejected": 0,
                "best_share": 0,
                "workers": [{"address": "bc1quser", "worker": "rig", "work": 0, "best": 0, "last_share": 0}],
            },
            {
                "t": 2000,
                "accepted_difficulty": 10,
                "accepted": 4,
                "rejected": 1,
                "best_share": 80,
                "workers": [
                    {
                        "address": "bc1quser",
                        "worker": "rig",
                        "work": 10 * (1 << 32),
                        "best": 80,
                        "last_share": 2000,
                    }
                ],
            },
        ]
        known = {
            ("bc1quser", "rig"): {
                "address": "bc1quser",
                "worker": "rig",
                "best": 80,
                "last_share": 2000,
                "seen": 2000,
            }
        }
        snap = metrics.build_snapshot(samples, known, 2000, True, "")
        self.assertEqual(snap["active_workers"], 1)
        self.assertEqual(snap["active_users"], 1)
        self.assertAlmostEqual(snap["hashrate_5m"], 10 * (1 << 32) / 300)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self._previous = {key: os.environ.get(key) for key in BITCOIN_ENV}
        os.environ.update(BITCOIN_ENV)
        self.data = Path(tempfile.mkdtemp(prefix="hydrapool-test-"))
        self.httpd = server.make_server("127.0.0.1", 0, self.data, start_sampler=False)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.thread.join(timeout=5)
        self.httpd.server_close()
        shutil.rmtree(self.data, ignore_errors=True)
        for key, value in self._previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read()
                return response.status, body
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_ui_and_both_modes(self):
        status, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"HYDRAPOOL", body)
        self.assertIn(b"hydrapool-theme", body)
        self.assertIn(b"theme-hashdash", body)
        self.assertIn(b"app.css?v=1.0.6", body)
        self.assertIn(b"app.js?v=1.0.6", body)
        self.assertIn(b"mascot.svg?v=1.0.6", body)
        status, body = self.request("/healthz")
        self.assertEqual(status, 200)

        status, body = self.request("/api/setup", {"mode": "solo", "payout_address": "bc1qnot-valid"})
        self.assertEqual(status, 400)
        self.assertIn(b"Bitcoin address", body)

        status, body = self.request(
            "/api/setup",
            {"mode": "solo", "payout_address": MAIN_BECH32},
        )
        self.assertEqual(status, 200, body)
        saved = json.loads(body)["setup"]
        self.assertEqual(saved["mode"], "solo")
        self.assertEqual(saved["worker_password"], "x")
        self.assertNotIn(b"test-rpc-password", body)
        solo_config = (self.data / "config" / "config.toml").read_text()
        self.assertIn("solo_address", solo_config)
        self.assertNotIn("donation", solo_config)

        status, body = self.request(
            "/api/setup",
            {
                "mode": "pplns",
                "payout_address": MAIN_BECH32,
                "fee_bps": 50,
                "fee_address": GENESIS,
                "tailscale_host": "umbrel.example.ts.net",
            },
        )
        self.assertEqual(status, 200, body)
        public = json.loads(body)["setup"]
        self.assertEqual(public["tailscale_url"], "stratum+tcp://umbrel.example.ts.net:34533")
        self.assertNotIn("token", public)
        pplns_config = (self.data / "config" / "config.toml").read_text()
        self.assertIn("fee = 50", pplns_config)
        self.assertNotIn("solo_address", pplns_config)
        secret = json.loads((self.data / "secrets.json").read_text())
        self.assertIn("$", secret["token"])
        self.assertNotIn(secret["password"], body.decode())

        status, body = self.request("/api/meta")
        meta = json.loads(body)
        self.assertEqual(meta["lan_url"], "stratum+tcp://umbrel.local:34533")
        self.assertTrue(meta["configured"])
        self.assertEqual(meta["network"], "main")
        self.assertNotIn("test-rpc-password", body.decode())


if __name__ == "__main__":
    unittest.main()
