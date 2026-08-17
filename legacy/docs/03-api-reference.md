

# TapScript Studio API Reference

This document provides a complete reference for the three local services that comprise TapScript Studio. Each service runs on a dedicated port and exposes a set of endpoints for image generation, MIDI composition, and TapScript parsing/compilation.

## Base URLs
| Service | Port | Base URL |
|---------|------|----------|
| Image Gallery | `5555` | `http://localhost:5555` |
| MIDI Studio | `5556` | `http://localhost:5556` |
| TapScript Studio | `5557` | `http://localhost:5557` |

---

## Image Gallery (Port 5555)
*Implementation: `scripts/gallery_v4.py` (stdlib `http.server`)*

### `GET /` or `GET /index.html`
Serves the Image Gallery HTML user interface.

**Request:** None
```bash
curl http://localhost:5555/
```
**Response:** HTML document

---

### `GET /api/gallery`
Returns a JSON list of scanned gallery images.

**Request:** None
```bash
curl http://localhost:5555/api/gallery
```
**Response:**
```json
[
  {
    "filename": "prompt_001.png",
    "path": "/home/user/tapscript/gallery/prompt_001.png",
    "timestamp": "2024-05-10T14:22:00Z"
  }
]
```

---

### `GET /api/models`
Returns a JSON list of locally available Stable Diffusion models.

**Request:** None
```bash
curl http://localhost:5555/api/models
```
**Response:**
```json
[
  "v1-5-pruned-emaonly.safetensors",
  "dreamshaper_8.safetensors"
]
```

---

### `GET /api/loras`
Returns a JSON list of available LoRA weights.

**Request:** None
```bash
curl http://localhost:5555/api/loras
```
**Response:**
```json
[
  {
    "name": "epiCRealism-negativeV6.safetensors",
    "path": "/home/user/stable-diffusion/loras/epiCRealism-negV6.safetensors"
  }
]
```

---

### `GET /api/albums`
Returns a JSON list of albums.

**Request:** None
```bash
curl http://localhost:5555/api/albums
```
**Response:**
```json
[
  {
    "name": "concept_art",
    "path": "/home/user/tapscript/albums/concept_art"
  }
]
```

---

### `GET /api/cloud-models`
Returns a JSON list of DeepInfra cloud models (e.g., FLUX-1-schnell).

**Request:** None
```bash
curl http://localhost:5555/api/cloud-models
```
**Response:**
```json
[
  "black-forest-labs/FLUX.1-schnell",
  "stabilityai/stable-diffusion-xl-base-1.0"
]
```

---

### `GET /api/status`
Returns the current generation worker status. Returns `idle` when no job is queued or running.

**Request:** None
```bash
curl http://localhost:5555/api/status
```
**Response:**
```json
{
  "status": "idle"
}
```

---

### `GET /image?path=<abs path>`
Serves an image file (PNG/JPEG) from the gallery.

**Request Parameters:**
- `path` (query): Absolute path to the image file

```bash
curl "http://localhost:5555/image?path=/home/user/tapscript/gallery/prompt_001.png"
```
**Response:** `image/png` or `image/jpeg` binary stream

---

### `POST /api/generate`
Queues a generation job and returns the queue position.

**Request Body:**
| Field | Type | Description |
|-------|------|-------------|
| `prompt` | string | Generation prompt |
| `negative_prompt` | string | Negative prompt |
| `model` | string | Model identifier |
| `steps` | integer | Sampling steps |
| `guidance` | float | CFG scale |
| `seed` | integer | Random seed (-1 for random) |
| `width` | integer | Output width |
| `height` | integer | Output height |
| `loras` | array | List of `{name, weight}` objects |
| `album` | string | Target album name |
| `init_image` | string | Absolute path or base64 data URI for img2img |
| `strength` | float | img2img denoise strength (only read if `init_image` is set) |

```bash
curl -X POST http://localhost:5555/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "a cyberpunk cityscape at night",
    "negative_prompt": "blurry, low quality",
    "model": "dreamshaper_8.safetensors",
    "steps": 30,
    "guidance": 7.5,
    "seed": 42,
    "width": 512,
    "height": 512,
    "loras": [{"name": "epiCRealism-negV6.safetensors", "weight": 0.8}],
    "album": "concept_art",
    "init_image": null
  }'
```
**Response:**
```json
{
  "ok": true,
  "position": 2
}
```

---

### `POST /api/reset-status`
Manually resets the generation worker status to idle.

**Request Body:** None
```bash
curl -X POST http://localhost:5555/api/reset-status
```
**Response:**
```json
{
  "ok": true
}
```

---

