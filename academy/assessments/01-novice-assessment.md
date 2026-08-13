# TapScript Level 01 Assessment — Novice Gate

**Purpose:** Verify foundational TapScript composition, structure, and self-correction skills.

---

## Part 1: Composition Tasks (5 blocks)

**Task 1 — Simple Tap (Warm-up)**
```json
{
  "task": "Create a tap that logs 'hello'",
  "expected_elements": ["tap_name", "tap_body", "log_output", "no_parameters"]
}
```

**Task 2 — Tap with Input**
```json
{
  "task": "Create a tap that accepts a `name` string and logs 'Hi, {name}'",
  "expected_elements": ["parameter_typed", "string_interpolation", "log_output", "tap_name"]
}
```

**Task 3 — Conditional Logic**
```json
{
  "task": "Create a tap that checks if a number is even or odd and logs the result",
  "expected_elements": ["if_else", "modulo_operator", "two_log_branches", "parameter_typed"]
}
```

**Task 4 — Loop over List**
```json
{
  "task": "Create a tap that takes a list of words and logs each word with its index",
  "expected_elements": ["for_loop", "list_parameter", "index_access", "log_inside_loop"]
}
```

**Task 5 — Error Handling**
```json
{
  "task": "Create a tap that divides two numbers but logs 'Error' if divisor is zero",
  "expected_elements": ["try_catch", "division_operation", "error_log", "return_or_break"]
}
```

---

## Part 2: Self-Grading Rubric (0–100)

| Criteria | Points |
|----------|--------|
| **Correct syntax** (no missing brackets, commas, or typos) | 30 |
| **All expected_elements present** (per task) | 40 (8 pts each) |
| **Logic correctness** (tap actually runs and produces correct output) | 20 |
| **Readability** (clear tap names, indentation, comments) | 10 |

**Deduct 5 pts** for each missing or renamed expected element.  
**Deduct 10 pts** if a tap does not compile or run.

---

## Part 3: Advancement Threshold

- **Passing score: 80/100 or higher.**  
- Score below 80 → review the TapScript Basics module and retry in 48 hours.

---

## Part 4: Saving to Knowledge Base

1. **Create a file** named `level01_assessment_results.md` in your personal knowledge base folder.
2. **Include:**  
   - Your 5 JSON task blocks (copy exactly as written).  
   - Your self-graded rubric table with scores per task.  
  
