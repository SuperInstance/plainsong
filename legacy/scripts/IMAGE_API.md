# Image Generation API — Quick Reference

## Generate an image (text-to-image)

```bash
curl -X POST http://localhost:5555/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "a gillnetter at anchor in a Southeast Alaska cove at dawn, fog",
    "negative_prompt": "blurry, low quality",
    "model": "dreamshaper_8",
    "steps": 25,
    "guidance": 7.5,
    "seed": null,
    "width": 512,
    "height": 768,
    "loras": [{"name": "sumi_e_ink_wash", "weight": 0.8}],
    "album": "hermes"
  }'
```

## Generate with a cloud model (DeepInfra)

```bash
curl -X POST http://localhost:5555/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "a lighthouse on a cliff at dawn",
    "model": "cloud:FLUX-1-schnell",
    "width": 1024,
    "height": 1024,
    "steps": 4,
    "guidance": 3.5
  }'
```

## Image-to-image (modify existing)

```bash
curl -X POST http://localhost:5555/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "change the lighting to red emergency",
    "model": "dreamshaper_8",
    "init_image": "/path/to/existing/image.png",
    "strength": 0.6,
    "steps": 25,
    "guidance": 7.5
  }'
```

## List available models

```bash
curl http://localhost:5555/api/models    # local checkpoints
curl http://localhost:5555/api/loras     # LoRAs
curl http://localhost:5555/api/cloud-models  # DeepInfra cloud models
```

## List gallery images

```bash
curl http://localhost:5555/api/gallery
```

## Check generation status

```bash
curl http://localhost:5555/api/status
# Returns: {"status": "idle"} or {"status": "generating", "started": timestamp}
# or {"status": "done", "output": "/path/to/image.png"}
```

## Move image to album

```bash
curl -X POST http://localhost:5555/api/move-to-album \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/image.png", "album": "hermes"}'
```

## Delete image

```bash
curl -X POST http://localhost:5555/api/delete \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/image.png"}'
```

## Python helper for agents

```python
import requests

def generate_image(prompt, model="dreamshaper_8", loras=None, album=None, **kwargs):
    """Generate an image via the gallery API. Returns the image path."""
    payload = {
        "prompt": prompt,
        "model": model,
        "steps": kwargs.get("steps", 25),
        "guidance": kwargs.get("guidance", 7.5),
        "width": kwargs.get("width", 512),
        "height": kwargs.get("height", 768),
        "negative_prompt": kwargs.get("negative_prompt", ""),
        "loras": loras or [],
        "seed": kwargs.get("seed"),
    }
    if album:
        payload["album"] = album
    
    r = requests.post("http://localhost:5555/api/generate", json=payload)
    return r.json()

# Example usage:
# generate_image("fog over Southeast Alaska water at dawn",
#     model="dreamshaper_8",
#     loras=[{"name": "sumi_e_ink_wash", "weight": 0.8}])
#
# generate_image("a lighthouse", model="cloud:FLUX-1-schnell",
#     width=1024, height=1024, steps=4)
```