### `POST /api/delete`
Deletes a gallery image and its `.json` sidecar.

**Request Body:**
| Field | Type | Description |
|-------|------|-------------|
| `path` | string | Absolute path to the image file |

```bash
curl -X POST http://localhost:5555/api/delete \
  -H "Content-Type: application/json" \
  -d '{"path": "/home/user/tapscript/gallery/prompt_001.png"}'
```
**Response:**
```json
{
  "ok": true
}
```

---

### `POST /api/move-to-album`
Moves an image and its `.json` sidecar into a specified album directory.

**Request Body:**
| Field | Type | Description |
|-------|------|-------------|
| `path` | string | Absolute path to the image file |
| `album` | string | Target album name |

```bash
curl -X POST http://localhost:5555/api/move-to-album \
  -H "Content-Type: application/json" \
  -d '{"path": "/home/user/tapscript/gallery/prompt_001.png", "album": "concept_art"}'
```
**Response:**
```json
{
  "ok": true,
  "new_path": "/home/user/tapscript/albums/concept_art/prompt_001.png"
}
```

---

## MIDI Studio (Port 5556)
*Implementation: `scripts/midi_studio.py` (stdlib `http.server`, CORS enabled)*

### `GET /`
Serves the MIDI Studio HTML interface (`midi_studio.html`).

**Request:** None
```bash
curl http://localhost:5556/
```
**Response:** HTML document

---

### `GET /api/presets`
Returns the available composition presets.

**Request:** None
```bash
curl http://localhost:5556/api/presets
```
**Response:** (`PRESETS` is a dict keyed by preset id; the real, current set is `harbor_dawn`, `tap_midnight`, `watch_3am`, `open_mic`)
```json
{
  "presets": {
    "harbor_dawn": {
      "name": "🌅 Harbor Dawn", "tempo": 60, "key": "D", "scale": "minor",
      "layers": [
        {"instrument": "piano", "role": "chords", "bars": 8, "volume": 70},
        {"instrument": "strings", "role": "pad", "bars": 8, "volume": 55}
      ],
      "chords": "Dm Am C G",
      "desc": "Dawn over a quiet harbor, fog lifting"
    },
    "tap_midnight": {
      "name": "🍻 Tap at Midnight", "tempo": 75, "key": "A", "scale": "minor",
      "layers": [
        {"instrument": "piano", "role": "chords", "bars": 8, "volume": 75},
        {"instrument": "bass", "role": "bassline", "bars": 8, "volume": 70},
        {"instrument": "flute", "role": "melody", "bars": 8, "volume": 65}
      ],
      "chords": "Am F C G",
      "desc": "The bar at midnight, amber light, intimate"
    }
  }
}
```

---

### `GET /api/download?path=<p>&type=mid|wav`
Serves a generated MIDI or WAV file. Rejects paths containing `..`.

**Request Parameters:**
- `path` (query): Absolute path to the generated file
- `type` (query): File extension (`mid` or `wav`)

```bash
curl "http://localhost:5556/api/download?path=/home/user/tapscript/output/track_001.mid&type=mid"
```
**Response:** `audio/midi` or `audio/wav` binary stream

---

### `POST /api/chat`
Chats with the DeepSeek composer model for music assistance.

**Request Body:**
| Field | Type | Description |
|-------|------|-------------|
| `message` | string | User prompt or question |

```bash
curl -X POST http://localhost:5556/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Generate a jazz chord progression in Bb major"}'
```
**Response:**
```json
{
  "reply": "Here's a classic ii-V-I progression in Bb major: Cm7 F7 Bbmaj7. Would you like me to generate a MIDI file with these chords?",
  "suggestion": "{\"tempo\": 95, \"key\": \"Bb\", \"scale\": \"major\", \"chords\": \"Cm7 F7 Bbmaj7\", \"bars\": 4}"
}
```

---

### `POST /api/generate-midi`
Compiles a composition prompt into a MIDI file and queues it for rendering.

**Request Body:**
| Field | Type | Description |
|-------|------|-------------|
| `tempo` | integer | BPM |
| `key` | string | Musical key (e.g., `C`, `Dm`) |
| `scale` | string | Scale type (`major`, `minor`, etc.) |
| `bars` | integer | Number of bars |
| `chords` | string | Space-separated chord progression |
| `layers` | array | List of `{instrument, role, bars, volume}` objects. `volume` is a MIDI-velocity-scale integer (0-127-ish; default `80` if a layer omits it), **not** a 0.0-1.0 fraction. Recognized `role` values are `chords`, `bassline`, `melody`, `pad`, `fingerpicking`, `strumming`; a layer with `instrument: "drums"` is routed to the drum generator regardless of `role`. If `layers` is omitted entirely, it defaults to a single `{"instrument": "piano", "role": "chords", "bars": bars, "volume": 75}` layer. |
| `swing` | float | Swing amount as a 0.0-1.0 fraction (scaled internally per-role, e.g. `swing * 0.15` for bass/melody), not a percentage |

