#!/usr/bin/env python3
"""
Discover nearest-neighbor "feel" edges → D1 `edges` table (kind='discovered').

Builds the kNN graph of the plainsong feel-space: for every song in
plainsong-feel-manifest.json, embed it with the REAL compiler pipeline
(same code path as the indexer — imported, not duplicated), query the
Cloudflare Vectorize index `plainsong-feel` for its top-K neighbors, and
write undirected edges (from_song < to_song, score = cosine similarity)
into the D1 `edges` table.

Edges are canonicalized (from_song < to_song) so the UNIQUE(from_song,to_song)
constraint dedupes reciprocal hits; self-edges are skipped.

⚠️  Index consistency guard (a real bug found 2026-08-19): the Vectorize index
had been populated by an EARLIER, *uncentered* version of the embedding pass —
the final centered sync never landed (self-matches came back at ~0.35 instead
of ~1.0, and raw uncentered vectors self-matched at exactly 1.0). Before
discovering, this script probes a sample of songs; if the index does not match
the current deterministic embedding, it repairs the index by upserting the
recomputed vectors (64 batches, ~1 min) and re-probes. Pass --no-resync to skip.

Outputs:
  - edges rows in D1 (kind='discovered')
  - tools/plainsong-discovered-edges.json   audit artifact (id pairs + scores)
  - tools/edges-queries-cache.jsonl         resumable per-song query cache

Usage: python3 tools/discover_edges.py [--top-k 8] [--workers 5] [--limit N]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Reuse the indexer's exact embedding math, token handling, and constants —
# importing guarantees discovery queries are byte-identical to what was indexed.
from vectorize_songbook import (  # noqa: E402
    BATCH_SIZE,
    D1_DB_ID,
    INDEX_NAME,
    VECTORIZE_BASE,
    get_token,
    to_vector,
    vectorize,
)

ACCOUNT_ID = VECTORIZE_BASE.split("/accounts/")[1].split("/")[0]
D1_QUERY_URL = (
    f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}"
    f"/d1/database/{D1_DB_ID}/query"
)

QUERY_URL = f"{VECTORIZE_BASE}/query"
UPSERT_URL = f"{VECTORIZE_BASE}/upsert"
SONG_ID_RE = re.compile(r"^song-[0-9a-f]{16}$")

_token_lock = threading.Lock()


def current_token() -> str:
    return get_token()


def refresh_token_via_wrangler() -> str:
    """Force wrangler to refresh its OAuth token, then re-read it."""
    import shutil

    wrangler = shutil.which("wrangler") or str(
        Path.home() / ".npm-global/bin/wrangler"
    )
    try:
        subprocess.run([wrangler, "whoami"], capture_output=True, timeout=120, check=False)
    except Exception as e:  # noqa: BLE001
        print(f"    (wrangler refresh failed: {e})")
    return get_token()


def api_post(
    url: str,
    payload: dict,
    timeout: int = 90,
    retries: int = 6,
) -> dict | None:
    """POST JSON to a Cloudflare API endpoint with 429/401 handling.

    429 → exponential backoff (5s,10s,20s… capped 60s).
    401 → re-read the wrangler OAuth token (refreshing via wrangler if stale).
    Returns parsed JSON or None on hard failure.
    """
    body = json.dumps(payload).encode("utf-8")
    token = current_token()
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            if e.code == 429:
                wait = min(2**attempt * 5, 60)
                print(f"    ⏳ 429, backing off {wait}s")
                time.sleep(wait)
                continue
            if e.code == 401:
                with _token_lock:
                    token = refresh_token_via_wrangler()
                continue
            print(f"    ⚠️  HTTP {e.code}: {raw[:200]}")
            return None
        except urllib.error.URLError as e:
            print(f"    ⚠️  URLError: {e}")
            time.sleep(min(2**attempt, 30))
    return None


# ---------------------------------------------------------------- embedding


def embed_corpus(manifest: dict, limit: int = 0) -> dict[str, list[float]]:
    """Deterministically re-embed every manifest song (compile → 32-dim vector)."""
    centroid = json.loads(
        (Path(__file__).resolve().parent / "corpus-centroids.json").read_text()
    )
    vectors: dict[str, list[float]] = {}
    items = list(manifest.items())
    if limit:
        items = items[:limit]
    t0 = time.time()
    for i, (vid, entry) in enumerate(items):
        text = (REPO_ROOT / entry["path"]).read_text(encoding="utf-8", errors="replace")
        try:
            _, per_bar, _ = vectorize(text, entry["path"])
        except Exception as e:  # noqa: BLE001
            print(f"    ⚠️ embed failed {entry['path']}: {type(e).__name__}: {e}")
            continue
        vec = to_vector(per_bar, centroid)
        if vec is not None:
            vectors[vid] = vec
        if (i + 1) % 1000 == 0:
            rate = (i + 1) / (time.time() - t0)
            print(f"  embedded {i + 1}/{len(items)} ({rate:.0f}/s)")
    return vectors


# ------------------------------------------------------- index consistency


def query_index(vector: list[float], top_k: int) -> list[dict]:
    res = api_post(QUERY_URL, {"vector": vector, "topK": top_k}, timeout=60)
    if res is None or not res.get("success"):
        return []
    return res["result"]["matches"]


def probe_index(vectors: dict, manifest: dict, n: int = 6) -> bool:
    """Healthy ⇔ each sampled song is its own top-1 match at ~1.0 cosine."""
    import random

    sample = random.sample(list(vectors), min(n, len(vectors)))
    ok = 0
    for vid in sample:
        matches = query_index(vectors[vid], 5)
        if matches and matches[0]["id"] == vid and matches[0]["score"] > 0.999:
            ok += 1
        else:
            top = (
                f"{matches[0]['id']} @{matches[0]['score']:.4f}" if matches else "none"
            )
            print(f"    probe miss: {manifest[vid]['title']!r} top1={top}")
    print(f"  index probe: {ok}/{len(sample)} self-matches at ~1.0")
    return ok == len(sample)


def ensure_synced(vectors: dict, manifest: dict) -> bool:
    """Verify the Vectorize index matches the current embedding; repair if not.

    Vectorize is eventually consistent: after an upsert, query replicas can
    serve stale vectors for a while, so we poll the probe for up to ~3 min.
    """
    if probe_index(vectors, manifest):
        return True
    print("  ⚠️ index does NOT match current embedding — upserting full corpus…")
    batch = []
    ids = list(vectors)
    for i, vid in enumerate(ids):
        e = manifest[vid]
        metadata = {
            "path": e["path"],
            "title": e["title"],
            "key": e["key"],
            "mode": e["mode"],
            "tempo": e["tempo"],
            "meter": e["meter"],
            "collection": e["collection"],
            "bars": e["bars"],
            "notes": e["notes"],
        }
        batch.append({"id": vid, "values": vectors[vid], "metadata": metadata})
        if len(batch) >= BATCH_SIZE:
            res = api_post(UPSERT_URL, {"vectors": batch})
            ok = bool(res and res.get("success"))
            print(f"  upserted {i + 1}/{len(ids)} (ok={ok})")
            if not ok:
                return False
            batch = []
    if batch:
        res = api_post(UPSERT_URL, {"vectors": batch})
        if not (res and res.get("success")):
            return False
        print(f"  upserted {len(ids)}/{len(ids)} (final batch)")
    print("  upsert complete — polling probe (eventual consistency)…")
    for wait in (10, 15, 20, 30, 30, 30, 45, 45):
        time.sleep(wait)
        if probe_index(vectors, manifest):
            return True
        print(f"    still stale — retrying ({wait}s waited)")
    return False


# ---------------------------------------------------------------- discovery


def discover_edges(
    vectors: dict,
    manifest: dict,
    top_k: int,
    workers: int,
    cache_path: Path,
    min_score: float = 0.0,
) -> dict[tuple[str, str], float]:
    """Query every song's neighbors; return {(a,b): score} with a<b (undirected)."""
    done: set[str] = set()
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["q"])
        print(f"  resuming: {len(done)} songs already queried (cache)")

    todo = [v for v in vectors if v not in done]
    print(f"  querying Vectorize for {len(todo)} songs "
          f"(topK={top_k + 1}, workers={workers})…")

    edges: dict[tuple[str, str], float] = {}
    cache_lock = threading.Lock()
    counter = {"n": 0, "fails": 0}
    t0 = time.time()

    def work(vid: str) -> None:
        matches = query_index(vectors[vid], top_k + 1)  # +1: self may lead
        rec = {
            "q": vid,
            "matches": [
                [m["id"], m["score"]] for m in matches if m["id"] != vid
            ][:top_k],
        }
        if not rec["matches"] and not matches:
            counter["fails"] += 1
        with cache_lock:
            with cache_path.open("a") as fh:
                fh.write(json.dumps(rec) + "\n")
            for nid, score in rec["matches"]:
                if score < min_score:
                    continue
                a, b = (vid, nid) if vid < nid else (nid, vid)
                key = (a, b)
                if key not in edges or score > edges[key]:
                    edges[key] = score
            counter["n"] += 1
            if counter["n"] % 500 == 0:
                rate = counter["n"] / (time.time() - t0)
                print(f"  …{counter['n']}/{len(todo)} queries "
                      f"({rate:.0f}/s, {len(edges)} edges)")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, todo))

    print(f"  queries done: {counter['n']}, failed: {counter['fails']}, "
          f"undirected edges: {len(edges)}")
    return edges


