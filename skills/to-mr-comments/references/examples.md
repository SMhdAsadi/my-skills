# Certified examples

Four comments that pass the selection test, and one that does not. Each certified example shows the verified anchor, the evidence line, the rendered copy box in both modes, and the reason it earns a slot in the budget.

The inline box is what you paste into a diff thread. The summary box is for an MR-level note or a comment that spans files. They contain the same prose; only the heading and target differ.

---

## 1. `blocker` — performance

**Anchor:** `src/components/VSlider/VSlider.tsx:118` (verified at `abc1234`, range `118-124`)
**Evidence:** `src/components/VSlider/VSlider.tsx:118` fires on every pan tick; ~120 calls/s at 120Hz.

**Inline:**

````markdown
**Throttle UI-to-JS dispatch in `panGesture.onChange`**

Calling `scheduleOnRN` on every pan tick dispatches up to 120 calls/sec at 120Hz. Throttling to 32ms keeps the thumb at native frame rate while cutting bridge traffic by about 75%.
````

**Summary:**

````markdown
### Throttle UI-to-JS dispatch in `panGesture.onChange`
**Target:** `src/components/VSlider/VSlider.tsx:118-124`

Calling `scheduleOnRN` on every pan tick dispatches up to 120 calls/sec at 120Hz. Throttling to 32ms keeps the thumb at native frame rate while cutting bridge traffic by about 75%.
````

**Why it passes:** unbounded per-frame cost (rule 4), a measured consequence (120 calls/s), and a verified anchor inside the diff. `agreed` + `high` confidence makes it a blocker.

---

## 2. `question` — edge case with an open decision

**Anchor:** `src/range.ts:10` (verified at `abc1234`)
**Evidence:** `src/range.ts:10` divides by `max - min` without a zero guard.

**Inline:**

````markdown
**Does a zero-width range reach this division?**

If `max === min` while the media duration is still loading, this divides by zero and pushes `NaN` into the value store. What should the percentage be during that window?
````

**Summary:**

````markdown
### Does a zero-width range reach this division?
**Target:** `src/range.ts:10`

If `max === min` while the media duration is still loading, this divides by zero and pushes `NaN` into the value store. What should the percentage be during that window?
````

**Why it passes:** a reachable wrong output (rule 1). The user's decision is `open`, so the comment asks rather than prescribing; the answer changes the fix.

---

## 3. `suggestion` — small, mechanical replacement

**Anchor:** `src/query/useJobs.ts:42` (verified at `abc1234`)
**Evidence:** `src/query/useJobs.ts:42` maps an empty page to `[undefined]`.

**Inline:**

````markdown
**Guard the empty page before mapping**

An empty page currently maps to `[undefined]`, which the list renders as a blank row. Returning early keeps the cache shape stable.

```suggestion:-0+0
if (!page.items.length) {
  return [];
}
```
````

**Summary:**

````markdown
### Guard the empty page before mapping
**Target:** `src/query/useJobs.ts:42`

An empty page currently maps to `[undefined]`, which the list renders as a blank row. Returning early keeps the cache shape stable.

```suggestion:-0+0
if (!page.items.length) {
  return [];
}
```
````

**Why it passes:** a reachable wrong output (rule 1), a 3-line replacement, and `agreed` + `high`. The native suggestion block makes the fix one click instead of a paragraph.

---

## 4. `test-gap` — changed behavior without coverage

**Anchor:** `src/components/Toast/Toast.tsx:88` (verified at `abc1234`)
**Evidence:** `src/components/Toast/Toast.tsx:88` starts a timer; the new cleanup covers only the error variant.

**Inline:**

````markdown
**Add a test for unmounting during auto-dismiss**

The success variant starts a timer, but the new cleanup is only covered for errors. A test that mounts a success toast, unmounts it, and advances fake timers would catch a leaked timer with about ten lines.
````

**Summary:**

````markdown
### Add a test for unmounting during auto-dismiss
**Target:** `src/components/Toast/Toast.tsx:88`

The success variant starts a timer, but the new cleanup is only covered for errors. A test that mounts a success toast, unmounts it, and advances fake timers would catch a leaked timer with about ten lines.
````

**Why it passes:** changed behavior is untested in a way that matters (rule 3), and the comment names the missing case and the cheapest useful test instead of asking for "more tests".

---

## Rejected anti-example

This is the old comment, kept here so the bar stays concrete. It reads well and says nothing checkable.

````markdown
### Consolidate LTR direction enforcement across media player containers
**Target:** `src/containers/post/PostCloudMeeting/PostCloudMeetingFooterFinished.tsx`, `src/containers/audio/AudioItemSliderContainer.tsx`

The footer media controls now enforce `direction: 'ltr'` directly. Let's make sure this pattern is uniformly used instead of legacy `flexDirection` flipping across all player sub-views so media controls stay strictly left-to-right in RTL mode.
````

**Why it is rejected:**

- **Unbounded audit.** "Across all player sub-views" is a repository-wide survey, not a finding the diff can satisfy.
- **No single anchor.** Two paths are named, neither with a line, and neither is the line under discussion.
- **No evidence.** There is no `path:line` fact, no measurement, no failing case.
- **No consequence.** "Stay strictly left-to-right" is a preference unless a specific control is visibly wrong.
- **Not `agreed`.** Nobody decided this; it was a thought that arrived mid-review.

It belongs in `dropped[]` as `{claim, reason: "unbounded audit; no anchor; no evidence"}` — or nowhere at all. Do not imitate its shape.