```bash
curl -X POST http://localhost:5556/api/generate-midi \
  -H "Content-Type: application/json" \
  -d '{
    "tempo": 120,
    "key": "C",
    "scale": "major",
    "bars": 8,
    "chords": "C G Am F",
    "layers": [
      {"instrument": "piano", "role": "melody", "bars": 8, "volume": 80},
      {"instrument": "bass", "role": "bassline", "bars": 8, "volume": 70}
    ],
    "swing": 0.05
  }'
```
**Response:**
```json
{
  "success": true,
  "path": "/home/user/tapscript/output/generated_001.mid",
  "filename": "generated_001.mid",
  "url": "/api/download?path=/home/user/tapscript/output/generated_001.mid&type=mid"
}
```

---

### `POST /api/render-wav`
Renders a MIDI file to WAV using the local sound font/VA synth.

**Request Body:**
| Field | Type | Description |
|-------|------|-------------|
| `midi_path` | string | Absolute path to the MIDI file |

```bash
curl -X POST http://localhost:5556/api/render-wav \
  -H "Content-Type: application/json" \
  -d '{"midi_path": "/home/user/tapscript/output/generated_001.mid"}'
```
**Response:**
```json
{
  "success": true,
  "path": "/home/user/tapscript/output/generated_001.wav",
  "filename": "generated_001.wav",
  "url": "/api/download?path=/home/user/tapscript/output/generated_001.wav&type=wav"
}
```

---

## TapScript Studio (Port 5557)
*Implementation: `scripts/tapscript.py` (Flask). This is the Roman-numeral,
key-relative notation engine — routes below match its real Flask app
exactly. Note this is a **different notation** than the absolute-pitch
format shown in the project README and taught in
[docs/01-getting-started.md](01-getting-started.md), which is implemented
by the separate `scripts/tapscript_v2.py` (a plain stdlib `http.server`,
not Flask — see [docs/02-architecture.md](02-architecture.md) for why two
engines share a default port).*

### `GET /`
Serves the TapScript Studio HTML interface.

**Request:** None
```bash
curl http://localhost:5557/
```
**Response:** HTML document

---

### `POST /api/parse`
Parses a TapScript source string into structured musical data.

**Request Body:**
| Field | Type | Description |
|-------|------|-------------|
| `tapscript` | string | Raw TapScript source code |

```bash
curl -X POST http://localhost:5557/api/parse \
  -H "Content-Type: application/json" \
  -d '{"tapscript": "key: D minor\ntempo: 60\nswing: 0\ntime: 4/4\n\n[Intro]\n  i    .    .    .   | III  .    .    .\n  1    .    3    .   | 5    .    .    .\n\n@wesley: piano | chords | vel: 60\n"}'
```
Real notation: an unlabeled Roman-numeral line (`i`, `III`, ...) is
auto-detected as a chord line, a line of digits (`1`, `5`, ...) as a scale-
degree melody line, and `@name: instrument | role | vel: N` (colon after
the name) registers an instrument.

**Response:**
```json
{
  "key": "D minor",
  "tempo": 60,
  "swing": 0,
  "time_sig": "4/4",
  "sections": [
    {"name": "Intro", "bars": 2}
  ],
  "total_bars": 2,
  "instruments": [
    {"name": "wesley", "instrument": "piano", "role": "chords"}
  ]
}
```

---

### `POST /api/compile`
Compiles a TapScript source string directly to a MIDI file.

**Request Body:**
| Field | Type | Description |
|-------|------|-------------|
| `tapscript` | string | Raw TapScript source code |

```bash
curl -X POST http://localhost:5557/api/compile \
  -H "Content-Type: application/json" \
  -d '{"tapscript": "key: A minor\ntempo: 90\n\n[Bridge]\n  iv   .    V    .   | i    .    .    .\n  1    .    5    .   | 3    .    .    .\n"}'
```
**Response:** (`midi_filename` is `tapscript_<md5-8-of-source>.mid` — the same input text always produces the same filename)
```json
{
  "midi_path": "/home/user/.openclaw/workspace/output/audio/tapscript_3f2a91bc.mid",
  "midi_filename": "tapscript_3f2a91bc.mid"
}
```

---

### `POST /api/render`
Renders a TapScript source string directly to a WAV audio file.

**Request Body:**
| Field | Type | Description |
|-------|------|-------------|
| `tapscript` | string | Raw TapScript source code |

