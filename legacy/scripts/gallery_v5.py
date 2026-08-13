#!/usr/bin/env python3
"""
Gallery v5 — Three-Panel Image Generation Studio
Left: Resident Artist Chat | Center: Gallery Grid | Right: Generation Params
Adds: AI artist chat, /api/chat, /api/artist-consult, model tiers, apply-to-generator.
Keeps all v4 features: gallery grid, albums, img2img, generation queue, cloud models.
"""

import os, sys, json, time, uuid, threading, subprocess, glob, traceback, base64, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

try:
    import requests as req_lib
except ImportError:
    req_lib = None

GALLERY_DIR = os.path.expanduser("~/.openclaw/workspace/output/images/gallery")
EXTRA_DIRS = [
    os.path.expanduser("~/.openclaw/workspace/output/images/tap-scenes"),
    os.path.expanduser("~/.openclaw/workspace/output/images"),
]
GEN_SCRIPT = os.path.expanduser("~/.openclaw/workspace/scripts/generate_img2img.py")
CLOUD_SCRIPT = os.path.expanduser("~/.openclaw/workspace/scripts/generate_cloud.py")
CHECKPOINT_DIR = "/mnt/c/Users/casey/Documents/ComfyUI/models/checkpoints"
LORA_DIR = "/mnt/c/Users/casey/Documents/ComfyUI/models/loras"
PORT = 5555

# Cloud models with real pricing (per 1024x1024 image)
CLOUD_MODELS = [
    {"id": "FLUX-1-schnell", "name": "FLUX-1-schnell ⚡", "price": "$0.0005/img", "cost": 0.0005},
    {"id": "sdxl-turbo", "name": "SDXL-Turbo ⚡", "price": "$0.0002/img", "cost": 0.0002},
    {"id": "FLUX-1-dev", "name": "FLUX-1-dev", "price": "$0.009/img", "cost": 0.009},
    {"id": "FLUX-2-klein-4b", "name": "FLUX-2-klein-4b", "price": "$0.014/img", "cost": 0.014},
    {"id": "FLUX-2-dev", "name": "FLUX-2-dev", "price": "$0.018/img", "cost": 0.018},
    {"id": "FLUX-1.1-pro", "name": "FLUX-1.1-pro ⭐", "price": "$0.04/img", "cost": 0.04},
    {"id": "FLUX-2-max", "name": "FLUX-2-max 💎", "price": "$0.07/img", "cost": 0.07},
]

# Artist chat models
ARTIST_MODELS = {
    "deepseek-flash":  {"label": "DeepSeek V4-Flash ⚡",     "endpoint": "https://api.deepseek.com/v1/chat/completions", "model": "deepseek-chat",      "provider": "deepseek",  "tier": "low",   "cost": "$0.001"},
    "seed-mini":       {"label": "Seed-2.0-mini ⚡",          "endpoint": "https://api.deepinfra.com/v1/openai/chat/completions", "model": "ByteDance/Seed-2.0-mini", "provider": "deepinfra", "tier": "low",   "cost": "~$0.002"},
    "qwen-35b":        {"label": "Qwen3.6-35B-A3B 🎯",       "endpoint": "https://api.deepinfra.com/v1/openai/chat/completions", "model": "Qwen/Qwen3.6-35B-A3B",  "provider": "deepinfra", "tier": "medium", "cost": "~$0.01"},
    "hermes-405b":     {"label": "Hermes-3-405B 🎯",          "endpoint": "https://api.deepinfra.com/v1/openai/chat/completions", "model": "NousResearch/Hermes-3-Llama-3.1-405B", "provider": "deepinfra", "tier": "medium", "cost": "~$0.02"},
    "deepseek-pro":    {"label": "DeepSeek V4-Pro 🧠",       "endpoint": "https://api.deepseek.com/v1/chat/completions", "model": "deepseek-reasoner",  "provider": "deepseek",  "tier": "high",  "cost": "~$0.03"},
    "nemotron-550b":   {"label": "Nemotron-3-Ultra-550B 🧠", "endpoint": "https://api.deepinfra.com/v1/openai/chat/completions", "model": "nvidia/Nemotron-3-Ultra-550B", "provider": "deepinfra", "tier": "high", "cost": "~$0.05"},
}

ARTIST_SYSTEM_PROMPT = (
    "You are a resident AI artist in a creative studio. You help the user craft image generation prompts, "
    "suggest models and LoRAs, and develop visual aesthetics. You can see what's in their gallery. "
    "When you suggest specific generation parameters, format them as a JSON block with: "
    "prompt, negative_prompt, model, steps, guidance, width, height, loras array. "
    "The user can click 'Apply' to push these to the generator. "
    "Be concise, creative, and passionate about art direction. Keep responses under 200 words unless asked for detail."
)

