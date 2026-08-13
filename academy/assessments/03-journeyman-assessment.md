**TAPSCRIPT LEVEL 03 ASSESSMENT: JOURNEYMAN GATE**

**Instructions:** Complete all 5 composition tasks in order. Each block must be valid JSON. After finishing, self-grade using the rubric. You must score **80/100** to advance.

---

### (1) Composition Tasks (JSON Blocks)

**Task 1 – Core Syntax (10 pts)**
```json
{
  "task": "Echo 'PASS' if variable 'level' equals 3, else 'FAIL'",
  "expected_elements": ["if", "else", "echo", "variable comparison"],
  "solution_hint": "Uses standard if/else with == operator."
}
```

**Task 2 – Data Handling (15 pts)**
```json
{
  "task": "Create an array of 5 fruits, then output the 3rd item.",
  "expected_elements": ["array declaration", "index access [2]", "echo"],
  "solution_hint": "Zero-based indexing; no loops required."
}
```

**Task 3 – Control Flow (20 pts)**
```json
{
  "task": "Loop from 1 to 10, skip even numbers, print odd numbers only.",
  "expected_elements": ["for loop", "modulo (%)", "continue", "echo"],
  "solution_hint": "Use 'if (i % 2 == 0) continue;' inside loop."
}
```

**Task 4 – Function & Scope (25 pts)**
```json
{
  "task": "Define a function 'multiply' that takes 2 args, returns product. Call it with 6 and 7, store result in global var, print it.",
  "expected_elements": ["function definition", "return", "global variable", "function call", "echo"],
  "solution_hint": "Declare global with 'global' keyword inside function."
}
```

**Task 5 – Complex Logic (30 pts)**
```json
{
  "task": "Parse a string 'name:age:city' (e.g., 'Alice:30:NYC'). Split on ':', validate age is numeric and >18, then output a formatted sentence.",
  "expected_elements": ["split()", "type validation", "logical AND", "string interpolation", "error handling (else)"],
  "solution_hint": "Use 'is_numeric' or regex; handle missing parts gracefully."
}
```

---

### (2) Self-Grading Rubric (0–100)

| Task | Max | Criteria | Deduct |
|------|-----|----------|--------|
| 1 | 10 | Correct if/else, exact output | -5 per syntax error |
| 2 | 15 | Array correct, index right | -5 if off-by-one |
| 3 | 
