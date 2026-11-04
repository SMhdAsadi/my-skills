#### C1 · blocker · src/components/VSlider/VSlider.tsx:118-124

**Anchor:** `src/components/VSlider/VSlider.tsx:118-124`

````markdown
**Throttle UI-to-JS dispatch in `panGesture.onChange`**

Calling `scheduleOnRN` on every pan tick can dispatch up to 120 calls/sec. Throttling to 32ms keeps the thumb at native frame rate while cutting bridge traffic by about 75%.
````

#### C2 · question · MR-level

**Anchor:** `MR-level`

````markdown
**Should the new flag stay public?**

The branch adds a public flag that only the slider reads. Is it meant for consumers, or can it stay internal until a second caller needs it?
````

**Dropped candidates**

| Candidate | Reason |
|---|---|
| Uniform LTR enforcement across all players | unbounded audit; no anchor |

2 comments · 2/2 anchors verified at abc1234 · 1 dropped · lang=en
