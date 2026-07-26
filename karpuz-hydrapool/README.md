# HydraPool for Umbrel

Run a self-hosted Bitcoin mining pool directly from an Umbrel node.

This directory contains the initial Umbrel integration for HydraPool.
The goal is to make solo and community PPLNS pool deployment accessible
without requiring users to manually manage Docker containers.

## Planned capabilities

- Automatic connection to Umbrel Bitcoin Core
- Solo and community PPLNS configuration
- Direct coinbase payouts
- Persistent pool accounting and statistics
- Local Stratum endpoint
- Grafana and Prometheus monitoring
- Clear miner connection instructions
- Optional remote-access support
- Configurable block finder reward

## Current status

This package is an early development scaffold and is not ready for
mainnet production use.

The following items still require implementation and testing:

- Generate `config.toml` during installation
- Obtain Bitcoin RPC credentials from Umbrel
- Confirm the Bitcoin Core ZMQ endpoint
- Verify the Umbrel Bitcoin Docker network name
- Add Prometheus authentication configuration
- Pin all Docker images to immutable multi-architecture digests
- Verify ARM64 and AMD64 support
- Add application icon and gallery assets
- Test installation and upgrades on umbrelOS

## Development priorities

### Milestone 0.1

- Install through a custom Umbrel App Store
- Connect to the Umbrel Bitcoin node
- Expose Stratum on port 3333
- Persist HydraPool data
- Open a browser-based connection page
- Provide access to Grafana

### Later milestones

- Guided solo and community-pool setup
- Automatic remote-access options
- Block finder reward
- Worker management and notifications

## Umbrel dependency variables

Umbrel exposes Bitcoin Core connection information to applications that
declare `bitcoin` as a dependency. The integration should use these
variables instead of assuming a Docker network name:

- `APP_BITCOIN_NODE_IP`
- `APP_BITCOIN_RPC_PORT`
- `APP_BITCOIN_RPC_USER`
- `APP_BITCOIN_RPC_PASS`

HydraPool also requires a ZMQ block endpoint. The exact variable or
supported connection method for the current Umbrel Bitcoin app must be
confirmed during device testing.

## Portal image

The browser connection page currently exists in `portal/index.html`, but
the Compose scaffold temporarily references the stock Nginx image.

Before this app can be installed normally, the portal must be published
as a small multi-architecture container image and referenced by an
immutable digest. A release workflow for that image will be added after
the initial page and app structure stabilize.
