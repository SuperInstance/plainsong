# TapScript Lesson 05: Adding a Second Instrument  
**Level:** Apprentice  

---

## Concept: Layering Tracks  
A single instrument is a voice. Two instruments create dialogue. In TapScript, you don’t just “add” a track — you define a **new instrument object** and then **interleave** its notes with the first. The key is **timing alignment**: both instruments share the same global tempo and bar grid, but each has its own `pattern` array. You can also set per-instrument `volume` and `pan` to create spatial separation.

---

## TapScript Example  
```tascript  
{  
  "tempo": 100,  
  "instruments": [  
    {  
      "id": "kick",  
      "wave": "sine",  
      "volume": 0.8,  
      "pattern": ["1:0", "1:2", "2:0", "2:2", "3:0", "4:0"]  
    },  
    {  
      "id": "hat",  
      "wave": "noise",  
      "volume": 0.3,  
      "highpass": 8000,  
      "pattern": ["1:0.5", "1:1.5", "2:0.5", "2:1.5", "3:0.5", "4:0.5", "4:1.5"]  
    }  
  ]  
}  
```  
The kick hits on beats, the hat on offbeats. Notice the `pattern` uses `"bar:beat"` format. Both instruments read from the same bar count — they stay locked.

---

## JSON Exercise Block  
Complete the script for a **bass + snare** duo. The bass plays on beats 1 and 3 of every bar. The snare plays on beat 2 and 4. Fill in the missing `pattern` arrays.

```tascript  
{  
  "tempo": 90,  
  "instruments": [  
    {  
      "id": "bass",  
      "wave": "triangle",  
      "volume": 0.6,  
      "pattern": [ ___ ]  
    },  
    {  
      "id": "snare",  
      "wave": "square",  
      "volume": 0.5,  
      "pattern": [ ___ ]  
    }  
  ]  
}  
```
**Hint:** Use 4 bars. Bass: `"1:0", "1:2", ...
