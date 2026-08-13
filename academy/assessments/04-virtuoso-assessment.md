# TapScript LEVEL 04 ASSESSMENT — Virtuoso Gate

**Purpose:** This exam certifies mastery of TapScript composition, recursion, and stateful logic. Passing advances you to Level 05 (Architect).

---

## Part 1: Composition Tasks (5 blocks)

### Task 1 — Warm‑up (Basic)
```json
{
  "id": "L4_T1",
  "prompt": "Emit a greeting, then a timestamp, then a farewell.",
  "expected_elements": ["emit_greeting", "emit_timestamp", "emit_farewell"],
  "constraints": "No loops, linear flow only."
}
```

### Task 2 — Conditional Branching
```json
{
  "id": "L4_T2",
  "prompt": "If input contains 'urgent', emit HIGH_PRIORITY; else emit NORMAL_PRIORITY. Then always log.",
  "expected_elements": ["if_condition", "emit_priority", "emit_log"],
  "constraints": "Use single if/else, no nested conditions."
}
```

### Task 3 — Recursive Reduction
```json
{
  "id": "L4_T3",
  "prompt": "Given a list, reduce it by summing all numeric values until empty, emitting each partial sum.",
  "expected_elements": ["recursive_call", "emit_partial", "base_case_check"],
  "constraints": "Tail‑recursion only, no mutation of original list."
}
```

### Task 4 — Stateful Pipeline
```json
{
  "id": "L4_T4",
  "prompt": "Maintain a counter across three separate events. Increment on each event, emit counter value, reset after third.",
  "expected_elements": ["state_definition", "increment_operation", "reset_trigger"],
  "constraints": "State must be external to event handlers."
}
```

### Task 5 — Meta‑Composition (Mastery)
```json
{
  "id": "L4_T5",
  "prompt": "Build a TapScript that takes another TapScript as input, validates its expected_elements, and emits a compliance report.",
  "expected_elements": ["input_script_parse", "schema_validation", "report_emit"],
  "constraints": "Must handle missing elements gracefully, no hardcoded script names."
}
```

---

## Part 2: Self‑Grading Rubric (0–100)

- **Correctness (40 pts):** Each task’s expected_elements fully present and in logical order. Missing element = −8 pts per task.
- **Efficiency (20 pts):** No redundant loops, optimal state usage. Deduct 2 pts per avoidable scan.
- **Readability (20 pts):** Clear
