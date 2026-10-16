// Little Prince Launcher - the page.  launcher_web.py serves it and answers:
//   /api/state        status, games, log lines, questions waiting for an answer
//   /api/play|open|server|lang|settings|prompt
//   /game/...         the game server's own /web/api/... (downloads, 星夜重圓)
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  var STR = {
    zh: {
      brand: "星願小王子", brand_sub: "遊戲啟動器", play: "開始遊戲", get: "下載並開始",
      getting: "下載中", starting: "啟動中…", accounts: "帳戶設定", mods: "模組", settings: "設定",
      log: "紀錄", server: "本機伺服器", start: "啟動", stop: "停止", test: "測試連線",
      revert: "還原 hosts", open_log: "打開紀錄檔", open_folder: "打開資料夾",
      on: "伺服器運行中", off: "伺服器已停止", ready: "已安裝", missing: "未下載",
      yes: "是", no: "否", ok: "好", cancel: "取消", save: "儲存", close: "關閉",
      lang: "語言", dl_from: "遊戲檔案下載來源", dl_auto: "自動（建議）", dl_pd: "Pixeldrain",
      dl_custom: "自訂網址", saved: "已儲存", android: "Android 模擬器",
      get_ask: "%s 還不在這部電腦上。\n\n現在下載嗎？（%n 個檔案，可能需要幾分鐘）",
      lic_title: "星夜重圓需要 Android 模擬器",
      lic_text: "星夜重圓只有 Android / iOS 版，所以啟動器會在 Google 的 Android 模擬器中執行它。它會從 dl.google.com 下載：%p。下面 Google 的授權條款（英文原文）適用於這些套件。你接受之前不會下載任何東西。",
      lic_yes: "我接受授權條款", lic_no: "不接受", lic_loading: "正在從 Google 載入授權條款…",
      admin_no: "沒有管理員權限：LP1–LP3 的登入需要 hosts 重新導向。",
      back: "返回", reload: "重新載入",
      lp5_note: "星願小王子的手機版 — 在 Android 模擬器中執行",
    },
    en: {
      brand: "Little Prince", brand_sub: "Game launcher", play: "Play", get: "Download & play",
      getting: "Downloading", starting: "Starting…", accounts: "Accounts", mods: "Mods", settings: "Settings",
      log: "Log", server: "Local server", start: "Start", stop: "Stop", test: "Test",
      revert: "Revert hosts", open_log: "Open log file", open_folder: "Open folder",
      on: "Server running", off: "Server stopped", ready: "Installed", missing: "Not downloaded",
      yes: "Yes", no: "No", ok: "OK", cancel: "Cancel", save: "Save", close: "Close",
      lang: "Language", dl_from: "Where game files download from", dl_auto: "Automatic (recommended)",
      dl_pd: "Pixeldrain", dl_custom: "Custom links", saved: "Saved", android: "Android emulator",
      get_ask: "%s is not on this PC yet.\n\nDownload it now? (%n files, may take a few minutes)",
      lic_title: "星夜重圓 needs the Android emulator",
      lic_text: "星夜重圓 only exists for Android and iOS, so the launcher runs it in Google's Android emulator. It downloads from dl.google.com: %p. Google's licence below applies to those packages. Nothing is downloaded until you accept.",
      lic_yes: "I accept the licence", lic_no: "Decline", lic_loading: "Loading the licence text from Google…",
      admin_no: "Not running as administrator: LP1-LP3 logins need the hosts redirect.",
      back: "Back", reload: "Reload",
      lp5_note: "星願小王子 on phones - runs in the Android emulator",
    },
  };
  // the portal's card art for each game (cloud/images)
  var CARD = { LP1: 1, LP2: 2, LP3: 3, LPO: 4, LP4: 5, LP5: 6 };
  // the Android setup's steps, as the portal words them
  var STEPS = [
    [/Downloading|\d+\/\d+ MB$/, "下載中", "Downloading"], [/^Unpacking/, "解壓中", "Unpacking"],
    [/^Installing the game/, "安裝遊戲", "Installing the game"], [/^Installing/, "安裝 Android SDK", "Installing Android"],
    [/^Creating/, "建立裝置", "Creating the device"], [/^Building/, "建立遊戲", "Building the game"],
    [/^Starting the Android/, "啟動模擬器", "Starting the emulator"], [/^Android is booting/, "Android 開機中", "Android is booting"],
    [/^Copying/, "複製資料", "Copying data"], [/^Starting /, "啟動遊戲", "Starting the game"],
    [/^Playing/, "遊戲中", "Playing"], [/^Working out/, "計算大小", "Working out the size"], [/^Ready/, "準備完成", "Ready"],
  ];

  var S = { lang: "zh", games: [], sel: null, cloud: {}, logSeq: 0, seenToasts: {}, openPrompt: null,
            busy: {}, playing: [], lastState: null };
  try { S.sel = localStorage.getItem("lp.sel"); } catch (e) { /* private window */ }

  function t(k) { return (STR[S.lang] || STR.zh)[k] || STR.en[k] || k; }
  function api(path, body) {
    var opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" },
                                          body: JSON.stringify(body) };
    return fetch(path, opt).then(function (r) { return r.json(); });
  }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function step(phase) {
    for (var i = 0; i < STEPS.length; i++) {
      if (STEPS[i][0].test(phase || "")) {
        var mb = /(\d+\/\d+ MB)/.exec(phase || "");
        return (S.lang === "zh" ? STEPS[i][1] : STEPS[i][2]) + (mb ? " " + mb[1] : "");
      }
    }
    return phase || "";
  }

  // ── words on the page ────────────────────────────────────────────────────
  function words() {
    document.documentElement.lang = S.lang === "zh" ? "zh-Hant" : "en";
    Array.prototype.forEach.call(document.querySelectorAll("[data-t]"), function (el) {
      el.textContent = t(el.getAttribute("data-t"));
    });
  }

  // ── the game list ────────────────────────────────────────────────────────
  function drawGames() {
    var nav = $("games");
    nav.innerHTML = S.games.map(function (g) {
      var c = S.cloud[g.code] || {};
      var pill = c.downloading ? '<span class="pill busy">' + (c.percent || 0) + "%</span>"
               : c.ready === false ? '<span class="pill get">' + t("missing") + "</span>" : "";
      return '<button class="game' + (g.code === S.sel ? " on" : "") + '" data-code="' + g.code + '">' +
             '<span class="thumb" style="background-image:url(' + g.banner + ')"></span>' +
             '<span class="txt"><b>' + esc(g.name) + "</b><small>" + esc(g.sub) + "</small></span>" + pill +
             "</button>";
    }).join("");
  }
  $("games").addEventListener("click", function (e) {
    var b = e.target.closest(".game");
    if (!b) { return; }
    S.sel = b.getAttribute("data-code");
    try { localStorage.setItem("lp.sel", S.sel); } catch (err) { /* ignore */ }
    drawGames(); drawBanner(true);
  });

  // ── the banner ───────────────────────────────────────────────────────────
  function current() {
    for (var i = 0; i < S.games.length; i++) { if (S.games[i].code === S.sel) { return S.games[i]; } }
    return S.games[0];
  }
  function drawBanner(swap) {
    var g = current();
    if (!g) { return; }
    var hero = $("hero");
    if (hero.getAttribute("src") !== g.banner) {
      if (!hero.getAttribute("src")) {
        hero.src = g.banner;                      // first paint: no fade to wait for
      } else {
        hero.classList.add("fade");
        setTimeout(function () {
          hero.onload = hero.onerror = function () { hero.classList.remove("fade"); };
          hero.src = g.banner;                    // onload first: a cached image fires at once
        }, 120);
      }
    }
    $("title").textContent = g.name;
    $("sub").textContent = g.code === "LP5" ? t("lp5_note") : g.sub;
    var c = S.cloud[g.code] || {};
    var play = $("play"), label = t("play"), busy = false, pct = null, text = "";
    if (c.downloading) {
      busy = true; pct = c.percent || 0;
      text = c.android ? step(c.phase) : t("getting") + " " + pct + "%";
      label = c.android ? t("starting") : t("getting");
    } else if (c.error) {
      text = c.error;
    }
    if (!busy && c.ready === false && !c.android) { label = t("get"); }
    var getting = S.playing.indexOf(g.code) >= 0;
    if (S.busy[g.code] || getting) { busy = true; if (!c.downloading) { label = t("starting"); } }
    play.disabled = busy;
    play.querySelector("span").textContent = label;
    $("progress").classList.toggle("hide", pct === null && !text);
    $("pbar").style.width = (pct || 0) + "%";
    $("ptext").textContent = text;
    $("state").textContent = c.ready === false && !c.downloading ? t("missing")
      : c.android ? t("android") : "";
  }

  $("play").addEventListener("click", function () {
    var g = current(); if (!g) { return; }
    var c = S.cloud[g.code] || {};
    if (c.android) { return playAndroid(g, c); }
    // one press: the launcher downloads what is missing (game, browser) and opens it
    S.busy[g.code] = true; drawBanner();
    api("/api/play", { code: g.code }).then(function () {
      setTimeout(function () { S.busy[g.code] = false; drawBanner(); }, 4000);
    });
  });

  function playAndroid(g, c) {
    function go() {
      S.busy[g.code] = true; drawBanner();
      api("/game/reunion/play", {}).then(function (d) {
        S.busy[g.code] = false;
        if (d && d.need_licences) { return licence(go); }
        if (d && d.ok === false) { toast({ kind: "error", title: g.name, text: d.error || "" }); }
        pollCloud();
      });
    }
    if (!c.licences) { return licence(go); }
    go();
  }

  // ── modal ────────────────────────────────────────────────────────────────
  function modal(html) { $("modal").innerHTML = html; $("veil").classList.remove("hide"); }
  function closeModal() { $("veil").classList.add("hide"); $("modal").innerHTML = ""; }
  function ask(title, text, cb) {
    modal("<h2>" + esc(title) + "</h2><div class='body'><p>" + esc(text) + "</p></div>" +
          "<div class='actions'><button class='secondary' id='mNo'>" + t("no") + "</button>" +
          "<button id='mYes'>" + t("yes") + "</button></div>");
    $("mYes").onclick = function () { closeModal(); cb(true); };
    $("mNo").onclick = function () { closeModal(); cb(false); };
  }
  function licence(after) {
    modal("<h2>" + t("lic_title") + "</h2><p id='licIntro'></p><pre class='lic' id='licText'>" +
          t("lic_loading") + "</pre><div class='actions'><button class='secondary' id='mNo'>" + t("lic_no") +
          "</button><button id='mYes' disabled>" + t("lic_yes") + "</button></div>");
    $("licIntro").textContent = t("lic_text").replace("%p", "…");
    $("mNo").onclick = closeModal;
    fetch("/game/reunion/licences").then(function (r) { return r.json(); }).then(function (d) {
      $("licText").textContent = (d.licences || []).map(function (l) { return "==== " + l.id + " ====\n\n" + l.text; })
        .join("\n\n\n") || "Could not load the licences.";
      $("licIntro").textContent = t("lic_text").replace("%p", (d.packages || []).join(", ") +
        " (~" + (d.size_mb || "?") + " MB)");
      $("mYes").disabled = false;
      $("mYes").onclick = function () {
        closeModal();
        api("/game/reunion/accept", { accept: true }).then(function (r) {
          if (r && r.ok === false) { return toast({ kind: "error", title: t("lic_title"), text: r.error || "" }); }
          after();
        });
      };
    }).catch(function () { $("licText").textContent = "Could not reach dl.google.com for the licence text."; });
  }

  // questions the launcher itself asks (the old Tk yes/no boxes)
  function prompts(list) {
    if (S.openPrompt || !list || !list.length) { return; }
    var p = list[0];
    S.openPrompt = p.id;
    ask(p.title, p.text, function (yes) {
      api("/api/prompt", { id: p.id, answer: yes }).then(function () { S.openPrompt = null; });
    });
  }
  function toast(x) {
    var el = document.createElement("div");
    el.className = "toast " + (x.kind || "info");
    el.innerHTML = "<b>" + esc(x.title) + "</b>" + esc(x.text);
    $("toasts").appendChild(el);
    setTimeout(function () { el.remove(); }, 7000);
  }

  // ── settings ─────────────────────────────────────────────────────────────
  $("settingsBtn").onclick = function () {
    api("/api/settings").then(function (s) {
      var custom = s.custom || {};
      modal("<h2>" + t("settings") + "</h2><div class='body'>" +
            "<p><b>" + t("lang") + "</b></p><div class='seg'>" +
            "<button data-lang='zh' class='" + (S.lang === "zh" ? "on" : "") + "'>中文</button>" +
            "<button data-lang='en' class='" + (S.lang === "en" ? "on" : "") + "'>English</button></div>" +
            "<p style='margin-top:16px'><b>" + t("dl_from") + "</b></p>" +
            [["auto", t("dl_auto")], ["pixeldrain", t("dl_pd")], ["custom", t("dl_custom")]].map(function (o) {
              return "<label class='opt'><input type='radio' name='dl' value='" + o[0] + "'" +
                     (s.method === o[0] ? " checked" : "") + "> " + o[1] + "</label>";
            }).join("") +
            (s.codes || []).map(function (c) {
              return "<div class='field'><span>" + c + "</span><input type='text' data-code='" + c +
                     "' value='" + esc(custom[c] || "") + "' placeholder='https://…'></div>";
            }).join("") +
            "<p class='small' id='setMsg'></p></div><div class='actions'>" +
            "<button class='secondary' id='mNo'>" + t("close") + "</button><button id='mYes'>" + t("save") + "</button></div>");
      Array.prototype.forEach.call(document.querySelectorAll("[data-lang]"), function (b) {
        b.onclick = function () {
          S.lang = b.getAttribute("data-lang");
          api("/api/lang", { lang: S.lang }).then(refresh);
          Array.prototype.forEach.call(document.querySelectorAll("[data-lang]"), function (x) {
            x.classList.toggle("on", x === b); });
          words();
        };
      });
      $("mNo").onclick = closeModal;
      $("mYes").onclick = function () {
        var method = (document.querySelector("input[name=dl]:checked") || {}).value || "auto";
        var cust = {};
        Array.prototype.forEach.call(document.querySelectorAll("input[data-code]"), function (i) {
          if (i.value.trim()) { cust[i.getAttribute("data-code")] = i.value.trim(); } });
        api("/api/settings", { method: method, custom: cust }).then(function (r) {
          $("setMsg").textContent = r.ok ? t("saved") : (r.error || "");
        });
      };
    });
  };
  $("lang").onclick = function () {
    S.lang = S.lang === "zh" ? "en" : "zh"; words();
    api("/api/lang", { lang: S.lang }).then(refresh);
  };
  $("veil").addEventListener("click", function (e) { if (e.target === $("veil") && !S.openPrompt) { closeModal(); } });

  // ── the accounts page and the mods, inside the window ────────────────────
  var SHEETS = { accounts: "/web", mods: "/mods" };
  function openSheet(kind) {
    var base = (S.lastState && S.lastState.game_base) || "http://127.0.0.1:8080";
    $("sheetTitle").textContent = t(kind);
    var url = base + SHEETS[kind];
    if ($("sheetFrame").getAttribute("data-kind") !== kind) {
      $("sheetFrame").setAttribute("data-kind", kind);
      $("sheetFrame").src = url;
    }
    $("sheet").classList.remove("hide");
    $("drawer").classList.add("hide"); $("serverPop").classList.add("hide");
  }
  function closeSheet() { $("sheet").classList.add("hide"); }
  Array.prototype.forEach.call(document.querySelectorAll("[data-sheet]"), function (b) {
    b.onclick = function () {
      var kind = b.getAttribute("data-sheet");
      if (!$("sheet").classList.contains("hide") && $("sheetFrame").getAttribute("data-kind") === kind) {
        return closeSheet();
      }
      openSheet(kind);
    };
  });
  $("sheetBack").onclick = closeSheet;
  $("sheetReload").onclick = function () { $("sheetFrame").src = $("sheetFrame").src; };

  // ── dock, server, log ────────────────────────────────────────────────────
  Array.prototype.forEach.call(document.querySelectorAll("[data-open]"), function (b) {
    b.onclick = function () { api("/api/open", { what: b.getAttribute("data-open") }); };
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-server]"), function (b) {
    b.onclick = function () { api("/api/server", { action: b.getAttribute("data-server") }).then(refresh); };
  });
  $("serverBtn").onclick = function () { $("serverPop").classList.toggle("hide"); $("drawer").classList.add("hide"); };
  $("logBtn").onclick = function () { $("drawer").classList.toggle("hide"); $("serverPop").classList.add("hide");
                                      var l = $("log"); l.scrollTop = l.scrollHeight; };
  $("drawerClose").onclick = function () { $("drawer").classList.add("hide"); };
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { $("drawer").classList.add("hide"); $("serverPop").classList.add("hide"); closeSheet();
                              if (!S.openPrompt) { closeModal(); } }
  });

  // ── polling ──────────────────────────────────────────────────────────────
  function refresh() {
    return api("/api/state?after=" + S.logSeq).then(function (st) {
      var langChanged = st.lang !== S.lang || !S.lastState;
      S.lang = st.lang; S.lastState = st;
      var gamesChanged = JSON.stringify(st.games) !== JSON.stringify(S.games);
      S.games = st.games;
      if (!S.sel || !S.games.some(function (g) { return g.code === S.sel; })) { S.sel = S.games[0] && S.games[0].code; }
      if (langChanged) { words(); }
      if (gamesChanged || langChanged) { drawGames(); drawBanner(); }
      $("dot").classList.toggle("ok", !!st.online);
      $("serverText").textContent = st.online ? t("on") : t("off");
      var LBL = S.lang === "zh" ? { hosts: "hosts 重新導向", requests: "請求", uptime: "運行時間",
                                    user: "權限", online: "Online 伺服器", multiplayer: "多人連線" } : {};
      $("stats").innerHTML = (st.stats || []).map(function (r) {
        return "<dt>" + esc(LBL[r[0]] || r[0]) + "</dt><dd>" + esc(r[1]) + "</dd>"; }).join("");
      $("footer").textContent = st.footer || "";
      $("marquee").textContent = st.marquee || "";
      $("note").textContent = st.admin ? "" : t("admin_no");
      if (st.log && st.log.length) {
        var pre = $("log"), atEnd = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 30;
        pre.textContent += st.log.map(function (l) { return l.t; }).join("\n") + "\n";
        if (pre.textContent.length > 200000) { pre.textContent = pre.textContent.slice(-150000); }
        S.logSeq = st.log[st.log.length - 1].n;
        if (atEnd) { pre.scrollTop = pre.scrollHeight; }
      }
      (st.toasts || []).forEach(function (x) { if (!S.seenToasts[x.id]) { S.seenToasts[x.id] = 1; toast(x); } });
      prompts(st.prompts);
      var playing = st.playing || [];
      if (JSON.stringify(playing) !== JSON.stringify(S.playing)) { S.playing = playing; drawBanner(); }
      if (st.task) {                       // the game browser's own download
        $("progress").classList.remove("hide");
        $("pbar").style.width = (st.task.pct || 0) + "%";
        $("ptext").textContent = st.task.label + (st.task.pct ? " " + st.task.pct + "%" : "");
      }
    }).catch(function () { $("dot").classList.remove("ok"); });
  }
  function pollCloud() {
    return fetch("/game/cloud_state").then(function (r) { return r.json(); }).then(function (d) {
      var g = (d && d.games) || {};
      var changed = JSON.stringify(g) !== JSON.stringify(S.cloud);
      S.cloud = g;
      if (changed) { drawGames(); drawBanner(); }
    }).catch(function () { /* the game server is still starting */ });
  }
  refresh(); pollCloud();
  setInterval(refresh, 1000);
  setInterval(pollCloud, 2000);
})();
