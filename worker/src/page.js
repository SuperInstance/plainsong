// The Feel Radio page — embedded HTML, no external dependencies.
// Dark navy + gold, the fleet-radio aesthetic.
// NOTE: this is a JS template literal, so the client script below deliberately
// avoids backticks and ${} — it uses string concatenation instead.

export const PAGE_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plainsong — Feel Radio</title>
<style>
  :root {
    --bg: #070f1d;
    --bg-glow: #0e1c33;
    --panel: #0b1628;
    --panel-2: #0e1c31;
    --line: #1d2d4a;
    --line-soft: #16233c;
    --gold: #d9b45b;
    --gold-bright: #f0d68a;
    --gold-dim: #8a7439;
    --ink: #c9d5e8;
    --ink-dim: #7e8ea8;
    --ink-faint: #55647e;
    --danger: #d98a5b;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { -webkit-text-size-adjust: 100%; }
  body {
    background:
      radial-gradient(1100px 500px at 50% -120px, var(--bg-glow), transparent 70%),
      repeating-linear-gradient(0deg, rgba(255,255,255,0.012) 0 1px, transparent 1px 3px),
      var(--bg);
    color: var(--ink);
    font-family: Georgia, 'Times New Roman', 'Palatino Linotype', serif;
    min-height: 100vh;
    line-height: 1.5;
  }
  .wrap { max-width: 900px; margin: 0 auto; padding: 0 20px 90px; }

  /* ---------- masthead ---------- */
  header { text-align: center; padding: 44px 0 26px; }
  .masthead-rule {
    display: flex; align-items: center; gap: 14px;
    color: var(--gold-dim); font-size: 11px; letter-spacing: .45em;
  }
  .masthead-rule::before, .masthead-rule::after {
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, transparent, var(--gold-dim), transparent);
  }
  h1.brand {
    font-size: 40px; font-weight: 400; letter-spacing: .34em;
    color: var(--gold); margin: 10px 0 2px; text-indent: .34em;
    text-shadow: 0 0 24px rgba(217,180,91,.25);
  }
  .tagline {
    color: var(--ink-dim); font-style: italic; font-size: 14.5px; letter-spacing: .08em;
  }

  /* ---------- search ---------- */
  .search { position: relative; margin: 22px 0 8px; }
  .search input {
    width: 100%; background: var(--panel); color: var(--ink);
    border: 1px solid var(--line); border-radius: 3px;
    padding: 12px 46px 12px 16px; font: inherit; font-size: 15px;
    outline: none; transition: border-color .2s, box-shadow .2s;
  }
  .search input::placeholder { color: var(--ink-faint); font-style: italic; }
  .search input:focus {
    border-color: var(--gold-dim);
    box-shadow: 0 0 0 1px rgba(217,180,91,.18), 0 0 18px rgba(217,180,91,.07);
  }
  .search .dial {
    position: absolute; right: 14px; top: 50%; transform: translateY(-50%);
    color: var(--gold-dim); font-size: 16px; pointer-events: none;
  }
  .results {
    background: var(--panel-2); border: 1px solid var(--line); border-radius: 3px;
    margin-top: 6px; max-height: 330px; overflow-y: auto; display: none;
  }
  .results.open { display: block; }
  .result-row {
    padding: 9px 14px; cursor: pointer; border-bottom: 1px solid var(--line-soft);
    display: flex; justify-content: space-between; gap: 12px; align-items: baseline;
  }
  .result-row:last-child { border-bottom: none; }
  .result-row:hover, .result-row.sel { background: rgba(217,180,91,.07); }
  .result-row .t { color: var(--ink); }
  .result-row:hover .t, .result-row.sel .t { color: var(--gold-bright); }
  .result-row .c { color: var(--ink-faint); font-size: 12px; white-space: nowrap; }

  /* ---------- trail ---------- */
  .trail {
    margin: 26px 0 0; font-size: 12.5px; color: var(--ink-faint);
    letter-spacing: .03em; line-height: 2; display: none;
  }
  .trail .step { color: var(--ink-dim); cursor: pointer; }
  .trail .step:hover { color: var(--gold-bright); text-decoration: underline; }
  .trail .sep { color: var(--gold-dim); padding: 0 4px; }
  .trail .step.here { color: var(--gold); cursor: default; font-style: italic; }

  /* ---------- on the air card ---------- */
  .card {
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    border: 1px solid var(--line); border-radius: 4px;
    padding: 26px 28px 24px; margin-top: 10px; position: relative; overflow: hidden;
  }
  .card::before {
    content: ''; position: absolute; inset: 0 auto 0 0; width: 2px;
    background: linear-gradient(180deg, transparent, var(--gold), transparent);
  }
  .onair {
    display: flex; align-items: center; gap: 10px;
    color: var(--gold-dim); font-size: 11px; letter-spacing: .38em; text-transform: uppercase;
  }
  .onair .pulse {
    width: 7px; height: 7px; border-radius: 50%; background: var(--gold);
    box-shadow: 0 0 10px rgba(217,180,91,.8);
    animation: pulse 2.4s ease-in-out infinite;
  }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
  h2.title {
    font-size: clamp(24px, 4.5vw, 34px); font-weight: 400; color: var(--gold-bright);
    margin: 10px 0 4px; letter-spacing: .01em; text-wrap: balance;
  }
  .meta-note { color: var(--ink-dim); font-size: 13px; font-style: italic; margin-bottom: 14px; }
  .badges { display: flex; flex-wrap: wrap; gap: 8px; }
  .badge {
    border: 1px solid var(--line); border-radius: 999px; padding: 3px 11px 4px;
    font-size: 11.5px; color: var(--ink-dim); letter-spacing: .06em;
    background: rgba(255,255,255,.015); white-space: nowrap;
  }
  .badge b { color: var(--gold); font-weight: 400; }
  .card .spacer { height: 18px; }
  .stale-note {
    margin-top: 16px; color: var(--danger); font-size: 12.5px; font-style: italic;
    border-top: 1px dashed var(--line); padding-top: 10px;
  }
  .tunerow { display: flex; justify-content: center; margin: 22px 0 4px; }
  button.tune {
    background: transparent; color: var(--gold); border: 1px solid var(--gold-dim);
    border-radius: 999px; padding: 9px 26px; font: inherit; font-size: 13px;
    letter-spacing: .22em; text-transform: uppercase; cursor: pointer;
    transition: all .2s;
  }
  button.tune:hover {
    background: rgba(217,180,91,.09); color: var(--gold-bright);
    box-shadow: 0 0 20px rgba(217,180,91,.15); border-color: var(--gold);
  }

  /* ---------- neighbors ---------- */
  .kin-head {
    display: flex; align-items: center; gap: 14px; margin: 36px 0 6px;
    color: var(--gold); font-size: 12px; letter-spacing: .34em; text-transform: uppercase;
  }
  .kin-head::before, .kin-head::after {
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, transparent, var(--gold-dim), transparent);
  }
  .kin-sub { text-align: center; color: var(--ink-faint); font-style: italic; font-size: 13px; margin-bottom: 18px; }
  .kin-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px;
  }
  .kin {
    background: var(--panel); border: 1px solid var(--line-soft); border-radius: 3px;
    padding: 14px 16px 13px; cursor: pointer; transition: border-color .15s, transform .15s, background .15s;
    display: flex; flex-direction: column; gap: 9px;
  }
  .kin:hover {
    border-color: var(--gold-dim); background: var(--panel-2);
    transform: translateY(-2px);
  }
  .kin .row1 { display: flex; align-items: baseline; gap: 10px; }
  .kin .rank {
    color: var(--gold-dim); font-size: 15px; min-width: 22px; font-style: italic;
  }
  .kin .name {
    color: var(--ink); font-size: 15.5px; line-height: 1.3;
  }
  .kin:hover .name { color: var(--gold-bright); }
  .kin .badges { gap: 5px; }
  .kin .badge { font-size: 10.5px; padding: 2px 8px 3px; color: var(--ink-faint); }
  .simbar { height: 3px; background: var(--line-soft); border-radius: 2px; overflow: hidden; }
  .simbar .fill {
    height: 100%; border-radius: 2px;
    background: linear-gradient(90deg, var(--gold-dim), var(--gold));
    box-shadow: 0 0 8px rgba(217,180,91,.35);
    transition: width .5s ease;
  }
  .simlabel { display: flex; justify-content: space-between; font-size: 11px; color: var(--ink-faint); }
  .simlabel .pct { color: var(--gold); }

  /* ---------- states ---------- */
  .loading { text-align: center; color: var(--ink-faint); font-style: italic; padding: 34px 0; letter-spacing: .08em; }
  .error { text-align: center; color: var(--danger); font-style: italic; padding: 34px 0; }
  .empty-kin { text-align: center; color: var(--ink-faint); font-style: italic; padding: 26px 0; }

  footer {
    margin-top: 64px; text-align: center; color: var(--ink-faint); font-size: 11.5px;
    letter-spacing: .14em; line-height: 2.1;
  }
  footer .f2 { color: #45536b; }
  footer b { color: var(--gold-dim); font-weight: 400; }
  ::-webkit-scrollbar { width: 9px; }
  ::-webkit-scrollbar-track { background: var(--panel); }
  ::-webkit-scrollbar-thumb { background: var(--line); border-radius: 5px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--gold-dim); }
  @media (max-width: 560px) {
    h1.brand { font-size: 28px; }
    .card { padding: 20px 18px; }
    .kin-grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="wrap">

  <header>
    <div class="masthead-rule">FEEL RADIO</div>
    <h1 class="brand">PLAINSONG</h1>
    <p class="tagline">the ship&rsquo;s musical memory &mdash; find a song, hear its kin, walk the space</p>
  </header>

  <div class="search">
    <input id="q" type="text" autocomplete="off" spellcheck="false"
           placeholder="Search titles, keys, meters, collections&hellip;" aria-label="Search songs">
    <span class="dial">&#9906;</span>
    <div class="results" id="results"></div>
  </div>

  <div class="trail" id="trail"></div>
  <section id="onair"></section>

  <div class="tunerow">
    <button class="tune" id="tune">&#8635; &nbsp;Tune the dial</button>
  </div>

  <section id="kin">
    <div class="kin-head">If you like it, the bar plays&hellip;</div>
    <div class="kin-sub" id="kinsub">nearest kin from the feel-space</div>
    <div id="kingrid"><div class="loading">warming the valves&hellip;</div></div>
  </section>

  <footer>
    <div><b>6,321</b> songs &middot; <b>33,789</b> discovered edges &middot; a 32-dimension feel-space</div>
    <div class="f2">plainsong feel radio &middot; dark water, gold light</div>
  </footer>

</div>

<script>
(function () {
  'use strict';

  var state = { trail: [], cache: {} };
  var qEl = document.getElementById('q');
  var resEl = document.getElementById('results');
  var trailEl = document.getElementById('trail');
  var onairEl = document.getElementById('onair');
  var kinEl = document.getElementById('kingrid');
  var kinsubEl = document.getElementById('kinsub');

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = (s === null || s === undefined) ? '' : String(s);
    return d.innerHTML;
  }
  function fmtTempo(t) { return (t === null || t === undefined) ? '' : Math.round(t) + ' bpm'; }
  function badge(inner) { return '<span class="badge">' + inner + '</span>'; }
  function badgesFor(s, short) {
    var parts = [];
    if (s.key) parts.push('<b>' + esc(s.key) + '</b>');
    if (s.tempo !== null && s.tempo !== undefined) parts.push(fmtTempo(s.tempo));
    if (s.meter) parts.push(esc(s.meter));
    if (s.collection) {
      var c = short ? tail(s.collection, 1) : s.collection;
      parts.push(esc(c));
    }
    if (!short && s.bars) parts.push(s.bars + ' bars');
    var html = '';
    for (var i = 0; i < parts.length; i++) html += badge(parts[i]);
    return html;
  }
  function tail(coll, n) {
    var bits = String(coll).split('/');
    return bits.slice(bits.length - n).join('/');
  }
  function pct(v) {
    if (v === null || v === undefined || isNaN(v)) return null;
    var x = Math.max(0, Math.min(1, v));
    return Math.round(x * 100) + '%';
  }

  // ---------- API ----------
  function get(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  // ---------- search ----------
  var timer = null, selIdx = -1, resItems = [];

  qEl.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(runSearch, 260);
  });
  qEl.addEventListener('focus', function () { if (qEl.value.trim().length >= 2) runSearch(); });
  qEl.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!resEl.classList.contains('open')) return;
      e.preventDefault();
      selIdx += (e.key === 'ArrowDown') ? 1 : -1;
      if (selIdx < 0) selIdx = resItems.length - 1;
      if (selIdx >= resItems.length) selIdx = 0;
      paintSel();
    } else if (e.key === 'Enter') {
      if (resEl.classList.contains('open') && selIdx >= 0 && resItems[selIdx]) pickResult(resItems[selIdx]);
    } else if (e.key === 'Escape') {
      closeResults();
    }
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest || !e.target.closest('.search')) closeResults();
  });

  function paintSel() {
    var rows = resEl.querySelectorAll('.result-row');
    for (var i = 0; i < rows.length; i++) rows[i].classList.toggle('sel', i === selIdx);
  }
  function runSearch() {
    var q = qEl.value.trim();
    if (q.length < 2) { closeResults(); return; }
    get('/api/search?q=' + encodeURIComponent(q)).then(function (d) {
      resItems = d.results || [];
      selIdx = -1;
      if (!resItems.length) {
        resEl.innerHTML = '<div class="result-row"><span class="c">nothing on that frequency &mdash; try another word</span></div>';
        resEl.classList.add('open');
        return;
      }
      var html = '';
      for (var i = 0; i < resItems.length; i++) {
        var s = resItems[i];
        html += '<div class="result-row" data-i="' + i + '">' +
          '<span class="t">' + esc(s.title) + '</span>' +
          '<span class="c">' + esc(s.key || '') + ' &middot; ' + esc(tail(s.collection || '', 1)) + '</span></div>';
      }
      resEl.innerHTML = html;
      resEl.classList.add('open');
      Array.prototype.forEach.call(resEl.querySelectorAll('.result-row'), function (row) {
        row.addEventListener('click', function () { pickResult(resItems[+row.getAttribute('data-i')]); });
      });
    }).catch(function () { closeResults(); });
  }
  function pickResult(s) { closeResults(); qEl.value = ''; loadSong(s.id, true); }
  function closeResults() { resEl.classList.remove('open'); resEl.innerHTML = ''; selIdx = -1; }

  // ---------- trail ----------
  function renderTrail() {
    if (state.trail.length < 2) { trailEl.style.display = 'none'; return; }
    trailEl.style.display = 'block';
    trailEl.innerHTML = '';
    var shown = state.trail.slice(-9);
    if (state.trail.length > 9) {
      var first = document.createElement('span');
      first.className = 'c'; first.textContent = '\u2026';
      trailEl.appendChild(first);
      trailEl.appendChild(sep());
    }
    var offset = state.trail.length - shown.length;
    shown.forEach(function (id, i) {
      var globalIdx = offset + i;
      var title = state.cache[id] || shorten(id);
      var span = document.createElement('span');
      span.className = 'step' + (globalIdx === state.trail.length - 1 ? ' here' : '');
      span.textContent = title;
      if (globalIdx !== state.trail.length - 1) {
        span.addEventListener('click', function () {
          state.trail = state.trail.slice(0, globalIdx + 1);
          loadSong(id, false);
        });
      }
      trailEl.appendChild(span);
      if (i < shown.length - 1) trailEl.appendChild(sep());
    });
    function sep() { var s = document.createElement('span'); s.className = 'sep'; s.textContent = '\u2192'; return s; }
  }
  function shorten(id) { return id.replace(/^song-/, '').slice(0, 8); }

  // ---------- song render ----------
  function loadSong(id, pushTrail) {
    if (location.hash !== '#' + id) {
      try { history.pushState(null, '', '#' + id); } catch (e) {}
    }
    onairEl.innerHTML = '';
    kinEl.innerHTML = '<div class="loading">pulling the record&hellip;</div>';
    get('/api/song/' + id).then(function (d) {
      state.cache[d.song.id] = d.song.title;
      if (pushTrail) state.trail.push(d.song.id);
      else if (state.trail[state.trail.length - 1] !== d.song.id) state.trail.push(d.song.id);
      render(d);
    }).catch(function () {
      kinEl.innerHTML = '<div class="error">that record isn&rsquo;t in the crate &mdash; tune the dial and try again</div>';
    });
  }

  function render(d) {
    var s = d.song;
    renderTrail();

    var html =
      '<div class="card">' +
        '<div class="onair"><span class="pulse"></span>' +
          (state.trail.length > 1 ? 'Now playing' : 'Now on the air') + '</div>' +
        '<h2 class="title">' + esc(s.title) + '</h2>' +
        '<div class="meta-note">' + esc(s.path || '') + '</div>' +
        '<div class="badges">' + badgesFor(s, false) + '</div>' +
        (d.note ? '<div class="stale-note">' + esc(d.note) + '</div>' : '') +
      '</div>';
    onairEl.innerHTML = html;

    if (!d.neighbors || !d.neighbors.length) {
      kinsubEl.textContent = 'no kin on record yet';
      kinEl.innerHTML = '<div class="empty-kin">a song alone in the dark &mdash; nothing sounds quite like it</div>';
      return;
    }
    if (d.source === 'edges') {
      kinsubEl.textContent = 'discovered edges ' + (d.note ? '' : '\u2014 feel-space settling');
    } else {
      kinsubEl.textContent = 'nearest kin from the feel-space';
    }

    kinEl.innerHTML = '';
    d.neighbors.forEach(function (n, i) {
      var score = (n.similarity !== null && n.similarity !== undefined) ? n.similarity : n.edge_score;
      var p = pct(score);
      var card = document.createElement('div');
      card.className = 'kin';
      card.innerHTML =
        '<div class="row1"><span class="rank">' + (i + 1) + '</span>' +
        '<span class="name">' + esc(n.title) + '</span></div>' +
        '<div class="badges">' + badgesFor(n, true) + '</div>' +
        '<div class="simbar"><div class="fill" style="width:0%"></div></div>' +
        '<div class="simlabel"><span>' + (n.edge_kind ? esc(n.edge_kind) + ' kin' : 'sounds like') + '</span>' +
        '<span class="pct">' + (p || '') + '</span></div>';
      card.addEventListener('click', function () { loadSong(n.id, true); });
      kinEl.appendChild(card);
      // animate the bar in
      setTimeout(function () {
        var fill = card.querySelector('.fill');
        fill.style.width = (p ? parseInt(p, 10) : 0) + '%';
      }, 40 + i * 35);
    });
  }

  // ---------- random / boot ----------
  document.getElementById('tune').addEventListener('click', function () {
    state.trail = [];
    boot(true);
  });

  function boot(fresh) {
    kinEl.innerHTML = '<div class="loading">warming the valves&hellip;</div>';
    get('/api/random').then(function (d) {
      loadSong(d.song.id, true);
    }).catch(function () {
      kinEl.innerHTML = '<div class="error">the radio is quiet &mdash; try again in a moment</div>';
    });
  }

  var h = location.hash.replace(/^#/, '');
  if (/^song-[0-9a-f]{6,32}$/.test(h)) {
    state.trail = [h];
    loadSong(h, true);
  } else {
    boot();
  }

  window.addEventListener('popstate', function () {
    var hh = location.hash.replace(/^#/, '');
    if (/^song-[0-9a-f]{6,32}$/.test(hh)) {
      state.trail = state.trail.slice(0, -1);
      loadSong(hh, false);
    }
  });
})();
</script>
</body>
</html>
`;
