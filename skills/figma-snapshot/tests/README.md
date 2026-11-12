# Tests

## Unit tests

```bash
python3 -m unittest discover -s tests -v
```

35 tests, stdlib only, no network and no token. They cover:

- URL parsing (`design`, `file`, `proto`, `board`, bare keys) and node-id normalization.
- Cache budget, spend, month rollover, reconciliation, manifest versioning, atomic writes, prune.
- Index/node summaries, including text extraction.
- Dry-run, budget exhaustion, offline hits and misses, node-id validation.
- 24-hour freshness: fresh hits skip meta; stale entries fall back to meta and refetch on a version change.
- HTTP error mapping (401 → exit 3, 429 → exit 6 with `Retry-After`).
- CLI `resolve`, `status`, and `budget --set` JSON output.

Run a single class:

```bash
python3 -m unittest tests.test_figma_snapshot.ParsingTests -v
```

## Live smoke test

Costs **3 Tier-1 requests** against your own quota. Use a throwaway cache and a low cap so a mistake cannot drain the month:

```bash
cd skills/figma-snapshot
export FIGMA_ACCESS_TOKEN="figd_..."        # read-only PAT
export FIGMA_CACHE_HOME=/tmp/figma-snapshot-live
export FIGMA_MONTHLY_BUDGET=5

# 1. node snapshot (spend 1)
python3 scripts/figma_snapshot.py --json node "<frame-url>"

# 2. repeat (hit, spend 0)
python3 scripts/figma_snapshot.py --json node "<frame-url>"

# 3. file index (spend 1)
python3 scripts/figma_snapshot.py --json index "<file-url>"

# 4. render (spend 1)
python3 scripts/figma_snapshot.py render "<frame-url>" --format png --scale 0.25

# 5. repeat render (hit, spend 0)
python3 scripts/figma_snapshot.py render "<frame-url>" --format png --scale 0.25

python3 scripts/figma_snapshot.py status
rm -rf /tmp/figma-snapshot-live
```

Expected: steps 1, 3, and 4 report `"spent": 1`; steps 2 and 5 report `"hit": true, "spent": 0`; status shows `3 / 5 spent` and `2 left`.

If a step fails, do not rerun it blindly: check `status`, then `resolve` the link. A 401 means the token expired (no spend); a 403 means access or scope (no spend); a 429 means the quota is already tight.

## Adding tests

Keep tests offline. Mock `fs.urllib.request.urlopen` for HTTP cases, or call the service with `offline=True` and a fixture in the cache. The live smoke test is manual; do not put it in CI.
