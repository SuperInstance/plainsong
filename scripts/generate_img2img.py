#!/usr/bin/env python3
"""
Generation script with img2img support.
Same as generate_image_v2.py but handles init_image + strength.
"""
import argparse, os, sys, time, json, torch
from PIL import Image

CHECKPOINT_DIR = "/mnt/c/Users/casey/Documents/ComfyUI/models/checkpoints"
LORA_DIR = "/mnt/c/Users/casey/Documents/ComfyUI/models/loras"
OUTPUT_DIR = os.path.expanduser("~/.openclaw/workspace/output/images/gallery")

def list_models():
    models = []
    if os.path.isdir(CHECKPOINT_DIR):
        for f in sorted(os.listdir(CHECKPOINT_DIR)):
            if f.endswith(('.safetensors', '.ckpt')): models.append(f.replace('.safetensors','').replace('.ckpt',''))
    return models

def generate(prompt, negative_prompt="", model_name="dreamshaper_8",
             steps=25, guidance=7.5, seed=None, width=512, height=512,
             output_path=None, scheduler="dpm++", loras=None,
             init_image=None, strength=0.6):
    
    from diffusers import StableDiffusionPipeline, StableDiffusionImg2ImgPipeline, DPMSolverMultistepScheduler
    
    ckpt_path = None
    for ext in ['.safetensors', '.ckpt']:
        candidate = os.path.join(CHECKPOINT_DIR, model_name + ext)
        if os.path.exists(candidate):
            ckpt_path = candidate
            break
    if not ckpt_path:
        print(f"Model '{model_name}' not found. Available: {', '.join(list_models())}", file=sys.stderr)
        sys.exit(1)
    
    t0 = time.time()
    
    pipe_class = StableDiffusionImg2ImgPipeline if init_image else StableDiffusionPipeline
    pipe = pipe_class.from_single_file(ckpt_path, torch_dtype=torch.float16, safety_checker=None, requires_safety_checker=False)
    
    if scheduler in ("dpm++", "dpmpp", "dpm"):
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    pipe = pipe.to("cuda")
    
    try: pipe.enable_xformers_memory_efficient_attention()
    except: pass
    try:
        pipe.vae.enable_tiling()
        pipe.enable_sequential_cpu_offload()
    except: pass
    
    loaded_loras = []
    if loras:
        for lora_name, weight in loras:
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
                    print(f"LoRA {lora_name} failed: {e}", file=sys.stderr)
    
    if seed is None:
        seed = torch.randint(0, 2**32 - 1, (1,)).item()
    
    t1 = time.time()
    
    if init_image:
        init_img = Image.open(init_image).convert("RGB")
        init_img = init_img.resize((width, height))
        print(f"Img2Img: {init_image} → {width}x{height}, strength={strength}", file=sys.stderr)
        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt if negative_prompt else None,
            num_inference_steps=steps,
            guidance_scale=guidance,
            generator=torch.Generator("cuda").manual_seed(seed),
            image=init_img,
            strength=strength,
        )
    else:
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
        output_path = os.path.join(OUTPUT_DIR, f"gen-{time.strftime('%Y%m%d-%H%M%S')}-s{seed}.png")
    
    image.save(output_path)
    t3 = time.time()
    
    metadata = {
        "prompt": prompt, "negative_prompt": negative_prompt,
        "model": model_name, "steps": steps, "guidance": guidance,
        "seed": seed, "width": width, "height": height,
        "scheduler": scheduler, "loras": loaded_loras,
        "init_image": init_image, "strength": strength,
        "timing": {"load": round(t1-t0,1), "generate": round(t2-t1,1), "save": round(t3-t2,1), "total": round(t3-t0,1)},
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "filename": os.path.basename(output_path),
    }
    
    with open(output_path.replace('.png','.json'), 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Load:{t1-t0:.1f}s Gen:{t2-t1:.1f}s Save:{t3-t2:.1f}s Total:{t3-t0:.1f}s", file=sys.stderr)
    print(output_path)
    
    del pipe
    torch.cuda.empty_cache()
    return output_path, seed

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prompt","-p",required=False,default=None)
    p.add_argument("--negative","-n",default="")
    p.add_argument("--model","-m",default="dreamshaper_8")
    p.add_argument("--steps","-s",type=int,default=25)
    p.add_argument("--guidance","-g",type=float,default=7.5)
    p.add_argument("--seed",type=int,default=None)
    p.add_argument("--width","-W",type=int,default=512)
    p.add_argument("--height","-H",type=int,default=512)
    p.add_argument("--output","-o",default=None)
    p.add_argument("--scheduler",default="dpm++")
    p.add_argument("--lora",action="append")
    p.add_argument("--lora-weight",action="append",type=float)
    p.add_argument("--init-image",default=None)
    p.add_argument("--strength",type=float,default=0.6)
    p.add_argument("--json-input","-j",default=None)
    args = p.parse_args()
    
    if args.json_input:
        with open(args.json_input) as f: params = json.load(f)
        generate(prompt=params.get("prompt",""), negative_prompt=params.get("negative_prompt",""),
                 model_name=params.get("model","dreamshaper_8"), steps=params.get("steps",25),
                 guidance=params.get("guidance",7.5), seed=params.get("seed"),
                 width=params.get("width",512), height=params.get("height",512),
                 output_path=params.get("output"), scheduler=params.get("scheduler","dpm++"),
                 loras=[(l["name"],l.get("weight",0.7)) for l in params.get("loras",[])],
                 init_image=params.get("init_image"), strength=params.get("strength",0.6))
    else:
        loras = None
        if args.lora:
            loras = []
            for i,name in enumerate(args.lora):
                w = args.lora_weight[i] if args.lora_weight and i < len(args.lora_weight) else 0.7
                loras.append((name,w))
        generate(prompt=args.prompt, negative_prompt=args.negative, model_name=args.model,
                 steps=args.steps, guidance=args.guidance, seed=args.seed,
                 width=args.width, height=args.height, output_path=args.output,
                 scheduler=args.scheduler, loras=loras,
                 init_image=args.init_image, strength=args.strength)

if __name__=="__main__": main()
