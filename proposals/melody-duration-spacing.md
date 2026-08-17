Here are three designs for Plainsong where **duration is shown by physical spacing**, along with full examples, parsing logic, and a final recommendation.

---

## **Format A: Note + tilde sustain**  
`E4~~~~` = whole note, `E4~~` = half, `E4` = eighth. Each tilde = one eighth of the beat (so 8 tildes = whole note, 4 = half, 2 = quarter, 1 = eighth, 0 = sixteenth? — but let's keep it simple: no tilde = eighth, each tilde adds an eighth).

### 1. Four bars of melody
```
Melody: | C4~~~~ D4~~~~ | E4~~ F4~~ G4~~ A4~~ | B4~~~~ C5~~~~ | D5~~ E5~~ F5~~ G5~~ |
```
(Each bar = 4 beats. First bar: two whole notes. Second: four half notes. Third: two whole notes. Fourth: four half notes.)

### 2. Chords (simultaneous notes)
Use `+` to stack notes vertically, each with its own tilde count. The tilde count must match per chord.  
```
Chords: | C4~~+E4~~+G4~~ | A4~~+C5~~+E5~~ | F4~~+A4~~+C5~~ | G4~~+B4~~+D5~~ |
```
All notes in a chord share the same duration.

### 3. Rests
Use `r` with tildes: `r~~~~` = whole rest, `r~~` = half rest, `r` = eighth rest.
```
Melody: | C4~~ r~~ | D4~~~~ | r~~~~ | E4~~ F4~~ |
```

### 4. Printed look (monospace)
```
| C4~~~~ D4~~~~ | E4~~ F4~~ G4~~ A4~~ |
| C4~~+E4~~+G4~~ | r~~~~           |
```

### 5. Regex to parse
```
^(?<bar>\|(?<note>[A-G]#?b?\d?+r?)(?<sustain>~*) 
    (?:\+(?<note2>[A-G]#?b?\d?+r?)(?<sustain2>~*))* 
    \s*\|)+$
```
Simpler for a single token: `([A-G]#?b?\d?|r)(~*)`  
For chords: `([A-G]#?b?\d?|r)(~*)(?:\+([A-G]#?b?\d?|r)(~*))*`

### 6. Pros/Cons
- ✅ Pros: Easy to type, clear visual length, no ambiguity between "hold" and "space".  
- ❌ Cons: Tildes at the end can be visually confused with punctuation, chords with long tildes get messy, and the mapping (tilde = eighth) is not intuitive.

---

## **Format B: Note + dash sustain**  
`E4------` = whole (6 dashes = 6 eighths? Let's define: dash = eighth. So 8 dashes = whole, 4 = half, 2 = quarter, 1 = eighth, 0 = sixteenth). Actually let's keep 1 dash = eighth for consistency.

### 1. Four bars of melody
```
Melody: | C4-------- D4-------- | E4---- F4---- G4---- A4---- | B4-------- C5-------- | D5---- E5---- F5---- G5---- |
```
(Each bar = 4 beats. Whole = 8 dashes, half = 4, quarter = 2, eighth = 1 dash? Actually no — let's set: whole = 8 dashes, half = 4, quarter = 2, eighth = 1. Then a bar of 4 beats = 8 dashes per whole note.)

### 2. Chords
Same `+` stacking, each note has its own dash count, but they must match.
```
Chords: | C4----+E4----+G4---- | A4----+C5----+E5---- | F4----+A4----+C5---- | G4----+B4----+D5---- |
```

### 3. Rests
Use `r` with dashes: `r--------` = whole rest, `r----` = half, `r--` = quarter, `r-` = eighth.
```
Melody: | C4---- r---- | D4-------- | r-------- | E4---- F4---- |
```

### 4. Printed look
```
| C4-------- D4-------- | E4---- F4---- G4---- A4---- |
| C4----+E4----+G4---- | r--------                   |
```

### 5. Regex
```
([A-G]#?b?\d?|r)(-*)(?:\+([A-G]#?b?\d?|r)(-*))*
```
Bar separator: `\|` ... `\|`

### 6. Pros/Cons
- ✅ Pros: Dashes are visually "drawn out" like a tie, very readable, easy to count.  
- ❌ Cons: Long sequences of dashes are easy to miscount, and chords become wide. Also dash is a common punctuation, so parsing needs care.

---

## **Format C: Block notation**  
`█████E4` = whole note, `██A4` = half, `█G4` = eighth. Each block = an eighth of the beat.

### 1. Four bars of melody
```
Melody: | ████████C4 ████████D4 | ████E4 ████F4 ████G4 ████A4 | ████████B4 ████████C5 | ████D5 ████E5 ████F5 ████G5 |
```
(Each block = 1/8 beat. Whole = 8 blocks, half = 4, quarter = 2, eighth = 1 block.)

### 2. Chords
Stack with `+`, but blocks are shared: `████C4+E4+G4` means all three notes sustain for 4 blocks (half note chord).
```
Chords: | ████C4+E4+G4 | ████A4+C5+E5 | ████F4+A4+C5 | ████G4+B4+D5 |
```

### 3. Rests
Use block characters without a note: `████████` = whole rest, `████` = half rest, `██` = quarter, `█` = eighth.
```
Melody: | ████C4 ████r | ████████D4 | █