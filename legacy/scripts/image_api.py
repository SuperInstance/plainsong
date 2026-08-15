#!/usr/bin/env python3
"""
Lucineer Image API — Python client for agents.
Drop this in the same directory and import it.

Usage:
    from image_api import generate, generate_cloud, list_models, list_loras
    
    # Generate locally
    path = generate("a gillnetter at anchor in fog", model="dreamshaper_8",
                    loras=[("sumi_e_ink_wash", 0.8)])
    
    # Generate with cloud (DeepInfra FLUX)
    path = generate("a lighthouse at dawn", model="cloud:FLUX-1-schnell",
                    width=1024, height=1024, steps=4)
    
    # Image-to-image
    path = generate("change lighting to red emergency", model="dreamshaper_8",
                    init_image="/path/to/source.png", strength=0.5)
"""

import requests
import time
import os

BASE_URL = "http://localhost:5555"

def generate(prompt, model="dreamshaper_8", negative_prompt="",
             steps=25, guidance=7.5, seed=None, width=512, height=768,
             loras=None, init_image=None, strength=0.6, album=None,
             wait=True, timeout=300):
    """
    Generate an image via the gallery API.
    
    Args:
        prompt: Text description of what to generate
        model: Checkpoint name or "cloud:FLUX-1-schnell" etc.
        negative_prompt: What to avoid
        steps: Inference steps (more = slower, higher quality)
        guidance: CFG scale (higher = follows prompt more closely)
        seed: Reproducible seed, or None for random
        width/height: Image dimensions (multiples of 64)
        loras: List of (name, weight) tuples, e.g. [("sumi_e_ink_wash", 0.8)]
        init_image: Path to source image for img2img mode
        strength: 0-1, how much to change the init image (1=ignore, 0=keep)
        album: Folder name to save into (creates if needed)
        wait: If True, block until generation completes. If False, return immediately.
        timeout: Max seconds to wait
    
    Returns:
        If wait=True: dict with {"path": "...", "seed": 123, "metadata": {...}}
        If wait=False: dict with {"ok": True, "position": N}
    """
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "model": model,
        "steps": steps,
        "guidance": guidance,
        "width": width,
        "height": height,
        "loras": [{"name": n, "weight": w} for n, w in (loras or [])],
    }
    if seed is not None:
        payload["seed"] = seed
    if init_image:
        payload["init_image"] = init_image
        payload["strength"] = strength
    if album:
        payload["album"] = album
    
    r = requests.post(f"{BASE_URL}/api/generate", json=payload)
    result = r.json()
    
    if not wait:
        return result
    
    # Poll until done
    position = result.get("position", 0)
    start = time.time()
    
    while time.time() - start < timeout:
        status = requests.get(f"{BASE_URL}/api/status").json()
        
        if status.get("status") == "done":
            # Reset status so we don't confuse the web UI
            requests.post(f"{BASE_URL}/api/reset-status", json={})
            output = status.get("output", "")
            
            # Load metadata sidecar if it exists
            meta = {}
            meta_path = output.replace(".png", ".json")
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    import json
                    meta = json.load(f)
            
            return {"path": output, "seed": meta.get("seed"), "metadata": meta}
        
        elif status.get("status") == "error":
            requests.post(f"{BASE_URL}/api/reset-status", json={})
            return {"error": status.get("error", "unknown")}
        
        time.sleep(3)
    
    return {"error": "timeout"}


def generate_cloud(prompt, model="FLUX-1-schnell", width=1024, height=1024,
                   steps=4, guidance=3.5, **kwargs):
    """Shortcut for cloud generation via DeepInfra."""
    return generate(prompt, model=f"cloud:{model}", width=width, height=height,
                    steps=steps, guidance=guidance, **kwargs)


def list_models():
    """List available local checkpoints."""
    return requests.get(f"{BASE_URL}/api/models").json()


def list_loras():
    """List available LoRAs."""
    return requests.get(f"{BASE_URL}/api/loras").json()


def list_cloud_models():
    """List available cloud models with pricing."""
    return requests.get(f"{BASE_URL}/api/cloud-models").json()


def list_albums():
    """List all albums/folders."""
    return requests.get(f"{BASE_URL}/api/albums").json()


def gallery():
    """List all images in the gallery."""
    return requests.get(f"{BASE_URL}/api/gallery").json()


def move_to_album(path, album):
    """Move an image to a different album/folder."""
    return requests.post(f"{BASE_URL}/api/move-to-album",
                         json={"path": path, "album": album}).json()


def delete(path):
    """Delete an image and its metadata."""
    return requests.post(f"{BASE_URL}/api/delete", json={"path": path}).json()


# === MARITIME PRESETS ===
# Curated combos for the "fishermen on anchor" aesthetic

MARITIME_PRESETS = {
    "fog_ink": {
        "model": "dreamshaper_8",
        "loras": [("sumi_e_ink_wash", 0.8)],
        "desc": "Ink-wash fog — Southeast Alaska morning, gray on gray",
    },
    "deck_photo": {
        "model": "juggernaut_reborn",
        "loras": [("analog_film", 0.6)],
        "desc": "Disposable camera deck shot — film grain, Fuji colors",
    },
    "cannery_label": {
        "model": "counterfeit_v3",
        "loras": [("woodcut_style", 0.9)],
        "desc": "Old cannery label / fishing manual woodcut",
    },
    "field_sketch": {
        "model": "dreamshaper_8",
        "loras": [("watercolor_style", 0.7)],
        "desc": "Field notebook watercolor — tide pool, biologist's sketch",
    },
    "harbor_etching": {
        "model": "dreamshaper_8",
        "loras": [("detail_tweaker_v3", 0.5)],
        "desc": "Fine-line etching of harbor scene",
    },
    "cloud_flux": {
        "model": "cloud:FLUX-1-schnell",
        "loras": [],
        "desc": "Cheapest cloud option — destroys SD 1.5 quality at $0.0005",
    },
    "cloud_flux_pro": {
        "model": "cloud:FLUX-1.1-pro",
        "loras": [],
        "desc": "Pro quality cloud generation at $0.04/img",
    },
}

def generate_maritime(scene, preset="fog_ink", **kwargs):
    """
    Generate using a curated maritime preset.
    
    Args:
        scene: The scene description (e.g. "gillnetter at anchor in Thomas Bay")
        preset: One of MARITIME_PRESETS keys
    """
    p = MARITIME_PRESETS.get(preset, MARITIME_PRESETS["fog_ink"])
    return generate(scene, model=p["model"], loras=p["loras"], **kwargs)


if __name__ == "__main__":
    # Quick test
    print("Testing API...")
    print(f"Models: {len(list_models())}")
    print(f"LoRAs: {len(list_loras())}")
    print(f"Gallery: {len(gallery())} images")
    print("\nPresets available:")
    for k, v in MARITIME_PRESETS.items():
        print(f"  {k}: {v['desc']}")
