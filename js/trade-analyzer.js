/* Desk trade check for Eagleridge Eddie's. Runs in the browser.
   Rosters are read from this repo and from the public league site, and
   the copy with the newer timestamp is kept. Week score files
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
  var TEAM_COUNT = 14;
  var SKILL = ["RB", "WR", "TE"];
  var VALUE_POS = ["QB", "RB", "WR", "TE", "DL", "LB", "DB"];
  /* Bill's lineup. Depth and replacement use this even when scoring.json differs. */
  var BILL_LINEUP = { QB: 1, RB: 1, WR: 1, TE: 1, RWT: 3, DL: 1, LB: 1, DB: 2, ID: 3 };
  var LOCAL = {
    rosterIndex: "data/hq/rosters/index.json",
    rankings: "data/hq/rankings.json",
    scoring: "data/scoring.json",
    teams: "data/hq/teams.json",
    scores: "data/hq/scores.json",
    values: "data/player-values.json",
    freeAgents: "data/free-agents.json"
  };
  var PRIVATE_TEXT = /@[a-z0-9.-]+\.[a-z]{2,}|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b/i;

  function rosterPath(id) {
    return "data/hq/rosters/" + id + ".json";
  }

  function rosterRequest(id) {
    if (!safeId(id)) return null;
    return { local: rosterPath(id), remote: HQ + "rosters/" + id + ".json" };
  }

  function rosterIndexRequest() {
    return { local: LOCAL.rosterIndex, remote: HQ + "rosters/index.json" };
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

function lineupsMatch(a, b) {
  if (!a || !b) return false;
  return ["QB", "RB", "WR", "TE", "RWT", "DL", "LB", "DB", "ID"].every(function (key) {
    return a[key] === b[key];
  });
}

function resolveLineup(scoring) {
  var parsed = lineupFromScoring(scoring);
  if (lineupsMatch(parsed, BILL_LINEUP)) return parsed;
  return {
    QB: BILL_LINEUP.QB,
    RB: BILL_LINEUP.RB,
    WR: BILL_LINEUP.WR,
    TE: BILL_LINEUP.TE,
    RWT: BILL_LINEUP.RWT,
    DL: BILL_LINEUP.DL,
    LB: BILL_LINEUP.LB,
    DB: BILL_LINEUP.DB,
    ID: BILL_LINEUP.ID
  };
}

function replacementBases(lineup, teamCount) {
  var line = lineup || BILL_LINEUP;
  var clubs = teamCount || TEAM_COUNT;
  return {
    QB: (line.QB || 0) * clubs,
    RB: (line.RB || 0) * clubs,
    WR: (line.WR || 0) * clubs,
    TE: (line.TE || 0) * clubs,
    DL: (line.DL || 0) * clubs,
    LB: (line.LB || 0) * clubs,
    DB: (line.DB || 0) * clubs
  };
}

function byPpg(a, b) {
  return b.ppg - a.ppg || String(a.name).localeCompare(String(b.name)) || String(a.key).localeCompare(String(b.key));
}

function takeBest(list, count, used) {
  var picked = [];
  if (!(count > 0)) return picked;
  list.slice().sort(byPpg).forEach(function (player) {
    if (picked.length >= count || !player || used.has(player.key)) return;
    if (!Number.isFinite(player.ppg) || VALUE_POS.indexOf(player.pos) === -1) return;
    used.add(player.key);
    picked.push(player);
  });
  return picked;
}

function teamFlex(players, lineup) {
  var used = new Set();
  var active = (players || []).filter(function (player) {
    return player && !player.ir && VALUE_POS.indexOf(player.pos) !== -1 && Number.isFinite(player.ppg);
  });
  VALUE_POS.forEach(function (pos) {
    takeBest(active.filter(function (player) { return player.pos === pos; }), lineup[pos] || 0, used);
  });
  var flex = { RB: 0, WR: 0, TE: 0, DL: 0, LB: 0, DB: 0 };
  function fill(group, slots) {
    var remaining = active.filter(function (player) {
      return group.indexOf(player.pos) !== -1 && !used.has(player.key);
    });
    takeBest(remaining, slots, used).forEach(function (player) { flex[player.pos] += 1; });
  }
  fill(SKILL, lineup.RWT || 0);
  fill(IDP, lineup.ID || 0);
  return { used: used, flex: flex };
}

function replacementPlan(teamRosters, freeAgents, lineup, teamCount) {
  var line = lineup || BILL_LINEUP;
  var clubs = teamCount || TEAM_COUNT;
  var bases = replacementBases(line, clubs);
  var flex = { RB: 0, WR: 0, TE: 0, DL: 0, LB: 0, DB: 0 };
  var used = new Set();
  (teamRosters || []).forEach(function (team) {
    var result = teamFlex(team.players || [], line);
    result.used.forEach(function (key) { used.add(key); });
    Object.keys(flex).forEach(function (pos) { flex[pos] += result.flex[pos] || 0; });
  });
  var pool = [];
  var seen = new Set();
  function add(player) {
    if (!player || player.ir || VALUE_POS.indexOf(player.pos) === -1 || !Number.isFinite(player.ppg)) return;
    var key = player.key || playerKey(player.name);
    if (!key || seen.has(key)) return;
    seen.add(key);
    pool.push({ key: key, name: player.name || key, pos: player.pos, ppg: player.ppg });
  }
  (teamRosters || []).forEach(function (team) {
    (team.players || []).forEach(add);
  });
  (freeAgents || []).forEach(add);
  function fillRemainder(group, need) {
    if (!(need > 0)) return;
    var remaining = pool.filter(function (player) {
      return group.indexOf(player.pos) !== -1 && !used.has(player.key);
    });
    takeBest(remaining, need, used).forEach(function (player) { flex[player.pos] += 1; });
  }
  var skillHave = SKILL.reduce(function (sum, pos) { return sum + flex[pos]; }, 0);
  var idHave = IDP.reduce(function (sum, pos) { return sum + flex[pos]; }, 0);
  fillRemainder(SKILL, (line.RWT || 0) * clubs - skillHave);
  fillRemainder(IDP, (line.ID || 0) * clubs - idHave);
  var ranks = {};
  var grouped = {};
  VALUE_POS.forEach(function (pos) {
    ranks[pos] = bases[pos] + (flex[pos] || 0);
    grouped[pos] = pool.filter(function (player) { return player.pos === pos; }).sort(byPpg);
  });
  var replacement = {};
  VALUE_POS.forEach(function (pos) {
    var list = grouped[pos];
    var rank = ranks[pos];
    var player = list.length && rank > 0 ? list[Math.min(rank, list.length) - 1] : null;
    replacement[pos] = {
      rank: rank,
      ppg: player ? player.ppg : null,
      name: player ? player.name : null,
      available: list.length
    };
  });
  return { bases: bases, flex: flex, ranks: ranks, replacement: replacement };
}

function playerVor(player, plan) {
  if (!player || !plan || !Number.isFinite(player.ppg)) return null;
  var pos = VALUE_POS.indexOf(player.valuePos) !== -1 ? player.valuePos : player.pos;
  var rep = plan.replacement && plan.replacement[pos];
  if (!rep || !Number.isFinite(rep.ppg)) return null;
  return player.ppg - rep.ppg;
}

function vorChange(sent, received, plan) {
  var delta = 0;
  var missing = false;
  function apply(list, sign) {
    (list || []).forEach(function (player) {
      var vor = playerVor(player, plan);
      if (vor == null) missing = true;
      else delta += sign * vor;
    });
  }
  apply(sent, -1);
  apply(received, 1);
  if (!(sent && sent.length) && !(received && received.length)) return 0;
  return missing ? null : delta;
}

function formulaNote(plan) {
  var ranks = plan
    ? VALUE_POS.map(function (pos) { return pos + " " + plan.ranks[pos]; }).join(", ")
    : "unavailable";
  return "Replacement rank starts at 14 times the required starters: QB 14, RB 14, WR 14, TE 14, DL 14, LB 14, DB 28. " +
    "The 42 RB/WR/TE flex spots and the 42 DL/LB/DB flex spots then go to the highest points per game left after each club fills its required starters. " +
    "A spot a club cannot fill goes to the next-best rostered or free-agent player. Final ranks: " + ranks + ". " +
    "VOR is points per game minus the points per game at that rank. Rostered rates come from player-values.json when the name is there, otherwise from logged points divided by weeks with a log. " +
    "Free-agent rates are fpg in free-agents.json. IR is not in the pool.";
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

  function signedPts(n) {
    var text = formatPts(n);
    if (text === "—") return text;
    if (Number(n) > 0) return "+" + text;
    return text;
  }

  function parseRosterStamp(raw) {
    if (raw == null) return null;
    var text = String(raw).trim();
    if (!text) return null;
    var match = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2})\s*(AM|PM))?(?:\s*PT)?$/i);
    if (!match) {
      var parsed = Date.parse(text);
      if (!Number.isFinite(parsed)) return null;
      return { ms: parsed, label: /PT\s*$/i.test(text) ? text : text + " PT" };
    }
    var hour = 0;
    var minute = 0;
    if (match[4]) {
      hour = Number(match[4]) % 12;
      if (String(match[6]).toUpperCase() === "PM") hour += 12;
      minute = Number(match[5]);
    }
    var label = match[4]
      ? match[1] + "-" + match[2] + "-" + match[3] + " " + Number(match[4]) + ":" + match[5] + " " + String(match[6]).toUpperCase() + " PT"
      : match[1] + "-" + match[2] + "-" + match[3] + " PT";
    return {
      ms: Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]), hour, minute),
      label: label
    };
  }

  function rosterClock(file) {
    if (!file || typeof file !== "object") return null;
    var best = null;
    ["asOf", "lastSynced", "updated"].forEach(function (key) {
      var parsed = parseRosterStamp(file[key]);
      if (!parsed) return;
      if (!best || parsed.ms > best.ms) best = parsed;
    });
    return best;
  }

  function pickFresher(localFile, remoteFile) {
    if (!remoteFile && !localFile) return null;
    if (!remoteFile) return { file: localFile, time: rosterClock(localFile), from: "local" };
    if (!localFile) return { file: remoteFile, time: rosterClock(remoteFile), from: "hq" };
    var localTime = rosterClock(localFile);
    var remoteTime = rosterClock(remoteFile);
    var localMs = localTime ? localTime.ms : -Infinity;
    var remoteMs = remoteTime ? remoteTime.ms : -Infinity;
    if (remoteMs >= localMs) return { file: remoteFile, time: remoteTime, from: "hq" };
    return { file: localFile, time: localTime, from: "local" };
  }

  function asOfLine(label) {
    if (!label) return "Rosters as of unknown";
    var text = String(label).trim();
    if (!/PT$/i.test(text)) text += " PT";
    return "Rosters as of " + text;
  }

  function loggedPpg(store, key) {
    var weeks = store && store.get(key);
    if (!weeks || !weeks.size) return null;
    var sum = 0;
    weeks.forEach(function (pts) { sum += pts; });
    return sum / weeks.size;
  }

  function rateIndex(valuesFile) {
    var map = new Map();
    ((valuesFile && valuesFile.players) || []).forEach(function (row) {
      var key = playerKey(row && row.name);
      var ppg = Number(row && row.ppg);
      var pos = row && row.position;
      if (!key || !Number.isFinite(ppg) || VALUE_POS.indexOf(pos) === -1) return;
      map.set(key, { ppg: ppg, pos: pos });
    });
    return map;
  }

  function freeAgentRates(file, rosteredKeys) {
    if (!file || file.sample === true) return [];
    var list = [];
    var seen = new Set();
    ((file && file.players) || []).forEach(function (row) {
      var pct = Number(row && row.rosteredPct);
      if (Number.isFinite(pct) && pct >= 100) return;
      var name = publicLabel(row && (row.player || row.name));
      var key = playerKey(name);
      var pos = row && row.pos;
      var ppg = Number(row && (row.fpg != null ? row.fpg : row.ppg));
      if (!key || seen.has(key) || (rosteredKeys && rosteredKeys.has(key))) return;
      if (VALUE_POS.indexOf(pos) === -1 || !Number.isFinite(ppg)) return;
      seen.add(key);
      list.push({ key: key, name: name, pos: pos, ppg: ppg, ir: false });
    });
    return list;
  }

  function attachRates(players, rates, logs) {
    (players || []).forEach(function (player) {
      var rate = rates && rates.get(player.key);
      var ppg = rate && Number.isFinite(rate.ppg) ? rate.ppg : loggedPpg(logs, player.key);
      player.ppg = Number.isFinite(ppg) ? ppg : null;
      if (VALUE_POS.indexOf(player.pos) !== -1) player.valuePos = player.pos;
      else if (rate && VALUE_POS.indexOf(rate.pos) !== -1) player.valuePos = rate.pos;
      else player.valuePos = null;
    });
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

  function vorSentence(changeA, changeB, nameA, nameB) {
    if (changeA == null || changeB == null) return "No VOR total. A player in the deal has no points per game, so the change is incomplete.";
    return nameA + " VOR " + signedPts(changeA) + ". " + nameB + " VOR " + signedPts(changeB) + ".";
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
      var vor = row.vor == null ? "VOR —" : "VOR " + signedPts(row.vor);
      var tag = row.ir ? " · IR" : "";
      return "<li><span>" + esc(row.name) + "</span> <span class=\"ta-pos\">" + esc(row.pos) + tag + "</span> <strong>" + esc(logged) + "</strong> <span class=\"ta-vor\">" + esc(vor) + "</span></li>";
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
    plan: null,
    asOfLabel: "",
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

  function sideCard(team, before, after, packet, vorDelta, showChange) {
    var change = showChange
      ? "<p class=\"ta-vorline\">" + esc(vorDelta == null ? "VOR change —" : "VOR change " + signedPts(vorDelta)) + "</p>"
      : "";
    return "<article class=\"ta-side\" data-team=\"" + esc(team.id) + "\"><h3><span class=\"ta-mark\" style=\"background:" +
      esc(team.color) + "\"></span> " + esc(team.name) + " <span class=\"ta-pos\">" + esc(team.abbrev) +
      "</span></h3><p class=\"ta-season\">" + esc(seasonLine(team)) + "</p><div data-depth=\"" + esc(team.id) + "\">" +
      depthTable(before, after) + "</div><h4>Players in the deal</h4>" + change +
      "<div data-points=\"" + esc(team.id) + "\">" + pointRows(packet) + "</div></article>";
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
    ptsA.rows.forEach(function (row, i) { row.vor = playerVor(markedA[i], state.plan); });
    ptsB.rows.forEach(function (row, i) { row.vor = playerVor(markedB[i], state.plan); });
    var pEdge = pointsEdge(ptsA, ptsB);
    var vorA = vorChange(markedA, markedB, state.plan);
    var vorB = vorChange(markedB, markedA, state.plan);
    var options = state.teams.map(function (team) {
      return "<option value=\"" + esc(team.id) + "\">" + esc(team.name) + "</option>";
    }).join("");
    var lists = same
      ? "<p class=\"ta-note\">Pick two different clubs.</p>"
      : "<div class=\"ta-grid\">" + playerColumn(teamA, state.pickA, "a") + playerColumn(teamB, state.pickB, "b") + "</div>";
    var dealOpen = !same && (markedA.length || markedB.length);
    var summary = same
      ? "Pick two different clubs to see depth, logged points, and VOR."
      : dealOpen
        ? depthSentence(edge, teamA.name, teamB.name) + " " + pointsSentence(pEdge, teamA.name, teamB.name) + " " + vorSentence(vorA, vorB, teamA.name, teamB.name)
        : "Mark the players moving each way. The tables are the current depth charts, offense and IDP.";
    var note = formulaNote(state.plan);
    app.innerHTML = "<div class=\"ta-picks\"><label>Sends <select id=\"taSideA\" data-side=\"a\">" + options +
      "</select></label><label>Receives from <select id=\"taSideB\" data-side=\"b\">" + options +
      "</select></label></div><section class=\"card ta-result\" id=\"taResult\"><h2>This deal</h2><p class=\"ta-summary\">" +
      esc(summary) + "</p>" + (dealOpen ? meterBar(edge, teamA.color, teamB.color) : "") + "<div class=\"ta-grid\">" +
      sideCard(teamA, beforeA, afterA, ptsA, vorA, dealOpen) + sideCard(teamB, beforeB, afterB, ptsB, vorB, dealOpen) +
      "</div><p class=\"ta-note\" id=\"taFormula\" title=\"VOR is points per game minus the replacement points per game.\">" +
      esc(note) + " IR is not active depth. Logged points come from the posted week score files and only where that player was listed. A blank log is not zero.</p></section>" +
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

  function setAsOf(label) {
    state.asOfLabel = label || "";
    var el = document.getElementById("taAsOf");
    var line = asOfLine(label);
    if (el) el.textContent = line;
    return line;
  }

  function loadOptional(url) {
    return fetchJson(url).catch(function () { return null; });
  }

  function loadRosterSet() {
    var indexReq = rosterIndexRequest();
    return Promise.all([
      loadOptional(indexReq.local),
      loadOptional(indexReq.remote)
    ]).then(function (pair) {
      var chosenIndex = pickFresher(pair[0], pair[1]);
      if (!chosenIndex || !chosenIndex.file) throw new Error("rosters");
      var ids = Array.isArray(chosenIndex.file.teams) ? chosenIndex.file.teams.filter(safeId) : [];
      return Promise.all(ids.map(function (id) {
        var req = rosterRequest(id);
        return Promise.all([
          loadOptional(req.local),
          loadOptional(req.remote)
        ]).then(function (files) {
          var chosen = pickFresher(files[0], files[1]);
          if (!chosen || !chosen.file) throw new Error(id);
          return { id: id, roster: chosen.file, time: chosen.time, from: chosen.from };
        });
      })).then(function (rows) {
        var oldest = null;
        rows.forEach(function (row) {
          if (!row.time) return;
          if (!oldest || row.time.ms < oldest.ms) oldest = row.time;
        });
        return { rows: rows, asOf: oldest || chosenIndex.time || null };
      });
    });
  }

  function startAnalyzer() {
    state.featured = FEATURED;
    var lede = document.getElementById("taLede");
    if (lede) {
      lede.textContent = "Desk copy for " + state.featured + ". Pick two clubs and the players moving each way. Depth includes IDP. Points are logged week totals. VOR is points per game over replacement. This page does not send trades.";
    }
    var app = document.getElementById("taApp");
    Promise.all([
      fetchJson(LOCAL.rankings),
      fetchJson(LOCAL.scoring),
      fetchJson(LOCAL.teams),
      loadLogs(),
      loadOptional(LOCAL.values),
      loadOptional(LOCAL.freeAgents),
      loadRosterSet()
    ]).then(function (loaded) {
      var rankings = loaded[0];
      var scoring = loaded[1];
      var teamsFile = loaded[2];
      var logs = loaded[3];
      var values = loaded[4];
      var freeAgents = loaded[5];
      var rosterSet = loaded[6];
      state.lineup = resolveLineup(scoring);
      state.logs = logs.store;
      var ranks = rankIndex(rankings);
      var colors = colorIndex(teamsFile);
      var rates = rateIndex(values);
      var teams = rosterSet.rows.map(function (row) {
        return teamRecord(row.id, row.roster, colors.get(row.id), ranks.get(row.id), state.featured);
      });
      var rosteredKeys = new Set();
      teams.forEach(function (team) {
        attachRates(team.players, rates, logs.store);
        team.players.forEach(function (player) { rosteredKeys.add(player.key); });
      });
      var fas = freeAgentRates(freeAgents, rosteredKeys);
      state.plan = replacementPlan(teams.map(function (team) {
        return {
          id: team.id,
          players: team.players.map(function (player) {
            var pos = VALUE_POS.indexOf(player.valuePos) !== -1 ? player.valuePos : player.pos;
            return { key: player.key, name: player.name, pos: pos, ppg: player.ppg, ir: player.ir };
          })
        };
      }), fas, state.lineup, TEAM_COUNT);
      state.teams = teams;
      if (!teams.some(function (team) { return team.id === state.sideA; }) && teams[0]) state.sideA = teams[0].id;
      if (!teams.some(function (team) { return team.id === state.sideB; })) {
        var other = teams.filter(function (team) { return team.id !== state.sideA; })[0] || teams[0];
        state.sideB = other ? other.id : state.sideA;
      }
      var bits = [setAsOf(rosterSet.asOf && rosterSet.asOf.label)];
      if (logs.through) bits.push("Score file through week " + logs.through);
      if (rankings && Number.isInteger(Number(rankings.week))) bits.push("power rankings week " + rankings.week);
      bits.push(teams.length + " clubs");
      setStrip(bits.join(" · "));
      render();
    }).catch(function (err) {
      console.error(err);
      setStrip("Roster or ranking files are unavailable.");
      setAsOf("");
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
    BILL_LINEUP: BILL_LINEUP,
    TEAM_COUNT: TEAM_COUNT,
    rosterPath: rosterPath,
    rosterRequest: rosterRequest,
    rosterIndexRequest: rosterIndexRequest,
    weekScoreRequest: weekScoreRequest,
    resolveLineup: resolveLineup,
    replacementBases: replacementBases,
    replacementPlan: replacementPlan,
    playerVor: playerVor,
    vorChange: vorChange,
    formulaNote: formulaNote,
    parseRosterStamp: parseRosterStamp,
    pickFresher: pickFresher,
    asOfLine: asOfLine,
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
