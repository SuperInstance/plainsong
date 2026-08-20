// plainsong-feel — the ship's musical memory, browsable.
// One Worker: serves the Feel Radio page + JSON API over D1 + Vectorize.
//
// Endpoints:
//   GET /                     the hero page (embedded HTML, no external deps)
//   GET /api/random           a random song id + metadata
//   GET /api/song/:id         metadata + nearest kin (Vectorize, self-probe guarded)
//   GET /api/song/:id/edges   D1 discovered-edges fallback (also served when
//                             Vectorize replicas are stale after a sync)
//   GET /api/search?q=        D1 LIKE over title / key / meter / collection
//
// Eventual-consistency guard: after a corpus sync, Vectorize query replicas can
// serve stale vectors for ~1h. Every neighbor query probes for the song's own
// vector (self-match must score ~1.0). On mismatch we fall back to D1 edges
// instead of returning garbage neighbors.

import { PAGE_HTML } from "./page.js";

const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };
const ID_RE = /^song-[0-9a-f]{6,32}$/; // defense-in-depth on top of bound params
const TOP_K = 13; // self + 12 neighbors
const SELF_MATCH_FLOOR = 0.9; // cosine self-match should be ~1.0

const SONG_COLS = `id, title, "key" AS key, tempo, meter, collection, bars, notes`;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function notFound(what) {
  return json({ error: `${what} not found` }, 404);
}

// ---------------------------------------------------------------- routes

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method !== "GET") return json({ error: "GET only" }, 405);

    if (path === "/" || path === "/index.html") {
      return new Response(PAGE_HTML, {
        headers: { "content-type": "text/html; charset=utf-8" },
      });
    }

    if (path === "/api/random") return handleRandom(env);

    if (path.startsWith("/api/search")) return handleSearch(env, url);

    const songMatch = path.match(/^\/api\/song\/([^/]+)(\/edges)?$/);
    if (songMatch) {
      const id = decodeURIComponent(songMatch[1]);
      if (!ID_RE.test(id)) return notFound("song");
      return songMatch[2]
        ? handleEdges(env, id)
        : handleSong(env, id);
    }

    if (path === "/api/health") return json({ ok: true });

    return notFound("route");
  },
};

// ---------------------------------------------------------------- handlers

async function handleRandom(env) {
  const song = await env.DB.prepare(
    `SELECT ${SONG_COLS} FROM songs ORDER BY RANDOM() LIMIT 1`
  ).first();
  if (!song) return notFound("songs table");
  return json({ song });
}

async function handleSearch(env, url) {
  const q = (url.searchParams.get("q") || "").trim();
  if (q.length < 2) return json({ results: [] });
  const like = `%${q.replace(/[%_]/g, (c) => "\\" + c)}%`;
  const prefix = `${q.replace(/[%_]/g, (c) => "\\" + c)}%`;
  const { results } = await env.DB.prepare(
    `SELECT ${SONG_COLS} FROM songs
     WHERE title LIKE ?1 ESCAPE '\\'
        OR "key" LIKE ?1 ESCAPE '\\'
        OR meter LIKE ?1 ESCAPE '\\'
        OR collection LIKE ?1 ESCAPE '\\'
     ORDER BY (title LIKE ?2 ESCAPE '\\') DESC, title
     LIMIT 40`
  )
    .bind(like, prefix)
    .all();
  return json({ results });
}

async function handleSong(env, id) {
  const song = await env.DB.prepare(
    `SELECT ${SONG_COLS} FROM songs WHERE id = ?1`
  )
    .bind(id)
    .first();
  if (!song) return notFound("song");

  const { neighbors, source, note } = await nearestKin(env, id);

  return json({ song, neighbors, source, note });
}

async function handleEdges(env, id) {
  const song = await env.DB.prepare(
    `SELECT ${SONG_COLS} FROM songs WHERE id = ?1`
  )
    .bind(id)
    .first();
  if (!song) return notFound("song");
  const neighbors = await edgesNeighbors(env, id, 24);
  return json({ song, neighbors, source: "edges" });
}

