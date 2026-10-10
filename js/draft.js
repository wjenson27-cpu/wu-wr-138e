/* Reusable draft-day War Room. Rankings live in data/draft/<season>.json.
   Edits and the live draft stay on this phone until you export the file. */
(function () {
  var FILTERS = ["ALL", "OFF", "OFLEX", "DEF", "QB", "RB", "WR", "TE", "LB", "DL", "DB"];
  var VERDICTS = ["", "SMASH", "LIKE", "CAUTION", "WATCH", "SLEEPER", "FADE"];
  var TIERS = ["", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"];
  var POS_TABS = ["LB", "RB", "WR", "DB", "QB", "TE"];
  var state = {
    season: null,
    year: 2026,
    years: [2026],
    scoring: null,
    lineup: null,
    vor: {},
    tab: "pboard",
    sort: "rank",
    filter: "ALL",
    q: "",
    hide: true,
    edit: false,
    posQ: {},
    posHide: {},
    live: { drafted: {}, current: 1, muted: false },
    lastAlert: 0,
    fromPhone: false,
    ready: {}
  };

  function $(id) { return document.getElementById(id); }
  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function yearKey(year) { return "wu-draft-board-" + year; }
  function liveKey(year) { return "wu-draft-live-" + year; }

  function lineupFrom(scoring) {
    var s = scoring && scoring.roster && scoring.roster.startingLineup;
    if (!s) return WUVor.DEFAULT_LINEUP;
    return {
      QB: s.QB || 0, RB: s.RB || 0, WR: s.WR || 0, TE: s.TE || 0,
      RWT: s.RWT_flex_RB_WR_TE || s.RWT || 0,
      DL: s.DL || 0, LB: s.LB || 0, DB: s.DB || 0,
      ID: s.ID_flex_any_IDP || s.ID || 0
    };
  }

  function saveBoard() {
    try { localStorage.setItem(yearKey(state.year), JSON.stringify(state.season)); } catch (e) {}
    state.fromPhone = true;
  }

  function saveLive() {
    try {
      localStorage.setItem(liveKey(state.year), JSON.stringify({
        drafted: state.live.drafted,
        current: state.live.current,
        muted: state.live.muted
      }));
    } catch (e) {}
  }

  function picks() {
    return state.season ? WUDraft.buildPicks(state.season) : [];
  }

  function yours() {
    return state.season ? WUDraft.userPicks(state.season) : [];
  }

  function isDrafted(name) { return !!state.live.drafted[name]; }

  function scoreVor() {
    if (!state.season) return;
    var lineup = state.lineup || WUVor.DEFAULT_LINEUP;
    var rostered = (state.season.players || []).map(function (p) {
      return { name: p.name, pos: p.pos, ppg: Number(p.pts) || 0 };
    });
    var ctx = WUVor.computeReplacement({
      rostered: rostered,
      freeAgents: [],
      lineup: lineup,
      teamCount: state.season.teamCount || (state.season.teams || []).length || 14,
      useWaiver: false,
      scarcity: false
    });
    state.vor = {};
    (state.season.players || []).forEach(function (p) {
      state.vor[p.name] = ctx.vorFor(Number(p.pts) || 0, p.pos);
    });
    var positions = state.season.positions || {};
    Object.keys(positions).forEach(function (pos) {
      (positions[pos].players || []).forEach(function (p) {
        if (state.vor[p.name] == null) state.vor[p.name] = ctx.vorFor(Number(p.pts) || 0, p.pos || pos);
      });
    });
  }

  function tierClass(tier) {
    return String(tier || "").toLowerCase();
  }

  function rowHtml(p, opts) {
    opts = opts || {};
    var taken = isDrafted(p.name);
    var tcls = tierClass(p.tier);
    var fade = p.verdict === "FADE";
    var you = (state.season.targets || []).indexOf(p.name) !== -1 || p.like;
    if (opts.hide && taken) return "";
    var vor = state.vor[p.name];
    var vorHtml = vor == null ? "" : '<span class="vor">VOR ' + Number(vor).toFixed(1) + "</span>";
    var pts = p.pts == null ? "" : '<span class="pts">' + p.pts + " pts</span>";
    var y25 = p.y25 == null ? "" : '<span class="y25">\'25 ' + p.y25 + "</span>";
    var win = p.window ? '<span class="vor">' + esc(p.window) + "</span>" : "";
    var role = p.role ? esc(p.role) + " · " : "";
    var html = '<div class="row ' + tcls + (you ? " you" : "") + (fade ? " fade" : "") + (taken ? " drafted" : "") + '">';
    html += '<div class="rank ' + tcls + '">' + esc(p.rank == null ? "" : p.rank) + "</div>";
    html += '<div class="info"><div class="name">' + esc(p.name) + ' <span class="tierchip ' + tcls + '">' + esc(p.tier || "") + "</span></div>";
    html += '<div class="meta">' + esc(p.team || "") + " · " + role + pts + " " + vorHtml + " " + y25 + " " + win + "</div>";
    if (p.note) html += '<div class="note">' + esc(p.note) + "</div>";
    if (state.edit) html += editBox(p);
    html += '</div><div class="pos ' + esc(p.pos) + '">' + esc(p.pos) + "</div>";
    if (p.verdict) html += '<div class="verdict ' + esc(p.verdict) + '">' + esc(p.verdict) + "</div>";
    html += taken
      ? '<button class="btn-draft taken" type="button">TAKEN</button>'
      : '<button class="btn-draft" type="button" data-draft="' + esc(p.name) + '" data-pos="' + esc(p.pos) + '">DRAFT</button>';
    html += "</div>";
    return html;
  }

  function editBox(p) {
    var tiers = TIERS.map(function (t) {
      return '<option' + (t === (p.tier || "") ? " selected" : "") + ">" + (t || "Tier") + "</option>";
    }).join("");
    var verdicts = VERDICTS.map(function (v) {
      return '<option value="' + v + '"' + (v === (p.verdict || "") ? " selected" : "") + ">" + (v || "Verdict") + "</option>";
    }).join("");
    return '<div class="editbox"><select data-edit="tier" data-name="' + esc(p.name) + '">' + tiers + "</select>" +
      '<select data-edit="verdict" data-name="' + esc(p.name) + '">' + verdicts + "</select>" +
      '<button type="button" class="star" data-star="' + esc(p.name) + '">' + (p.like ? "★" : "☆") + "</button>" +
      '<button type="button" class="btn ghost" data-drop="' + esc(p.name) + '">Remove</button></div>' +
      '<textarea data-edit="note" data-name="' + esc(p.name) + '">' + esc(p.note || "") + "</textarea>";
  }

  function posMatch(pos, filt) {
    if (!filt || filt === "ALL") return true;
    if (filt === "OFF") return pos === "RB" || pos === "WR" || pos === "TE" || pos === "QB";
    if (filt === "OFLEX") return pos === "RB" || pos === "WR" || pos === "TE";
    if (filt === "DEF") return pos === "LB" || pos === "DL" || pos === "DB";
    return pos === filt;
  }

  function boardRows() {
    var q = state.q.toLowerCase();
    var rows = (state.season.players || []).filter(function (p) {
      if (state.hide && isDrafted(p.name)) return false;
      if (!posMatch(p.pos, state.filter)) return false;
      if (!q) return true;
      return (p.name + " " + (p.team || "") + " " + p.pos).toLowerCase().indexOf(q) !== -1;
    });
    rows.sort(function (a, b) {
      if (state.sort === "pts") return (Number(b.pts) || -9999) - (Number(a.pts) || -9999);
      if (state.sort === "vor") return (state.vor[b.name] || -9999) - (state.vor[a.name] || -9999);
      return (a.rank || 9999) - (b.rank || 9999);
    });
    return rows;
  }

  function renderBoard() {
    var host = $("pboard");
    if (!state.ready.board) {
      state.ready.board = true;
      host.innerHTML = '<div class="filters" id="filt"></div><div class="sorts" id="sorts"><span class="lbl">Sort</span></div>' +
        '<label class="hide-drafted"><input type="checkbox" id="hideDrafted" checked> Hide drafted</label>' +
        '<input type="search" id="q" placeholder="Search name, team, position" autocomplete="off">' +
        '<div id="listBoard"></div>';
      $("filt").innerHTML = FILTERS.map(function (f) {
        return '<button type="button" data-pos="' + f + '"' + (f === "ALL" ? ' class="on"' : "") + ">" + f + "</button>";
      }).join("");
      $("sorts").insertAdjacentHTML("beforeend",
        '<button type="button" class="on" data-sort="rank">Rank</button><button type="button" data-sort="pts">Proj</button><button type="button" data-sort="vor">VOR</button>');
    }
    var rows = boardRows();
    $("listBoard").innerHTML = rows.length ? rows.map(function (p) { return rowHtml(p); }).join("") : '<p class="tiny">No matches.</p>';
  }

  function renderLikes() {
    var host = $("plikes");
    if (!state.ready.likes) {
      state.ready.likes = true;
      host.innerHTML = '<div class="filters" id="filtLikes"></div><div id="listLikes"></div>';
      $("filtLikes").innerHTML = ["ALL", "OFF", "DEF", "QB", "RB", "WR", "TE", "LB", "DL", "DB"].map(function (f, i) {
        return '<button type="button" data-like="' + f + '"' + (i === 0 ? ' class="on"' : "") + ">" + f + "</button>";
      }).join("");
      state.likeFilter = "ALL";
    }
    var list = (state.season.likes && state.season.likes.length)
      ? state.season.likes
      : (state.season.players || []).filter(function (p) { return p.like; });
    var by = {};
    list.forEach(function (p) {
      if (!posMatch(p.pos, state.likeFilter || "ALL")) return;
      if (!by[p.pos]) by[p.pos] = [];
      by[p.pos].push(p);
    });
    var html = "";
    ["TE", "RB", "WR", "QB", "LB", "DL", "DB"].forEach(function (pos) {
      if (!by[pos]) return;
      html += '<div class="sec">' + pos + "</div>";
      by[pos].forEach(function (p) { html += rowHtml(p, { hide: false }); });
    });
    $("listLikes").innerHTML = html || '<p class="tiny">No likes yet. Turn on Edit and tap the star.</p>';
  }

  function renderPos(pos) {
    var id = "p" + pos.toLowerCase();
    var host = $(id);
    var bucket = (state.season.positions && state.season.positions[pos]) || { hint: "", players: [] };
    var list = bucket.players && bucket.players.length
      ? bucket.players
      : (state.season.players || []).filter(function (p) { return p.pos === pos; });
    if (!state.ready[pos]) {
      state.ready[pos] = true;
      state.posHide[pos] = true;
      host.innerHTML = '<p class="idp-hint">' + esc(bucket.hint || "") + "</p>" +
        '<label class="hide-drafted"><input type="checkbox" data-phide="' + pos + '" checked> Hide drafted</label>' +
        '<input type="search" data-pq="' + pos + '" placeholder="Search" autocomplete="off"><div id="list-' + pos + '"></div>';
    }
    var q = (state.posQ[pos] || "").toLowerCase();
    var rows = list.filter(function (p) {
      if (state.posHide[pos] && isDrafted(p.name)) return false;
      if (!q) return true;
      return (p.name + " " + (p.team || "") + " " + (p.note || "")).toLowerCase().indexOf(q) !== -1;
    });
    $("list-" + pos).innerHTML = rows.length ? rows.map(function (p) { return rowHtml(p); }).join("") : '<p class="tiny">No matches.</p>';
  }

  function renderIdp() {
    var g = (state.season && state.season.greenDot) || { linebackers: [], box: [], order: [], hint: "" };
    var edit = state.edit;
    function cell(value, kind, index, field) {
      if (!edit) return esc(value || "");
      return '<input data-dot="' + kind + '" data-i="' + index + '" data-f="' + field + '" value="' + esc(value || "") + '">';
    }
    var lbs = (g.linebackers || []).map(function (r, i) {
      return "<tr><td>" + cell(r.team, "lb", i, "team") + "</td><td>" + cell(r.greenDot, "lb", i, "greenDot") +
        "</td><td>" + cell(r.other, "lb", i, "other") + "</td><td>" + cell(r.notes, "lb", i, "notes") + "</td></tr>";
    }).join("");
    var box = (g.box || []).map(function (r, i) {
      return "<tr><td>" + cell(r.player, "box", i, "player") + "</td><td>" + cell(r.team, "box", i, "team") +
        "</td><td>" + cell(r.role, "box", i, "role") + "</td><td>" + cell(r.why, "box", i, "why") + "</td></tr>";
    }).join("");
    var order = (g.order || []).map(function (line) { return "<li>" + esc(line) + "</li>"; }).join("");
    $("pidp").innerHTML = '<p class="idp-hint">' + esc(g.hint || "") + "</p>" +
      '<div class="card"><h3>Green-dot linebackers</h3><div class="scroll"><table class="idp-table"><thead><tr><th>Team</th><th>Green dot</th><th>Other</th><th>Notes</th></tr></thead><tbody>' +
      lbs + "</tbody></table></div></div>" +
      '<div class="card"><h3>Box and slot safeties</h3><div class="scroll"><table class="idp-table"><thead><tr><th>Player</th><th>Team</th><th>Role</th><th>Why</th></tr></thead><tbody>' +
      box + "</tbody></table></div></div>" +
      '<div class="card"><h3>First IDP</h3><ul>' + order + "</ul></div>";
  }

  function renderLive() {
    var all = picks();
    var current = all[state.live.current - 1];
    var mine = yours();
    var recent = [];
    for (var i = state.live.current - 2; i >= 0 && recent.length < 8; i--) {
      if (all[i] && state.live.drafted && pickPlayer(all[i])) recent.push(all[i]);
    }
    var recentHtml = recent.length ? recent.map(function (p, idx) {
      var who = pickPlayer(p);
      return '<div class="recent-pick"><span>' + p.round + "." + p.pick + " " + esc(p.short) + " — <b>" + esc(who.name) + "</b> (" + esc(who.pos) + ")</span>" +
        (idx === 0 ? '<button type="button" class="undo-btn" id="btnUndo">UNDO</button>' : "") + "</div>";
    }).join("") : '<p class="tiny">No picks yet.</p>';
    var grid = all.map(function (p) {
      var who = pickPlayer(p);
      var cls = (p.overall === state.live.current ? " current" : "") + (p.owner === (state.season.user && state.season.user.owner) ? " yours" : "");
      return '<div class="pick-slot' + cls + '"><div class="pick-num">' + p.round + "." + (p.pick < 10 ? "0" : "") + p.pick +
        '</div><div class="pick-team">' + esc(p.short) + '</div><div class="pick-player' + (who ? " filled" : "") + '">' +
        (who ? esc(who.name) + " (" + esc(who.pos) + ")" : "—") + "</div></div>";
    }).join("");
    var next = mine.filter(function (n) { return n >= state.live.current; }).slice(0, 4).join(", ");
    $("plive").innerHTML = '<div class="live-header"><div class="pick-status">Clock: <span id="onClock"></span></div>' +
      '<button type="button" class="btn danger" id="btnReset">Reset draft</button></div>' +
      '<p class="tiny">Your picks: ' + esc(next || "none left") + ". A refresh keeps this draft.</p>" +
      '<div class="sec">Recent</div>' + recentHtml + '<div class="sec">Full draft</div>' + grid;
    paintClock();
  }

  function pickPlayer(slot) {
    var names = Object.keys(state.live.drafted);
    for (var i = 0; i < names.length; i++) {
      var d = state.live.drafted[names[i]];
      if (d.overall === slot.overall) return { name: names[i], pos: d.pos };
    }
    return null;
  }

  function renderSetup() {
    var host = $("psetup");
    var s = state.season;
    if (!state.ready.setup) {
      state.ready.setup = true;
      host.innerHTML = '<div class="card"><h3>This phone</h3><p id="phoneNote"></p><div class="actions">' +
        '<button type="button" class="btn ghost" id="btnReload">Reload the file</button>' +
        '<button type="button" class="btn" id="btnExport">Export season JSON</button></div>' +
        '<label class="tc-label">Import a season file</label><input type="file" id="fileJson" accept="application/json,.json"></div>' +
        '<div class="card"><h3>Rankings spreadsheet</h3><p>Download the template, fill a row per player, then bring it back here. If you fill the stat columns, points are scored with this league\'s rules, including the tight end premium and IDP tackles.</p>' +
        '<div class="actions"><a class="btn ghost" href="data/draft/rankings-template.csv" download>Download CSV template</a></div>' +
        '<label class="tc-label">Import CSV</label><input type="file" id="fileCsv" accept=".csv,text/csv"></div>' +
        '<div class="card"><h3>Add a player</h3><input id="addName" placeholder="Name"><input id="addPos" placeholder="POS"><input id="addTeam" placeholder="TEAM">' +
        '<button type="button" class="btn" id="btnAdd">Add to the board</button></div>' +
        '<div class="card"><h3>Draft order</h3><p>Round 1 runs top to bottom. Even rounds reverse. Your slot is wherever your name sits.</p>' +
        '<label class="hide-drafted"><input type="checkbox" id="straightSnake"' + (s.straightSnake ? " checked" : "") + "> Straight snake, no traded picks</label>" +
        '<label class="tc-label">Rounds</label><input type="number" id="rounds" min="1" max="30" value="' + esc(s.rounds || 16) + '">' +
        '<label class="tc-label">Your slot</label><input type="number" id="slot" min="1" value="' + esc(s.user && s.user.slot || 1) + '">' +
        '<div id="orderList"></div></div>' +
        '<div class="card"><h3>Season</h3><label class="tc-label">Open a season</label><select id="seasonPick"></select></div>';
    }
    $("phoneNote").textContent = state.fromPhone
      ? "Edits are saved on this phone. Export the file when you want that season kept for next time."
      : "This is the season file. Edits you make are kept on this phone.";
    $("seasonPick").innerHTML = state.years.map(function (y) {
      return '<option value="' + y + '"' + (y === state.year ? " selected" : "") + ">" + y + "</option>";
    }).join("");
    $("straightSnake").checked = !!s.straightSnake;
    if (document.activeElement !== $("rounds")) $("rounds").value = s.rounds || 16;
    if (document.activeElement !== $("slot")) $("slot").value = (s.user && s.user.slot) || 1;
    $("orderList").innerHTML = (s.teams || []).map(function (t, i) {
      var mine = s.user && t.owner === s.user.owner;
      return '<div class="order-row"><span>' + (i + 1) + ". " + esc(t.short || t.owner) + " · " + esc(t.name) + (mine ? " · you" : "") +
        '</span><button type="button" class="btn ghost" data-up="' + i + '">Up</button><button type="button" class="btn ghost" data-down="' + i + '">Down</button></div>';
    }).join("");
  }

  function paintClock() {
    var all = picks();
    var slot = all[state.live.current - 1];
    var mine = yours();
    var until = 0;
    for (var i = 0; i < mine.length; i++) {
      if (mine[i] >= state.live.current) { until = mine[i] - state.live.current; break; }
    }
    var clock = slot ? (slot.round + "." + (slot.pick < 10 ? "0" : "") + slot.pick + " " + slot.owner) : "Done";
    var onClock = $("stripClock");
    if (onClock) onClock.textContent = clock;
    var untilEl = $("stripUntil");
    if (untilEl) untilEl.textContent = mine.indexOf(state.live.current) !== -1 ? "YOU'RE UP" : ("You're up in " + until);
    var liveClock = $("onClock");
    if (liveClock) liveClock.textContent = clock;
    var alert = $("turnAlert");
    var yoursNow = mine.indexOf(state.live.current) !== -1;
    if (alert) alert.classList.toggle("show", yoursNow);
    if (yoursNow && state.lastAlert !== state.live.current) {
      state.lastAlert = state.live.current;
      playCaw();
      if (navigator.vibrate) navigator.vibrate([200, 80, 200]);
    }
    var mute = $("btnMute");
    if (mute) mute.textContent = state.live.muted ? "Muted" : "Sound";
  }

  function renderChips() {
    var el = $("chips");
    if (!el || !state.season) return;
    el.innerHTML = (state.season.targets || []).map(function (n) {
      return '<div class="chip' + (isDrafted(n) ? " gone" : "") + '">' + esc(n) + "</div>";
    }).join("");
  }

  function render() {
    if (!state.season) return;
    scoreVor();
    paintClock();
    renderChips();
    if (state.tab === "pboard") renderBoard();
    else if (state.tab === "plikes") renderLikes();
    else if (state.tab === "pidp") renderIdp();
    else if (state.tab === "plive") renderLive();
    else if (state.tab === "psetup") renderSetup();
    else {
      POS_TABS.forEach(function (pos) {
        if (state.tab === "p" + pos.toLowerCase()) renderPos(pos);
      });
    }
    var edit = $("btnEdit");
    if (edit) edit.textContent = state.edit ? "Done" : "Edit";
  }

  function show(id) {
    state.tab = id;
    document.querySelectorAll("nav button").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-p") === id);
    });
    document.querySelectorAll(".panel").forEach(function (p) { p.classList.toggle("active", p.id === id); });
    render();
  }

  function playCaw() {
    if (state.live.muted) return;
    var audio = $("eagleCaw");
    if (!audio) return;
    try {
      audio.currentTime = 0;
      var pending = audio.play();
      if (pending && pending.catch) pending.catch(function () {});
    } catch (e) {}
  }

  function draftPlayer(name, pos) {
    if (isDrafted(name)) return;
    var all = picks();
    var slot = all[state.live.current - 1];
    if (!slot) return;
    state.live.drafted[name] = { overall: slot.overall, pos: pos, team: slot.team, owner: slot.owner };
    state.live.current += 1;
    saveLive();
    render();
  }

  function undo() {
    if (state.live.current <= 1) return;
    state.live.current -= 1;
    var overall = picks()[state.live.current - 1].overall;
    Object.keys(state.live.drafted).forEach(function (name) {
      if (state.live.drafted[name].overall === overall) delete state.live.drafted[name];
    });
    saveLive();
    render();
  }

  function resetDraft() {
    if (!confirm("Clear every pick in this draft?")) return;
    state.live.drafted = {};
    state.live.current = 1;
    state.lastAlert = 0;
    saveLive();
    render();
  }

  function eachNamed(name, fn) {
    function walk(list) { (list || []).forEach(function (p) { if (p.name === name) fn(p); }); }
    walk(state.season.players);
    walk(state.season.likes);
    var positions = state.season.positions || {};
    Object.keys(positions).forEach(function (k) { walk(positions[k].players); });
  }

  function patch(name, fields) {
    eachNamed(name, function (p) {
      Object.keys(fields).forEach(function (k) { p[k] = fields[k]; });
    });
    if (fields.like === true) {
      var likes = state.season.likes || (state.season.likes = []);
      if (!likes.some(function (p) { return p.name === name; })) {
        var found = (state.season.players || []).filter(function (p) { return p.name === name; })[0];
        if (found) likes.push(Object.assign({}, found));
      }
    }
    if (fields.like === false && state.season.likes) {
      state.season.likes = state.season.likes.filter(function (p) { return p.name !== name; });
    }
    saveBoard();
    render();
  }

  function moveTeam(index, dir) {
    var teams = state.season.teams;
    var j = index + dir;
    if (j < 0 || j >= teams.length) return;
    var tmp = teams[index];
    teams[index] = teams[j];
    teams[j] = tmp;
    var owner = state.season.user && state.season.user.owner;
    var slot = teams.findIndex(function (t) { return t.owner === owner; }) + 1;
    if (slot > 0) state.season.user.slot = slot;
    saveBoard();
    render();
  }

  function parseCsv(text) {
    var rows = [];
    var row = [];
    var cur = "";
    var quoted = false;
    text = String(text || "").replace(/^\uFEFF/, "");
    for (var i = 0; i < text.length; i++) {
      var c = text[i];
      if (quoted) {
        if (c === '"') {
          if (text[i + 1] === '"') { cur += '"'; i++; }
          else quoted = false;
        } else cur += c;
      } else if (c === '"') quoted = true;
      else if (c === ",") { row.push(cur); cur = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(cur);
        cur = "";
        if (row.some(function (cell) { return cell !== ""; })) rows.push(row);
        row = [];
      } else cur += c;
    }
    if (cur.length || row.length) {
      row.push(cur);
      if (row.some(function (cell) { return cell !== ""; })) rows.push(row);
    }
    return rows;
  }

  function importCsv(text) {
    var table = parseCsv(text);
    if (!table.length) return;
    var head = table[0].map(function (h) { return h.trim().toLowerCase(); });
    var idx = {};
    head.forEach(function (h, i) { idx[h] = i; });
    function col(cells, name) {
      if (idx[name] == null) return "";
      return (cells[idx[name]] || "").trim();
    }
    var statKeys = ["passyds", "passtd", "interceptions", "rushyds", "rushtd", "carries", "receptions", "recyds", "rectd", "tefirstdowns", "solo", "assisted", "sacks", "tfl", "pd", "defint"];
    var statMap = { passyds: "passYds", passtd: "passTd", interceptions: "interceptions", rushyds: "rushYds", rushtd: "rushTd", carries: "carries", receptions: "receptions", recyds: "recYds", rectd: "recTd", tefirstdowns: "teFirstDowns", solo: "solo", assisted: "assisted", sacks: "sacks", tfl: "tfl", pd: "pd", defint: "defInt" };
    var players = [];
    for (var r = 1; r < table.length; r++) {
      var cells = table[r];
      var name = col(cells, "name");
      var note = col(cells, "note");
      if (!name || /delete this example/i.test(note)) continue;
      var pos = col(cells, "pos").toUpperCase();
      var stats = {};
      var any = false;
      statKeys.forEach(function (k) {
        var raw = col(cells, k);
        if (raw !== "") { stats[statMap[k]] = Number(raw); any = true; }
      });
      var pts = col(cells, "pts") === "" ? null : Number(col(cells, "pts"));
      if (any && state.scoring) pts = WUScore.scoreLine(stats, pos, state.scoring);
      players.push({
        name: name,
        pos: pos,
        team: col(cells, "team").toUpperCase(),
        rank: Number(col(cells, "rank")) || players.length + 1,
        tier: col(cells, "tier").toUpperCase(),
        verdict: col(cells, "verdict").toUpperCase(),
        like: /^(y|yes|true|1|star)$/i.test(col(cells, "like")),
        note: note,
        pts: pts,
        y25: col(cells, "y25") === "" ? null : Number(col(cells, "y25")),
        role: col(cells, "role"),
        window: col(cells, "window")
      });
    }
    state.season.players = players;
    state.season.likes = players.filter(function (p) { return p.like; }).map(function (p) { return Object.assign({}, p); });
    state.season.positions = state.season.positions || {};
    ["QB", "RB", "WR", "TE", "LB", "DL", "DB"].forEach(function (pos) {
      var prev = state.season.positions[pos] || {};
      state.season.positions[pos] = {
        hint: prev.hint || "",
        players: players.filter(function (p) { return p.pos === pos; }).map(function (p) { return Object.assign({}, p); })
      };
    });
    state.ready = { setup: state.ready.setup };
    saveBoard();
    render();
  }

  function exportJson() {
    var blob = new Blob([JSON.stringify(state.season, null, 2)], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (state.season.season || state.year) + ".json";
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  function copyBoard() {
    var lines = ["Available — pick " + state.live.current];
    (state.season.players || []).filter(function (p) { return !isDrafted(p.name); }).slice(0, 40).forEach(function (p) {
      lines.push((p.rank || "") + ". " + p.name + " (" + p.pos + " " + (p.team || "") + ")");
    });
    var text = lines.join("\n");
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(function () { prompt("Copy this:", text); });
    } else prompt("Copy this:", text);
  }

  function onClick(event) {
    var tab = event.target.closest("nav button");
    if (tab) { show(tab.getAttribute("data-p")); return; }
    var filt = event.target.closest("#filt button");
    if (filt) {
      state.filter = filt.getAttribute("data-pos");
      document.querySelectorAll("#filt button").forEach(function (b) { b.classList.toggle("on", b === filt); });
      renderBoard();
      return;
    }
    var sort = event.target.closest("#sorts button");
    if (sort) {
      state.sort = sort.getAttribute("data-sort");
      document.querySelectorAll("#sorts button").forEach(function (b) { b.classList.toggle("on", b === sort); });
      renderBoard();
      return;
    }
    var like = event.target.closest("[data-like]");
    if (like) {
      state.likeFilter = like.getAttribute("data-like");
      document.querySelectorAll("#filtLikes button").forEach(function (b) { b.classList.toggle("on", b === like); });
      renderLikes();
      return;
    }
    var draftBtn = event.target.closest("[data-draft]");
    if (draftBtn) {
      state.pending = { name: draftBtn.getAttribute("data-draft"), pos: draftBtn.getAttribute("data-pos") };
      var slot = picks()[state.live.current - 1];
      $("modalTxt").textContent = "Mark " + state.pending.name + " drafted to " + (slot ? slot.owner : "?") + " at " + (slot ? slot.round + "." + slot.pick : "?") + "?";
      $("modal").classList.add("show");
      return;
    }
    if (event.target.id === "modalOk") {
      $("modal").classList.remove("show");
      if (state.pending) draftPlayer(state.pending.name, state.pending.pos);
      state.pending = null;
      return;
    }
    if (event.target.id === "modalNo") { $("modal").classList.remove("show"); state.pending = null; return; }
    if (event.target.id === "btnUndo" || event.target.id === "btnUndo2") { undo(); return; }
    if (event.target.id === "btnReset") { resetDraft(); return; }
    if (event.target.id === "btnMute") { state.live.muted = !state.live.muted; saveLive(); render(); return; }
    if (event.target.id === "btnTest") { state.live.muted = false; saveLive(); playCaw(); render(); return; }
    if (event.target.id === "btnCopy") { copyBoard(); return; }
    if (event.target.id === "btnEdit") { state.edit = !state.edit; state.ready.idp = false; render(); return; }
    var star = event.target.closest("[data-star]");
    if (star) {
      var current = false;
      eachNamed(star.getAttribute("data-name"), function (p) { current = !!p.like; });
      patch(star.getAttribute("data-name"), { like: !current });
      return;
    }
    var drop = event.target.closest("[data-drop]");
    if (drop) {
      var name = drop.getAttribute("data-name");
      function without(list) { return (list || []).filter(function (p) { return p.name !== name; }); }
      state.season.players = without(state.season.players);
      state.season.likes = without(state.season.likes);
      Object.keys(state.season.positions || {}).forEach(function (k) {
        state.season.positions[k].players = without(state.season.positions[k].players);
      });
      saveBoard();
      render();
      return;
    }
    var up = event.target.closest("[data-up]");
    if (up) { moveTeam(+up.getAttribute("data-up"), -1); return; }
    var down = event.target.closest("[data-down]");
    if (down) { moveTeam(+down.getAttribute("data-down"), 1); return; }
    if (event.target.id === "btnAdd") {
      var name = $("addName").value.trim();
      var pos = $("addPos").value.trim().toUpperCase();
      if (!name || !pos) return;
      var player = { name: name, pos: pos, team: $("addTeam").value.trim().toUpperCase(), rank: (state.season.players || []).length + 1, tier: "T5", verdict: "", like: false, note: "", pts: null };
      state.season.players.push(player);
      if (state.season.positions && state.season.positions[pos]) state.season.positions[pos].players.push(Object.assign({}, player));
      saveBoard();
      $("addName").value = "";
      render();
      return;
    }
    if (event.target.id === "btnExport") { exportJson(); return; }
    if (event.target.id === "btnReload") {
      localStorage.removeItem(yearKey(state.year));
      state.fromPhone = false;
      loadSeason(state.year, true);
    }
  }

  function onChange(event) {
    var edit = event.target.closest("[data-edit]");
    if (edit) {
      var field = edit.getAttribute("data-edit");
      var value = edit.value;
      if (field === "tier" && value === "Tier") value = "";
      if (field === "verdict" && value === "Verdict") value = "";
      patch(edit.getAttribute("data-name"), field === "note" ? { note: value } : (field === "tier" ? { tier: value } : { verdict: value }));
      return;
    }
    var dot = event.target.closest("[data-dot]");
    if (dot) {
      var kind = dot.getAttribute("data-dot");
      var list = kind === "lb" ? state.season.greenDot.linebackers : state.season.greenDot.box;
      var row = list[+dot.getAttribute("data-i")];
      if (row) row[dot.getAttribute("data-f")] = dot.value;
      saveBoard();
      return;
    }
    if (event.target.id === "straightSnake") {
      state.season.straightSnake = event.target.checked;
      saveBoard();
      render();
      return;
    }
    if (event.target.id === "rounds") {
      state.season.rounds = Math.max(1, Number(event.target.value) || 16);
      saveBoard();
      render();
      return;
    }
    if (event.target.id === "slot") {
      state.season.teams = WUDraft.setUserSlot(state.season, Number(event.target.value) || 1);
      state.season.user.slot = Number(event.target.value) || 1;
      saveBoard();
      render();
      return;
    }
    if (event.target.id === "seasonPick") {
      loadSeason(Number(event.target.value), false);
      return;
    }
    if (event.target.id === "hideDrafted") { state.hide = event.target.checked; renderBoard(); return; }
    var ph = event.target.getAttribute && event.target.getAttribute("data-phide");
    if (ph) { state.posHide[ph] = event.target.checked; renderPos(ph); }
  }

  function onInput(event) {
    if (event.target.id === "q") { state.q = event.target.value.trim(); renderBoard(); return; }
    var pq = event.target.getAttribute && event.target.getAttribute("data-pq");
    if (pq) { state.posQ[pq] = event.target.value.trim(); renderPos(pq); }
  }

  function readFile(input, cb) {
    var file = input.files && input.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function () { cb(String(reader.result || "")); input.value = ""; };
    reader.readAsText(file);
  }

  async function loadSeason(year, forceFile) {
    state.year = year;
    var saved = null;
    if (!forceFile) {
      try { saved = JSON.parse(localStorage.getItem(yearKey(year)) || "null"); } catch (e) {}
    }
    if (saved && saved.players) {
      state.season = saved;
      state.fromPhone = true;
    } else {
      var res = await WUData.load("data/draft/" + year + ".json");
      state.season = res.data;
      state.fromPhone = false;
    }
    if (!state.season) return;
    state.ready = {};
    var live = null;
    try { live = JSON.parse(localStorage.getItem(liveKey(year)) || "null"); } catch (e2) {}
    state.live = {
      drafted: (live && live.drafted) || {},
      current: (live && live.current) || 1,
      muted: !!(live && live.muted)
    };
    var title = $("title");
    if (title) title.textContent = (state.season.title || ("WU" + year + " War Room"));
    document.title = state.season.title || document.title;
    render();
  }

  async function boot() {
    var index = await WUData.load("data/draft/index.json");
    var extra = [];
    try { extra = JSON.parse(localStorage.getItem("wu-draft-seasons") || "[]"); } catch (e) {}
    var years = ((index.data && index.data.seasons) || [2026]).concat(extra);
    state.years = years.filter(function (y, i) { return years.indexOf(y) === i; }).sort();
    var scoring = await WUData.load(WUData.HQ + "scoring.json", "data/scoring.json");
    state.scoring = scoring.data;
    state.lineup = lineupFrom(state.scoring);
    document.body.addEventListener("click", onClick);
    document.body.addEventListener("change", onChange);
    document.body.addEventListener("input", onInput);
    document.body.addEventListener("change", function (event) {
      if (event.target.id === "fileCsv") readFile(event.target, importCsv);
      if (event.target.id === "fileJson") {
        readFile(event.target, function (text) {
          var data;
          try { data = JSON.parse(text); } catch (e) {
            window.alert("That file could not be read. Export a season file and try that one.");
            return;
          }
          if (!data || !data.players) {
            window.alert("That file is not a season board.");
            return;
          }
          var year = data.season || state.year;
          state.season = data;
          state.year = year;
          if (state.years.indexOf(year) === -1) state.years.push(year);
          try {
            var bag = JSON.parse(localStorage.getItem("wu-draft-seasons") || "[]");
            if (bag.indexOf(year) === -1) bag.push(year);
            localStorage.setItem("wu-draft-seasons", JSON.stringify(bag));
          } catch (e) {}
          saveBoard();
          state.ready = {};
          render();
        });
      }
    });
    await loadSeason(state.years[state.years.length - 1] || 2026, false);
    show("pboard");
  }

  boot().catch(function (err) {
    var el = $("pboard");
    if (el) el.innerHTML = '<div class="card"><p>The draft board did not load.</p></div>';
    console.error(err);
  });
})();