def merge_cache_edges(cache_path: Path, min_score: float) -> dict[tuple[str, str], float]:
    """Rebuild the edge map from the cache (for --verify-only / resume)."""
    edges: dict[tuple[str, str], float] = {}
    for line in cache_path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        for nid, score in rec["matches"]:
            if score < min_score:
                continue
            a, b = (rec["q"], nid) if rec["q"] < nid else (nid, rec["q"])
            if (a, b) not in edges or score > edges[(a, b)]:
                edges[(a, b)] = score
    return edges


# ------------------------------------------------------------------- D1 I/O


def d1_execute(sql: str) -> list[dict]:
    res = api_post(D1_QUERY_URL, {"sql": sql}, timeout=120)
    if res is None or not res.get("success"):
        errs = res.get("errors") if res else None
        raise RuntimeError(f"D1 execute failed: {errs}")
    return [r for stmt in res["result"] for r in stmt.get("results", [])]


def write_edges_to_d1(edges: dict[tuple[str, str], float], reset: bool) -> int:
    if reset:
        deleted = d1_execute(
            "SELECT COUNT(*) AS n FROM edges WHERE kind='discovered'"
        )[0]["n"]
        d1_execute("DELETE FROM edges WHERE kind='discovered'")
        print(f"  reset: deleted {deleted} existing 'discovered' edges")

    rows = sorted(edges.items(), key=lambda kv: -kv[1])  # best edges first
    written = 0
    CHUNK = 300  # rows per INSERT statement
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        values = []
        for (a, b), score in chunk:
            if not (SONG_ID_RE.match(a) and SONG_ID_RE.match(b)):
                raise ValueError(f"bad song id in edge {(a, b)!r}")
            if not math.isfinite(score):
                raise ValueError(f"bad score {score!r}")
            values.append(f"('{a}','{b}',{score!r},'discovered')")
        sql = (
            "INSERT OR IGNORE INTO edges (from_song, to_song, score, kind) VALUES "
            + ",".join(values) + ";"
        )
        d1_execute(sql)
        written += len(chunk)
        print(f"  wrote {written}/{len(rows)} edges")
    return written