QUEUE_FILE = os.path.join(GALLERY_DIR, ".queue.json")
STATUS_FILE = os.path.join(GALLERY_DIR, ".gen-status.json")
UPLOAD_DIR = os.path.join(GALLERY_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALBUMS_DIR = os.path.expanduser("~/.openclaw/workspace/output/images")

# In-memory chat history
CHAT_HISTORY = []

# ─── Helpers ────────────────────────────────────────────────────────────────────

def list_albums():
    albums = []
    if os.path.isdir(ALBUMS_DIR):
        for d in sorted(os.listdir(ALBUMS_DIR)):
            full = os.path.join(ALBUMS_DIR, d)
            if os.path.isdir(full) and d != 'gallery':
                count = len(glob.glob(os.path.join(full, '*.png')))
                if count > 0:
                    albums.append({"name": d, "count": count, "path": full})
    return albums

def list_models():
    models = []
    if os.path.isdir(CHECKPOINT_DIR):
        for f in sorted(os.listdir(CHECKPOINT_DIR)):
            if f.endswith(('.safetensors', '.ckpt')):
                models.append(f.replace('.safetensors', '').replace('.ckpt', ''))
    return models

def list_loras():
    loras = []
    if os.path.isdir(LORA_DIR):
        for f in sorted(os.listdir(LORA_DIR)):
            if f.endswith(('.safetensors', '.ckpt')):
                loras.append(f.replace('.safetensors', '').replace('.ckpt', ''))
    return loras

def scan_gallery():
    items, seen = [], set()
    for d in [GALLERY_DIR] + EXTRA_DIRS:
        if not os.path.isdir(d):
            continue
        for ext in ('*.png', '*.jpg', '*.jpeg'):
            for img_path in sorted(glob.glob(os.path.join(d, ext)), reverse=True):
                if img_path in seen:
                    continue
                seen.add(img_path)
                meta = None
                mp = img_path.rsplit('.', 1)[0] + '.json'
                if os.path.exists(mp):
                    try:
                        with open(mp) as f:
                            meta = json.load(f)
                    except:
                        pass
                if not meta:
                    fname = os.path.basename(img_path)
                    gm = "unknown"
                    for m in list_models():
                        if m.lower() in fname.lower():
                            gm = m
                            break
                    meta = {"prompt": "", "negative_prompt": "", "model": gm, "steps": 25,
                            "guidance": 7.5, "seed": "", "width": 512, "height": 512,
                            "loras": [], "filename": fname}
                meta['_path'] = img_path
                meta['_serve'] = f"/image?path={img_path}"
                items.append(meta)
    return items

def get_gallery_context(limit=8):
    """Recent images for artist context."""
    items = scan_gallery()
    ctx = []
    for it in items[:limit]:
        ctx.append({
            "filename": it.get("filename", ""),
            "prompt": it.get("prompt", "")[:200],
            "model": it.get("model", ""),
            "loras": it.get("loras", []),
        })
    return ctx

def call_artist_model(model_key, messages):
    """Call the selected LLM for artist chat. Returns (text, error)."""
    if not req_lib:
        return "", "requests library not installed"
    cfg = ARTIST_MODELS.get(model_key)
    if not cfg:
        return "", f"Unknown model: {model_key}"
    api_key = None
    if cfg["provider"] == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_KEY_FROM_ENV")
    elif cfg["provider"] == "deepinfra":
        api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        return "", f"No API key for {cfg['provider']} (env var missing)"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "max_tokens": 1200,
        "temperature": 0.8,
    }
    try:
        resp = req_lib.post(cfg["endpoint"], headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return text, None
    except Exception as e:
        return "", f"API error: {e}"

def extract_params_json(text):
    """Try to extract a JSON params block from artist response."""
    # Look for ```json ... ``` blocks
    matches = re.findall(r'```(?:json)?\s*\n?(\{[^`]+\})\s*\n?```', text)
    if matches:
        for m in matches:
            try:
                p = json.loads(m)
                if "prompt" in p:
                    return p
            except:
                pass
    # Fallback: look for bare JSON object with "prompt" key
    matches = re.findall(r'\{[^{}]*"prompt"[^{}]*\}', text, re.DOTALL)
    if matches:
        for m in matches:
            try:
                p = json.loads(m)
                if "prompt" in p:
                    return p
            except:
                pass
    return None

# ─── Generation Worker ──────────────────────────────────────────────────────────

def generation_worker():
    while True:
        try:
            if not os.path.exists(QUEUE_FILE):
                time.sleep(2)
                continue
            with open(QUEUE_FILE) as f:
                queue = json.load(f)
            if not queue:
                time.sleep(2)
                continue
            job = queue.pop(0)
            with open(QUEUE_FILE, 'w') as f:
                json.dump(queue, f)
            with open(STATUS_FILE, 'w') as f:
                json.dump({"status": "generating", "job": job, "started": time.time()}, f)
            params = {
                "prompt": job.get("prompt") or "",
                "negative_prompt": job.get("negative_prompt") or "",
                "model": job.get("model") or "dreamshaper_8",
                "steps": int(job.get("steps") or 25),
                "guidance": float(job.get("guidance") or 7.5),
                "width": int(job.get("width") or 512),
                "height": int(job.get("height") or 512),
                "loras": job.get("loras") or [],
            }
            seed = job.get("seed")
            if seed is not None:
                params["seed"] = int(seed)
            strength = job.get("strength")
            if strength is not None:
                params["strength"] = float(strength)
            init_image = job.get("init_image")
            if init_image:
                params["init_image"] = init_image

            output_path = os.path.join(GALLERY_DIR, f"{int(time.time())}-{uuid.uuid4().hex[:6]}.png")
            model_name = params.get("model", "")
            is_cloud = model_name.startswith("cloud:")
            if is_cloud:
                cloud_model = model_name.replace("cloud:", "")
                cloud_params = {
                    "prompt": params["prompt"],
                    "model": cloud_model,
                    "negative_prompt": params.get("negative_prompt", ""),
                    "width": params.get("width", 1024),
                    "height": params.get("height", 1024),
                    "output": output_path,
                }
                params_file = output_path.replace('.png', '.params.json')
                with open(params_file, 'w') as f:
                    json.dump(cloud_params, f)
                cmd = ["python3", CLOUD_SCRIPT, "-p", params["prompt"], "-m", cloud_model,
                       "-W", str(params.get("width", 1024)), "-H", str(params.get("height", 1024)),
                       "-o", output_path]
                print(f"[Worker] Cloud: {cloud_model}", flush=True)
            else:
                params["output"] = output_path
                params_file = output_path.replace('.png', '.params.json')
                with open(params_file, 'w') as f:
                    json.dump(params, f)
                cmd = ["python3", GEN_SCRIPT, "--json-input", params_file]
                print(f"[Worker] Local: model={params['model']}, steps={params['steps']}, img2img={'yes' if init_image else 'no'}", flush=True)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                with open(STATUS_FILE, 'w') as f:
                    json.dump({"status": "done", "job": job, "finished": time.time(), "output": output_path}, f)
                print(f"[Worker] Done: {output_path}", flush=True)
            else:
                err = result.stderr[-500:] if result.stderr else "unknown"
                with open(STATUS_FILE, 'w') as f:
                    json.dump({"status": "error", "job": job, "error": err}, f)
                print(f"[Worker] Error: {err[-200:]}", flush=True)
            try:
                os.remove(params_file)
            except:
                pass
            time.sleep(1)
        except Exception as e:
            print(f"[Worker] Exception: {e}", flush=True)
            with open(STATUS_FILE, 'w') as f:
                json.dump({"status": "error", "job": {}, "error": str(e)}, f)
            time.sleep(2)

# ─── HTML Template ──────────────────────────────────────────────────────────────

HTML = r'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>🎨 Generation Studio v5</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#e0e0e0;font-family:system-ui,sans-serif;height:100vh;overflow:hidden;display:flex;flex-direction:column}

/* Header */
.hdr{background:#0d0d14;padding:8px 20px;border-bottom:1px solid #1e1e2e;display:flex;align-items:center;gap:16px;flex-shrink:0}
.hdr h1{font-size:15px;color:#7c8cf0}
.hdr .st{font-size:11px;color:#555}

/* Three-panel layout */
.main{display:flex;flex:1;overflow:hidden}

/* LEFT PANEL — Artist Chat */
.chat-panel{width:320px;flex-shrink:0;background:#0b0b12;border-right:1px solid #1e1e2e;display:flex;flex-direction:column;overflow:hidden}
.chat-header{padding:10px 12px;border-bottom:1px solid #1e1e2e;flex-shrink:0}
.chat-header h2{font-size:12px;color:#7c8cf0;margin-bottom:6px}
.chat-header select{width:100%;background:#06060c;border:1px solid #2a2a3e;color:#ccc;padding:5px 8px;border-radius:4px;font-size:11px}
.chat-header optgroup{color:#999;font-style:normal}
.chat-header option{color:#ccc;padding:2px}
.chat-messages{flex:1;overflow-y:auto;padding:8px 10px;display:flex;flex-direction:column;gap:8px}
.chat-msg{max-width:90%;padding:7px 11px;border-radius:11px;font-size:12px;line-height:1.45;word-wrap:break-word;white-space:pre-wrap}
.chat-msg.user{align-self:flex-end;background:#1a2a4e;color:#cde}
.chat-msg.artist{align-self:flex-start;background:#1e1e2e;color:#dcc}
.chat-msg.system{align-self:center;background:#1a1a0a;color:#aa8;font-size:10px;padding:3px 8px}
.chat-msg .msg-model{font-size:8px;color:#555;margin-top:3px;display:block}
.chat-msg pre{font-size:10px;white-space:pre-wrap;margin-top:4px;background:rgba(0,0,0,.3);padding:4px 6px;border-radius:4px}
.apply-btn{background:#2a4a1a;color:#8d8;border:1px solid #4a6;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:10px;margin-top:5px}
.apply-btn:hover{background:#3a5a2a;color:#afa}
.thinking{align-self:flex-start;background:#1e1e2e;color:#666;padding:8px 12px;border-radius:11px;font-size:12px;font-style:italic;animation:pulse 1.5s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:.5}50%{opacity:1}}
.chat-input-row{padding:8px 10px;border-top:1px solid #1e1e2e;display:flex;gap:6px;flex-shrink:0}
.chat-input-row input{flex:1;background:#06060c;border:1px solid #2a2a3e;color:#ccc;padding:7px 10px;border-radius:5px;font-size:12px}
.chat-input-row input:focus{outline:none;border-color:#7c8cf0}
.chat-input-row button{background:#7c8cf0;color:#fff;border:none;padding:7px 14px;border-radius:5px;cursor:pointer;font-size:12px;font-weight:600}
.chat-input-row button:hover{background:#6a7ae0}
.chat-input-row button:disabled{opacity:.4;cursor:default}
.clear-chat{background:none;border:none;color:#555;font-size:9px;cursor:pointer;text-decoration:underline;margin-top:4px}
.clear-chat:hover{color:#777}

/* CENTER — Gallery */
.gp{flex:1;overflow-y:auto;padding:14px}
.album-bar{display:flex;gap:8px;padding:6px 0 12px;flex-wrap:wrap;align-items:center}
.album-chip{background:#15152a;border:1px solid #2e2e4e;color:#777;padding:4px 12px;border-radius:14px;cursor:pointer;font-size:11px;transition:all .12s}
.album-chip:hover{border-color:#7c8cf0;color:#7c8cf0}
.album-chip.active{background:#1a1a3e;border-color:#7c8cf0;color:#9af}
.album-chip .count{font-size:9px;color:#555;margin-left:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}
.gi{background:#111;border-radius:6px;overflow:hidden;cursor:pointer;border:2px solid transparent;transition:all .12s;position:relative}
.gi:hover{transform:scale(1.04);border-color:#556}
.gi.active{border-color:#4a9}
.gi img{width:100%;aspect-ratio:1;object-fit:cover;display:block}
.gi .tag{position:absolute;bottom:0;left:0;right:0;background:rgba(0,0,0,.75);font-size:9px;padding:2px 4px;color:#9ad}
.gi .nb{position:absolute;top:4px;right:4px;background:#4a9;color:#000;font-size:8px;font-weight:bold;padding:1px 5px;border-radius:3px}
.gi .actions{position:absolute;top:4px;left:4px;display:none;gap:4px}
.gi:hover .actions{display:flex}
.gi .act-btn{background:rgba(0,0,0,.7);border:none;color:#ccc;width:24px;height:24px;border-radius:4px;cursor:pointer;font-size:12px}
.gi .act-btn:hover{background:rgba(40,40,60,.9)}
.gi .act-btn.del:hover{background:rgba(60,20,20,.9);color:#f77}

/* RIGHT PANEL — Params */
.cp{width:380px;flex-shrink:0;background:#0d0d14;border-left:1px solid #1e1e2e;overflow-y:auto;padding:16px}
.cp h2{font-size:13px;color:#7c8cf0;margin-bottom:12px}
.f{margin-bottom:10px}
.f label{display:block;font-size:10px;color:#666;text-transform:uppercase;margin-bottom:3px}
.f textarea,.f input,.f select{width:100%;background:#06060c;border:1px solid #1e1e2e;color:#ccc;padding:7px 9px;border-radius:5px;font-size:12px;font-family:inherit}
.f textarea{min-height:50px;resize:vertical}
.f input:focus,.f textarea:focus,.f select:focus{outline:none;border-color:#7c8cf0}
.fr{display:flex;gap:8px}
.fr .f{flex:1}
.lr{display:flex;gap:6px;align-items:center;margin-bottom:5px}
.lr select{flex:1;font-size:11px}
.lr input{width:50px;font-size:11px}
.lr b{background:#2a1a1a;color:#e55;width:22px;height:22px;border-radius:4px;cursor:pointer;border:none;font-size:10px}
.ab{background:#15152a;border:1px dashed #333;color:#777;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:11px}
.ab:hover{border-color:#7c8cf0;color:#7c8cf0}
.btn{background:#7c8cf0;color:#fff;border:none;padding:9px 18px;border-radius:5px;cursor:pointer;font-size:13px;font-weight:600}
.btn:hover{background:#6a7ae0}
.bg{background:#1a1a2a;color:#888}
.bg:hover{background:#2a2a3a;color:#ccc}
.br{display:flex;gap:8px;margin-top:14px}
.hint{font-size:10px;color:#444;margin-top:6px}

/* Status box */
.sb{position:fixed;bottom:14px;right:14px;background:#0d0d14;border:1px solid #333;padding:10px 16px;border-radius:6px;font-size:12px;display:none;z-index:500}
.sb.active{display:block}
.sb.gen{border-color:#7c8cf0}
.sb.done{border-color:#4a9}
.sb.err{border-color:#e55}

/* Drop zone for img2img */
.drop-zone{border:2px dashed #333;border-radius:6px;padding:12px;text-align:center;color:#555;font-size:11px;cursor:pointer;margin-bottom:6px}
.drop-zone:hover{border-color:#7c8cf0;color:#7c8cf0}
.drop-zone.dragover{border-color:#4a9;background:#0a1a0a}
.i2i-preview{max-width:100%;max-height:120px;border-radius:4px;margin-top:4px;display:none}
.i2i-preview.show{display:block}

/* Move dropdown */
.move-dd{position:fixed;background:#0d0d14;border:1px solid #333;border-radius:5px;padding:4px;z-index:50;display:none;min-width:120px}
.move-dd.active{display:block}
.move-dd div{padding:5px 10px;cursor:pointer;font-size:11px;color:#aaa;border-radius:3px}
.move-dd div:hover{background:#1a1a2e;color:#fff}

/* Lightbox */
.lightbox{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.92);z-index:999;display:none;justify-content:center;align-items:center;flex-direction:column}
.lightbox.active{display:flex}
.lightbox img{max-width:90vw;max-height:85vh;object-fit:contain;border-radius:4px}
.lightbox .lb-bar{margin-top:12px;display:flex;gap:10px}
.lightbox .lb-btn{background:#1a1a2a;color:#ccc;border:1px solid #333;padding:8px 16px;border-radius:5px;cursor:pointer;font-size:13px}
.lightbox .lb-btn:hover{background:#2a2a3a;color:#fff}
.lightbox .lb-btn.danger{background:#2a1a1a;color:#e55;border-color:#533}
.lightbox .lb-btn.danger:hover{background:#3a1a1a;color:#f77}
.lightbox .lb-close{position:absolute;top:16px;right:20px;font-size:28px;color:#666;cursor:pointer;background:none;border:none}
.lightbox .lb-close:hover{color:#fff}
.lightbox .lb-info{margin-top:8px;font-size:11px;color:#666;text-align:center;max-width:600px}

/* Scrollbars */
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:#0a0a0f}
::-webkit-scrollbar-thumb{background:#333;border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:#555}
</style>
</head>
<body>
<div class="hdr">
  <h1>🎨 Generation Studio v5</h1>
  <div class="st" id="stats">Loading...</div>
</div>
<div class="main">

  <!-- LEFT: Artist Chat -->
  <div class="chat-panel">
    <div class="chat-header">
      <h2>🧑‍🎨 Resident Artist</h2>
      <select id="artistModel">
        <optgroup label="⚡ LOW BUDGET">
          <option value="deepseek-flash">DeepSeek V4-Flash ($0.001)</option>
          <option value="seed-mini">Seed-2.0-mini (~$0.002)</option>
        </optgroup>
        <optgroup label="🎯 MEDIUM">
          <option value="qwen-35b">Qwen3.6-35B (~$0.01)</option>
          <option value="hermes-405b">Hermes-3-405B (~$0.02)</option>
        </optgroup>
        <optgroup label="🧠 HIGH END">
          <option value="deepseek-pro">DeepSeek V4-Pro (~$0.03)</option>
          <option value="nemotron-550b">Nemotron-550B (~$0.05)</option>
        </optgroup>
      </select>
      <button class="clear-chat" onclick="clearChat()">Clear conversation</button>
    </div>
    <div class="chat-messages" id="chatMsgs">
      <div class="chat-msg system">Artist session started. Ask for prompt ideas, art direction, or model suggestions!</div>
    </div>
    <div class="chat-input-row">
      <input type="text" id="chatInput" placeholder="Ask the artist..." onkeydown="if(event.key==='Enter')sendChat()">
      <button id="chatSend" onclick="sendChat()">Send</button>
    </div>
  </div>

  <!-- CENTER: Gallery -->
  <div class="gp">
    <div class="album-bar" id="albumBar"></div>
    <div class="grid" id="grid"></div>
  </div>

  <!-- RIGHT: Generation Params -->
  <div class="cp">
    <h2 id="ptitle">⚡ New Generation</h2>
    <div id="pc"></div>
  </div>

</div><!-- /main -->

<div class="sb" id="sbox"></div>

<!-- Lightbox -->
<div class="lightbox" id="lightbox">
  <button class="lb-close" onclick="closeLightbox()">&times;</button>
  <img id="lb-img" src="">
  <div class="lb-info" id="lb-info"></div>
  <div class="lb-bar">
    <button class="lb-btn" onclick="downloadCurrent()">💾 Save</button>
    <button class="lb-btn" onclick="loadFromLightbox()">📝 Edit</button>
    <button class="lb-btn danger" onclick="deleteFromLightbox()">🗑 Delete</button>
  </div>
</div>

<script>
const M=__MODELS__, L=__LORAS__;
const CM=__CLOUD_MODELS__;
let items=[], sel=-1, currentAlbum='all';
let uploadedImgData=null;
let pollTimer=null;
const BLANK={prompt:'',negative_prompt:'',model:M[0]||'dreamshaper_8',steps:25,guidance:7.5,seed:null,width:512,height:768,loras:[],strength:0.6,init_image:null,_blank:true};

// ─── Params Panel ─────────────────────────────────────────────────────────
function rp(it){
  const b=it._blank;
  let lh='';
  if(it.loras) it.loras.forEach(l=>{lh+=lr(l.name,l.weight)});
  document.getElementById('pc').innerHTML=`
    ${!b?'<div style="font-size:10px;color:#444;margin-bottom:10px;word-break:break-all">'+esc(it._path||'')+'</div>':''}
    <div class="f"><label>Prompt</label><textarea id="fP" placeholder="Describe what you want...">${esc(it.prompt||'')}</textarea></div>
    <div class="f"><label>Negative Prompt</label><textarea id="fN" placeholder="What to avoid...">${esc(it.negative_prompt||'')}</textarea></div>
    <div class="f"><label>Model</label><select id="fM"><optgroup label="─ Local (SD 1.5, Free) ─">${M.map(m=>'<option value="'+m+'"'+(m===it.model?' selected':'')+'>'+m+'</option>').join('')}</optgroup><optgroup label="─ DeepInfra Cloud ─">${CM.map(m=>'<option value="cloud:'+m.id+'"'+(('cloud:'+m.id)===it.model?' selected':'')+'>'+m.name+' ('+m.price+')</option>').join('')}</optgroup></select></div>
    <div class="fr"><div class="f"><label>Steps</label><input type="number" id="fS" value="${it.steps||25}"></div>
    <div class="f"><label>CFG</label><input type="number" step="0.5" id="fG" value="${it.guidance||7.5}"></div></div>
    <div class="fr"><div class="f"><label>Width</label><input type="number" id="fW" value="${it.width||512}" step="64"></div>
    <div class="f"><label>Height</label><input type="number" id="fH" value="${it.height||768}" step="64"></div>
    <div class="f"><label>Seed</label><input type="number" id="fSeed" value="${(it.seed&&!b)?it.seed:''}" placeholder="rand"></div></div>
    <div class="f">
      <label>Image-to-Image</label>
      <div class="drop-zone" id="dropZone" onclick="document.getElementById('fImg').click()">Drop image here or click to upload → use as starting point</div>
      <input type="file" id="fImg" accept="image/*" style="display:none" onchange="handleImg(this)">
      <img class="i2i-preview" id="fImgPreview">
      <div class="fr" style="margin-top:4px${!it.init_image?';display:none':''}">
        <div class="f"><label>Strength (0=keep, 1=ignore)</label><input type="range" id="fStr" min="0.1" max="1.0" step="0.05" value="${it.strength||0.6}" oninput="this.nextElementSibling.textContent=this.value"></div>
      </div>
    </div>
    <div class="f"><label>LoRAs</label><div id="lL">${lh}</div><button class="ab" onclick="addLora()">+ Add LoRA</button></div>
    <div class="br"><button class="btn" onclick="gen(false)">⚡ Generate</button><button class="btn bg" onclick="gen(true)">🎲 Variation</button></div>
    <div class="hint">${b?'Write a prompt and hit Generate. Add an image for img2img mode.':'Edit any field and Generate to remix. Variation = new random seed.'}</div>
  `;
  updateDropZone();
}
function lr(n,w){return '<div class="lr"><select>'+L.map(l=>'<option value="'+l+'"'+(l===n?' selected':'')+'>'+l+'</option>').join('')+'</select><input type="number" step="0.1" value="'+(w||0.7)+'"><b onclick="this.parentElement.remove()">✕</b></div>'}
function addLora(){const d=document.createElement('div');d.className='lr';d.innerHTML='<select><option value="">-- LoRA --</option>'+L.map(l=>'<option value="'+l+'">'+l+'</option>').join('')+'</select><input type="number" step="0.1" value="0.7"><b onclick="this.parentElement.remove()">✕</b>';document.getElementById('lL').appendChild(d)}

function handleImg(input){
  const file=input.files[0]; if(!file) return;
  const reader=new FileReader();
  reader.onload=e=>{
    uploadedImgData=e.target.result;
    const prev=document.getElementById('fImgPreview');
    prev.src=uploadedImgData; prev.classList.add('show');
    document.getElementById('dropZone').textContent='✓ '+file.name+' ('+Math.round(file.size/1024)+'KB) — click to change';
  };
  reader.readAsDataURL(file);
}
function updateDropZone(){
  const dz=document.getElementById('dropZone'); if(!dz) return;
  dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('dragover')});
  dz.addEventListener('dragleave',()=>dz.classList.remove('dragover'));
  dz.addEventListener('drop',e=>{
    e.preventDefault(); dz.classList.remove('dragover');
    if(e.dataTransfer.files.length){
      document.getElementById('fImg').files=e.dataTransfer.files;
      handleImg(document.getElementById('fImg'));
    }
  });
}
function params(){
  const ls=[];
  document.querySelectorAll('#lL .lr').forEach(r=>{const s=r.querySelector('select'),i=r.querySelector('input');if(s&&s.value&&i)ls.push({name:s.value,weight:parseFloat(i.value)})});
  const sv=document.getElementById('fSeed')?document.getElementById('fSeed').value:'';
  const str=document.getElementById('fStr')?parseFloat(document.getElementById('fStr').value):0.6;
  return{
    prompt:document.getElementById('fP').value,
    negative_prompt:document.getElementById('fN').value,
    model:document.getElementById('fM').value,
    steps:parseInt(document.getElementById('fS').value)||25,
    guidance:parseFloat(document.getElementById('fG').value)||7.5,
    seed:sv?parseInt(sv):null,
    width:parseInt(document.getElementById('fW').value)||512,
    height:parseInt(document.getElementById('fH').value)||768,
    loras:ls,strength:str,init_image:uploadedImgData
  };
}
function gen(v){
  let p=params(); if(v) p.seed=null;
  if(!p.prompt.trim()){alert('Write a prompt first!');return;}
  ssb('Uploading...','gen');
  fetch('/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)})
    .then(r=>r.json()).then(()=>{ssb('Queued! ~60s...','gen');uploadedImgData=null;setTimeout(poll,3000)})
    .catch(e=>{ssb('Error: '+e,'err');setTimeout(hsb,5000)});
}

// ─── Status polling ────────────────────────────────────────────────────────
let pollTimer=null;
async function poll(){
  try{
    const r=await fetch('/api/status');
    const d=await r.json();
    if(d.status==='generating'){ssb('⚙️ '+Math.round(Date.now()/1000-d.started)+'s','gen');pollTimer=setTimeout(poll,4000);}
    else if(d.status==='done'){ssb('✅ Done! Loading new image...','done');fetch('/api/reset-status',{method:'POST'});await load(true);setTimeout(hsb,2000);}
    else if(d.status==='error'){ssb('❌ '+(d.error||'').substring(0,100),'err');fetch('/api/reset-status',{method:'POST'});setTimeout(hsb,8000);}
  }catch(e){pollTimer=setTimeout(poll,5000);}
}
function ssb(m,t){const s=document.getElementById('sbox');s.textContent=m;s.className='sb active '+t}
function hsb(){document.getElementById('sbox').className='sb'}

// ─── Gallery load ──────────────────────────────────────────────────────────
async function load(mkNew){
  try{
    const r=await fetch('/api/gallery');
    const ni=await r.json();
    if(mkNew&&items.length){
      const op=new Set(items.map(i=>i._path));
      ni.forEach(i=>{if(!op.has(i._path))i._new=true});
    }
    items=ni;
    const g=document.getElementById('grid');g.innerHTML='';
    document.getElementById('stats').textContent=items.length+' images | '+new Set(items.map(i=>i.model)).size+' models';
    renderGrid(items);
  }catch(e){console.error('load error',e)}
}
function renderGrid(list){
  const g=document.getElementById('grid');g.innerHTML='';
  list.forEach((it)=>{
    const realIdx=items.indexOf(it);
    const d=document.createElement('div');
    d.className='gi'+(it._new?' nb':'')+(realIdx===sel?' active':'');
    d.onclick=()=>si(realIdx);
    d.ondblclick=()=>openLightbox(realIdx);
    const im=document.createElement('img');im.src=it._serve;im.loading='lazy';d.appendChild(im);
    const t=document.createElement('div');t.className='tag';t.textContent=(it.model||'?').substring(0,22);d.appendChild(t);
    const acts=document.createElement('div');acts.className='actions';
    const sv=document.createElement('button');sv.className='act-btn';sv.textContent='💾';sv.title='Save';sv.onclick=e=>{e.stopPropagation();downloadImage(realIdx)};
    const mv=document.createElement('button');mv.className='act-btn';mv.textContent='📁';mv.title='Move to album';mv.onclick=e=>{e.stopPropagation();showMoveMenu(e,realIdx)};
    const dl=document.createElement('button');dl.className='act-btn del';dl.textContent='🗑';dl.title='Delete';dl.onclick=e=>{e.stopPropagation();deleteImage(realIdx)};
    acts.appendChild(sv);acts.appendChild(mv);acts.appendChild(dl);d.appendChild(acts);
    g.appendChild(d);
  });
}
function si(idx){
  sel=idx;
  document.querySelectorAll('.gi').forEach((e)=>{e.className=e.className.replace(' active','')});
  document.querySelectorAll('.gi')[Array.from(document.querySelectorAll('.gi')).findIndex(e=>e===document.querySelectorAll('.gi')[idx])]?.classList.add('active');
  rp(items[idx]);
  document.getElementById('ptitle').textContent='📷 Loaded — Edit & Remix';
}
function esc(t){if(!t)return'';const d=document.createElement('div');d.textContent=t;return d.innerHTML}

// ─── Albums ────────────────────────────────────────────────────────────────
let albums=[];
async function loadAlbums(){
  try{
    const r=await fetch('/api/albums');
    albums=await r.json();
    renderAlbumBar();
  }catch(e){console.error('album load',e)}
}
function renderAlbumBar(){
  const bar=document.getElementById('albumBar'); if(!bar) return;
  let html='<div class="album-chip'+(currentAlbum==='all'?' active':'')+'" onclick="selectAlbum(\'all\')">📁 All <span class="count">('+items.length+')</span></div>';
  albums.forEach(a=>{
    html+='<div class="album-chip'+(currentAlbum===a.name?' active':'')+'" onclick="selectAlbum(\''+a.name+'\')">📁 '+a.name+' <span class="count">('+a.count+')</span></div>';
  });
  html+='<div class="album-chip'+(currentAlbum==='tap-scenes'?' active':'')+'" onclick="selectAlbum(\'tap-scenes\')">📁 tap-scenes</div>';
  html+='<div class="album-chip'+(currentAlbum==='gallery'?' active':'')+'" onclick="selectAlbum(\'gallery\')">📁 gallery</div>';
  bar.innerHTML=html;
}
function selectAlbum(name){
  currentAlbum=name;
  renderAlbumBar();
  const filtered = name==='all' ? items : items.filter(i => i._path.includes('/'+name+'/'));
  renderGrid(filtered);
}
function showMoveMenu(e,idx){
  const ex=document.querySelector('.move-dd'); if(ex) ex.remove();
  const dd=document.createElement('div');dd.className='move-dd active';
  dd.style.left=e.clientX+'px';dd.style.top=e.clientY+'px';
  let html=albums.map(a=>'<div onclick="moveToAlbum('+idx+',\''+a.name+'\')">📁 '+a.name+'</div>').join('');
  html+='<div onclick="moveToAlbum('+idx+',\'tap-scenes\')">📁 tap-scenes</div>';
  html+='<div onclick="createNewAlbum('+idx+')">+ New album...</div>';
  dd.innerHTML=html;
  document.body.appendChild(dd);
  setTimeout(()=>document.addEventListener('click',()=>dd.remove(),{once:true}),100);
}
async function moveToAlbum(idx,album){
  const it=items[idx]; if(!it) return;
  try{
    await fetch('/api/move-to-album',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:it._path,album})});
    await load(false); loadAlbums();
    ssb('Moved to '+album,'done'); setTimeout(hsb,2000);
  }catch(e){ssb('Move failed','err');setTimeout(hsb,3000)}
}
async function createNewAlbum(idx){
  const name=prompt('New album name:'); if(!name) return;
  await moveToAlbum(idx,name);
}

// ─── Lightbox ──────────────────────────────────────────────────────────────
let lbIdx=-1;
function openLightbox(idx){
  lbIdx=idx;
  const it=items[idx];
  document.getElementById('lb-img').src=it._serve;
  document.getElementById('lb-info').textContent=(it.model||'?')+' — '+(it.prompt||'').substring(0,120);
  document.getElementById('lightbox').classList.add('active');
}
function closeLightbox(){document.getElementById('lightbox').classList.remove('active');lbIdx=-1}
function loadFromLightbox(){if(lbIdx>=0){si(lbIdx);closeLightbox()}}
function downloadCurrent(){if(lbIdx>=0)downloadImage(lbIdx)}
function deleteFromLightbox(){if(lbIdx>=0){closeLightbox();deleteImage(lbIdx)}}
function downloadImage(idx){
  const it=items[idx];
  const a=document.createElement('a');a.href=it._serve;a.download=(it.filename||'image.png');
  document.body.appendChild(a);a.click();document.body.removeChild(a);
}
async function deleteImage(idx){
  const it=items[idx]; if(!it) return; if(!confirm('Delete this image? '+it.filename)) return;
  try{
    const r=await fetch('/api/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:it._path})});
    if(r.ok){
      fetch('/api/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:it._path.replace('.png','.json').replace('.jpg','.json')})});
      await load(false);
      ssb('Deleted','done');setTimeout(hsb,2000);
    }else{ssb('Delete failed','err');setTimeout(hsb,3000);}
  }catch(e){ssb('Delete error: '+e,'err');setTimeout(hsb,3000)}
}

// ─── ARTIST CHAT ───────────────────────────────────────────────────────────
let chatBusy=false;

async function sendChat(){
  const inp=document.getElementById('chatInput');
  const msg=inp.value.trim();
  if(!msg||chatBusy) return;
  const modelKey=document.getElementById('artistModel').value;
  const modelName=document.getElementById('artistModel').selectedOptions[0]?.text||modelKey;

  // Render user message
  addChatMsg('user',msg);
  inp.value='';

  // Thinking indicator
  const think=document.createElement('div');
  think.className='thinking';think.textContent='🎨 Artist is thinking...';
  think.id='thinkBubble';
  document.getElementById('chatMsgs').appendChild(think);
  scrollChat();

  chatBusy=true;
  document.getElementById('chatSend').disabled=true;

  try{
    const r=await fetch('/api/chat',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        message:msg,
        artist_model:modelKey,
        current_album:currentAlbum
      })
    });
    const d=await r.json();
    document.getElementById('thinkBubble')?.remove();
    if(d.error){
      addChatMsg('system','⚠️ Error: '+d.error);
    }else{
      addChatMsg('artist',d.response,modelName,d.params);
    }
  }catch(e){
    document.getElementById('thinkBubble')?.remove();
    addChatMsg('system','⚠️ Network error: '+e);
  }

  chatBusy=false;
  document.getElementById('chatSend').disabled=false;
}

function addChatMsg(role,text,modelName,params){
  const wrap=document.createElement('div');
  wrap.className='chat-msg '+role;
  let html=esc(text);
  if(modelName && role==='artist'){
    html+='<span class="msg-model">'+esc(modelName)+'</span>';
  }
  if(params){
    const pj=JSON.stringify(params,null,2);
    html+='<pre>'+esc(pj)+'</pre>';
    html+='<button class="apply-btn" onclick=\'applyParams('+JSON.stringify(JSON.stringify(params))+'\'>⬇ Apply to Generator</button>';
  }
  wrap.innerHTML=html;
  document.getElementById('chatMsgs').appendChild(wrap);
  scrollChat();
}

function scrollChat(){
  const el=document.getElementById('chatMsgs');
  el.scrollTop=el.scrollHeight;
}

function applyParams(pjson){
  try{
    const p=JSON.parse(pjson);
    // Map to generator fields
    const target={
      prompt:p.prompt||'',
      negative_prompt:p.negative_prompt||'',
      model:p.model||M[0]||'dreamshaper_8',
      steps:p.steps||25,
      guidance:p.guidance||7.5,
      seed:null,
      width:p.width||512,
      height:p.height||768,
      loras:p.loras||[],
      strength:0.6,
      init_image:null,
      _blank:false
    };
    rp(target);
    document.getElementById('ptitle').textContent='🎨 From Artist — Review & Generate';
    ssb('Applied artist params!','done');setTimeout(hsb,2000);
    // Visual feedback — flash right panel
    document.querySelector('.cp').style.borderColor='#4a9';
    setTimeout(()=>{document.querySelector('.cp').style.borderColor=''},1500);
  }catch(e){alert('Bad params: '+e)}
}

function clearChat(){
  if(!confirm('Clear all chat messages?'))return;
  document.getElementById('chatMsgs').innerHTML='<div class="chat-msg system">Conversation cleared.</div>';
  fetch('/api/chat-clear',{method:'POST'});
}

// ─── Init ──────────────────────────────────────────────────────────────────
rp(BLANK);
load();
loadAlbums();
setTimeout(poll,2000);

document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){
    sel=-1;rp(BLANK);
    document.getElementById('ptitle').textContent='⚡ New Generation';
    closeLightbox();
  }
});
</script>
</body></html>'''


# ─── HTTP Handler ───────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        p = parsed.path
        try:
            if p in ('/', '/index.html'):
                html = (HTML
                        .replace('__MODELS__', json.dumps(list_models()))
                        .replace('__LORAS__', json.dumps(list_loras()))
                        .replace('__CLOUD_MODELS__', json.dumps(CLOUD_MODELS)))
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(html.encode())

            elif p == '/api/gallery':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(scan_gallery()).encode())

            elif p == '/api/models':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(list_models()).encode())

            elif p == '/api/loras':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(list_loras()).encode())

            elif p == '/api/albums':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(list_albums()).encode())

            elif p == '/api/cloud-models':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(CLOUD_MODELS).encode())

            elif p == '/api/artist-models':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(ARTIST_MODELS).encode())

            elif p == '/api/status':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                if os.path.exists(STATUS_FILE):
                    self.wfile.write(open(STATUS_FILE).read().encode())
                else:
                    self.wfile.write(json.dumps({"status": "idle"}).encode())

            elif p == '/api/chat-history':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(CHAT_HISTORY).encode())

            elif p == '/image':
                params = parse_qs(parsed.query)
                img_path = params.get('path', [''])[0]
                if img_path and os.path.exists(img_path):
                    data = open(img_path, 'rb').read()
                    self.send_response(200)
                    ext = img_path.rsplit('.', 1)[-1].lower()
                    self.send_header('Content-Type', 'image/png' if ext == 'png' else 'image/jpeg')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_response(404)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            print(f"[GET err] {e}")
            self.send_response(500)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            cl = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(cl) if cl > 0 else b'{}'
            data = json.loads(body) if body else {}

            if parsed.path == '/api/generate':
                params = data
                # Handle base64 image upload
                if params.get('init_image', '') and not params['init_image'].startswith('/'):
                    img_data = params['init_image'].split(',')[1] if ',' in params['init_image'] else params['init_image']
                    img_name = f"upload-{int(time.time())}-{uuid.uuid4().hex[:6]}.png"
                    img_path = os.path.join(UPLOAD_DIR, img_name)
                    with open(img_path, 'wb') as f:
                        f.write(base64.b64decode(img_data))
                    params['init_image'] = img_path
                    print(f"[Upload] Saved: {img_path}", flush=True)
                queue = []
                if os.path.exists(QUEUE_FILE):
                    queue = json.load(open(QUEUE_FILE))
                queue.append(params)
                with open(QUEUE_FILE, 'w') as f:
                    json.dump(queue, f)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "position": len(queue)}).encode())

            elif parsed.path == '/api/reset-status':
                with open(STATUS_FILE, 'w') as f:
                    json.dump({"status": "idle"}, f)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode())

            elif parsed.path == '/api/delete':
                fpath = data.get('path', '')
                if fpath and os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                        print(f"[Delete] Removed: {fpath}", flush=True)
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({"ok": True}).encode())
                    except Exception as e:
                        self.send_response(500)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            elif parsed.path == '/api/move-to-album':
                src = data.get('path', '')
                album = data.get('album', '')
                if src and album and os.path.exists(src):
                    album_dir = os.path.join(ALBUMS_DIR, album)
                    os.makedirs(album_dir, exist_ok=True)
                    dst = os.path.join(album_dir, os.path.basename(src))
                    os.rename(src, dst)
                    sidecar = src.rsplit('.', 1)[0] + '.json'
                    if os.path.exists(sidecar):
                        dst_side = dst.rsplit('.', 1)[0] + '.json'
                        os.rename(sidecar, dst_side)
                    print(f"[Move] {src} → {dst}", flush=True)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True, "new_path": dst}).encode())
                else:
                    self.send_response(400)
                    self.end_headers()

            elif parsed.path == '/api/chat':
                # ─── Artist Chat Endpoint ───
                message = data.get('message', '')
                artist_model = data.get('artist_model', 'deepseek-flash')
                current_album = data.get('current_album', 'all')

                if not message.strip():
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Empty message"}).encode())
                    return

                # Build conversation context
                gallery_ctx = get_gallery_context(limit=6)
                gallery_summary = ""
                if gallery_ctx:
                    gallery_summary = "\n\nRecent gallery images:\n"
                    for i, g in enumerate(gallery_ctx):
                        gallery_summary += f"{i+1}. Model: {g['model']}, Prompt: \"{g['prompt'][:80]}...\"\n"

                # Build messages for the LLM
                history_msgs = [{"role": "system", "content": ARTIST_SYSTEM_PROMPT + gallery_summary}]

                # Add chat history (last 10 messages)
                for h in CHAT_HISTORY[-10:]:
                    role = "user" if h["role"] == "user" else "assistant"
                    history_msgs.append({"role": role, "content": h["text"]})

                # Add current message
                history_msgs.append({"role": "user", "content": message})

                # Call the model
                text, err = call_artist_model(artist_model, history_msgs)

                if err:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": err}).encode())
                else:
                    # Try to extract params JSON
                    extracted = extract_params_json(text)

                    # Save to in-memory history
                    CHAT_HISTORY.append({"role": "user", "text": message, "ts": time.time()})
                    CHAT_HISTORY.append({"role": "artist", "text": text, "model": artist_model, "params": extracted, "ts": time.time()})

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "response": text,
                        "params": extracted,
                        "model": artist_model
                    }).encode())

            elif parsed.path == '/api/chat-clear':
                CHAT_HISTORY.clear()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode())

            elif parsed.path == '/api/artist-consult':
                # ─── External Agent Consult Endpoint ───
                consult_prompt = data.get('prompt', '')
                consult_model = data.get('artist_model', 'deepseek-flash')
                album_context = data.get('album_context', True)

                if not consult_prompt.strip():
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Empty prompt"}).encode())
                    return

                gallery_ctx = get_gallery_context(limit=8) if album_context else []
                gallery_summary = ""
                if gallery_ctx:
                    gallery_summary = "\n\nCurrent gallery context:\n"
                    for i, g in enumerate(gallery_ctx):
                        gallery_summary += f"{i+1}. Model: {g['model']}, Prompt: \"{g['prompt'][:100]}\"\n"

                consult_system = (
                    ARTIST_SYSTEM_PROMPT + gallery_summary + "\n\n"
                    "An external agent is consulting you for art direction. Provide structured advice. "
                    "Always include a JSON params block with your recommendation."
                )

                msgs = [
                    {"role": "system", "content": consult_system},
                    {"role": "user", "content": consult_prompt}
                ]

                text, err = call_artist_model(consult_model, msgs)

                if err:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": err}).encode())
                else:
                    extracted = extract_params_json(text)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "advice": text,
                        "suggested_params": extracted,
                        "model": consult_model
                    }).encode())

            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            print(f"[POST err] {e}")
            traceback.print_exc()
            self.send_response(500)
            self.end_headers()

    def log_message(self, *a):
        pass


# ─── Main ───────────────────────────────────────────────────────────────────────

def load_keys():
    """Load API keys from bashrc if not in env."""
    bashrc = os.path.expanduser('~/.bashrc')
    if os.path.exists(bashrc):
        with open(bashrc) as f:
            for line in f:
                line = line.strip()
                if line.startswith('export ') and '=' in line:
                    parts = line.split('=', 1)
                    key_name = parts[0].replace('export ', '').strip()
                    key_val = parts[1].strip().strip('"').strip("'")
                    if key_name in ('DEEPSEEK_API_KEY', 'DEEPINFRA_API_KEY') and not os.environ.get(key_name):
                        os.environ[key_name] = key_val


def main():
    load_keys()
    os.makedirs(GALLERY_DIR, exist_ok=True)
    if os.path.exists(QUEUE_FILE):
        os.remove(QUEUE_FILE)
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, 'w') as f:
            json.dump({"status": "idle"}, f)

    # Check deps
    if not req_lib:
        print("⚠️  'requests' library not found — artist chat will not work.")
        print("   Install: pip install requests")

    threading.Thread(target=generation_worker, daemon=True).start()
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f"🎨 Studio v5 at http://localhost:{PORT}", flush=True)
    print(f"   {len(scan_gallery())} images | {len(list_models())} models | {len(list_loras())} LoRAs", flush=True)
    print(f"   Artist chat: {len(ARTIST_MODELS)} models available", flush=True)
    deepseek_key = bool(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_KEY_FROM_ENV"))
    deepinfra_key = bool(os.environ.get("DEEPINFRA_API_KEY"))
    print(f"   DeepSeek API: {'✅' if deepseek_key else '❌ no key'} | DeepInfra API: {'✅' if deepinfra_key else '❌ no key'}", flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
