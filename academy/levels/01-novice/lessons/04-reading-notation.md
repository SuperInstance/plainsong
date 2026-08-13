### TapScript Lesson 04: Reading Notation (Novice)

**(1) Before you start:** You know what a TapScript file looks like (`.tap`), can run it at `http://localhost:5557`, and understand that a script is a list of instructions executed top-to-bottom.

**(2) The concept simply:** TapScript reads like a recipe. Each line is a **step**. The **ingredients** are *variables* (like `x`), the **actions** are *commands* (like `print`), and the **seasoning** is *syntax* (symbols like `=`, `+`, `;`). Reading notation means: identify what is a *variable*, what is a *value*, and what is an *operator*—before you even run it.

**Example (paste into http://localhost:5557):**
```tap
// A simple notation read
let myNumber = 5;   // 'myNumber' is a variable, '5' is a literal value
let myText = "hello"; // 'myText' is a variable, "hello" is a string literal
print myNumber + 2;  // '+' is an operator, output: 7
print myText;        // output: hello
```
*Read it aloud:* "Let myNumber equal five. Let myText equal hello. Print myNumber plus two. Print myText."

**(3) JSON exercise block:**
```json
{
  "exercise": "Read the following TapScript and write the output in your answer. Script: let a = 10; let b = 3; print a - b; print a * b;",
  "submit_to": "/api/exercise-check",
  "expected_elements": ["7", "30"],
  "passing_criteria": "Answer must contain exactly two integers, separated by a space or newline, matching order."
}
```

**(4) What to save to your knowledge base (KB):**
```
[KB/TapScript/04_ReadingNotation]
- Notation = variable names (letters, no spaces), literals (numbers, strings in quotes), operators (+, -, *, /, =).
- Semicolon (;) ends a statement. // is a comment (ignored).
- Read left-to-right: `let x = 1;` → assign, then `print x;` →
