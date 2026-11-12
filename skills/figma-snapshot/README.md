# Figma snapshot

Read a Figma design without burning the API quota.

If your Figma seat is **View**, the REST API allows **20 Tier-1 requests per month** — and so does the official MCP server. A live agent that re-reads a frame on every turn exhausts that in one sitting. This skill snapshots a file index, a node subtree, or a rendered image **once**, caches it globally, and serves every later read from disk.

- One request per new target; zero on repeats.
- Read-only: no canvas edits, no Code Connect, no write scopes.
- Works headless, with no desktop app and no MCP.
- Keeps design JSON and images out of your repository.

## Install

```bash
npx skills add SMhdAsadi/my-skills -s figma-snapshot
```

Or copy `skills/figma-snapshot/` into your agent's skills directory. Requires Python 3.10+ (stdlib only).

## Setup

1. Open Figma → **Settings → Security → Personal access tokens → Generate new token**.
2. Add scopes: **`file_content:read`**, **`file_metadata:read`**, **`current_user:read`**.
3. Set a short expiration and generate. The token is shown once.
4. Store it (pick one):

```bash
# Option A: environment
export FIGMA_ACCESS_TOKEN="figd_..."

# Option B: file (recommended for agents)
mkdir -p ~/.config/figma-snapshot
install -m 600 /dev/null ~/.config/figma-snapshot/token
printf '%s' 'figd_...' > ~/.config/figma-snapshot/token
```

5. Verify:

```bash
python3 scripts/figma_snapshot.py status
python3 scripts/figma_snapshot.py status --whoami
```

`--whoami` is free but needs `current_user:read`. If you skip it, paste the token into the file directly; never commit it.

## Use

Point the agent at a Figma link:

> Implement the empty state in https://www.figma.com/design/…?node-id=5150-60514

The agent resolves the link, spends **one** request on the node, and answers follow-ups from the cached JSON. Ask for another screen; only the new frame costs a request.

### Commands

| Command | What it does | Cost |
| :--- | :--- | ---: |
| `resolve <url>` | Parse file key and `node-id`; no network | 0 |
| `status` | Token, cache size, spend, remaining | 0 |
| `status --whoami` | Verify the token and account | 0 |
| `index <url>` | Whole-file outline (`?depth=2`) | 1 |
| `node <url>` | One node subtree, including children, styles, text | 1 |
| `render <url> --format png --scale 2` | Render one node to PNG/JPG/SVG/PDF | 1 |
| `budget --set 20` | Set the monthly cap | 0 |
| `budget --record 12` | Reconcile spend after using another machine | 0 |
| `prune --days 30` | Delete snapshots older than 30 days | 0 |
| `--offline` | Read a cached target without a token | 0 |
| `--dry-run` | Show what a command would spend | 0 |

Global flags (`--json`, `--cache-home`, `--timeout`) go **before** the subcommand:

```bash
python3 scripts/figma_snapshot.py --json node "<url>"
```

`--json` returns the cache `path`, a `summary`, `spent`, and `remaining` — the shape an agent should parse.

### Example

```bash
$ python3 scripts/figma_snapshot.py node "https://www.figma.com/design/gdlq…/Design-System?node-id=8-658"
Snapshot (node): ~/.cache/figma-snapshot/files/gdlq…/nodes/8_658.json
Node: Colors (FRAME 8:658) · 2481×4070 at (-1022,-1884)
Children: 89 · text: 5
Remaining: 19 / 20 · resets 2026-12-01

$ python3 scripts/figma_snapshot.py node "https://www.figma.com/design/gdlq…/Design-System?node-id=8-658"
Cache hit (node): ~/.cache/figma-snapshot/files/gdlq…/nodes/8_658.json
Remaining: 19 / 20 · resets 2026-12-01
```

## How it works

```
~/.cache/figma-snapshot/
├── config.json              # {"monthly_budget": 20}
├── usage.json               # monthly ledger + entries
└── files/<file-key>/
    ├── manifest.json        # version per entry
    ├── index.json           # ?depth=2 response
    ├── nodes/<id>.json      # /nodes?ids= response
    └── images/<id>@<scale>x.png
```

- **Freshness:** before a repeat, the script calls `/v1/files/:key/meta` (Tier 3, 10/min on a View seat, free) and compares `version`. A changed file misses the cache and costs one request; unchanged files cost zero Tier-1.
- **Versioning:** each index, node, and image entry stores the file version it came from. Fetching a new frame at a new version does not make an old frame look current.
- **Budget:** the ledger is global per machine and resets on the first of the month. `--offline` still reads cached targets when the budget is 0.
- **No token needed for cached reads:** `--offline` skips meta and serves the cached file.

## Seats and limits

| Seat | MCP | REST Tier 1 |
| :--- | :--- | :--- |
| View / Collab | 20 calls/month | **20 requests/month** |
| Dev / Full (Professional) | 200/day | 15/min |
| Dev / Full (Organization) | 200/day | 20/min |
| Dev / Full (Enterprise) | 600/day | 20/min |

A **Dev seat is $12/mo** on Professional ($25 Org, $35 Enterprise) and is the supported way to raise limits. This skill is designed for the 20/month case; on a Dev seat it still saves time and context, but you can afford more refreshes.

## Team notes

- **One PAT per person.** Never share a token; the quota is per user and the audit trail matters.
- **The cache is machine-local.** Two laptops have separate caches and separate ledgers. Reconcile with `budget --record` if you alternate.
- **Keep tokens out of repos.** Use `FIGMA_ACCESS_TOKEN` or the 0600 token file. Add `.design-cache/` to `.gitignore` if you ever copy snapshots into a project.
- **Access follows the person.** A token sees only files that person can open. Granting the skill to an agent does not grant new Figma access.
- **Revoke on offboarding.** Tokens are per user; remove them in Figma → Settings → Security.

## Troubleshooting

| Symptom | Fix |
| :--- | :--- |
| `Token has expired` | Generate a new PAT; update the env or file. |
| `403` on a file | The file isn't shared with that account, or the token lacks `file_content:read`. Run `status --whoami`. |
| `403` only on a repeat | The token lacks `file_metadata:read` (needed for freshness). Add it, or use `--offline`. |
| `404` | Re-copy the link; file keys and node IDs are easy to truncate. |
| `429` | Wait `Retry-After`. The error prints `X-Figma-Rate-Limit-Type`, `X-Figma-Plan-Tier`, and the upgrade link. |
| Budget exhausted | Read `--offline`; raise `budget --set` only with the owner's approval. |
| Empty `children` from `?ids=` | Use `node`, which calls `/nodes?ids=`; the `/v1/files?ids=` shape is different. |
| `figma_snapshot.py: command not found` | Run it with `python3 scripts/…` from the skill directory; it is not installed globally. |

## Tests

```bash
python3 -m unittest discover -s tests -v
```

28 tests, no network. A live smoke test (3 requests) is documented in [`tests/README.md`](tests/README.md).

## License

MIT. See the repository [LICENSE](../../LICENSE).
