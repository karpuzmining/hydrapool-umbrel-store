# Hydrapool for Umbrel

**Experimental.** Hydrapool on Umbrel is experimental software. Test with a
small hashrate first. It comes with no warranty.

Hydrapool is an open-source Bitcoin mining pool from the 256 Foundation.
This repository is a community Umbrel app store that installs it on umbrelOS.

The pool does not hold a wallet. A block pays Bitcoin addresses from the
coinbase. You choose those addresses during setup. Nothing in this store
is a private key, a pool wallet, or a default password.

## Install

1. On umbrelOS, open the App Store and add this community app store:

   `https://github.com/karpuzmining/hydrapool-umbrel-store`

2. Install **Bitcoin Node** and let it run. Hydrapool reads that app's RPC
   user, password, port, and ZMQ block port. Bitcoin Core and Bitcoin Knots
   both work when they are the node behind Umbrel's Bitcoin app.

3. Install **Hydrapool**. The dashboard opens even before the pool process
   is configured. The pool stays stopped until you save a payout address.
   Updates pull the pinned dashboard image, because Umbrel replaces
   `docker-compose.yml`. The pre-start hook still copies the pool starter
   from the store checkout. Reload the page after an update.

4. Open Hydrapool and pick a mode.

The app id inside this store is `karpuz-hydrapool`. Umbrel requires that
prefix because the store id is `karpuz`.

## Choose a mode

You can switch modes later from the Setup tab. Saving restarts the pool.
Miners reconnect on their own. Old share data is kept.

### Local solo

Use this when the miners are yours and they sit on the same LAN as the Umbrel.

- Payout address: your own Bitcoin address, on the same network as the node
  (mainnet, testnet4, or signet).
- Stratum URL: `stratum+tcp://umbrel.local:34533`
- Username: `your-address.worker-name`
- Password: `x`

If a miner cannot resolve `umbrel.local`, use the Umbrel's LAN IP and port
34533. Host port 3333 is left free because Public Pool already publishes
stratum there on many Umbrels. Every miner should use your payout address. Hydrapool pays the address
embedded in the username. The miners table marks a different address so you
can see it.

### PPLNS over Tailscale

Use this when friends mine with you and each friend is paid. PPLNS means
pay per last N shares: recent shares, weighted by difficulty, decide each
coinbase output.

1. Install Umbrel's **Tailscale** app and sign this Umbrel into your tailnet.
   That app uses host networking. Hydrapool publishes port 34533 on the host,
   so people on the tailnet can reach the pool without extra port forwarding.
2. In the Tailscale app, copy this Umbrel's MagicDNS name. It looks like
   `umbrel.tailnet-name.ts.net`.
3. In Hydrapool setup, choose PPLNS and paste that name.
4. Share `stratum+tcp://umbrel.tailnet-name.ts.net:34533`.
5. Each friend sets the miner username to their own Bitcoin address, a dot,
   and a worker name. The password is `x`.

Your address is the bootstrap payout for a block found before any shares
exist, and it receives the optional pool fee. The fee is in basis points
(100 basis points is 1%) and starts at 0. Friends' coins are not held by
the pool.

Miners on your own LAN can still use `stratum+tcp://umbrel.local:34533`.

## What the dashboard shows

The header theme switch keeps the neon dashboard or selects Hashdash, a
glass layout on the same pages. The choice is remembered in the browser.
A link can set it with `?theme=neon` or `?theme=hashdash`. The overview
follows the 256 Foundation Hashdash layout: 5 minute and 1 hour
hashrate, active users, active workers, a hashrate history chart, a miner
share donut, and a users and workers table with search, grouping, and a
show-idle toggle. Stratum URL, username, and password, with copy buttons
for solo and for PPLNS, are on the Connect tab. The look borrows the Mujina
fleet monitor: a dark grid, neon status tiles, and clipped panels. The orange
Hydra mascot is the app icon.

## Limits

- The published pool image `ghcr.io/256foundation/hydrapool:latest` is
  **amd64 only**. Umbrel on a 64-bit PC or VM can run it. Umbrel Home and
  Raspberry Pi cannot start the pool process until the Hydrapool project
  publishes an arm64 image. The dashboard container is multi-arch and still
  installs. See `docs/upstream-pr.md` for the image change to send upstream.
- A large PPLNS pool can make the coinbase too big for Bitcoin Core's default
  `blockmaxweight`. A handful of friends is fine. Umbrel's Bitcoin app does
  not expose that setting.
- Updates on umbrelOS 2.0 replace `docker-compose.yml`, `exports.sh`, and
  `hooks`, and leave `portal/` and `scripts/` from the first install. The
  dashboard runs from
  `ghcr.io/karpuzmining/hydrapool-umbrel-portal`, pinned by digest in
  `docker-compose.yml`, which Umbrel does pull. `hooks/pre-start` still
  copies `scripts/` (and the on-disk portal tree) from the store checkout
  so the pool starter is not stuck on the first install.
- While Bitcoin Knots or Bitcoin Core is downloading blocks,
  `getblocktemplate` returns code -10. The dashboard then says the node is
  syncing and shows verification progress.
- The compose stack in this repository was tested with Docker Compose and a
  fake Bitcoin RPC. See below.

## Found a bug?

Report it at <https://github.com/karpuzmining/hydrapool-umbrel-store/issues>.

Include:

- umbrelOS version
- hardware and architecture (for example a mini PC, `x86_64`)
- app version (the version on the Hydrapool app page)
- Bitcoin node app and sync state (Bitcoin Node or Bitcoin Knots, and whether it is still downloading blocks)
- miner model and firmware
- relevant `docker logs` output, with secrets removed

Do not paste RPC passwords, API tokens, or wallet material. A bug report
form on that page asks for the same fields.

## How this was tested

`scripts/verify.sh` does four things:

1. Unit tests for address validation, solo and PPLNS config, the setup API,
   and a `getblocktemplate` error of -10.
2. A pre-start check that a stale `portal/` and `scripts/` are replaced from
   the store checkout, and that `data/` is left alone.
3. `docker compose` of the Umbrel compose file with `APP_DATA_DIR` set to a
   copy of the app, and the project directory pointed somewhere else, plus
   a fake Bitcoin node.
4. HTTP checks that an invalid address is rejected, solo and PPLNS both
   write a config, the dashboard HTML loads, and host port 34533 accepts a
   stratum `mining.subscribe`.

```bash
bash scripts/verify.sh
```

GitHub Actions runs the same script on every push and pull request.

The fake node is only for that test. An Umbrel install talks to the Bitcoin
Node app instead.

Screenshots of the dashboard are in the pull request description. They were
taken from the portal with sample hashrate so the layout is visible; the
verification script uses an empty pool plus the live stratum port.
