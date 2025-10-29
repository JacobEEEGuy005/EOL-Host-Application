v0.2 (Stage-2) - Draft
======================

This release prepares Stage‑2: persistent DBC support, hardware adapters, and observability improvements.

Notable changes
- Persist uploaded DBC files to `backend/data/dbcs/` and provide list/delete/rename management endpoints.
- Add DBC decode endpoint and improved serialization for cantools decoded values.
- New PCAN adapter (`backend/adapters/pcan.py`) and SocketCAN adapter (`backend/adapters/socketcan.py`).
- Instrument PCAN/Sim/SocketCAN adapters with lightweight in-memory metrics and expose `/api/metrics`.
- Added unit and e2e tests for DBC handling and adapters.
- CI: added GitHub Actions workflow to run full pytest suite on ubuntu-latest.

Upgrade notes
- To use SocketCAN smoke tests on Linux, create a `vcan0` interface (see `docs/SocketCAN.md`).
- The DBC persistence path is `backend/data/dbcs/` by default; do not store secrets in this directory.

Next steps before final release
- Run CI on Windows runners (add windows workflow).
- Add more observability (structured logging, metrics exporter).
- Review DBC collision policy; currently auto-rename on collision.
