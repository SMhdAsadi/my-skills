# Fetch recipes

The scripts wrap these commands. This file exists so a failure can be debugged by hand without guessing, and so the GitLab quirks are written down where the next person will find them.

Verified against `glab` 1.123.0.

---

## GitLab

### Discussions are the contract

`glab mr note list --state unresolved` exists and does exactly what it says, but its own help text calls it experimental and "not ready for production use". The REST endpoint behind it is stable, so that is what the fetcher calls:

```bash
glab api --hostname HOST "projects/GROUP%2FPROJECT/merge_requests/2340/discussions?per_page=100&page=1"
glab api --hostname HOST "projects/GROUP%2FPROJECT/merge_requests/2340"
```

The project path must be URL-encoded (`group/project` → `group%2Fproject`). `glab api projects/:fullpath/...` does this for you when run inside the repo; the fetcher encodes explicitly so it also works with `--repo`.

For a convenience view of the same data:

```bash
glab mr view --unresolved        # implies --comments
glab mr note list --state unresolved -F json
```

### Filtering the payload

Two traps, both observed on real MRs:

```bash
# Wrong: system notes carry resolvable=false and resolved=null
jq '[.[] | select(.notes[0].resolved == false)]'

# Right: only resolvable, non-system discussions are review threads
jq '[.[] | select(.notes[0].resolvable == true and .notes[0].resolved == false and (.notes[0].system | not))]'
```

A discussion with `individual_note: true`, `resolvable: false`, `system: true` is a commit notice or a plain comment, not a thread.

Position fields worth knowing:

| Field | Meaning |
|---|---|
| `position.new_path` / `old_path` | File on each side of the diff |
| `position.new_line` / `old_line` | Null when the comment sits on the other side |
| `position.line_range.start` / `.end` | Multi-line comments; the range, not a single line |
| `position.head_sha` | Diff version the comment was written against — compare with `mr.diff_refs.head_sha` for staleness |

`type` is `DiffNote` for inline comments and `DiscussionNote` for MR-level threads. Both can be `resolvable: true`, and an MR can mix them — one real MR had six resolvable threads with `position: null`, all MR-level. A table with a mandatory "file and line" column breaks on those.

### Self-hosted instances

```bash
glab auth status                       # per-host token state
glab api --hostname code.example.com projects/:fullpath/merge_requests/1
```

`glab` fails with *"none of the git remotes configured for this repository point to a known GitLab host"* when the remote is not GitLab or is unauthenticated. Pass `--hostname` explicitly, and `-R HOST/GROUP/PROJECT` for `glab mr` commands.

### Replying and resolving

```bash
glab api --hostname HOST --method POST \
  "projects/GROUP%2FPROJECT/merge_requests/2340/discussions/DISCUSSION_ID/notes" \
  -f body="..."

glab api --hostname HOST --method PUT \
  "projects/GROUP%2FPROJECT/merge_requests/2340/discussions/DISCUSSION_ID?resolved=true"
```

`DISCUSSION_ID` is the full 40-character id. `glab mr note create --reply` accepts an 8-character prefix, but the REST endpoint does not.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Zero threads on a busy MR | Resolution filter applied to the wrong field | Use `resolvable && !resolved` on GitLab |
| Discussions missing after a short first page | Pagination stopped early | Follow the `per_page`/`page` loop until a short page |
| `401 Unauthorized` | Token missing for that host | `glab auth login --hostname HOST` |
| State file shows up in `git status` | Written outside an ignored dir | Let the resolver pick the path; never hardcode one |
| Replies post to the wrong thread | Short id used instead of the full discussion id | `remoteId` from the state file |
