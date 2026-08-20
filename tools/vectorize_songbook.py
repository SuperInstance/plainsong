#!/usr/bin/env python3
"""
Vectorize the Plainsong notation corpus → Cloudflare Vectorize + D1.

Walks every .song in the plainsong repo (songbook + examples + docs, skipping
legacy/), compiles each through the REAL compiler, extracts the 16 per-bar
features, and builds a 32-dim vector per piece:

    mean(16 features) ⊕ std(16 features)

(mean = average feel, std = internal contrast). Vectorize's dimension floor is
32, so the 16 features are used twice — still fully named, strictly richer than
the raw 16. L2-normalized so cosine = dot product.

Outputs:
  - plainsong-feel-manifest.json   local manifest (offline query + audit)
  - plainsong-songs.sql            D1 INSERT statements for the `songs` table
  - features-fixture.json          a few (note-data -> 16-vector) cases, for the
                                   TS port's byte-equality test
  - syncs vectors to Vectorize `plainsong-feel` via REST

Usage:  python3 tools/vectorize_songbook.py [--no-sync] [--limit N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# The plainsong package (this repo's root).
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from plainsong.notation import arrange, parse  # noqa: E402
from plainsong import features as F  # noqa: E402

ACCOUNT_ID = "049ff5e84ecf636b53b162cbb580aae6"
INDEX_NAME = "plainsong-feel"
VECTORIZE_BASE = (
    f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}"
    f"/vectorize/v2/indexes/{INDEX_NAME}"
)
BATCH_SIZE = 100

D1_DB_ID = "bb0cbc42-0397-4052-9299-cd423fe7113d"


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


def walk_corpus(root: Path) -> list[Path]:
    found: list[Path] = []
    for entry in sorted(root.rglob("*.song")):
        if "legacy" in entry.parts:
            continue
        found.append(entry)
    return found


def collection_of(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    # songbook/english/jazz/x.song -> english/jazz
    # docs/fakebook-archive/english/blues/x.song -> fakebook-archive/english/blues
    # examples/... -> examples
    parts = rel.split("/")
    if parts[0] == "songbook":
        return "/".join(parts[1:-1])
    if parts[0] == "examples":
        return "examples"
    if "fakebook-archive" in parts:
        idx = parts.index("fakebook-archive")
        return "/".join(parts[idx:-1])
    return parts[0] if len(parts) > 1 else "root"


def vectorize(text: str, path: str) -> tuple[dict, list[list[float]], list[dict]]:
    """Compile one piece and return (meta, per_bar_vectors, bar_notes_for_fixture)."""
    arr = arrange(parse(text, path=path))
    bars = F.extract(arr)
    per_bar = [bar.vector for bar in bars]
    meta = {
        "title": arr.meta.title or Path(path).stem,
        "key": arr.meta.key.name(),
        "mode": arr.meta.key.mode,
        "tempo": arr.meta.tempo,
        "meter": str(arr.meta.meter),
        "swing": arr.meta.swing,
        "subdivision": arr.meta.subdivision,
        "bars": len(bars),
        "notes": arr.note_count,
        "players": arr.meta if False else len(arr.tracks),
        "dialect": "absolute",  # parse() default; refine below
    }
    # bar note fixtures: the exact (note fields -> 16-vector) pairs the TS port must reproduce
    fixtures = [
        {
            "bar": bar.bar,
            "start": bar.start,
            "notes": [
                {
                    "start": round(n.start, 9),
                    "duration": round(n.duration, 9),
                    "pitch": n.pitch,
                    "velocity": n.velocity,
                    "voice": t.name,
                }
                for t in arr.tracks
                for n in t.notes
            ],
            "vector": bar.vector,
        }
        for bar in bars
    ]
    return meta, per_bar, fixtures


def to_vector(per_bar: list[list[float]], centroid: list[float]) -> list[float] | None:
    """mean(16) ⊕ std(16), centered against the corpus centroid, L2-normalized.

    Centering is load-bearing: raw cosine over chord-charts collapses to ~0.997
    (they all share the same 'this is a chord chart' DC signature — sustain≈1,
    rest≈0, syncopation≈0). Centered cosine spreads to mean ~0.18, sd ~0.72.
    None if no bars (nothing to embed).
    """
    if not per_bar:
        return None
    means = [statistics.mean(col) for col in zip(*per_bar)]
    stds = [statistics.pstdev(col) if len(per_bar) > 1 else 0.0 for col in zip(*per_bar)]
    vec = [v - c for v, c in zip(means + stds, centroid)]
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 1e-9:
        return None
    return [x / norm for x in vec]


def corpus_centroid(files: list[Path], root: Path) -> list[float]:
    """Two-pass step 1: the mean of every 32-dim vector over the corpus.

    Returns the per-dim mean of mean(16)⊕std(16) across all files. This is the
    centroid every vector gets centered against — the query side must use the
    exact same centroid, so it is persisted to corpus-centroids.json.
    """
    dims: list[list[float]] = [[] for _ in range(32)]
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            _, per_bar, _ = vectorize(path.read_text(encoding="utf-8", errors="replace"), rel)
        except Exception:  # noqa: BLE001
            continue
        if not per_bar:
            continue
        means = [statistics.mean(col) for col in zip(*per_bar)]
        stds = [statistics.pstdev(col) if len(per_bar) > 1 else 0.0 for col in zip(*per_bar)]
        for i, v in enumerate(means + stds):
            dims[i].append(v)
    return [statistics.mean(d) if d else 0.0 for d in dims]


def make_vector_id(path: str) -> str:
    return "song-" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def api_post(url: str, token: str, vectors: list, retries: int = 4) -> bool:
    payload = json.dumps({"vectors": vectors}).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if not result.get("success"):
                    print(f"    ⚠️  API errors: {result.get('errors')}")
                    return False
                return True
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 429:
                wait = min(2 ** attempt * 5, 60)
                print(f"    ⏳ 429, backing off {wait}s")
                time.sleep(wait)
                continue
            print(f"    ⚠️  HTTP {e.code}: {body[:200]}")
            return False
        except urllib.error.URLError as e:
            print(f"    ⚠️  URLError: {e}")
            time.sleep(2)
    return False


def sql_escape(s: str) -> str:
    return s.replace("'", "''")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sync", action="store_true", help="skip Vectorize sync")
    ap.add_argument("--limit", type=int, default=0, help="only process first N files")
    ap.add_argument("--recompute-centroid", action="store_true", help="recompute corpus centroid (else load from disk)")
    args = ap.parse_args()

    root = REPO_ROOT
    files = walk_corpus(root)
    if args.limit:
        files = files[: args.limit]
    print(f"corpus: {len(files)} .song files")

    out_dir = Path(__file__).resolve().parent
    centroid_path = out_dir / "corpus-centroids.json"
    if centroid_path.exists() and not args.recompute_centroid:
        centroid = json.loads(centroid_path.read_text())
        print(f"loaded corpus centroid ({len(centroid)} dims) from {centroid_path}")
    else:
        print("computing corpus centroid (two-pass step 1)…")
        centroid = corpus_centroid(files, root)
        centroid_path.write_text(json.dumps(centroid, ensure_ascii=False, indent=1))
        print(f"  centroid saved to {centroid_path}")

    manifest: dict[str, dict] = {}
    sql_lines: list[str] = []
    fixture_export: dict = {"songs": []}
    vectors_batch: list[dict] = []
    errors: list[str] = []
    skipped: int = 0

    token = None if args.no_sync else get_token()

    for i, path in enumerate(files):
        rel = path.relative_to(root).as_posix()
        try:
            meta, per_bar, fixtures = vectorize(path.read_text(encoding="utf-8", errors="replace"), rel)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{rel}: {type(e).__name__}: {e}")
            continue
        vec = to_vector(per_bar, centroid)
        if vec is None:
            skipped += 1
            continue
        vid = make_vector_id(rel)
        entry = {
            "id": vid,
            "path": rel,
            "collection": collection_of(path, root),
            **meta,
            "vector": vec,
        }
        manifest[vid] = {k: v for k, v in entry.items() if k != "vector"}

        # D1 INSERT (title, path, key, tempo, meter, collection, bars, notes)
        sql_lines.append(
            "INSERT INTO songs (id, path, title, key, tempo, meter, collection, bars, notes) "
            f"VALUES ('{vid}', '{sql_escape(rel)}', '{sql_escape(meta['title'])}', "
            f"'{sql_escape(meta['key'])}', {meta['tempo']:g}, '{sql_escape(meta['meter'])}', "
            f"'{sql_escape(entry['collection'])}', {meta['bars']}, {meta['notes']});"
        )

        # Vectorize upsert (metadata is flat scalars; strip non-scalar keys)
        metadata = {
            "path": rel,
            "title": meta["title"],
            "key": meta["key"],
            "mode": meta["mode"],
            "tempo": meta["tempo"],
            "meter": meta["meter"],
            "collection": entry["collection"],
            "bars": meta["bars"],
            "notes": meta["notes"],
        }
        vectors_batch.append({"id": vid, "values": vec, "metadata": metadata})

        # Keep a few fixtures for the TS port test (first 3 songs, first 3 bars each)
        if len(fixture_export["songs"]) < 3:
            fixture_export["songs"].append(
                {"path": rel, "bars": fixtures[:3]}
            )

        if len(vectors_batch) >= BATCH_SIZE:
            if token and not args.no_sync:
                ok = api_post(f"{VECTORIZE_BASE}/insert", token, vectors_batch)
                print(f"  synced batch of {len(vectors_batch)} (ok={ok})")
            vectors_batch = []

        if (i + 1) % 500 == 0:
            print(f"  …{i + 1} processed, {len(manifest)} embedded, {len(errors)} errors")

    # final batch
    if vectors_batch and token and not args.no_sync:
        ok = api_post(f"{VECTORIZE_BASE}/insert", token, vectors_batch)
        print(f"  final batch of {len(vectors_batch)} (ok={ok})")

    out_dir = Path(__file__).resolve().parent
    manifest_path = out_dir / "plainsong-feel-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    sql_path = out_dir / "plainsong-songs.sql"
    sql_path.write_text("\n".join(sql_lines) + "\n")
    fixture_path = out_dir / "features-fixture.json"
    fixture_path.write_text(json.dumps(fixture_export, ensure_ascii=False, indent=1))

    print(f"\nembedded: {len(manifest)}  skipped(no bars): {skipped}  errors: {len(errors)}")
    if errors:
        print("first errors:")
        for e in errors[:10]:
            print("  -", e)
    print(f"manifest -> {manifest_path}")
    print(f"sql      -> {sql_path}")
    print(f"fixture  -> {fixture_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
