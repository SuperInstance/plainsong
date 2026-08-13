**TAPSCRIPT LEVEL 05 ASSESSMENT: MASTER AGENT CERTIFICATION**

**Instructions:** Complete all 5 tasks sequentially. Each JSON block must be syntactically valid and contain only allowed elements. You may use internal reasoning but final output must be pure JSON. Time limit: 90 minutes.

---

### (1) Composition Tasks

**Task 1 – Foundational (15 pts)**
```json
{
  "goal": "Extract all email addresses from a text block",
  "expected_elements": ["regex_pattern", "find_all", "output_list"],
  "constraints": ["no_loops", "single_line"]
}
```

**Task 2 – Intermediate (20 pts)**
```json
{
  "goal": "Transform a CSV string into a JSON array of objects",
  "expected_elements": ["split_by_newline", "split_by_comma", "header_mapping", "json_serialize"],
  "constraints": ["no_external_libraries", "pure_functions"]
}
```

**Task 3 – Advanced (20 pts)**
```json
{
  "goal": "Filter and sort a list of maps by nested key, then deduplicate",
  "expected_elements": ["filter_condition", "sort_by_nested", "deduplicate_by_key", "pipeline_chain"],
  "constraints": ["immutable_operations", "no_mutation_of_input"]
}
```

**Task 4 – Expert (25 pts)**
```json
{
  "goal": "Build a recursive directory tree from a flat path list",
  "expected_elements": ["recursive_function", "tree_node_creation", "path_parsing", "cycle_detection", "depth_tracking"],
  "constraints": ["tail_recursion_optimization", "max_depth_param"]
}
```

**Task 5 – Master (20 pts)**
```json
{
  "goal": "Create a self-healing data pipeline that retries failed transforms with exponential backoff",
  "expected_elements": ["retry_wrapper", "backoff_calculator", "error_classification", "circuit_breaker", "fallback_strategy"],
  "constraints": ["async_compatible", "no_global_state"]
}
```

---

### (2) Self-Grading Rubric (0–100)

| Criteria | 0 pts | 5–10 pts | 15–20 pts |
|----------|-------|-----------|-----------|
| **Correctness** | Fails all tests | Partial execution | All expected_elements present & functional |
| **Efficiency** | O(n²) or worse | Acceptable | Optimal (O(n) or better) |
| **Readability** | Unreadable | Some comments | Clear naming, logical flow |
| **Robustness** | Crashes on edge |
