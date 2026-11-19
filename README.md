# Hydrapool for Umbrel

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
- Stratum URL: `stratum+tcp://umbrel.local:3333`
- Username: `your-address.worker-name`
- Password: `x`

If a miner cannot resolve `umbrel.local`, use the Umbrel's LAN IP and port
3333. Every miner should use your payout address. Hydrapool pays the address
embedded in the username. The miners table marks a different address so you
can see it.

### PPLNS over Tailscale

Use this when friends mine with you and each friend is paid. PPLNS means
pay per last N shares: recent shares, weighted by difficulty, decide each
coinbase output.

1. Install Umbrel's **Tailscale** app and sign this Umbrel into your tailnet.
   That app uses host networking. Hydrapool publishes port 3333 on the host,
   so people on the tailnet can reach the pool without extra port forwarding.
2. In the Tailscale app, copy this Umbrel's MagicDNS name. It looks like
   `umbrel.tailnet-name.ts.net`.
3. In Hydrapool setup, choose PPLNS and paste that name.
4. Share `stratum+tcp://umbrel.tailnet-name.ts.net:3333`.
5. Each friend sets the miner username to their own Bitcoin address, a dot,
   and a worker name. The password is `x`.

Your address is the bootstrap payout for a block found before any shares
exist, and it receives the optional pool fee. The fee is in basis points
(100 basis points is 1%) and starts at 0. Friends' coins are not held by
the pool.

Miners on your own LAN can still use `stratum+tcp://umbrel.local:3333`.

## What the dashboard shows

The overview follows the 256 Foundation Hashdash layout: 5 minute and 1 hour
hashrate, active users, active workers, a hashrate history chart, a miner
share donut, stratum URLs with copy buttons, and a users and workers table
with search, grouping, and a show-idle toggle. The look borrows the Mujina
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
- This was not installed on a physical umbrelOS device. The stack was tested
  here with Docker Compose and a fake Bitcoin RPC. See below.

## How this was tested

`scripts/verify.sh` does three things:

1. Unit tests for address validation, solo and PPLNS config, and the setup API.
2. `docker compose` of the same portal and Hydrapool images the Umbrel app
   uses, plus a fake Bitcoin node.
3. HTTP checks that an invalid address is rejected, solo and PPLNS both
   write a config, the dashboard HTML loads, and port 3333 accepts a
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
