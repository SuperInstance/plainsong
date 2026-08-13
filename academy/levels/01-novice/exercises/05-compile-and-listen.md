# TapScript Exercise 05: Compile and Listen

**Task Description**  
You are a novice agent learning TapScript. Your goal is to write a script that compiles successfully and then *listens* for a simple input event. Specifically:
1. Create a script named `listen.tap`.
2. The script must contain a `main` function.
3. Inside `main`, use the `listen` command to wait for a single keypress (e.g., `listen("key")`).
4. After the keypress, print a message using `print("Key pressed!")`.
5. Compile the script using `tapc listen.tap -o listen.tbc` and then run it with `tap run listen.tbc`. Verify it prints the message after you press any key.

**JSON Criteria Block**
```json
{
  "expected_elements": [
    "function main()",
    "listen(\"key\")",
    "print(\"Key pressed!\")"
  ],
  "passing_criteria": [
    "Script compiles without errors",
    "Running the compiled bytecode prints 'Key pressed!' after a keypress",
    "No undefined variables or syntax errors"
  ]
}
```

**Hint**  
Remember: `listen` pauses execution until input. The argument `"key"` tells TapScript to detect any keyboard key. Ensure your `main` function is the entry point—no extra parentheses or missing braces.

**Expert Solution**  
```tapscript
function main() {
    listen("key");
    print("Key pressed!");
}
```
Compile with `tapc listen.tap -o listen.tbc`, then run `tap run listen.tbc`. Press any key—it will print the message. This teaches you the basic input loop, which you'll extend in future exercises.
