/* Desk trade check for Eagleridge Eddie's. Runs in the browser.
   Rosters, power rankings, the latest score file, club colors, and the
   lineup rules are the copies already in this repo. Week score files
   (scores-wN-2026.json) are not stored here; those are read from the
   public league site. Owner, contact, and pending bid/trade fields are
   never shown. Nothing is written back. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (typeof document !== "undefined") api.mount();
  root.WUTradeAnalyzer = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var OFFENSE = ["QB", "RB", "WR", "TE"];
  var IDP = ["DL", "LB", "DB"];
  var SLOT_ORDER = OFFENSE.concat(IDP, ["IR"]);
  var POS_LABEL = {
    QB: "QB",
    RB: "RB",
    WR: "WR",
    TE: "TE",
    RWT: "RWT flex",
    DL: "DL",
    LB: "LB",
    DB: "DB",
    ID: "ID flex",
    IR: "IR"
  };
  var FEATURED = "Eagleridge Eddie's";
  var HQ = "https://wjenson27-cpu.github.io/wheels-up-league-hq/data/";
  var LOCAL = {
    rosterIndex: "data/hq/rosters/index.json",
    rankings: "data/hq/rankings.json",
    scoring: "data/scoring.json",
    teams: "data/hq/teams.json",
    scores: "data/hq/scores.json"
  };
  var PRIVATE_TEXT = /@[a-z0-9.-]+\.[a-z]{2,}|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b/i;

  function rosterPath(id) {
    return "data/hq/rosters/" + id + ".json";
  }

  function weekScoreRequest(week) {
    var n = Number(week);
    if (!Number.isInteger(n) || n < 1 || n > 30) return null;
    var name = "scores-w" + n + "-2026.json";
    return { local: "data/hq/" + name, remote: HQ + name };
  }

  function playerKey(name) {
    return String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  function publicLabel(value) {
    var text = String(value == null ? "" : value).trim();
    if (!text || PRIVATE_TEXT.test(text)) return "";
    return text;
  }

  function playerName(entry) {
    if (typeof entry === "string") return entry.trim();
    if (entry && typeof entry === "object" && typeof entry.name === "string") return entry.name.trim();
    return "";
  }

  function clubName(id, rosterName, featured) {
    if (id === "eddies") return featured || FEATURED;
    if (id === "ttab") return "TTAB";
    return rosterName || id;
  }

  function lineupFromScoring(data) {
    var raw = data && data.roster && data.roster.startingLineup;
    if (!raw) return null;
    function num(key) {
      var n = Number(raw[key]);
      return Number.isInteger(n) && n >= 0 ? n : null;
    }
    var lineup = {
      QB: num("QB"),
      RB: num("RB"),
      WR: num("WR"),
      TE: num("TE"),
      RWT: num("RWT_flex_RB_WR_TE"),
      DL: num("DL"),
      LB: num("LB"),
      DB: num("DB"),
      ID: num("ID_flex_any_IDP")
    };
    if (Object.keys(lineup).some(function (key) { return lineup[key] == null; })) return null;
    return lineup;
  }

  function rosterPlayers(roster) {
    var chart = roster && roster.roster;
    if (!chart || typeof chart !== "object") return [];
    var irNames = new Set(
      (Array.isArray(chart.IR) ? chart.IR : []).map(function (entry) {
        return playerKey(publicLabel(playerName(entry)));
      }).filter(Boolean)
    );
    var keys = SLOT_ORDER.filter(function (pos) { return Array.isArray(chart[pos]); });
    var extra = Object.keys(chart).filter(function (pos) {
      return SLOT_ORDER.indexOf(pos) === -1 && /^[A-Z]{1,4}$/.test(pos) && Array.isArray(chart[pos]);
    });
    var players = [];
    var seen = new Set();
    keys.concat(extra).forEach(function (pos) {
      chart[pos].forEach(function (entry) {
        var name = publicLabel(playerName(entry));
        var key = playerKey(name);
        if (!key || seen.has(key)) return;
        seen.add(key);
        var ir = pos === "IR" || irNames.has(key);
        players.push({ name: name, key: key, pos: ir ? "IR" : pos, ir: ir });
      });
    });
    return players;
  }

  function activeCounts(players) {
    var counts = { QB: 0, RB: 0, WR: 0, TE: 0, DL: 0, LB: 0, DB: 0 };
    players.forEach(function (player) {
      if (player.ir || counts[player.pos] == null) return;
      counts[player.pos] += 1;
    });
    return counts;
  }

  function depthReport(counts, lineup) {
    var have = {};
    OFFENSE.concat(IDP).forEach(function (pos) {
      have[pos] = Math.max(0, Number(counts[pos]) || 0);
    });
    var remain = {};
    var holes = [];
    var dedicatedFilled = 0;
    OFFENSE.concat(IDP).forEach(function (pos) {
      var need = lineup[pos];
      var got = Math.min(have[pos], need);
      dedicatedFilled += got;
      remain[pos] = have[pos] - got;
      if (got < need) holes.push({ pos: pos, short: need - got, group: IDP.indexOf(pos) !== -1 ? "IDP" : "offense" });
    });
    var rwtPool = remain.RB + remain.WR + remain.TE;
    var rwtFilled = Math.min(lineup.RWT, rwtPool);
    if (rwtFilled < lineup.RWT) holes.push({ pos: "RWT", short: lineup.RWT - rwtFilled, group: "offense" });
    var idPool = remain.DL + remain.LB + remain.DB;
    var idFilled = Math.min(lineup.ID, idPool);
    if (idFilled < lineup.ID) holes.push({ pos: "ID", short: lineup.ID - idFilled, group: "IDP" });
    var starterNeed = OFFENSE.concat(IDP).reduce(function (sum, pos) { return sum + lineup[pos]; }, 0) + lineup.RWT + lineup.ID;
    return {
      have: have,
      holes: holes,
      starters: dedicatedFilled + rwtFilled + idFilled,
      starterNeed: starterNeed,
      bench: (rwtPool - rwtFilled) + (idPool - idFilled)
    };
  }

  function applyDeal(players, sendKeys, receivePlayers) {
    var drop = sendKeys instanceof Set ? sendKeys : new Set(sendKeys);
    var next = players.filter(function (player) { return !drop.has(player.key); }).map(function (player) {
      return Object.assign({}, player);
    });
    var have = new Set(next.map(function (player) { return player.key; }));
    (receivePlayers || []).forEach(function (player) {
      if (!player || have.has(player.key)) return;
      next.push(Object.assign({}, player));
      have.add(player.key);
    });
    return next;
  }

  function addWeekLogs(store, file) {
    if (!file || !Array.isArray(file.matchups)) return store;
    var week = Number(file.week);
    if (!Number.isInteger(week)) return store;
    file.matchups.forEach(function (game) {
      ((game && game.topScorers) || []).forEach(function (row) {
        var key = playerKey(row && row.player);
        var pts = Number(row && row.pts);
        if (!key || !Number.isFinite(pts)) return;
        if (!store.has(key)) store.set(key, new Map());
        var weeks = store.get(key);
        if (!weeks.has(week)) weeks.set(week, pts);
      });
    });
    return store;
  }

  function loggedTotal(store, key) {
    var weeks = store.get(key);
    if (!weeks || !weeks.size) return null;
    var sum = 0;
    weeks.forEach(function (pts) { sum += pts; });
    return sum;
  }

  function dealPoints(store, players) {
    var knownSum = 0;
    var known = 0;
    var missing = 0;
    var rows = players.map(function (player) {
      var pts = loggedTotal(store, player.key);
      if (pts == null) missing += 1;
      else {
        known += 1;
        knownSum += pts;
      }
      return { name: player.name, pos: player.pos, ir: player.ir, pts: pts };
    });
    return {
      rows: rows,
      known: known,
      missing: missing,
      knownSum: known ? knownSum : null,
      sum: missing || !known ? null : knownSum
    };
  }

  function depthEdge(beforeA, afterA, beforeB, afterB) {
    var startersA = afterA.starters - beforeA.starters;
    var startersB = afterB.starters - beforeB.starters;
    var benchA = afterA.bench - beforeA.bench;
    var benchB = afterB.bench - beforeB.bench;
    var netStarters = startersA - startersB;
    var side = "even";
    if (netStarters > 0) side = "a";
    else if (netStarters < 0) side = "b";
    else if (benchA - benchB > 0) side = "a";
    else if (benchA - benchB < 0) side = "b";
    return { startersA: startersA, startersB: startersB, benchA: benchA, benchB: benchB, netStarters: netStarters, side: side };
  }

  function pointsEdge(pointsA, pointsB) {
    if (!pointsA || !pointsB || pointsA.sum == null || pointsB.sum == null) {
      return { side: "unknown", diff: null };
    }
    var diff = pointsA.sum - pointsB.sum;
    if (diff > 0.05) return { side: "a", diff: diff };
    if (diff < -0.05) return { side: "b", diff: -diff };
    return { side: "even", diff: 0 };
  }

  function formatPts(n) {
    if (!Number.isFinite(Number(n))) return "—";
    var rounded = Math.round(Number(n) * 10) / 10;
    return String(rounded);
  }

  function safeId(id) {
    return /^[a-z0-9-]{1,40}$/.test(String(id || "")) ? String(id) : "";
  }

  function safeColor(value) {
    return /^#[0-9a-fA-F]{3,8}$/.test(String(value || "")) ? String(value) : "#69BE28";
  }

  function safeAbbrev(value, id) {
    var text = String(value || "");
    if (/^[A-Z0-9]{2,6}$/.test(text)) return text;
    return String(id || "").slice(0, 3).toUpperCase();
  }

  function rankIndex(rankings) {
    var map = new Map();
    if (!rankings || rankings.pendingPublish === true) return map;
    (rankings.rankings || []).forEach(function (row) {
      if (!row || row.pendingPublish === true || !row.teamId) return;
      map.set(row.teamId, {
        rank: Number.isFinite(Number(row.rank)) ? Number(row.rank) : null,
        pf: Number.isFinite(Number(row.pf)) ? Number(row.pf) : null
      });
    });
    return map;
  }

  function colorIndex(teamsFile) {
    var map = new Map();
    ((teamsFile && teamsFile.teams) || []).forEach(function (team) {
      if (!team || !team.id) return;
      map.set(team.id, {
        color: safeColor(team.color),
        abbrev: safeAbbrev(team.abbrev, team.id)
      });
    });
    return map;
  }

  function teamRecord(id, roster, meta, rank, featured) {
    var rosterName = publicLabel(roster && roster.teamName);
    var name = publicLabel(clubName(id, rosterName, featured || FEATURED)) || id;
    return {
      id: id,
      name: name,
      color: safeColor(meta && meta.color),
      abbrev: safeAbbrev(meta && meta.abbrev, id),
      rank: rank && Number.isFinite(Number(rank.rank)) ? Number(rank.rank) : null,
      pf: rank && Number.isFinite(Number(rank.pf)) ? Number(rank.pf) : null,
      players: rosterPlayers(roster)
    };
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function holeText(hole) {
    var label = POS_LABEL[hole.pos] || hole.pos;
    return "Short " + hole.short + " " + label;
  }

  function seasonLine(team) {
    if (team.rank == null && team.pf == null) return "Season points are not on the published board.";
    var bits = [];
    if (team.rank != null) bits.push("Power #" + team.rank);
    if (team.pf != null) bits.push(formatPts(team.pf) + " season points");
    return bits.join(" · ") + ". From the power rankings file. It does not move with this deal.";
  }

  function depthSentence(edge, nameA, nameB) {
    if (edge.netStarters === 0 && edge.side === "even") return "Starter slots and bench depth are about even.";
    if (edge.netStarters === 0) {
      var benchName = edge.side === "a" ? nameA : nameB;
      return "Starter slots are even. Bench depth favors " + benchName + ".";
    }
    var name = edge.side === "a" ? nameA : nameB;
    return "Depth favors " + name + ".";
  }

  function pointsSentence(edge, nameA, nameB) {
    if (edge.side === "unknown") return "No points edge. A player in the deal has no week log, so the logged total is incomplete. These are week logs, not a forecast.";
    if (edge.side === "even") return "Logged points are even. These are week logs, not a forecast.";
    var name = edge.side === "a" ? nameA : nameB;
    return "Logged points favor " + name + " by " + formatPts(edge.diff) + ". These are week logs, not a forecast.";
  }

  function depthTable(before, after) {
    var rows = OFFENSE.concat(IDP).map(function (pos) {
      var now = before.have[pos];
      var later = after.have[pos];
      var changed = later !== now ? "is-changed" : "";
      return "<tr class=\"" + changed + "\"><th scope=\"row\">" + esc(pos) + "</th><td>" + now + "</td><td>" + later + "</td></tr>";
    }).join("");
    var holes = after.holes.length
      ? after.holes.map(function (hole) { return "<li>" + esc(holeText(hole)) + "</li>"; }).join("")
      : "<li>No hole in the starting lineup.</li>";
    return "<table class=\"ta-table\"><thead><tr><th scope=\"col\">Pos</th><th scope=\"col\">Now</th><th scope=\"col\">After</th></tr></thead><tbody>" +
      rows + "</tbody></table><p class=\"ta-starters\">" + before.starters + "/" + before.starterNeed +
      " starters → " + after.starters + "/" + after.starterNeed + ". Bench " + before.bench + " → " + after.bench +
      ".</p><ul class=\"ta-holes\">" + holes + "</ul>";
  }

  function pointRows(packet) {
    if (!packet.rows.length) return "<p class=\"ta-empty\">No players marked.</p>";
    return "<ul class=\"ta-points\">" + packet.rows.map(function (row) {
      var logged = row.pts == null ? "no week log" : formatPts(row.pts) + " logged";
      var tag = row.ir ? " · IR" : "";
      return "<li><span>" + esc(row.name) + "</span> <span class=\"ta-pos\">" + esc(row.pos) + tag + "</span> <strong>" + esc(logged) + "</strong></li>";
    }).join("") + "</ul>";
  }

  function meterBar(edge, colorA, colorB) {
    var net = Math.max(-4, Math.min(4, edge.netStarters));
    var widthA = 50 + net * 10;
    var widthB = 100 - widthA;
    return "<div class=\"ta-meter\" role=\"img\" aria-label=\"Depth meter\"><span style=\"width:" + widthA +
      "%;background:" + esc(colorA) + "\"></span><span style=\"width:" + widthB + "%;background:" + esc(colorB) + "\"></span></div>";
  }

  var state = {
    teams: [],
    lineup: null,
    logs: new Map(),
    featured: FEATURED,
    sideA: "eddies",
    sideB: "ultron",
    pickA: new Set(),
    pickB: new Set()
  };
  var started = false;

  function teamById(id) {
    return state.teams.filter(function (team) { return team.id === id; })[0] || null;
  }

  function sideCard(team, before, after, packet) {
    return "<article class=\"ta-side\" data-team=\"" + esc(team.id) + "\"><h3><span class=\"ta-mark\" style=\"background:" +
      esc(team.color) + "\"></span> " + esc(team.name) + " <span class=\"ta-pos\">" + esc(team.abbrev) +
      "</span></h3><p class=\"ta-season\">" + esc(seasonLine(team)) + "</p><div data-depth=\"" + esc(team.id) + "\">" +
      depthTable(before, after) + "</div><h4>Players in the deal</h4><div data-points=\"" + esc(team.id) + "\">" +
      pointRows(packet) + "</div></article>";
  }

  function playerColumn(team, picks, side) {
    var groups = [];
    var shownIdp = false;
    SLOT_ORDER.forEach(function (pos) {
      var players = team.players.filter(function (player) {
        return (player.ir ? "IR" : player.pos) === pos;
      });
      if (!players.length) return;
      if (IDP.indexOf(pos) !== -1 && !shownIdp) {
        groups.push("<p class=\"pos-label\" data-group=\"idp\">IDP</p>");
        shownIdp = true;
      }
      var boxes = players.map(function (player) {
        var checked = picks.has(player.key) ? " checked" : "";
        return "<label class=\"ta-player\"><input type=\"checkbox\" data-side=\"" + side + "\" data-key=\"" +
          esc(player.key) + "\"" + checked + " /><span>" + esc(player.name) + "</span><span class=\"ta-pos\">" +
          esc(player.ir ? "IR" : player.pos) + "</span></label>";
      }).join("");
      groups.push("<div class=\"pos-block\"><div class=\"pos-label\">" + esc(POS_LABEL[pos] || pos) + "</div>" + boxes + "</div>");
    });
    return "<section class=\"card ta-roster\" data-roster=\"" + esc(team.id) + "\"><h3>" + esc(team.name) + "</h3>" + groups.join("") + "</section>";
  }

  function render() {
    var app = document.getElementById("taApp");
    if (!app) return;
    app.removeAttribute("aria-busy");
    var teamA = teamById(state.sideA);
    var teamB = teamById(state.sideB);
    if (!state.lineup || !teamA || !teamB) {
      app.innerHTML = "<div class=\"banner\">Roster or lineup files are unavailable. No depth or points were filled in.</div>";
      return;
    }
    var same = teamA.id === teamB.id;
    var markedA = teamA.players.filter(function (player) { return state.pickA.has(player.key); });
    var markedB = teamB.players.filter(function (player) { return state.pickB.has(player.key); });
    var afterPlayersA = same ? teamA.players : applyDeal(teamA.players, state.pickA, markedB);
    var afterPlayersB = same ? teamB.players : applyDeal(teamB.players, state.pickB, markedA);
    var beforeA = depthReport(activeCounts(teamA.players), state.lineup);
    var beforeB = depthReport(activeCounts(teamB.players), state.lineup);
    var afterA = depthReport(activeCounts(afterPlayersA), state.lineup);
    var afterB = depthReport(activeCounts(afterPlayersB), state.lineup);
    var edge = depthEdge(beforeA, afterA, beforeB, afterB);
    var ptsA = dealPoints(state.logs, markedA);
    var ptsB = dealPoints(state.logs, markedB);
    var pEdge = pointsEdge(ptsA, ptsB);
    var options = state.teams.map(function (team) {
      return "<option value=\"" + esc(team.id) + "\">" + esc(team.name) + "</option>";
    }).join("");
    var lists = same
      ? "<p class=\"ta-note\">Pick two different clubs.</p>"
      : "<div class=\"ta-grid\">" + playerColumn(teamA, state.pickA, "a") + playerColumn(teamB, state.pickB, "b") + "</div>";
    var dealOpen = !same && (markedA.length || markedB.length);
    var summary = same
      ? "Pick two different clubs to see depth and logged points."
      : dealOpen
        ? depthSentence(edge, teamA.name, teamB.name) + " " + pointsSentence(pEdge, teamA.name, teamB.name)
        : "Mark the players moving each way. The tables are the current depth charts, offense and IDP.";
    app.innerHTML = "<div class=\"ta-picks\"><label>Sends <select id=\"taSideA\" data-side=\"a\">" + options +
      "</select></label><label>Receives from <select id=\"taSideB\" data-side=\"b\">" + options +
      "</select></label></div><section class=\"card ta-result\" id=\"taResult\"><h2>This deal</h2><p class=\"ta-summary\">" +
      esc(summary) + "</p>" + (dealOpen ? meterBar(edge, teamA.color, teamB.color) : "") + "<div class=\"ta-grid\">" +
      sideCard(teamA, beforeA, afterA, ptsA) + sideCard(teamB, beforeB, afterB, ptsB) +
      "</div><p class=\"ta-note\">IDP starters are DL, LB, and DB, plus the ID flex. RWT flex is RB, WR, and TE. IR is not active depth. Logged points come from the posted week score files and only where that player was listed. A blank log is not zero.</p></section>" +
      lists;
    var selA = document.getElementById("taSideA");
    var selB = document.getElementById("taSideB");
    if (selA) selA.value = teamA.id;
    if (selB) selB.value = teamB.id;
  }

  function onChange(ev) {
    var select = ev.target.closest("select");
    if (select) {
      var side = select.getAttribute("data-side");
      if (side === "a") {
        state.sideA = select.value;
        state.pickA = new Set();
      } else {
        state.sideB = select.value;
        state.pickB = new Set();
      }
      render();
      return;
    }
    var box = ev.target.closest("input[type='checkbox']");
    if (!box) return;
    var key = box.getAttribute("data-key");
    var set = box.getAttribute("data-side") === "a" ? state.pickA : state.pickB;
    if (box.checked) set.add(key);
    else set.delete(key);
    render();
  }

  function fetchJson(url) {
    return fetch(url, { cache: "no-store", referrerPolicy: "no-referrer" }).then(function (res) {
      if (!res.ok) throw new Error(String(res.status));
      return res.json();
    });
  }

  function fetchFirst(urls) {
    var index = 0;
    function next(err) {
      if (index >= urls.length) throw err || new Error("missing");
      var url = urls[index];
      index += 1;
      return fetchJson(url).catch(next);
    }
    return next();
  }

  function loadLogs() {
    var store = new Map();
    return fetchJson(LOCAL.scores).catch(function () { return null; }).then(function (latest) {
      if (latest) addWeekLogs(store, latest);
      var through = latest && Number.isInteger(Number(latest.week)) ? Number(latest.week) : 0;
      var jobs = [];
      for (var week = 1; week <= through; week += 1) {
        var req = weekScoreRequest(week);
        if (!req) continue;
        jobs.push(fetchFirst([req.local, req.remote]).catch(function () { return null; }));
      }
      return Promise.all(jobs).then(function (files) {
        files.forEach(function (file) {
          if (file) addWeekLogs(store, file);
        });
        return { store: store, through: through };
      });
    });
  }

  function setStrip(text) {
    var strip = document.getElementById("strip");
    if (strip) strip.textContent = text;
  }

  function startAnalyzer() {
    state.featured = FEATURED;
    var lede = document.getElementById("taLede");
    if (lede) {
      lede.textContent = "Desk copy for " + state.featured + ". Pick two clubs and the players moving each way. Depth includes IDP. Points are logged week totals only. This page does not send trades.";
    }
    var app = document.getElementById("taApp");
    Promise.all([
      fetchJson(LOCAL.rosterIndex),
      fetchJson(LOCAL.rankings),
      fetchJson(LOCAL.scoring),
      fetchJson(LOCAL.teams),
      loadLogs()
    ]).then(function (loaded) {
      var index = loaded[0];
      var rankings = loaded[1];
      var scoring = loaded[2];
      var teamsFile = loaded[3];
      var logs = loaded[4];
      state.lineup = lineupFromScoring(scoring);
      state.logs = logs.store;
      var ranks = rankIndex(rankings);
      var colors = colorIndex(teamsFile);
      var ids = Array.isArray(index.teams) ? index.teams.filter(safeId) : [];
      return Promise.all(ids.map(function (id) {
        return fetchJson(rosterPath(id)).then(function (roster) {
          return teamRecord(id, roster, colors.get(id), ranks.get(id), state.featured);
        });
      })).then(function (teams) {
        state.teams = teams;
        if (!teams.some(function (team) { return team.id === state.sideA; }) && teams[0]) state.sideA = teams[0].id;
        if (!teams.some(function (team) { return team.id === state.sideB; })) {
          var other = teams.filter(function (team) { return team.id !== state.sideA; })[0] || teams[0];
          state.sideB = other ? other.id : state.sideA;
        }
        var bits = [];
        if (logs.through) bits.push("Score file through week " + logs.through);
        if (rankings && Number.isInteger(Number(rankings.week))) bits.push("power rankings week " + rankings.week);
        bits.push(teams.length + " clubs");
        setStrip(bits.join(" · "));
        render();
      });
    }).catch(function (err) {
      console.error(err);
      setStrip("Roster or ranking files are unavailable.");
      if (app) app.innerHTML = "<div class=\"banner\">Roster or ranking files are unavailable. No depth or points were filled in.</div>";
    });
  }

  function mount() {
    if (started || typeof document === "undefined") return;
    started = true;
    function start() {
      var app = document.getElementById("taApp");
      if (app) app.addEventListener("change", onChange);
      startAnalyzer();
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
    else start();
  }

  return {
    FEATURED: FEATURED,
    HQ: HQ,
    LOCAL: LOCAL,
    OFFENSE: OFFENSE,
    IDP: IDP,
    rosterPath: rosterPath,
    weekScoreRequest: weekScoreRequest,
    playerKey: playerKey,
    publicLabel: publicLabel,
    clubName: clubName,
    lineupFromScoring: lineupFromScoring,
    rosterPlayers: rosterPlayers,
    activeCounts: activeCounts,
    depthReport: depthReport,
    applyDeal: applyDeal,
    addWeekLogs: addWeekLogs,
    loggedTotal: loggedTotal,
    dealPoints: dealPoints,
    depthEdge: depthEdge,
    pointsEdge: pointsEdge,
    formatPts: formatPts,
    rankIndex: rankIndex,
    colorIndex: colorIndex,
    teamRecord: teamRecord,
    mount: mount
  };
});
