# Draft pull request for 256foundation/hydrapool

Do not open this yet. It is the branch plan and the description to paste
when someone is ready to propose the Umbrel app upstream.

Ryan's fork is https://github.com/karpuzmining/Hydrapool. It already has
`feature/umbrel-support`. Leave that branch alone. It hardcodes a payout
address and an API token, mounts files from Umbrel's data directory, and
the portal container does not serve the checked-in page. Start from a
fresh branch off current `256foundation/hydrapool` `main`.

## Branch

```text
git clone https://github.com/karpuzmining/Hydrapool.git
cd Hydrapool
git checkout main
git pull upstream main
git checkout -b umbrel-app
```

If `upstream` is not set:

```text
git remote add upstream https://github.com/256foundation/hydrapool.git
git fetch upstream
git checkout -b umbrel-app upstream/main
```

Open the pull request from `karpuzmining/Hydrapool` branch `umbrel-app`
into `256foundation/hydrapool` `main` when the time comes. The community
store at `karpuzmining/hydrapool-umbrel-store` stays the installable app
until that pull request lands and an official app-store submission exists.

## What to copy

Copy `karpuz-hydrapool/` from the community store into `umbrel/` and
rename the app id. The official app does not use the `karpuz-` prefix.

| Community store | Upstream `umbrel/` |
| --- | --- |
| id `karpuz-hydrapool` | id `hydrapool` |
| `APP_HOST: karpuz-hydrapool_portal_1` | `APP_HOST: hydrapool_portal_1` |
| submission URL pointing at the community store | submission URL pointing at the upstream pull request |

Keep the portal, the supervisor script, address checks, and the rule that
the pool does not start on the image's default config. That default config
sets a 100% donation.

Also change `.github/workflows/build-docker.yml` so the Hydrapool image is
multi-arch. The workflow builds on `ubuntu-latest` and does not set
`platforms`, so `ghcr.io/256foundation/hydrapool:latest` is amd64 only.
Umbrel Home and Raspberry Pi cannot run it. Add:

```yaml
platforms: linux/amd64,linux/arm64
```

to the `docker/build-push-action` step. Confirm the image runs on arm64
before asking Umbrel to list the app in the official store.

## Suggested pull request

Title: Add an Umbrel app for solo and PPLNS pools

Body:

```markdown
## Summary

Add an `umbrel/` app so Hydrapool can be installed from an Umbrel app
store. The dashboard asks the operator to choose a local solo pool or a
PPLNS pool shared over Tailscale, checks the payout address, and only
then writes `config.toml` and starts the pool.

The pool keeps using the existing image, RPC settings from Umbrel's
Bitcoin app, and coinbase payouts. The Umbrel package does not add a
custody wallet.

## What the app contains

- `umbrel/umbrel-app.yml` depends on the Bitcoin app and opens the dashboard.
- `umbrel/docker-compose.yml` runs the pool plus a small Python portal.
  Stratum is published on port 3333 so LAN miners and Umbrel's Tailscale
  app (host networking) can reach it. The API port stays on the app network.
- Setup writes a per-install API password into the app data directory.
  The image's default config is not used.
- Solo mode records one payout address. PPLNS mode records an operator
  address, an optional fee, and the tailnet hostname to share.
- The dashboard shows 5 minute and 1 hour hashrate, active users and
  workers, history, a share donut, and a searchable workers table.

## Image architecture

`build-docker.yml` needs `platforms: linux/amd64,linux/arm64`. Without
that, Umbrel Home and Pi cannot start the pool. I have not pushed that
workflow change in the community store because the image is published
from this repository.

## Testing

The community store ran `scripts/verify.sh`: unit tests, `docker compose`
against a fake Bitcoin RPC, dashboard HTTP, both setup modes, and a
stratum subscribe on port 3333. A physical umbrelOS device was not used.
```
