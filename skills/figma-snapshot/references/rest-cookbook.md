# Figma REST cookbook

Verified against Figma's official REST docs on 2026-11-12. The API is versioned at `/v1`; all requests use the `X-Figma-Token` header.

- [File endpoints](https://developers.figma.com/docs/rest-api/file-endpoints/)
- [Rate limits](https://developers.figma.com/docs/rest-api/rate-limits)
- [Scopes](https://developers.figma.com/docs/rest-api/scopes/)
- [Authentication](https://developers.figma.com/docs/rest-api/authentication/)

## URL shapes

| Link | Meaning |
| :--- | :--- |
| `figma.com/design/<key>/<name>?node-id=1-2` | Design file; `node-id` points at a frame/component. |
| `figma.com/file/<key>/<name>` | Legacy design link; same file key. |
| `figma.com/proto/<key>/...?node-id=1-2` | Prototype; the file key still works with the REST API. |
| `figma.com/board/<key>/...` | FigJam. |
| `figma.com/slides/<key>/...` | Slides. |

`node-id` arrives as `1-2`; the API wants `1:2`. The script normalizes both. Instance descendants may look like `I1:2;3:4`; keep the separators.

## Endpoints

| Endpoint | Returns | Tier | Scope |
| :--- | :--- | :--- | :--- |
| `GET /v1/files/:key/meta` | Name, role, `last_touched_at`, `version` | 3 | `file_metadata:read` |
| `GET /v1/files/:key?depth=2` | `document`, pages, top-level nodes, `components`, `componentSets`, `styles` | 1 | `file_content:read` |
| `GET /v1/files/:key?depth=1` | Pages only | 1 | `file_content:read` |
| `GET /v1/files/:key/nodes?ids=1:2` | Subtree for each node + local `components`/`styles` | 1 | `file_content:read` |
| `GET /v1/images/:key?ids=1:2` | Temporary render URLs | 1 | `file_content:read` |
| `GET /v1/files/:key/images` | Image-fill URLs (14 days) | 2 | `file_content:read` |
| `GET /v1/me` | Current user | — | `current_user:read` |
| `GET /v1/files/:key/variables/local` | Variables | — | `file_variables:read` (Enterprise) |

`depth` only applies to `GET /v1/files/:key`, not to `/nodes`:

- `depth=1`: pages, no children.
- `depth=2`: pages + their top-level nodes.
- omitted: full tree (large).

## `?ids=` vs `/nodes`

`GET /v1/files/:key?ids=1:2` accepts a comma list and returns the requested nodes plus ancestors and dependencies. In practice the top-level `document.children` can come back with empty `children`, so drilling into a node is unreliable from that endpoint.

Use `GET /v1/files/:key/nodes?ids=1:2` for a subtree. The response is:

```json
{
  "name": "File",
  "role": "viewer",
  "version": "2420595941707487487",
  "nodes": {
    "1:2": {
      "document": { "id": "1:2", "name": "Frame", "type": "FRAME", "children": [] },
      "components": {},
      "componentSets": {},
      "styles": {}
    }
  }
}
```

A missing or inaccessible node appears as `null` under `nodes`.

## Images

`GET /v1/images/:key?ids=1:2,1:3&format=png&scale=2`

- `format`: `jpg`, `png`, `svg`, `pdf`.
- `scale`: `0.01`–`4`; ignored for SVG.
- SVG flags: `svg_outline_text`, `svg_include_id`, `svg_include_node_id`, `svg_simplify_stroke`.
- `contents_only`, `use_absolute_bounds`, `version` are also supported.
- URLs expire after 30 days; download immediately. 32 MP cap per render.
- Batch node IDs in one request; the response maps ID → URL.

## Response fields worth querying

- `document.children` — pages (index) or child layers (node).
- `absoluteBoundingBox` — `x`, `y`, `width`, `height`.
- `fills`, `strokes`, `effects`, `cornerRadius` — visual style.
- `style` — text style (`fontFamily`, `fontSize`, `fontWeight`, `lineHeight`).
- `characters` — text content.
- `componentId` — instance's main component.
- `components`, `componentSets`, `styles` — local assets in the subtree/file.
- `version` — file version; use it for freshness.

## Errors

| Status | Meaning | Exit code |
| :--- | :--- | :--- |
| `400` | Invalid parameter (often a malformed node id) | 5 |
| `401` | Invalid or expired token | 3 |
| `403` | Token valid but lacks scope, or no file access | 3 |
| `404` | File or node not found | 4 |
| `429` | Rate limited; honor `Retry-After` | 6 |
| `5xx` | Figma-side failure; retry later | 6 |

`429` responses also carry `X-Figma-Rate-Limit-Type` (`low` for View/Collab, `high` for Dev/Full), `X-Figma-Plan-Tier`, and `X-Figma-Upgrade-Link`.

## Rate limits

Tier 1 is the scarce one for a View seat: `GET /v1/files/:key`, `/nodes`, and `/images`.

| Seat | Tier 1 | Tier 2 | Tier 3 |
| :--- | :--- | :--- | :--- |
| View / Collab | **20/month** | 5/min | 10/min |
| Dev / Full — Starter | 10/min | 25/min | 50/min |
| Dev / Full — Professional | 15/min | 50/min | 100/min |
| Dev / Full — Organization | 20/min | 100/min | 150/min |

Figma resets limits monthly; this script's ledger uses the UTC calendar month. Limits are per user (PAT/OAuth), per plan, or per plan token; they do not stack across tokens.

## Why not the MCP server here?

Figma's hosted MCP server is capped at **20 tool calls/month** on a View seat too. The desktop MCP server requires a Dev/Full seat. So on a View seat, the REST cache is the only path that scales. A full OpenCode/Figma comparison is kept in the Virasty repo's `docs/research/` notes.
