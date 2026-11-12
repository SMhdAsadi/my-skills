# Changelog

All notable changes to `figma-snapshot` are documented here.

## [1.0.0] - 2026-11-12

### Added

- Read-only Figma snapshots through the REST API: whole-file index (`?depth=2`), one node subtree (`/nodes?ids=`), and rendered images (`/images`).
- Global cache under `~/.cache/figma-snapshot`, keyed by file key and node ID, with per-entry versioning so a file change invalidates only the affected target.
- Global monthly ledger, default 20 Tier-1 requests, with `status`, `budget --set`, `budget --record`, and `--offline`.
- `--dry-run` for quota-free planning, `--force` for deliberate refreshes, and `prune` for old snapshots.
- URL and node-id parsing for `design`, `file`, `proto`, `board`, `slides`, `make`, and `buzz` links.
- Actionable errors for 400/401/403/404/429, including `Retry-After` and Figma rate-limit headers.
- 28 stdlib tests, plus a live smoke test covering node, index, render, and cache hits.
