#!/usr/bin/env python3
"""
Query the Plainsong feel-space: embed a piece (or a raw notation fragment) with
the real compiler, then find its nearest neighbors in Vectorize `plainsong-feel`.

Usage:
  python3 tools/query_feel.py <path-to-.song>            # nearest neighbors of a piece
  python3 tools/query_feel.py --inline "..."             # a notation fragment
  python3 tools/query_feel.py --by-id song-<digest>      # query by existing vector id
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from plainsong.notation import arrange, parse  # noqa: E402
from plainsong import features as F  # noqa: E402

ACCOUNT_ID = "049ff5e84ecf636b53b162cbb580aae6"
INDEX_NAME = "plainsong-feel"
QUERY_URL = (
    f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}"
    f"/vectorize/v2/indexes/{INDEX_NAME}/query"
)


def get_token() -> str:
    token = os.environ.get("CLOUDFLARE_API_TOKEN") or os.environ.get("CLOUDFLARE_TOKEN")
    if token:
        return token
    for path in (
        Path.home() / ".config/.wrangler/config/default.toml",
        Path.home() / ".wrangler/config/default.toml",
    ):
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line.startswith("oauth_token"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("No Cloudflare token found")


def to_vector(text: str, path: str = "") -> list[float]:
    arr = arrange(parse(text, path=path))
    bars = F.extract(arr)
    per_bar = [bar.vector for bar in bars]
    means = [sum(col) / len(col) for col in zip(*per_bar)]
    stds = [
        (sum((x - m) ** 2 for x in col) / len(col)) ** 0.5 if len(col) > 1 else 0.0
        for col, m in zip(zip(*per_bar), means)
    ]
    centroid = json.loads((Path(__file__).parent / "corpus-centroids.json").read_text())
    vec = [v - c for v, c in zip(means + stds, centroid)]
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 1e-9 else [0.0] * 32


def query(vector: list[float], token: str, top_k: int = 8) -> dict:
    # Vectorize REST /query accepts only {vector, topK} and returns id+score.
    payload = json.dumps({"vector": vector, "topK": top_k}).encode()
    req = urllib.request.Request(
        QUERY_URL,
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("--inline", default="")
    ap.add_argument("--by-id", default="")
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args()

    token = get_token()

    if args.by_id:
        # can't query by id directly via REST; fetch manifest and use its vector
        manifest = json.loads((Path(__file__).parent / "plainsong-feel-manifest.json").read_text())
        # manifest doesn't store vectors; re-embed from path
        entry = manifest.get(args.by_id)
        if not entry:
            print(f"unknown id {args.by_id}")
            return 1
        text = (REPO_ROOT / entry["path"]).read_text()
        vec = to_vector(text, entry["path"])
        label = entry["path"]
    elif args.inline:
        vec = to_vector(args.inline, "inline")
        label = "<inline>"
    elif args.path:
        p = Path(args.path)
        text = p.read_text()
        vec = to_vector(text, str(p))
        label = str(p)
    else:
        ap.error("give a path, --inline, or --by-id")

    result = query(vec, token, args.top)
    if not result.get("success"):
        print("query failed:", result.get("errors"))
        return 1

    # enrich scores with metadata from the local manifest (id -> title/key/collection)
    manifest = json.loads((Path(__file__).parent / "plainsong-feel-manifest.json").read_text())
    matches = result["result"]["matches"]
    print(f"query: {label}\nnearest {len(matches)} matches:")
    for m in matches:
        md = manifest.get(m["id"], {})
        print(
            f"  {m['score']:.4f}  {md.get('title','?'):<36} "
            f"[{md.get('collection','?')}]  {md.get('key','?')} {md.get('tempo','?')}bpm"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
