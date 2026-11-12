---
name: figma-snapshot
description: Read Figma designs without burning the View-seat quota. Use when a task references a Figma URL, a frame or node id, a design-system file, design tokens, or a screen to implement or compare. Fetches a file index, one node subtree, or a rendered image once, caches it globally, and serves repeat reads for free.
license: MIT
compatibility: Python 3.10+ and a Figma personal access token with file_content:read and file_metadata:read.
metadata:
  author: SMhd
  version: 1.0.0
  tags: [figma, design-to-code, rest-api, caching, quota]
---

# Figma snapshot

Read a Figma design from the local cache. Spend a request only when the target is new.

A View seat gets **20 Tier-1 requests per month**. A live agent loop exhausts that in one task. This skill makes the first read cost one request and every later read cost zero.

Paths below are relative to this skill's directory (the harness reports it).

## Invariants

- **Read-only.** The token needs `file_content:read` and `file_metadata:read`. No write scope, no canvas edits, no Code Connect writes.
- **Spend once per target.** New node → 1 request. Repeat → 0. The ledger is global per machine.
- **Cache outside the project.** `~/.cache/figma-snapshot` by default. Never commit design JSON or images.
- **Read the file, not the API.** After a snapshot, answer follow-ups with `jq`/Python on the cached JSON.

## 1. Resolve

Turn the link into a file key and node id without spending:

```bash
python3 scripts/figma_snapshot.py resolve "<figma-url>"
```

Completion: you have `file_key`, and either a `node_id` or an explicit decision to read at file level.

- A link with `?node-id=1-2` targets a frame or component. `node` is the right read.
- A link with no `node-id` targets a file. Use `index` only when you need to find a frame; otherwise ask for the frame link.

## 2. Price the read

```bash
python3 scripts/figma_snapshot.py status
```

Completion: you know `remaining`. If it is 0, use `--offline` on a cached target or ask for a Dev seat; do not retry.

`status --whoami` checks the token and shows the account (free, needs `current_user:read`).

## 3. Spend once

| Need | Command | Requests |
| :--- | :--- | ---: |
| Frame or component (link has `node-id`) | `node "<url>"` | 1 |
| File outline (no frame chosen yet) | `index "<url>"` | 1 |
| Visual check of one frame | `render "<url>" --format png --scale 0.5` | 1 |
| Repeat any command above | same command | 0 |
| URL parsing, budget, cache status | `resolve` / `status` / `budget` | 0 |

Add `--json` before the subcommand for machine-readable output; `path` is the cached file.

Before an uncertain spend, add `--dry-run` (free, no network). To read a cached target without a token or freshness check, add `--offline`.

Completion: the command prints a `path` and `spent` is 0 or 1. A cache hit is success; don't force a refresh to "make sure".

## 4. Read locally

The cached node JSON is the full `/nodes?ids=` response. The cached index is the full `?depth=2` response. Query it; don't re-fetch details.

```bash
NODE=$(python3 scripts/figma_snapshot.py --json node "<url>" | jq -r .path)

jq '.nodes["<id>"].document | {name, type, bbox: .absoluteBoundingBox, children: [.children[]? | {id, name, type}]}' "$NODE"
jq '[.. | objects | select(.type == "TEXT") | .characters] | unique' "$NODE"
jq '.nodes["<id>"].styles' "$NODE"
```

For a file index:

```bash
INDEX=$(python3 scripts/figma_snapshot.py --json index "<url>" | jq -r .path)
jq '.document.children[] | {name, top_level: (.children | length)}' "$INDEX"
```

Useful fields: `document.children`, `absoluteBoundingBox`, `fills`, `strokes`, `style` (text), `characters`, `componentId`, `components`, `styles`. Node IDs stay stable across versions; use them to refer to elements.

## 5. Report

State the file and node you read, and whether it was a cache hit or a new spend. Quote only the few values that answer the question; keep the full JSON on disk.

## Failures

| Signal | Action |
| :--- | :--- |
| `401` / token expired | Recreate a PAT (see `references/token-setup.md`). Don't retry. |
| `403` | The file isn't shared with you, or a scope is missing. Run `status --whoami`; ask for access. |
| `404` | Wrong file key or node id. Copy the link again; run `resolve`. |
| `429` | Wait `Retry-After`; read cached targets meanwhile. The response names the plan tier and upgrade link. |
| `400` | Malformed node id. Run `resolve` first. |
| Budget exhausted | Read `--offline`; ask for a Dev seat or raise the cap only with the owner's approval. |
| No `node_id` | Run `index`, pick a frame, then `node`. |
| Node output is huge | Target a smaller frame; don't re-fetch the file. |
| `?ids=` on `/v1/files` returns empty children | Use `/nodes?ids=`; the script already does. |

## References

- `references/rest-cookbook.md` — endpoints, tiers, scopes, response shapes.
- `references/cache-and-budget.md` — cache layout, ledger, reconciliation, exit codes.
- `references/token-setup.md` — PAT creation, scopes, seats, team rollout.

## Team setup

Install the skill globally, give each person their own read-only PAT, and keep the cache machine-local. Sharing one token defeats the per-user quota and audit; a Dev seat ($12/mo on Professional) is the supported way to raise limits.