// ------------------------------------------------- the guarded kin query

async function nearestKin(env, id) {
  // 1) Pull the song's own vector from Vectorize.
  let vector = null;
  try {
    const vecs = await env.VECTORIZE_INDEX.getByIds([id]);
    vector = vecs?.[0]?.values ?? null;
  } catch {
    vector = null;
  }

  if (vector && vector.length === 32) {
    try {
      // 2) Query its kin. The top hit must be the song itself at ~1.0
      //    cosine — that proves the replica serving this query has the
      //    post-sync vector for this song. If not, the replica is stale
      //    and the scores are untrustworthy.
      const res = await env.VECTORIZE_INDEX.query(vector, { topK: TOP_K });
      const hits = res?.matches ?? [];
      const self = hits.find((h) => h.id === id);

      if (self && self.score >= SELF_MATCH_FLOOR) {
        const ids = hits
          .filter((h) => h.id !== id)
          .slice(0, 12)
          .map((h) => h.id);
        const items = await joinSongs(env, ids, hits, id);
        return { neighbors: items, source: "vectorize", note: null };
      }
      return {
        neighbors: await edgesNeighbors(env, id, 12),
        source: "edges",
        note: "Vectorize replicas are settling after a sync — showing discovered edges.",
      };
    } catch {
      // fall through to edges
    }
  }

  const neighbors = await edgesNeighbors(env, id, 12);
  return {
    neighbors,
    source: "edges",
    note: vector ? null : "No feel-vector for this song yet — showing discovered edges.",
  };
}

// D1 join: Vectorize gives id+score only; titles/keys/meters come from D1.
async function joinSongs(env, ids, hits, selfId) {
  if (!ids.length) return [];
  const placeholders = ids.map(() => "?").join(",");
  const scoreById = new Map(hits.map((h) => [h.id, h.score]));
  const { results } = await env.DB.prepare(
    `SELECT ${SONG_COLS} FROM songs WHERE id IN (${placeholders})`
  )
    .bind(...ids)
    .all();

  // Edge scores (discovered kin) enrich the vector scores where they exist.
  const edgeRows = await env.DB.prepare(
    `SELECT to_song AS other, score, kind FROM edges WHERE from_song = ?1
     UNION ALL
     SELECT from_song AS other, score, kind FROM edges WHERE to_song = ?1`
  )
    .bind(selfId)
    .all();
  const edgeByOther = new Map(
    (edgeRows.results ?? []).map((r) => [r.other, r])
  );

  return results
    .map((row) => {
      const similarity = scoreById.get(row.id) ?? null;
      const edge = edgeByOther.get(row.id);
      return {
        ...row,
        similarity,
        edge_score: edge ? edge.score : null,
        edge_kind: edge ? edge.kind : null,
      };
    })
    .sort((a, b) => (b.similarity ?? -1) - (a.similarity ?? -1));
}

// D1 fallback: bidirectional discovered edges.
async function edgesNeighbors(env, id, limit) {
  const { results } = await env.DB.prepare(
    `SELECT s.id, s.title, s."key" AS key, s.tempo, s.meter, s.collection, s.bars, s.notes,
            e.score AS edge_score, e.kind AS edge_kind
     FROM edges e JOIN songs s ON s.id = e.to_song
     WHERE e.from_song = ?1
     UNION ALL
     SELECT s.id, s.title, s."key" AS key, s.tempo, s.meter, s.collection, s.bars, s.notes,
            e.score AS edge_score, e.kind AS edge_kind
     FROM edges e JOIN songs s ON s.id = e.from_song
     WHERE e.to_song = ?1
     ORDER BY edge_score DESC
     LIMIT ?2`
  )
    .bind(id, limit)
    .all();
  return (results ?? []).map((r) => ({
    ...r,
    similarity: null,
  }));
}
