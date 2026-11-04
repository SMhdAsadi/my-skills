# GitLab recipes (v1)

Every network call goes through `glab api`. No direct HTTP, no `gh`. The scripts build these commands; this page exists so a human can debug or run them by hand.

---

## Resolve the target

```bash
git remote get-url origin                       # host + group/project
git rev-parse --abbrev-ref HEAD                 # source branch
git rev-parse HEAD                              # head SHA for verification
```

Platform check, hardest first:

```bash
glab auth status --hostname gitlab.example.com
glab api --hostname gitlab.example.com version
```

If neither confirms GitLab, stop. A host that merely *looks* self-hosted is not evidence.

Discover the MR from the current branch:

```bash
glab api --hostname gitlab.example.com \
  "projects/team%2Fapi/merge_requests?source_branch=feat%2Fslider&state=opened&per_page=1"
```

The project path is URL-encoded (`team/api` → `team%2Fapi`). Keep the IID, not the global id: every endpoint below uses `/merge_requests/<iid>`.

Read the MR metadata once at init:

```bash
glab api --hostname gitlab.example.com "projects/team%2Fapi/merge_requests/2340"
```

Store `diff_refs.base_sha`, `diff_refs.start_sha`, `diff_refs.head_sha`, `web_url`, `target_branch`. Those SHAs are what GitLab uses to place a diff note; a local `HEAD` that differs from `head_sha` means the branch moved and the position may be rejected.

---

## Payloads

`glab api --input -` sends `application/json`. This matters: bracketed form fields (`position[new_line]=118`) are not parsed for POST bodies, so always pass nested JSON.

### Inline discussion note

```json
{
  "body": "**Throttle UI-to-JS dispatch in `panGesture.onChange`**\n\nCalling `scheduleOnRN` on every pan tick…",
  "position": {
    "base_sha": "1111111",
    "start_sha": "2222222",
    "head_sha": "abc1234",
    "position_type": "text",
    "old_path": "src/components/VSlider/VSlider.tsx",
    "new_path": "src/components/VSlider/VSlider.tsx",
    "new_line": 118
  }
}
```

```bash
glab api --hostname gitlab.example.com --method POST \
  "projects/team%2Fapi/merge_requests/2340/discussions" \
  --input - < payload.json
```

The discussions endpoint takes the note text under `body`. Do not send `note`; that key belongs to a different payload shape and is rejected here.

Rules:

- `old_path` and `new_path` are both required. Use the same value unless the diff says the file was renamed.
- An added or context line uses `new_line` only. A deleted line uses `old_line` only; v1 does not anchor deletions and demotes them to a `file` note.
- `line_range` / `line_code` are deliberately not used. See the last section.

### File note

```json
{
  "body": "**Drop the unused export**\n\nNo caller imports this symbol.",
  "position": {
    "base_sha": "1111111",
    "start_sha": "2222222",
    "head_sha": "abc1234",
    "position_type": "file",
    "new_path": "src/legacy/helpers.ts"
  }
}
```

The file must appear in the MR diff. A binary file is a valid `file` anchor and never an `inline` one. A file note also goes to `/discussions`; only the position differs.

### MR-level note

MR-level comments have no position, so they use the notes endpoint:

```bash
glab api --hostname gitlab.example.com --method POST \
  "projects/team%2Fapi/merge_requests/2340/notes" \
  --input - < note.json
```

```json
{ "body": "### Should the new flag stay public?\n\nThe branch adds a public flag…" }
```

MR-level notes go through the same dedupe check as discussions.

---

## Posting

One gate: preview with no flags, then `--post` after explicit approval. There is no staging endpoint; every write is a real comment.

```bash
# Preview: prints the exact endpoint and payload per comment. No network.
python3 scripts/post_comments.py

# Post every approved comment.
python3 scripts/post_comments.py --post

# Retry a single comment after a partial failure.
python3 scripts/post_comments.py --post --one C2
```

