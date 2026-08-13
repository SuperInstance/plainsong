# TapScript LEVEL 02 ASSESSMENT — Apprentice → Journeyman

**Purpose:** Verify mastery of composition, nesting, and dynamic referencing.  
**Time limit:** 45 minutes.  
**Tools allowed:** TapScript editor, official docs. No AI assistance.

---

## PART 1 — Composition Tasks (5 JSON blocks)

Complete each task. Each block must be valid JSON and contain **all** `expected_elements`.

### Task 1 — Basic Trigger + Action (Easy)
```json
{
  "trigger": "on_message",
  "condition": "message contains 'hello'",
  "action": "reply 'Hi there!'",
  "expected_elements": ["trigger", "condition", "action", "string_literal"]
}
```

### Task 2 — Multi-step with Variables (Medium)
```json
{
  "trigger": "on_timer",
  "interval": "30s",
  "variables": {"count": 0},
  "steps": [
    {"set": "count = count + 1"},
    {"if": "count > 5", "then": "reply 'Limit reached'", "else": "log count"}
  ],
  "expected_elements": ["timer", "variable_assignment", "conditional_branch", "increment_operation"]
}
```

### Task 3 — Nested Conditionals (Hard)
```json
{
  "trigger": "on_webhook",
  "payload": "order",
  "steps": [
    {"if": "order.total > 100",
     "then": [
       {"if": "order.priority == 'high'", "then": "apply_discount 0.2"},
       {"else": "apply_discount 0.1"}
     ],
     "else": "apply_discount 0"},
    {"record": "order.id", "to": "processed_orders"}
  ],
  "expected_elements": ["nested_if", "discount_function", "else_branch", "data_recording"]
}
```

### Task 4 — Loops + External Call (Expert)
```json
{
  "trigger": "on_schedule",
  "cron": "0 9 * * 1",
  "steps": [
    {"fetch": "https://api.example.com/items", "store": "items"},
    {"loop": "items",
     "body": [
       {"if": "item.stock < 10", "then": "send_alert item.id"},
       {"update": "item.stock", "with": "item.stock - 5"}
     ]},
    {"log": "Completed loop"}
  ],
  "expected_elements": ["cron_trigger", "http_fetch", "loop_block", "conditional_inside_loop", "state_update"]
}
```

### Task 5 — Parallel + Error Handling (Master
