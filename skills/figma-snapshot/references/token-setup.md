# Token setup

## Create a personal access token

1. Sign in to Figma.
2. Open **Settings → Security → Personal access tokens**.
3. **Generate new token**.
4. Name it after the machine or agent (for example `agent-laptop-figma-snapshot`).
5. Set an expiration. 30–90 days is a good default; shorter for shared machines.
6. Select scopes:

| Scope | Why |
| :--- | :--- |
| `file_content:read` | Read file JSON, nodes, and renders. **Required.** |
| `file_metadata:read` | Check `version` for cache freshness. **Required for repeat hits.** |
| `current_user:read` | `status --whoami` only. Optional but useful. |

7. Generate and copy the token. Figma shows it once.

Do **not** add write scopes. This skill never writes to Figma, and a read-only token limits the damage if it leaks.

## Store it

```bash
# Environment (shell profile, CI secret, etc.)
export FIGMA_ACCESS_TOKEN="figd_..."

# File (recommended for agents)
mkdir -p ~/.config/figma-snapshot
install -m 600 /dev/null ~/.config/figma-snapshot/token
printf '%s' 'figd_...' > ~/.config/figma-snapshot/token
```

The file path is:

| OS | Path |
| :--- | :--- |
| macOS / Linux | `~/.config/figma-snapshot/token` (honors `XDG_CONFIG_HOME`) |
| Windows | `%APPDATA%\figma-snapshot\token` |

The environment variable wins over the file. The script warns if the file is group/world-readable.

Never commit a token, put it in a skill, or paste it into a prompt. If a token appears in a transcript, revoke it and create a new one.

## Verify

```bash
python3 scripts/figma_snapshot.py status           # present/missing, no network
python3 scripts/figma_snapshot.py status --whoami  # calls /v1/me, free
```

Expected:

```
Token: present (/Users/you/.config/figma-snapshot/token)
Account: your-handle <you@example.com>
```

If `--whoami` returns `403`, the token lacks `current_user:read`; recreate it with the scope. If it returns `401`, the token is expired or malformed.

## Access is per person

A token sees exactly the files that its owner can open. Sharing a token does not share access; it shares one person's access, one person's quota, and one person's audit trail. For a team:

- Each person creates their own token.
- Each machine stores its own token at 0600.
- Revoke tokens on offboarding or when a laptop is lost.
- Use a **Dev seat** for a person who needs 200 MCP calls/day or normal REST limits. It is $12/mo on Professional.
- For a shared CI pipeline on **Organization/Enterprise**, an admin can create a **plan access token** (not user-bound, scoped to plan resources, up to 1 year, MFA required). The skill accepts it via the same `FIGMA_ACCESS_TOKEN` variable. Figma does not document which rate-limit row applies to plan tokens; confirm with support before relying on a high volume.

## Seat and quota quick reference

| Seat | MCP | REST Tier 1 |
| :--- | :--- | :--- |
| View / Collab | 20 calls/month | 20 requests/month |
| Dev / Full — Professional | 200/day | 15/min |
| Dev / Full — Organization | 200/day | 20/min |
| Dev / Full — Enterprise | 600/day | 20/min |

The View-seat REST number is the one this skill is built around. It is shared across `GET /v1/files/:key`, `/nodes`, and `/images`.

## Revoke

Figma → **Settings → Security → Personal access tokens** → revoke the token. The cache keeps working `--offline`; new fetches stop immediately.

## Troubleshooting

| Error | Cause | Fix |
| :--- | :--- | :--- |
| `401 Token has expired` | Expired or revoked PAT | Create a new token; update env/file. |
| `403` on every file | Missing `file_content:read`, or the account has no access | Recreate with the scope; ask the file owner. |
| `403` only on repeat reads | Missing `file_metadata:read` | Add the scope, or use `--offline`. |
| `403` on `--whoami` | Missing `current_user:read` | Add the scope, or skip `--whoami`. |
| `429` | Rate limit | Wait `Retry-After`; cached targets still read. |
| `status` says missing but the file exists | Wrong path or empty file | Check `default token path` in the error; write the token without a trailing newline. |