# --------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=8, help="neighbors per song")
    ap.add_argument("--workers", type=int, default=5, help="concurrent queries")
    ap.add_argument("--limit", type=int, default=0, help="only first N songs")
    ap.add_argument("--min-score", type=float, default=0.0, help="edge score floor")
    ap.add_argument("--no-resync", action="store_true",
                    help="skip the index consistency probe/repair")
    ap.add_argument("--no-reset", action="store_true",
                    help="don't delete existing 'discovered' edges first")
    ap.add_argument("--verify-only", action="store_true",
                    help="skip discovery; rebuild edges from cache and verify D1")
    args = ap.parse_args()

    tools = Path(__file__).resolve().parent
    manifest = json.loads((tools / "plainsong-feel-manifest.json").read_text())
    cache_path = tools / "edges-queries-cache.jsonl"
    print(f"corpus: {len(manifest)} songs in manifest")

    if args.verify_only:
        edges = merge_cache_edges(cache_path, args.min_score)
    else:
        print("embedding corpus (deterministic, same code as indexer)…")
        vectors = embed_corpus(manifest)  # always full corpus
        print(f"  embedded {len(vectors)} songs")

        if not args.no_resync:
            print("checking Vectorize index consistency…")
            if not ensure_synced(vectors, manifest):
                print("  ❌ index repair failed — aborting")
                return 1
        else:
            print("  (--no-resync: skipping consistency check)")

        if args.limit:
            vectors = dict(list(vectors.items())[: args.limit])
        edges = discover_edges(
            vectors, manifest, args.top_k, args.workers, cache_path, args.min_score
        )
        artifact = {
            "kind": "discovered",
            "top_k": args.top_k,
            "songs_queried": len(vectors),
            "edge_count": len(edges),
            "edges": [
                {"from_song": a, "to_song": b, "score": s}
                for (a, b), s in sorted(edges.items(), key=lambda kv: -kv[1])
            ],
        }
        (tools / "plainsong-discovered-edges.json").write_text(
            json.dumps(artifact, ensure_ascii=False)
        )
        print(f"  audit artifact → tools/plainsong-discovered-edges.json")

    print(f"writing {len(edges)} edges to D1 (kind='discovered')…")
    write_edges_to_d1(edges, reset=not args.no_reset)

    # ---------------------------------------------------------- verify
    n = d1_execute("SELECT COUNT(*) AS n FROM edges WHERE kind='discovered'")[0]["n"]
    total = d1_execute("SELECT COUNT(*) AS n FROM edges")[0]["n"]
    songs = d1_execute("SELECT COUNT(DISTINCT from_song) + COUNT(DISTINCT to_song) AS n FROM edges")[0]["n"]
    avg = d1_execute("SELECT AVG(score) AS s, MIN(score) AS lo, MAX(score) AS hi FROM edges WHERE kind='discovered'")[0]
    print(f"\n✅ D1 verification: {total} edges total ({n} 'discovered'), "
          f"{songs} distinct songs touched")
    print(f"   score avg={avg['s']:.4f} min={avg['lo']:.4f} max={avg['hi']:.4f}")

    sample = d1_execute(
        "SELECT sa.title AS ta, sa.key AS ka, sa.tempo AS tpa, sb.title AS tb, "
        "       sb.key AS kb, sb.tempo AS tpb, e.score "
        "FROM edges e JOIN songs sa ON sa.id = e.from_song "
        "             JOIN songs sb ON sb.id = e.to_song "
        "WHERE e.kind='discovered' ORDER BY e.score DESC LIMIT 6"
    )
    print("   top edges:")
    for r in sample:
        print(f"     {r['score']:.4f}  {r['ta']!r} [{r['ka']},{r['tpa']:g}bpm]  <->  "
              f"{r['tb']!r} [{r['kb']},{r['tpb']:g}bpm]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
