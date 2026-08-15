#!/usr/bin/env python3
"""
Gallery v4 — fixes: auto-refresh after generation, img2img support.
"""

import os, sys, json, time, uuid, threading, subprocess, glob, traceback, base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

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
QUEUE_FILE = os.path.join(GALLERY_DIR, ".queue.json")
STATUS_FILE = os.path.join(GALLERY_DIR, ".gen-status.json")
UPLOAD_DIR = os.path.join(GALLERY_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALBUMS_DIR = os.path.expanduser("~/.openclaw/workspace/output/images")

def list_albums():
    """List subdirectories that serve as albums."""
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
            if f.endswith(('.safetensors', '.ckpt')): models.append(f.replace('.safetensors','').replace('.ckpt',''))
    return models

def list_loras():
    loras = []
    if os.path.isdir(LORA_DIR):
        for f in sorted(os.listdir(LORA_DIR)):
            if f.endswith(('.safetensors', '.ckpt')): loras.append(f.replace('.safetensors','').replace('.ckpt',''))
    return loras

def scan_gallery():
    items, seen = [], set()
    for d in [GALLERY_DIR] + EXTRA_DIRS:
        if not os.path.isdir(d): continue
        for ext in ('*.png','*.jpg','*.jpeg'):
            for img_path in sorted(glob.glob(os.path.join(d, ext)), reverse=True):
                if img_path in seen: continue
                seen.add(img_path)
                meta = None
                mp = img_path.rsplit('.',1)[0]+'.json'
                if os.path.exists(mp):
                    try:
                        with open(mp) as f: meta = json.load(f)
                    except: pass
                if not meta:
                    fname = os.path.basename(img_path)
                    gm = "unknown"
                    for m in list_models():
                        if m.lower() in fname.lower(): gm = m; break
                    meta = {"prompt":"","negative_prompt":"","model":gm,"steps":25,"guidance":7.5,"seed":"","width":512,"height":512,"loras":[],"filename":fname}
                meta['_path']=img_path
                meta['_serve']=f"/image?path={img_path}"
                items.append(meta)
    return items

def generation_worker():
    while True:
        try:
            if not os.path.exists(QUEUE_FILE):
                time.sleep(2); continue
            with open(QUEUE_FILE) as f: queue = json.load(f)
            if not queue:
                time.sleep(2); continue
            job = queue.pop(0)
            with open(QUEUE_FILE,'w') as f: json.dump(queue, f)
            with open(STATUS_FILE,'w') as f: json.dump({"status":"generating","job":job,"started":time.time()}, f)
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
            if seed is not None: params["seed"] = int(seed)
            strength = job.get("strength")
            if strength is not None: params["strength"] = float(strength)
            init_image = job.get("init_image")
            if init_image: params["init_image"] = init_image
            
            output_path = os.path.join(GALLERY_DIR, f"{int(time.time())}-{uuid.uuid4().hex[:6]}.png")
            # Route to cloud or local script
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
                params_file = output_path.replace('.png','.params.json')
                with open(params_file,'w') as f: json.dump(cloud_params, f)
                cmd = ["python3", CLOUD_SCRIPT, "-p", params["prompt"], "-m", cloud_model,
                       "-W", str(params.get("width",1024)), "-H", str(params.get("height",1024)),
                       "-o", output_path]
                print(f"[Worker] Cloud: {cloud_model}", flush=True)
            else:
                params["output"] = output_path
                params_file = output_path.replace('.png','.params.json')
                with open(params_file,'w') as f: json.dump(params, f)
                cmd = ["python3", GEN_SCRIPT, "--json-input", params_file]
                print(f"[Worker] Local: model={params['model']}, steps={params['steps']}, img2img={'yes' if init_image else 'no'}", flush=True)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                with open(STATUS_FILE,'w') as f: json.dump({"status":"done","job":job,"finished":time.time(),"output":output_path}, f)
                print(f"[Worker] Done: {output_path}", flush=True)
            else:
                err = result.stderr[-500:] if result.stderr else "unknown"
                with open(STATUS_FILE,'w') as f: json.dump({"status":"error","job":job,"error":err}, f)
                print(f"[Worker] Error: {err[-200:]}", flush=True)
            try: os.remove(params_file)
            except: pass
            time.sleep(1)
        except Exception as e:
            print(f"[Worker] Exception: {e}", flush=True)
            with open(STATUS_FILE,'w') as f: json.dump({"status":"error","job":{},"error":str(e)}, f)
            time.sleep(2)

HTML = '''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>🎨 Generation Studio</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#e0e0e0;font-family:system-ui,sans-serif;height:100vh;overflow:hidden;display:flex;flex-direction:column}
.hdr{background:#0d0d14;padding:10px 20px;border-bottom:1px solid #1e1e2e;display:flex;align-items:center;gap:16px;flex-shrink:0}
.hdr h1{font-size:15px;color:#7c8cf0}
.hdr .st{font-size:11px;color:#555}
.main{display:flex;flex:1;overflow:hidden}
.gp{flex:1;overflow-y:auto;padding:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.gi{background:#111;border-radius:6px;overflow:hidden;cursor:pointer;border:2px solid transparent;transition:all .12s;position:relative}
.gi:hover{transform:scale(1.04);border-color:#556}
.gi.active{border-color:#4a9}
.gi img{width:100%;aspect-ratio:1;object-fit:cover;display:block}
.gi .tag{position:absolute;bottom:0;left:0;right:0;background:rgba(0,0,0,.75);font-size:9px;padding:2px 4px;color:#9ad}
.gi .nb{position:absolute;top:4px;right:4px;background:#4a9;color:#000;font-size:8px;font-weight:bold;padding:1px 5px;border-radius:3px}
.cp{width:400px;flex-shrink:0;background:#0d0d14;border-left:1px solid #1e1e2e;overflow-y:auto;padding:16px}
.cp h2{font-size:13px;color:#7c8cf0;margin-bottom:12px}
.f{margin-bottom:10px}
.f label{display:block;font-size:10px;color:#666;text-transform:uppercase;margin-bottom:3px}
.f textarea,.f input,.f select{width:100%;background:#06060c;border:1px solid #1e1e2e;color:#ccc;padding:7px 9px;border-radius:5px;font-size:12px;font-family:inherit}
.f textarea{min-height:100px;resize:vertical}
.f input:focus,.f textarea:focus,.f select:focus{outline:none;border-color:#7c8cf0}
.fr{display:flex;gap:8px}.fr .f{flex:1}
.lr{display:flex;gap:6px;align-items:center;margin-bottom:5px}
.lr select{flex:1;font-size:11px}.lr input{width:50px;font-size:11px}
.lr b{background:#2a1a1a;color:#e55;width:22px;height:22px;border-radius:4px;cursor:pointer;border:none;font-size:10px}
.ab{background:#15152a;border:1px dashed #333;color:#777;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:11px}
.ab:hover{border-color:#7c8cf0;color:#7c8cf0}
.btn{background:#7c8cf0;color:#fff;border:none;padding:9px 18px;border-radius:5px;cursor:pointer;font-size:13px;font-weight:600}
.btn:hover{background:#6a7ae0}
.bg{background:#1a1a2a;color:#888}.bg:hover{background:#2a2a3a;color:#ccc}
.br{display:flex;gap:8px;margin-top:14px}
.sb{position:fixed;bottom:14px;right:14px;background:#0d0d14;border:1px solid #333;padding:10px 16px;border-radius:6px;font-size:12px;display:none;z-index:500}
.sb.active{display:block}.sb.gen{border-color:#7c8cf0}.sb.done{border-color:#4a9}.sb.err{border-color:#e55}
.hint{font-size:10px;color:#444;margin-top:6px}
/* Album bar */
.album-bar{display:flex;gap:8px;padding:8px 14px;border-bottom:1px solid #1e1e2e;flex-wrap:wrap;align-items:center;background:#08080e}
.album-chip{background:#15152a;border:1px solid #2e2e4e;color:#777;padding:4px 12px;border-radius:14px;cursor:pointer;font-size:11px;transition:all .12s}
.album-chip:hover{border-color:#7c8cf0;color:#7c8cf0}
.album-chip.active{background:#1a1a3e;border-color:#7c8cf0;color:#9af}
.album-chip .count{font-size:9px;color:#555;margin-left:4px}
.move-dd{position:absolute;background:#0d0d14;border:1px solid #333;border-radius:5px;padding:4px;z-index:50;display:none;min-width:120px}
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
/* Save/Delete buttons on gallery items */
.gi .actions{position:absolute;top:4px;left:4px;display:none;gap:4px}
.gi:hover .actions{display:flex}
.gi .act-btn{background:rgba(0,0,0,.7);border:none;color:#ccc;width:24px;height:24px;border-radius:4px;cursor:pointer;font-size:12px}
.gi .act-btn:hover{background:rgba(40,40,60,.9)}
.gi .act-btn.del:hover{background:rgba(60,20,20,.9);color:#f77}
.i2i-preview{max-width:100%;max-height:120px;border-radius:4px;margin-top:4px;display:none}
.i2i-preview.show{display:block}
.i2i-row{display:flex;gap:8px;align-items:center}
.i2i-row input[type=file]{flex:1;font-size:11px}
.drop-zone{border:2px dashed #333;border-radius:6px;padding:12px;text-align:center;color:#555;font-size:11px;cursor:pointer;margin-bottom:6px}
.drop-zone:hover{border-color:#7c8cf0;color:#7c8cf0}
.drop-zone.dragover{border-color:#4a9;background:#0a1a0a}
</style>
</head>
<body>
<div class="hdr"><h1>🎨 Generation Studio</h1><div class="st" id="stats">Loading...</div></div>
<div class="main">
<div class="gp">
  <div class="album-bar" id="albumBar"></div>
  <div class="grid" id="grid"></div>
</div>
<div class="cp"><h2 id="ptitle">⚡ New Generation</h2><div id="pc"></div></div>
</div>
<div class="sb" id="sbox"></div>

<!-- Lightbox for fullscreen view -->
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
const M=__MODELS__,L=__LORAS__;
const CM=__CLOUD_MODELS__;
let items=[],sel=-1,currentAlbum='all';
const BLANK={prompt:'',negative_prompt:'',model:M[0]||'dreamshaper_8',steps:25,guidance:7.5,seed:null,width:512,height:768,loras:[],strength:0.6,init_image:null,_blank:true};

function rp(it){
  const b=it._blank;
  let lh='';
  if(it.loras)it.loras.forEach(l=>{lh+=lr(l.name,l.weight)});
  document.getElementById('pc').innerHTML=`
    ${!b?'<div style="font-size:10px;color:#444;margin-bottom:10px;word-break:break-all">'+esc(it._path||'')+'</div>':''}
    <div class="f"><label>Prompt</label><textarea id="fP" placeholder="Describe what you want...">${esc(it.prompt||'')}</textarea></div>
    <div class="f"><label>Negative Prompt</label><textarea id="fN" placeholder="What to avoid...">${esc(it.negative_prompt||'')}</textarea></div>
    <div class="f"><label>Model</label><select id="fM"><optgroup label="─ Local (SD 1.5, Free)─">${M.map(m=>'<option value="'+m+'"'+(m===it.model?' selected':'')+'>'+m+'</option>').join('')}</optgroup><optgroup label="─ DeepInfra Cloud ─">${CM.map(m=>'<option value="cloud:'+m.id+'"'+(('cloud:'+m.id)===it.model?' selected':'')+'>'+m.name+' ('+m.price+')</option>').join('')}</optgroup></select></div>
    <div class="fr"><div class="f"><label>Steps</label><input type="number" id="fS" value="${it.steps||25}"></div>
    <div class="f"><label>CFG</label><input type="number" step="0.5" id="fG" value="${it.guidance||7.5}"></div></div>
    <div class="fr"><div class="f"><label>Width</label><input type="number" id="fW" value="${it.width||512}" step="64"></div>
    <div class="f"><label>Height</label><input type="number" id="fH" value="${it.height||768}" step="64"></div>
    <div class="f"><label>Seed</label><input type="number" id="fSeed" value="${(it.seed&&!b)?it.seed:''}" placeholder="rand"></div></div>
    
    <div class="f">
      <label>Image-to-Image (modify an existing image)</label>
      <div class="drop-zone" id="dropZone" onclick="document.getElementById('fImg').click()">
        Drop image here or click to upload → use as starting point
      </div>
      <input type="file" id="fImg" accept="image/*" style="display:none" onchange="handleImg(this)">
      <img class="i2i-preview" id="fImgPreview">
      <div class="fr" style="margin-top:4px${!it.init_image?';display:none':''}">
        <div class="f"><label>Strength (0=keep image, 1=ignore)</label><input type="range" id="fStr" min="0.1" max="1.0" step="0.05" value="${it.strength||0.6}" oninput="this.nextElementSibling.textContent=this.value"></div>
      </div>
    </div>
    
    <div class="f"><label>LoRAs</label><div id="lL">${lh}</div><button class="ab" onclick="addLora()">+ Add LoRA</button></div>
    <div class="br"><label style="display:flex;align-items:center;gap:6px;font-size:11px;color:#888;cursor:pointer"><input type="checkbox" id="fAutofull" style="width:auto">Fullscreen on done</label><button class="btn" onclick="gen(false)">⚡ Generate</button><button class="btn bg" onclick="gen(true)">🎲 Variation</button></div>
    <div class="hint">${b?'Write a prompt and hit Generate. Add an image for img2img mode.':'Edit any field and Generate to remix. Variation = new random seed.'}</div>
  `;
  updateDropZone();
}
function lr(n,w){return '<div class="lr"><select>'+L.map(l=>'<option value="'+l+'"'+(l===n?' selected':'')+'>'+l+'</option>').join('')+'</select><input type="number" step="0.1" value="'+(w||0.7)+'"><b onclick="this.parentElement.remove()">✕</b></div>'}
function addLora(){const d=document.createElement('div');d.className='lr';d.innerHTML='<select><option value="">-- LoRA --</option>'+L.map(l=>'<option value="'+l+'">'+l+'</option>').join('')+'</select><input type="number" step="0.1" value="0.7"><b onclick="this.parentElement.remove()">✕</b>';document.getElementById('lL').appendChild(d)}
let uploadedImgData=null;
function handleImg(input){
  const file=input.files[0];
  if(!file)return;
  const reader=new FileReader();
  reader.onload=e=>{
    uploadedImgData=e.target.result;
    const prev=document.getElementById('fImgPreview');
    prev.src=uploadedImgData;prev.classList.add('show');
    document.getElementById('dropZone').textContent='✓ '+file.name+' ('+Math.round(file.size/1024)+'KB) — click to change';
  };
  reader.readAsDataURL(file);
}
function updateDropZone(){
  const dz=document.getElementById('dropZone');
  if(!dz)return;
  dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('dragover')});
  dz.addEventListener('dragleave',()=>dz.classList.remove('dragover'));
  dz.addEventListener('drop',e=>{
    e.preventDefault();dz.classList.remove('dragover');
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
    loras:ls,
    strength:str,
    init_image:uploadedImgData
  };
}
function gen(v){
  let p=params();
  if(v)p.seed=null;
  if(!p.prompt.trim()){alert('Write a prompt first!');return;}
  ssb('Uploading...','gen');
  fetch('/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)})
    .then(r=>r.json()).then(()=>{ssb('Queued! ~60s...','gen');uploadedImgData=null;setTimeout(poll,3000)})
    .catch(e=>{ssb('Error: '+e,'err');setTimeout(hsb,5000)});
}
let pollTimer=null;
async function poll(){
  try{
    const r=await fetch('/api/status');
    const d=await r.json();
    if(d.status==='generating'){
      ssb('⚙️ '+Math.round(Date.now()/1000-d.started)+'s','gen');
      pollTimer=setTimeout(poll,4000);
    }else if(d.status==='done'){
      ssb('✅ Done! Loading new image...','done');
      fetch('/api/reset-status',{method:'POST'});
      await load(true);
      // If fullscreen checkbox is checked, open the newest image in lightbox
      if(document.getElementById('fAutofull')&&document.getElementById('fAutofull').checked){
        // The newest image is items[0] after load(true) with mkNew badge
        setTimeout(()=>{if(items.length>0)openLightbox(0);},500);
      }
      setTimeout(hsb,2000);
    }else if(d.status==='error'){
      ssb('❌ '+(d.error||'').substring(0,100),'err');
      fetch('/api/reset-status',{method:'POST'});
      setTimeout(hsb,8000);
    }
  }catch(e){pollTimer=setTimeout(poll,5000)}
}
function ssb(m,t){const s=document.getElementById('sbox');s.textContent=m;s.className='sb active '+t}
function hsb(){document.getElementById('sbox').className='sb'}
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
    items.forEach((it,idx)=>{
      const d=document.createElement('div');
      d.className='gi'+(it._new?' nb':'')+(idx===sel?' active':'');
      d.onclick=()=>si(idx);
      d.ondblclick=()=>openLightbox(idx);
      const im=document.createElement('img');im.src=it._serve;im.loading='lazy';d.appendChild(im);
      const t=document.createElement('div');t.className='tag';t.textContent=(it.model||'?').substring(0,22);d.appendChild(t);
      // Save/delete buttons on hover
      const acts=document.createElement('div');acts.className='actions';
      const sv=document.createElement('button');sv.className='act-btn';sv.textContent='💾';sv.title='Save';sv.onclick=e=>{e.stopPropagation();downloadImage(idx);};
      const dl=document.createElement('button');dl.className='act-btn del';dl.textContent='🗑';dl.title='Delete';dl.onclick=e=>{e.stopPropagation();deleteImage(idx);};
      acts.appendChild(sv);acts.appendChild(dl);d.appendChild(acts);
      g.appendChild(d);
    });
  }catch(e){console.error('load error',e)}
}
function si(idx){
  sel=idx;
  document.querySelectorAll('.gi').forEach((e,i)=>{e.className=e.className.replace(' active','')+(i===idx?' active':'')});
  rp(items[idx]);
  document.getElementById('ptitle').textContent='📷 Loaded — Edit & Remix';
}
function esc(t){if(!t)return'';const d=document.createElement('div');d.textContent=t;return d.innerHTML}
rp(BLANK);
load();
loadAlbums();
setTimeout(poll,2000);

// === ALBUMS ===
let albums=[];
async function loadAlbums(){
  try{
    const r=await fetch('/api/albums');
    albums=await r.json();
    renderAlbumBar();
  }catch(e){console.error('album load',e)}
}
function renderAlbumBar(){
  const bar=document.getElementById('albumBar');
  if(!bar)return;
  let html='<div class="album-chip'+(currentAlbum==='all'?' active':'')+'" data-album="all">📁 All <span class="count">('+items.length+')</span></div>';
  albums.forEach(a=>{
    html+='<div class="album-chip'+(currentAlbum===a.name?' active':'')+'" data-album="'+a.name+'">📁 '+a.name+' <span class="count">('+a.count+')</span></div>';
  });
  html+='<div class="album-chip'+(currentAlbum==='tap-scenes'?' active':'')+'" data-album="tap-scenes">📁 tap-scenes</div>';
  html+='<div class="album-chip'+(currentAlbum==='gallery'?' active':'')+'" data-album="gallery">📁 gallery</div>';
  // Attach click handlers via data attribute (avoids quote escaping hell)
  bar.querySelectorAll('.album-chip').forEach(c=>{c.onclick=()=>selectAlbum(c.dataset.album);});
  bar.innerHTML=html;
}
function selectAlbum(name){
  currentAlbum=name;
  renderAlbumBar();
  // Filter items by directory
  const filtered = name==='all' ? items : items.filter(i => i._path.includes('/'+name+'/'));
  const g=document.getElementById('grid');g.innerHTML='';
  filtered.forEach((it,idx)=>{
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
function showMoveMenu(e,idx){
  const ex=document.querySelector('.move-dd');if(ex)ex.remove();
  const dd=document.createElement('div');dd.className='move-dd active';
  dd.style.left=e.clientX+'px';dd.style.top=e.clientY+'px';
  ['hermes','tap-scenes','avatars'].forEach(alb=>{
    const opt=document.createElement('div');
    opt.textContent='📁 '+alb;
    opt.onclick=()=>{dd.remove();moveToAlbum(idx,alb)};
    dd.appendChild(opt);
  });
  const neu=document.createElement('div');
  neu.textContent='+ New album...';
  neu.onclick=()=>{dd.remove();createNewAlbum(idx)};
  dd.appendChild(neu);
  document.body.appendChild(dd);
  setTimeout(()=>document.addEventListener('click',()=>dd.remove(),{once:true}),100);
}
async function moveToAlbum(idx,album){
  const it=items[idx];if(!it)return;
  try{
    await fetch('/api/move-to-album',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:it._path,album})});
    await load(false);loadAlbums();
    ssb('Moved to '+album,'done');setTimeout(hsb,2000);
  }catch(e){ssb('Move failed','err');setTimeout(hsb,3000)}
}
async function createNewAlbum(idx){
  const name=prompt('New album name:');
  if(!name)return;
  await moveToAlbum(idx,name);
}
document.addEventListener('keydown',e=>{if(e.key==='Escape'){sel=-1;rp(BLANK);document.getElementById('ptitle').textContent='⚡ New Generation';closeLightbox()}});

// === LIGHTBOX ===
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
  const a=document.createElement('a');
  a.href=it._serve;
  a.download=(it.filename||'image.png');
  document.body.appendChild(a);a.click();document.body.removeChild(a);
}
async function deleteImage(idx){
  const it=items[idx];
  if(!confirm('Delete this image? '+it.filename))return;
  try{
    const r=await fetch('/api/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:it._path})});
    if(r.ok){
      // Also delete sidecar JSON
      fetch('/api/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:it._path.replace('.png','.json').replace('.jpg','.json')})});
      await load(false);
      ssb('Deleted','done');setTimeout(hsb,2000);
    }else{
      ssb('Delete failed','err');setTimeout(hsb,3000);
    }
  }catch(e){ssb('Delete error: '+e,'err');setTimeout(hsb,3000)}
}
</script>
</body></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed=urlparse(self.path); p=parsed.path
        try:
            if p in ('/','/index.html'):
                html=HTML.replace('__MODELS__',json.dumps(list_models())).replace('__LORAS__',json.dumps(list_loras())).replace('__CLOUD_MODELS__',json.dumps(CLOUD_MODELS))
                self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
                self.wfile.write(html.encode())
            elif p=='/api/gallery':
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps(scan_gallery()).encode())
            elif p=='/api/models':
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps(list_models()).encode())
            elif p=='/api/loras':
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps(list_loras()).encode())
            elif p=='/api/albums':
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps(list_albums()).encode())
            elif p=='/api/cloud-models':
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps(CLOUD_MODELS).encode())
            elif p=='/api/status':
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                if os.path.exists(STATUS_FILE):
                    self.wfile.write(open(STATUS_FILE).read().encode())
                else:
                    self.wfile.write(json.dumps({"status":"idle"}).encode())
            elif p=='/image':
                params=parse_qs(parsed.query)
                img_path=params.get('path',[''])[0]
                if img_path and os.path.exists(img_path):
                    data=open(img_path,'rb').read()
                    self.send_response(200)
                    ext=img_path.rsplit('.',1)[-1].lower()
                    self.send_header('Content-Type','image/png' if ext=='png' else 'image/jpeg')
                    self.send_header('Content-Length',str(len(data)))
                    self.end_headers();self.wfile.write(data)
                else:
                    self.send_response(404);self.end_headers()
            else:
                self.send_response(404);self.end_headers()
        except Exception as e:
            print(f"[GET err] {e}");self.send_response(500);self.end_headers()

    def do_POST(self):
        parsed=urlparse(self.path)
        try:
            if parsed.path=='/api/generate':
                body=self.rfile.read(int(self.headers['Content-Length']))
                params=json.loads(body)
                # Handle base64 image upload
                if params.get('init_image','') and not params['init_image'].startswith('/'):
                    # It's base64 data — save to uploads
                    img_data=params['init_image'].split(',')[1] if ',' in params['init_image'] else params['init_image']
                    img_name=f"upload-{int(time.time())}-{uuid.uuid4().hex[:6]}.png"
                    img_path=os.path.join(UPLOAD_DIR,img_name)
                    with open(img_path,'wb') as f:
                        f.write(base64.b64decode(img_data))
                    params['init_image']=img_path
                    print(f"[Upload] Saved: {img_path}",flush=True)
                queue=[]
                if os.path.exists(QUEUE_FILE):
                    queue=json.load(open(QUEUE_FILE))
                queue.append(params)
                with open(QUEUE_FILE,'w') as f:json.dump(queue,f)
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps({"ok":True,"position":len(queue)}).encode())
            elif parsed.path=='/api/reset-status':
                with open(STATUS_FILE,'w') as f:
                    json.dump({"status":"idle"},f)
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps({"ok":True}).encode())
            elif parsed.path=='/api/delete':
                body=self.rfile.read(int(self.headers['Content-Length']))
                d=json.loads(body)
                fpath=d.get('path','')
                if fpath and os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                        print(f"[Delete] Removed: {fpath}",flush=True)
                        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                        self.wfile.write(json.dumps({"ok":True}).encode())
                    except Exception as e:
                        self.send_response(500);self.send_header('Content-Type','application/json');self.end_headers()
                        self.wfile.write(json.dumps({"ok":False,"error":str(e)}).encode())
                else:
                    self.send_response(404);self.end_headers()
            elif parsed.path=='/api/move-to-album':
                body=self.rfile.read(int(self.headers['Content-Length']))
                d=json.loads(body)
                src=d.get('path','')
                album=d.get('album','')
                if src and album and os.path.exists(src):
                    album_dir=os.path.join(ALBUMS_DIR, album)
                    os.makedirs(album_dir, exist_ok=True)
                    dst=os.path.join(album_dir, os.path.basename(src))
                    os.rename(src, dst)
                    # Move sidecar too
                    sidecar=src.rsplit('.',1)[0]+'.json'
                    if os.path.exists(sidecar):
                        dst_side=dst.rsplit('.',1)[0]+'.json'
                        os.rename(sidecar, dst_side)
                    print(f"[Move] {src} → {dst}",flush=True)
                    self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                    self.wfile.write(json.dumps({"ok":True,"new_path":dst}).encode())
                else:
                    self.send_response(400);self.end_headers()
            else:
                self.send_response(404);self.end_headers()
        except Exception as e:
            print(f"[POST err] {e}");self.send_response(500);self.end_headers()

    def log_message(self,*a):pass


def main():
    os.makedirs(GALLERY_DIR,exist_ok=True)
    if os.path.exists(QUEUE_FILE):os.remove(QUEUE_FILE)
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE,'w') as f:json.dump({"status":"idle"},f)
    threading.Thread(target=generation_worker,daemon=True).start()
    server=HTTPServer(('0.0.0.0',PORT),Handler)
    print(f"🎨 Studio v4 at http://localhost:{PORT}",flush=True)
    print(f"   {len(scan_gallery())} images | {len(list_models())} models | {len(list_loras())} LoRAs",flush=True)
    server.serve_forever()

if __name__=='__main__':main()