```bash
curl -X POST http://localhost:5557/api/render \
  -H "Content-Type: application/json" \
  -d '{"tapscript": "key: F major\ntempo: 110\n\n[Chorus]\n  I    V    vi   IV  | I    V    vi   IV\n  1    5    6    4   | 1    5    6    4\n"}'
```
**Response:** (`wav_filename` is also derived from `tapscript_<md5-8-of-source>.wav`)
```json
{
  "wav_path": "/home/user/.openclaw/workspace/output/audio/tapscript_7c1de44a.wav",
  "wav_filename": "tapscript_7c1de44a.wav"
}
```

---

### `POST /api/transpose`
Transposes a TapScript source to a new key.

**Request Body:**
| Field | Type | Description |
|-------|------|-------------|
| `tapscript` | string | Raw TapScript source code |
| `key` | string | Target musical key |

```bash
curl -X POST http://localhost:5557/api/transpose \
  -H "Content-Type: application/json" \
  -d '{"tapscript": "key: C major\ntempo: 100\n\n[A]\n  I    V    vi   IV\n  1    5    6    3\n", "key": "G major"}'
```
Because this notation is key-relative (Roman numerals + scale degrees, not
letter names), transposing is *only* a header rewrite — the body text is
byte-for-byte unchanged. `transpose()` does a single regex substitution of
the `key:` line on the raw source and re-parses; every `I`/`V`/`vi`/`IV`
and every scale-degree digit resolves to a different absolute pitch purely
because the active key changed, with no per-token rewriting needed.

**Response:**
```json
{
  "tapscript": "key: G major\ntempo: 100\n\n[A]\n  I    V    vi   IV\n  1    5    6    3\n"
}
```

---

### `GET /api/example`
Returns a list of built-in example TapScript files.

**Request:** None
```bash
curl http://localhost:5557/api/example
```
The three built-in examples (`EXAMPLES` dict in `scripts/tapscript.py`) —
note these are distinct pieces of text from the five examples bundled with
`scripts/tapscript_v2.py`, even where the names match:
```json
{
  "examples": [
    {"id": "harbor_dawn", "name": "Harbor Dawn"},
    {"id": "the_room_is_safe", "name": "The Room Is Safe"},
    {"id": "open_mic", "name": "Open Mic"}
  ]
}
```

---

### `GET /api/example/<name>`
Returns the content of a specific example TapScript.

**Request Parameters:**
- `name` (path): Example identifier (`harbor_dawn`, `the_room_is_safe`, or `open_mic`)

```bash
curl http://localhost:5557/api/example/harbor_dawn
```
**Response (200 OK):**
```json
{
  "name": "Harbor Dawn",
  "tapscript": "key: D minor\ntempo: 60\nswing: 0\ntime: 4/4\n\n[Intro]\n  i    .    .    .   | III  .    .    .\n  1    .    3    .   | 5    .    .    .\n\n[A]\n  i    vi   III  VII | i    .    IV   .\n  3    5    1    .   | 3    2    1    -\n\n[C]\n  i    .    VI   .   | v    .    IV   .\n  5    .    .    3   | 1    .    .    .\n\n[Outro]\n  i    .    .    .   | .    .    .    .\n  1    .    -    .   | -    .    -    .\n\n@wesley: piano | chords | vel: 60\n@flash: strings | pad | vel: 50\n",
  "tempo": 60
}
```
**Response (404 Not Found):**
```json
{
  "error": "Not found"
}
```

---

### `POST /api/example`
Identical to `GET /api/example`. Returns the examples list.

**Request Body:** None
```bash
curl -X POST http://localhost:5557/api/example
```
**Response:**
```json
{
  "examples": [
    {"id": "harbor_dawn", "name": "Harbor Dawn"},
    {"id": "the_room_is_safe", "name": "The Room Is Safe"},
    {"id": "open_mic", "name": "Open Mic"}
  ]
}
```

---

### `GET /audio/<filename>`
Serves a previously rendered WAV or MIDI file from the output directory
(`~/.openclaw/workspace/output/audio`). Anything the request matches under
that directory by filename is served with a guessed MIME type via
`send_file`; there's no extension allow-list.

**Request Parameters:**
- `filename` (path): filename previously returned by `/api/compile` or `/api/render` (e.g., `tapscript_3f2a91bc.mid`)

```bash
curl http://localhost:5557/audio/tapscript_3f2a91bc.mid
```
**Response (200):** binary file stream, MIME type inferred from the file
**Response (404 if missing):** plain text `Not found` (HTTP 404) — not a JSON error body

---
*End of API Reference.*