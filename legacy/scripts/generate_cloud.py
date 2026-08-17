#!/usr/bin/env python3
"""
Cloud image generation via DeepInfra API.
Supports FLUX models, Qwen-Image, etc.
"""
import os, sys, json, time, base64, requests

DEEPINFRA_KEY = os.environ.get('DEEPINFRA_API_KEY') or "zYuVMGC4JySULP2waqKW35jI42TjaPkl"

CLOUD_MODELS = {
    "FLUX-1-schnell": "black-forest-labs/FLUX-1-schnell",
    "FLUX-1-dev": "black-forest-labs/FLUX-1-dev",
    "FLUX-1.1-pro": "black-forest-labs/FLUX-1.1-pro",
    "FLUX-2-max": "black-forest-labs/FLUX-2-max",
    "FLUX-2-dev": "black-forest-labs/FLUX-2-dev",
    "FLUX-2-klein-4b": "black-forest-labs/FLUX-2-klein-4b",
    "sdxl-turbo": "stabilityai/sdxl-turbo",
    "Qwen-Image-Max": "Qwen/Qwen-Image-Max",
}

def generate_cloud(prompt, model_key, negative_prompt="", width=1024, height=1024, 
                   num_steps=4, guidance=3.5, seed=None, output_path=None):
    """Generate an image via DeepInfra API."""
    model_id = CLOUD_MODELS.get(model_key, model_key)
    
    payload = {
        "prompt": prompt,
        "num_images": 1,
        "width": width,
        "height": height,
    }
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    if seed is not None:
        payload["seed"] = seed
    if num_steps:
        payload["num_steps"] = num_steps
    if guidance:
        payload["guidance"] = guidance
    
    t0 = time.time()
    
    resp = requests.post(
        f"https://api.deepinfra.com/v1/inference/{model_id}",
        headers={
            "Authorization": f"Bearer {DEEPINFRA_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    
    t1 = time.time()
    
    if resp.status_code != 200:
        raise Exception(f"DeepInfra error {resp.status_code}: {resp.text[:300]}")
    
    data = resp.json()
    
    if 'images' not in data or not data['images']:
        raise Exception(f"No images in response: {json.dumps(data)[:300]}")
    
    # Decode base64 image
    img_b64 = data['images'][0]
    if ',' in img_b64:
        img_b64 = img_b64.split(',')[1]
    img_bytes = base64.b64decode(img_b64)
    
    if not output_path:
        from pathlib import Path
        output_dir = Path.home() / ".openclaw/workspace/output/images/gallery"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"cloud-{int(time.time())}.png")
    
    with open(output_path, 'wb') as f:
        f.write(img_bytes)
    
    t2 = time.time()
    
    # Save metadata
    meta = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "model": f"cloud:{model_key}",
        "steps": num_steps,
        "guidance": guidance,
        "seed": seed,
        "width": width,
        "height": height,
        "scheduler": "deepinfra",
        "loras": [],
        "timing": {"generate": round(t1-t0, 1), "save": round(t2-t1, 1), "total": round(t2-t0, 1)},
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "filename": os.path.basename(output_path),
    }
    with open(output_path.replace('.png', '.json'), 'w') as f:
        json.dump(meta, f, indent=2)
    
    print(f"Cloud gen: {model_key} in {t2-t0:.1f}s", file=sys.stderr)
    print(output_path)
    return output_path

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", "-p", required=True)
    p.add_argument("--model", "-m", default="FLUX-1-schnell")
    p.add_argument("--negative", "-n", default="")
    p.add_argument("--width", "-W", type=int, default=1024)
    p.add_argument("--height", "-H", type=int, default=1024)
    p.add_argument("--steps", "-s", type=int, default=4)
    p.add_argument("--guidance", "-g", type=float, default=3.5)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--output", "-o", default=None)
    args = p.parse_args()
    generate_cloud(args.prompt, args.model, args.negative, args.width, args.height,
                   args.steps, args.guidance, args.seed, args.output)
