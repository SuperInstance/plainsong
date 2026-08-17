#!/usr/bin/env python3
"""
Local image generation via diffusers + CUDA.
Loads SD 1.5 checkpoints from the Windows ComfyUI models folder.

Usage:
  python3 generate_image.py --prompt "a lighthouse on a cliff" --output /path/to/out.png
  python3 generate_image.py --prompt "..." --model dreamshaper_8 --steps 25 --guidance 7.5 --seed 42

The pipeline stays warm in memory if run as a server (future enhancement).
For now, each invocation loads, generates, and unloads.
"""

import argparse
import os
import sys
import time
import torch
from pathlib import Path

CHECKPOINT_DIR = "/mnt/c/Users/casey/Documents/ComfyUI/models/checkpoints"
DEFAULT_MODEL = "dreamshaper_8"
OUTPUT_DIR = os.path.expanduser("~/.openclaw/workspace/output/images")

def list_models():
    """List available checkpoint files."""
    models = []
    if os.path.isdir(CHECKPOINT_DIR):
        for f in sorted(os.listdir(CHECKPOINT_DIR)):
            if f.endswith(('.safetensors', '.ckpt')):
                name = f.replace('.safetensors', '').replace('.ckpt', '')
                models.append(name)
    return models

def generate(prompt, negative_prompt="", model_name=DEFAULT_MODEL, 
             steps=25, guidance=7.5, seed=None, width=512, height=512,
             output_path=None, scheduler="dpm++"):
    """Generate an image from a text prompt."""
    
    # Find the checkpoint file
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
    
    print(f"Loading model: {model_name} from {ckpt_path}", file=sys.stderr)
    t0 = time.time()
    
    # Load pipeline optimized for low VRAM (6GB RTX 4050)
    from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler
    
    pipe = StableDiffusionPipeline.from_single_file(
        ckpt_path,
        torch_dtype=torch.float16,
        safety_checker=None,  # We handle safety at the fleet level
        requires_safety_checker=False,
    )
    
    # Select scheduler
    if scheduler in ("dpm++", "dpmpp", "dpm"):
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    
    pipe = pipe.to("cuda")
    
    # Enable memory-efficient attention if available
    try:
        pipe.enable_xformers_memory_efficient_attention()
        print("xformers enabled", file=sys.stderr)
    except Exception:
        print("xformers not available, using default attention", file=sys.stderr)
    
    # Enable VAE tiling for low VRAM
    try:
        pipe.enable_vae_tiling()
        pipe.enable_sequential_cpu_offload()
        print("VAE tiling + CPU offload enabled", file=sys.stderr)
    except Exception as e:
        print(f"Offload note: {e}", file=sys.stderr)
    
    # Generate
    if seed is None:
        seed = torch.randint(0, 2**32 - 1, (1,)).item()
    
    print(f"Generating: '{prompt}'", file=sys.stderr)
    print(f"Steps={steps}, CFG={guidance}, Seed={seed}, Size={width}x{height}", file=sys.stderr)
    
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
    
    # Determine output path
    if not output_path:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        output_path = os.path.join(OUTPUT_DIR, f"gen-{timestamp}-s{seed}.png")
    
    image.save(output_path)
    t3 = time.time()
    
    print(f"Load: {t1-t0:.1f}s | Generate: {t2-t1:.1f}s | Save: {t3-t2:.1f}s | Total: {t3-t0:.1f}s", file=sys.stderr)
    print(f"Seed: {seed}", file=sys.stderr)
    
    # Output the path on stdout (for scripts to capture)
    print(output_path)
    
    # Clean up VRAM
    del pipe
    torch.cuda.empty_cache()
    
    return output_path, seed


def main():
    parser = argparse.ArgumentParser(description="Local SD image generation")
    parser.add_argument("--prompt", "-p", required=False, default=None, help="Text prompt")
    parser.add_argument("--negative", "-n", default="", help="Negative prompt")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL, help=f"Model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--steps", "-s", type=int, default=25, help="Inference steps")
    parser.add_argument("--guidance", "-g", type=float, default=7.5, help="CFG scale")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--width", "-W", type=int, default=512, help="Image width")
    parser.add_argument("--height", "-H", type=int, default=512, help="Image height")
    parser.add_argument("--output", "-o", default=None, help="Output file path")
    parser.add_argument("--list-models", "-l", action="store_true", help="List available models")
    parser.add_argument("--scheduler", default="dpm++", help="Scheduler (dpm++, euler, default)")
    
    args = parser.parse_args()
    
    if args.list_models:
        models = list_models()
        for m in models:
            print(m)
        return
    
    generate(
        prompt=args.prompt,
        negative_prompt=args.negative,
        model_name=args.model,
        steps=args.steps,
        guidance=args.guidance,
        seed=args.seed,
        width=args.width,
        height=args.height,
        output_path=args.output,
        scheduler=args.scheduler,
    )


if __name__ == "__main__":
    main()
