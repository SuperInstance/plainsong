#!/usr/bin/env python3
"""
Enhanced image generation with LoRA support + metadata saving.
Each generated image gets a companion .json file with full generation parameters.
"""

import argparse
import os
import sys
import time
import json
import torch
from pathlib import Path
from PIL import Image

CHECKPOINT_DIR = "/mnt/c/Users/casey/Documents/ComfyUI/models/checkpoints"
LORA_DIR = "/mnt/c/Users/casey/Documents/ComfyUI/models/loras"
OUTPUT_DIR = os.path.expanduser("~/.openclaw/workspace/output/images/gallery")

def list_models():
    models = []
    if os.path.isdir(CHECKPOINT_DIR):
        for f in sorted(os.listdir(CHECKPOINT_DIR)):
            if f.endswith(('.safetensors', '.ckpt')):
                name = f.replace('.safetensors', '').replace('.ckpt', '')
                models.append(name)
    return models

def list_loras():
    loras = []
    if os.path.isdir(LORA_DIR):
        for f in sorted(os.listdir(LORA_DIR)):
            if f.endswith(('.safetensors', '.ckpt')):
                name = f.replace('.safetensors', '').replace('.ckpt', '')
                loras.append(name)
    return loras

def generate(prompt, negative_prompt="", model_name="dreamshaper_8",
             steps=25, guidance=7.5, seed=None, width=512, height=512,
             output_path=None, scheduler="dpm++",
             loras=None, lora_weights=None):
    """
    Generate an image. loras = list of (name, weight) tuples.
    Saves image + .json metadata sidecar.
    """
    from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler
    
    # Find checkpoint
    ckpt_path = None
    for ext in ['.safetensors', '.ckpt']:
        candidate = os.path.join(CHECKPOINT_DIR, model_name + ext)
        if os.path.exists(candidate):
            ckpt_path = candidate
            break
    
    if not ckpt_path:
        available = list_models()
        print(f"Model '{model_name}' not found. Available: {', '.join(available)}", file=sys.stderr)
        sys.exit(1)
    
    t0 = time.time()
    
    pipe = StableDiffusionPipeline.from_single_file(
        ckpt_path,
        torch_dtype=torch.float16,
        safety_checker=None,
        requires_safety_checker=False,
    )
    
    if scheduler in ("dpm++", "dpmpp", "dpm"):
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    
    pipe = pipe.to("cuda")
    
    try:
        pipe.enable_xformers_memory_efficient_attention()
    except Exception:
        pass
    
    try:
        pipe.vae.enable_tiling()
        pipe.enable_sequential_cpu_offload()
    except Exception:
        pass
    
    # Load LoRAs
    loaded_loras = []
    if loras:
        for i, (lora_name, weight) in enumerate(loras):
            lora_path = None
            for ext in ['.safetensors', '.ckpt']:
                candidate = os.path.join(LORA_DIR, lora_name + ext)
                if os.path.exists(candidate):
                    lora_path = candidate
                    break
            if lora_path:
                try:
                    pipe.load_lora_weights(lora_path)
                    pipe.fuse_lora(lora_scale=weight)
                    loaded_loras.append({"name": lora_name, "weight": weight})
                    print(f"Loaded LoRA: {lora_name} @ {weight}", file=sys.stderr)
                except Exception as e:
                    print(f"Failed to load LoRA {lora_name}: {e}", file=sys.stderr)
    
    if seed is None:
        seed = torch.randint(0, 2**32 - 1, (1,)).item()
    
    t1 = time.time()
    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt if negative_prompt else None,
        num_inference_steps=steps,
        guidance_scale=guidance,
        generator=torch.Generator("cuda").manual_seed(seed),
        width=width,
        height=height,
    )
    t2 = time.time()
    
    image = result.images[0]
    
    if not output_path:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        output_path = os.path.join(OUTPUT_DIR, f"gen-{timestamp}-s{seed}.png")
    
    image.save(output_path)
    t3 = time.time()
    
    # Save metadata sidecar
    metadata = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "model": model_name,
        "steps": steps,
        "guidance": guidance,
        "seed": seed,
        "width": width,
        "height": height,
        "scheduler": scheduler,
        "loras": loaded_loras,
        "timing": {
            "load": round(t1 - t0, 1),
            "generate": round(t2 - t1, 1),
            "save": round(t3 - t2, 1),
            "total": round(t3 - t0, 1),
        },
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "filename": os.path.basename(output_path),
    }
    
    meta_path = output_path.replace('.png', '.json').replace('.jpg', '.json')
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Load: {t1-t0:.1f}s | Generate: {t2-t1:.1f}s | Save: {t3-t2:.1f}s | Total: {t3-t0:.1f}s", file=sys.stderr)
    print(json.dumps(metadata, indent=2), file=sys.stderr)
    print(output_path)
    
    del pipe
    torch.cuda.empty_cache()
    
    return output_path, seed, metadata


def main():
    parser = argparse.ArgumentParser(description="Local SD generation with LoRA support")
    parser.add_argument("--prompt", "-p", required=False, default=None)
    parser.add_argument("--negative", "-n", default="")
    parser.add_argument("--model", "-m", default="dreamshaper_8")
    parser.add_argument("--steps", "-s", type=int, default=25)
    parser.add_argument("--guidance", "-g", type=float, default=7.5)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--width", "-W", type=int, default=512)
    parser.add_argument("--height", "-H", type=int, default=512)
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--scheduler", default="dpm++")
    parser.add_argument("--lora", action="append", help="LoRA name (can repeat)")
    parser.add_argument("--lora-weight", action="append", type=float, help="LoRA weight (matches --lora order)")
    parser.add_argument("--list-models", "-l", action="store_true")
    parser.add_argument("--list-loras", action="store_true")
    parser.add_argument("--json-input", "-j", help="Read params from JSON file")
    
    args = parser.parse_args()
    
    if args.list_models:
        for m in list_models():
            print(m)
        return
    
    if args.list_loras:
        for l in list_loras():
            print(l)
        return
    
    # Load from JSON if provided
    if args.json_input:
        with open(args.json_input) as f:
            params = json.load(f)
        prompt = params.get("prompt", "")
        negative = params.get("negative_prompt", "")
        model_name = params.get("model", "dreamshaper_8")
        steps = params.get("steps", 25)
        guidance = params.get("guidance", 7.5)
        seed = params.get("seed")
        width = params.get("width", 512)
        height = params.get("height", 512)
        output = params.get("output")
        lora_list = params.get("loras", [])
        loras = [(l["name"], l.get("weight", 0.7)) for l in lora_list]
    else:
        prompt = args.prompt
        negative = args.negative
        model_name = args.model
        steps = args.steps
        guidance = args.guidance
        seed = args.seed
        width = args.width
        height = args.height
        output = args.output
        
        # Build loras list from args
        loras = None
        if args.lora:
            loras = []
            for i, name in enumerate(args.lora):
                weight = args.lora_weight[i] if args.lora_weight and i < len(args.lora_weight) else 0.7
                loras.append((name, weight))
    
    if not prompt:
        print("Error: --prompt required", file=sys.stderr)
        sys.exit(1)
    
    generate(
        prompt=prompt,
        negative_prompt=negative,
        model_name=model_name,
        steps=steps,
        guidance=guidance,
        seed=seed,
        width=width,
        height=height,
        output_path=output,
        scheduler=args.scheduler,
        loras=loras,
    )


if __name__ == "__main__":
    main()
