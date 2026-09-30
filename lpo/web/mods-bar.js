/* The mods strip for the game window.
 *
 * The Mods entry point is in the browser's own menu bar (fetch_browser.py adds an
 * MR_MODS_MENU block to the browser's main.js).  This strip is the readout: a
 * transparent overlay that stays faint until the pointer comes near the top edge,
 * then shows what the account the game signed in as is holding.
 *
 * Conventions kept from the rest of the package: English only, no emoji, inline
 * SVG icons, no modern syntax the browser's Electron 4 / Chromium 69 cannot parse
 * (no optional chaining, no nullish coalescing), and it never eats a click meant
 * for the game - the strip is pointer-events:none except while the pointer is on it.
 */
(function () {
  'use strict';

  var POLL_MS = 4000;
  var ID = 'lpo-mod-bar';

  var CSS = [
    '#' + ID + ' { position:fixed; top:0; left:0; right:0; height:26px;',
    '  display:flex; align-items:center; gap:14px; padding:0 10px;',
    '  font:12px/1 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;',
    '  color:#fff; background:transparent; text-shadow:0 1px 3px rgba(0,0,0,.95);',
    '  pointer-events:none; opacity:.35; transition:opacity .2s ease,background .2s ease;',
    '  z-index:2147483647; white-space:nowrap; overflow:hidden; }',
    '#' + ID + '.hot { opacity:1; background:rgba(0,0,0,.78); }',
    '#' + ID + ' .acct { font-weight:600; }',
    '#' + ID + ' .sep { width:1px; height:12px; background:rgba(255,255,255,.35); }',
    '#' + ID + ' .kv { color:rgba(255,255,255,.82); }',
    '#' + ID + ' .kv b { color:#fff; font-weight:600; }',
    '#' + ID + ' .gemsep { color:rgba(255,255,255,.3); }',
    '#' + ID + '.hot { height:auto; min-height:26px; padding-bottom:4px; white-space:normal;'
        + ' line-height:1.5; }',
    '#' + ID + ' .grow { flex:1 1 auto; }',
    '#' + ID + ' button { pointer-events:auto; font:inherit; color:#fff;',
    '  background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.4);',
    '  border-radius:999px; padding:2px 10px; cursor:pointer; }',
    '#' + ID + ' button:hover { background:rgba(255,255,255,.24); }',
    '#' + ID + ' svg { vertical-align:-2px; }'
  ].join('\n');

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }

  var ICON = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" ' +
             'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
             '<line x1="4" y1="8" x2="20" y2="8"/><circle cx="9" cy="8" r="2.4"/>' +
             '<line x1="4" y1="16" x2="20" y2="16"/><circle cx="15" cy="16" r="2.4"/></svg>';

  // LP1/LP2 keep eight star-element slots: the game's own HUD draws the first five
  // as coloured diamonds and the last three as hexagons, and labels none of them -
  // the colour IS the label.  The strip used to print `gems[0]` (not even a total),
  // so it said nothing a player could match to the row of diamonds in front of them.
  // Name the colours only for that eight-slot shape; other games (LP3 keeps ten
  // counters in a different scheme) get neutral slot numbers rather than a colour
  // claim this code cannot back up.
  var GEM_KINDS = ['red', 'green', 'yellow', 'white', 'blue',
                   'hidden1', 'hidden2', 'hidden3'];
  var GEM_TINTS = ['#ff6b6b', '#63d471', '#ffd95a', '#f2f2f2', '#63c8ff',
                   '#c9a6ff', '#c9a6ff', '#c9a6ff'];

  function gemsHtml(raw) {
    var parts = String(raw === undefined || raw === null ? '' : raw).split(',');
    var named = parts.length === GEM_KINDS.length;
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      var v = parseInt(parts[i], 10);
      if (isNaN(v)) v = 0;
      var name = named ? GEM_KINDS[i] : ('gem' + (i + 1));
      var tint = named ? GEM_TINTS[i] : '#fff';
      out.push('<span style="color:' + tint + '">' + name + '</span> <b>' + v + '</b>');
    }
    return out.length ? out.join(' <span class="gemsep">|</span> ') : '<b>0</b>';
  }

  function bar() {
    var host = document.getElementById(ID);
    if (host) return host;

    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    host = el('div');
    host.id = ID;

    host.appendChild(el('span', 'acct', 'not signed in'));
    host.appendChild(el('span', 'sep'));
    var coins = el('span', 'kv');
    coins.innerHTML = 'Coins <b>0</b>';
    host.appendChild(coins);
    var crys = el('span', 'kv');
    crys.innerHTML = 'Crystals <b>0</b>';
    host.appendChild(crys);
    var gems = el('span', 'kv');
    gems.innerHTML = 'Gems <b>0</b>';
    host.appendChild(gems);
    var stars = el('span', 'kv');
    stars.innerHTML = 'Levels <b>0/0</b>';
    host.appendChild(stars);
    host.appendChild(el('span', 'grow'));

    // The Mods entry itself lives in the browser's own menu bar, beside
    // 星願小王子瀏覽器 - see the MR_MODS_MENU block that fetch_browser.py adds to the
    // browser's main.js.  This strip only reports the numbers.

    document.body.appendChild(host);

    // faint in the background, solid while the pointer is along the top edge
    function hot(on) {
      if (on) host.className = 'hot';
      else host.className = '';
    }
    document.addEventListener('mousemove', function (e) { hot(e.clientY <= 40); });
    host.addEventListener('mouseenter', function () { hot(true); });
    host.addEventListener('mouseleave', function () { hot(false); });
    return host;
  }

  function set(host, i, value) {
    var b = host.children[i].getElementsByTagName('b')[0];
    if (b && b.textContent !== String(value)) b.textContent = String(value);
  }

  function load(host) {
    var req = new XMLHttpRequest();
    req.open('GET', '/web/api/hud', true);
    req.onreadystatechange = function () {
      if (req.readyState !== 4) return;
      if (req.status !== 200) { host.children[0].textContent = 'not signed in'; return; }
      var d;
      try { d = JSON.parse(req.responseText); } catch (e) { return; }
      var prof = d.profile || {};
      var prog = d.progress || {};
      host.children[0].textContent = d.name || d.login_name || 'guest';
      set(host, 2, prof.coins || '0');
      set(host, 3, prof.totalCrystals || '0');

      var gems = (prog.gems || '').split(',');
      var own = 0;
      for (var i = 0; i < gems.length; i++) { if (parseInt(gems[i], 10) > 0) own++; }
      host.children[4].innerHTML = 'Gems ' + gemsHtml(prog.gems);

      var st = (prog.stars || '').split(',');
      var cleared = 0;
      for (var j = 0; j < st.length; j++) { if (parseInt(st[j], 10) > 0) cleared++; }
      set(host, 5, cleared + '/' + (st.length && st[0] !== '' ? st.length : 0));
    };
    try { req.send(); } catch (e) { /* page is gone */ }
  }

  function start() {
    // LP1/LP2/LP3 draw their own counter row (LP1's five diamonds and three
    // hexagons are the same eight star-element values this strip reports), so the
    // strip is left off those pages - a second, differently-labelled copy of the
    // same numbers is just noise over the game's own HUD.  Decided here rather than
    // by editing each game page, because this file ships with the launcher while the
    // game pages arrive inside the per-game packs.  ?nobar=1 forces it off anywhere,
    // ?nobar=0 forces it on.
    if (/[?&]nobar=1/.test(window.location.search)) return;
    if (!/[?&]nobar=0/.test(window.location.search) &&
        /\/LP\/personal\/LP[123](\/|$)/i.test(window.location.pathname)) return;

    var host = bar();
    load(host);
    window.setInterval(function () { load(host); }, POLL_MS);
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    window.setTimeout(start, 0);
  } else {
    window.addEventListener('DOMContentLoaded', start);
  }
})();