`--post` refuses unless HEAD equals the state HEAD, every selected comment is `approved`, and every anchor verifies at that HEAD. A comment whose near-identical discussion is already live is refused and skipped, not repeated.

**A 204 is success.** GitLab answers `204 No Content` for a write that returns no body. `glab_json` returns `{}` for that case and the comment is recorded as posted; treating the empty body as a parse error would look like a failure and invite a retry that duplicates the note.

The response tells you where the note landed:

- `/discussions` → `{ "id": "<discussion-id>", "notes": [{ "id": <note-id>, … }] }`
- `/notes` → `{ "id": <note-id>, … }`

Store `posted.noteId` (and `posted.discussionId` when present) and print `#note_<note-id>` against the MR's `web_url`.

---

## Dedupe

Fetch existing discussion notes, paginated:

```bash
glab api --hostname gitlab.example.com \
  "projects/team%2Fapi/merge_requests/2340/discussions?per_page=100&page=1"
```

Flatten every `discussions[].notes[]`, skipping notes where `system` is true: system notes are join/rename events, not review comments.

A note is comparable when `position.new_path` / `position.new_line` match the comment's anchor.

Normalise before comparing:

1. Lowercase.
2. Strip Markdown punctuation: `#`, `*`, backticks, `>`, brackets, `_`, `~`.
3. Replace remaining punctuation with spaces.
4. Collapse whitespace.

Compare the normalised comment body and the normalised note body with `difflib.SequenceMatcher`. A ratio of **0.9 or higher** is the same finding. Record a `skipped-duplicate` event and store the existing note id; do not post again.

Idempotence has a second layer: `--post` skips any comment that already carries a `posted.noteId`, including the one it stored when it matched a live duplicate. Re-running the command creates zero duplicates.

---

## Native suggestion syntax

A suggestion is a fenced block with the `suggestion` language tag. Put it in the note body exactly like this:

````markdown
```suggestion:-0+0
if (max > min) {
  apply(value);
}
```
````

- `-0` is the number of lines above the anchor to replace.
- `+0` is the number of lines below the anchor to replace.
- The replacement is at most 5 lines in v1. Larger rewrites belong in prose, not a suggestion block.
- Never wrap the block in another fence when building the API payload. The copy-box fence in `mr-comments.md` is for the chat UI; the note body contains the inner block only.

---

## Error table

| Status / symptom | Meaning | Action |
|---|---|---|
| `400 Bad Request` on create | The position is not in the diff, or a SHA is stale. | Run `comments.py verify`, re-anchor or demote to `file`/`mr`. Never retry unchanged. |
| `401` / `403` | Missing or under-scoped token. | Report the exact command. The token needs `api` scope for the target host. Do not retry. |
| `404` | Wrong project path, IID, or host. | Re-run `init --from-mr`; check the URL-encoded project path. |
| `409` / `422` | Duplicate note, locked MR, or invalid body. | Report the comment id and the response body. Do not loop. |
| `204 No Content` on a write | The write succeeded with no body. | Treat as success, store what you have, never retry. |
| `glab: command not found` | CLI unavailable. | Stop at `mr-comments.md`; copy-paste still works. |
| Non-JSON output | A proxy or auth page answered instead of the API. | Treat as an error; print the first 200 characters. |

No failure path posts a partial batch silently. Created note ids are saved before the next request, and the error names what was already posted; `--post --one C2` retries exactly one comment.

---

## Why not `line_range`

GitLab supports `position[line_range]` for multi-line notes, but the payload needs both start and end line codes tied to a specific diff version. Those codes break on rebase, rename, and whitespace-only changes, and a rejected position is silent enough to waste a review cycle.

v1 sends one `new_line` and keeps `endLine` as display metadata. The rendered comment still says `path:118-124`, so the human sees the range; GitLab anchors the note at 118. If a future version needs true ranges, add them behind a capability check rather than replacing the single-line default.
