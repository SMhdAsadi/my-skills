# Fetch recipes

The scripts wrap these commands. This file exists so a failure can be debugged by hand without guessing, and so the GitLab quirks are written down where the next person will find them.

Verified against `glab` 1.123.0. The state file is schema **v2** and lives at `gitlab-<repo-slug>-<number>.json`; every command below takes `--state PATH` when the resolver would pick the wrong file.

---

## Discussions are the contract

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

### Pagination

Follow `per_page`/`page` until a short page. The fetcher asks for 100 per page and stops after 20 pages with a warning if the MR is still returning full pages; that cap is a safety valve, not a silent truncation.

```bash
for page in 1 2 3; do
  glab api --hostname HOST \
    "projects/GROUP%2FPROJECT/merge_requests/2340/discussions?per_page=100&page=$page"
done
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

The root note is the first non-system, resolvable note, even when a system note precedes it. A discussion with no such note is dropped entirely.

Position fields worth knowing:

| Field | Meaning |
|---|---|
| `position.new_path` / `old_path` | File on each side of the diff; `new_path` wins, deleted files keep `old_path` |
| `position.new_line` / `old_line` | Null when the comment sits on the other side |
| `position.line_range.start` / `.end` | Multi-line comments; the range, not a single line |
| `position.head_sha` | Diff version the comment was written against — compare with `mr.diff_refs.head_sha` for staleness |

### Anchor side and old path

`side` is `new` when `new_line` exists, otherwise `old` when `old_line` exists. When both are null, read `line_range`: any non-null `new_line` in `start`/`end` makes it `new`; only otherwise do the non-null `old_line` values make it `old`. A mixed range is therefore read against the new file. `line`/`endLine` are the min/max of that side's values.

`oldPath` is `old_path` only when it differs from the chosen `path`; otherwise it is null. A renamed file keeps both paths, and a deleted file uses the old path as `path` because it has no `new_path`.

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

`DISCUSSION_ID` is the full 40-character id (`remoteId` in the state file). `glab mr note create --reply` accepts an 8-character prefix, but the REST endpoint does not.

The scripts only send these two calls from `post_reply.py`, and only with `--post`. Resolving is a second decision: `--resolve` closes only `authorKind: self` threads; `--resolve-other` is required for anyone else and appends a `resolve-override` event.

---

## Debugging the state file

```bash
python3 scripts/triage_state.py path          # resolved state path and its source
python3 scripts/triage_state.py threads       # thread ids, anchors, authors
python3 scripts/triage_state.py show          # plan with statuses and warnings
python3 scripts/triage_state.py render        # the Markdown table
```

All three commands accept `--state PATH`. `path` works before the first fetch and prints the directory the resolver would use.

If `load_state` reports a schema mismatch, the file predates schema v2. Re-run `fetch_threads.py`; the scripts do not migrate old files.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Zero threads on a busy MR | Resolution filter applied to the wrong field | Use `resolvable && !resolved` and drop `system` notes on GitLab |
| Discussions missing after a short first page | Pagination stopped early | Follow the `per_page`/`page` loop until a short page; a 20-page cap warning means the MR is unusually large |
| `401 Unauthorized` | Token missing for that host | `glab auth login --hostname HOST` |
| State file shows up in `git status` | Written outside an ignored dir | Let the resolver pick the path; an unignored `$MR_TRIAGE_DIR` inside the repo is refused |
| State filename is unexpected | The slug is derived from `repo`, not the local directory | Check `host`/`repo` in the file or re-run with explicit `--repo` |
| `schema version 1` error | Old state file | Delete it or re-run `fetch_threads.py` with `--reset` |
| Item will not post | It is orphaned, unapproved, or already posted | `triage_state.py show`; re-fetch and re-plan orphans, run `approve` for a code item, and let the journal skip already-posted threads |
| Reply batch refuses with a thread ownership conflict | Two items name the same thread, or a thread already has a post record on another item | Keep each thread id on exactly one item; inspect `show`, fix the plan, and retry. The refusal happens before any preview or `glab` call |
| `set --status applied` refuses with "no clean preflight" | The clean check was not recorded after this item was approved | Run `triage_state.py preflight` after `approve` and before applying; preflight taken earlier, or a dirty preflight, does not count |
| Reply batch refuses with "Gate 1 is required" | The plan contains an unapproved `ACCEPT`/`ALTERNATIVE` item | `triage_state.py approve all`, or skip the code item and re-run `--all-approved` |
| `--resolve` refuses a thread you own | `authorKind` is `human`, not `self` | Authenticate the account that authored it, or use `--resolve-other` deliberately (audited) |
| Execute phase refuses to start | `preflight` found a dirty tree | Commit or stash the named paths, then re-run `triage_state.py preflight` |
| Replies post to the wrong thread | Short id used instead of the full discussion id | Use `remoteId` from the state file; the scripts always do |
| A partial batch stopped halfway | One `glab` call failed | Re-run the same command: threads with a post record are skipped, the failed thread and the unattempted threads are printed |
