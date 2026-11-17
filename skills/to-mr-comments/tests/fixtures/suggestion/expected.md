#### C1 · suggestion · src/range.ts:10-12

**Anchor:** `src/range.ts:10-12`

````markdown
**Guard the zero-width range**

A zero-width range divides by zero here and pushes `NaN` into the value store.

```suggestion:-0+0
if (max > min) {
  apply(value);
}
```
````

1 comment · 1/1 anchors verified at abc1234 · 0 dropped · lang=en
