#### C1 · src/components/VSlider/VSlider.tsx:118-124

**Anchor:** `src/components/VSlider/VSlider.tsx:118-124`

````markdown
**Throttle UI-to-JS dispatch in `panGesture.onChange`**

**Type:** `blocker` · **Kind:** `bug` · **Severity:** `correctness` · **Affects users:** `yes`

Calling `scheduleOnRN` on every pan tick can dispatch up to 120 calls/sec. Throttling to 32ms keeps the thumb at native frame rate while cutting bridge traffic by about 75%.

**Steps to Reproduce**

1. Open a post with a media slider.
2. Drag the thumb quickly from 0 to 100.
3. Watch the thumb lag behind the finger by roughly two frames.

**Expected:** The thumb tracks the finger.
**Actual:** It stutters at high tick rates.
````

#### C2 · src/config/flags.ts:42

**Anchor:** `src/config/flags.ts:42`

````markdown
**Fold the slider flag into the shared config**

**Type:** `follow-up` · **Kind:** `refactor` · **Severity:** `maintainability` · **Affects users:** `no`

The branch adds a one-off public flag. A follow-up can move it beside the other slider settings once the API settles.
````

2 comments · 2/2 anchors verified at abc1234 · 0 dropped · lang=en
