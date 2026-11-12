# Cache and budget

## Layout

```
~/.cache/figma-snapshot/          # FIGMA_CACHE_HOME overrides
├── config.json                   # {"monthly_budget": 20}
├── usage.json                    # {"month": "2026-11", "spent": 3, "entries": [...]}
└── files/<file-key>/
    ├── manifest.json
    ├── index.json
    ├── nodes/<node-id>.json
    └── images/<node-id>@<scale>x.<ext>
```

`<node-id>` has `:` and `;` replaced with `_` on disk; the manifest keeps the original ID.

Token lives outside the cache at `~/.config/figma-snapshot/token` (or `%APPDATA%\figma-snapshot\token`), so deleting the cache never deletes the credential. The image cache is disposable; the token is not.

## Manifest

```json
{
  "file_key": "gdlqrdtv6MifZVY3rleCeh",
  "name": "Design System Virasty",
  "role": "viewer",
  "editor_type": "figma",
  "version": "2420595941707487487",
  "last_modified": "2026-11-11T13:30:09Z",
  "updated_at": "2026-11-12T13:20:00Z",
  "index": {"version": "2420595941707487487", "fetched_at": "2026-11-12T13:19:47Z"},
  "nodes": {
    "8:658": {"version": "2420595941707487487", "fetched_at": "2026-11-12T13:20:00Z"}
  },
  "images": {
    "8:658:png:0.25": {"version": "2420595941707487487", "fetched_at": "2026-11-12T13:21:00Z"}
  }
}
```

Each entry's `version` is the file version it was fetched from. A new fetch does not promote old entries; a stale frame stays stale until it is re-read.

## Freshness algorithm

1. If the target file is not cached, or `--force`, fetch it (one Tier-1 request).
2. If cached, call `GET /v1/files/:key/meta` (Tier 3) and compare `version`.
3. Equal → return the cached file, spend 0.
4. Different → fetch, replace the entry, spend 1.
5. `--offline` skips meta and step 2; the cached file is served regardless of age.
6. A `403` on meta means the token lacks `file_metadata:read`; the error says so. Use `--offline` or add the scope.

Meta is free against Tier 1 but still rate-limited at 10/min on a View seat. A tight loop should hit the cache instead of re-running `node` per turn.

## Ledger

`usage.json` is per machine, not per project:

```json
{
  "month": "2026-11",
  "spent": 3,
  "entries": [
    {"at": "2026-11-12T13:19:00Z", "kind": "node", "file_key": "gdlq…", "node_id": "8:658", "note": null}
  ]
}
```

- `spent` is authoritative; `entries` is an audit trail.
- On the first run of a new UTC month, the ledger resets to 0.
- `budget --set N` changes the cap; `budget --record N` reconciles after using another machine.
- Default is 20. `FIGMA_MONTHLY_BUDGET` overrides both config and flag for CI.
- The ledger does not know about requests made by the Figma app, MCP, or another machine. Reconcile deliberately.

## Budget rules

- A cache hit is allowed at 0 remaining.
- A miss at 0 raises exit code 2 before any network call.
- `--dry-run` prices a miss without spending and without requiring a token.
- Raising the cap is an owner decision; the skill never raises it silently.

## Prune

`prune --days 30` deletes whole file directories whose newest file is older than the cutoff. It never touches `config.json` or `usage.json`, so the ledger survives. Images are the biggest files; `index.json` for a large file can be 2–4 MB.

## Exit codes

| Code | Meaning |
| :--- | :--- |
| 0 | Success (including cache hit) |
| 1 | Unclassified API or parse failure |
| 2 | Monthly budget exhausted |
| 3 | Auth or permission failure (401/403) |
| 4 | File or node not found (404) |
| 5 | Bad target, flag, or parameter |
| 6 | Network, timeout, 429, or 5xx |

`--json` failures print `{"ok": false, "error": ..., "code": ..., "detail": ...}`.

## Concurrency

Writes are atomic (`<name>.tmp` + `os.replace`), so a crash leaves either the old file or the new one. Two concurrent processes can both miss and both spend; the ledger records both. For parallel agents, serialize snapshot fetches or give each agent its own `--cache-home` (and accept split quotas), then reconcile.

## Portability

The cache is portable across machines; copy `files/` if you need the snapshots. The ledger is not: it is per machine by design. Don't copy `usage.json` between machines, or two machines will under-count.
