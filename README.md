# Hydrapool for Umbrel

> [!CAUTION]
> **Experimental software — not ready for production use**
>
> This repository contains an early development build of the Hydrapool
> integration for umbrelOS. It is being published for development,
> testing, and review only.
>
> Do not rely on this package for production mining, pool accounting,
> payouts, or custody of funds. Installation procedures, configuration
> formats, container images, and upgrade behavior may change without notice.

Hydrapool for Umbrel is intended to make running a self-hosted Bitcoin
mining pool accessible through the Umbrel interface.

## Current development status

The current test build can:

- Install through a custom Umbrel Community App Store
- Connect automatically to Bitcoin Knots
- Generate Hydrapool RPC and ZMQ configuration
- Start the Hydrapool Stratum server
- Accept connections from Bitcoin miners
- Serve a preliminary local connection page

The following work remains before the package should be considered ready
for broader testing:

- Remove all hardcoded payout configuration
- Add first-run Bitcoin address setup through the web interface
- Add safe configuration updates and restarts
- Complete monitoring and dashboard integration
- Test upgrades, restarts, backups, and uninstall behavior
- Pin all container images to immutable multi-architecture digests
- Test Bitcoin Core and Bitcoin Knots independently
- Review security and authentication
- Complete upstream review with the Hydrapool maintainers

## Project information

Hydrapool is a 256 Foundation project.

For more information, visit:

https://hydrapool.org

## Installation

Public installation is not currently recommended. Developers and reviewers
should understand that this repository is under active development and may
contain breaking changes.
