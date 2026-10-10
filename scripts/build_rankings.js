#!/usr/bin/env node
/* Build data/rankings/<season>-wk<N>.json from free public feeds.
   One failed source is recorded and skipped. The file is still written
   when at least one source produced players. */
"use strict";

const fs = require("fs");
const path = require("path");
const WUScore = require("../js/scoring.js");
const WUWeek = require("../js/week.js");
const M = require("../js/rankings-math.js");

const ROOT = path.join(__dirname, "..");
const UA = "WURankings/1.0 (fantasy research; +https://github.com/wjenson27-cpu/wu-wr-138e)";
const POS_LIST = ["QB", "RB", "WR", "TE", "DL", "LB", "DB"];
const FP_PAGES = [
  ["qb", "QB"],
  ["rb", "RB"],
  ["wr", "WR"],
  ["te", "TE"],
  ["dl", "DL"],
  ["lb", "LB"],
  ["db", "DB"]
];

function envNum(name) {
  const raw = process.env[name];
  if (raw == null || String(raw).trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function defaultSeason(date) {
  const p = WUWeek.ptParts(date || new Date());
  const month = Number(p.month);
  const year = Number(p.year);
  return month < 3 ? year - 1 : year;
}

function sleep(ms) {
  return new Promise(function (resolve) { setTimeout(resolve, ms); });
}

function avg(nums) {
  if (!nums.length) return null;
  let sum = 0;
  nums.forEach(function (n) { sum += n; });
  return sum / nums.length;
}

function injuryCode(parts) {
  const raw = parts.filter(Boolean).join(" ").toLowerCase();
  if (!raw || raw === "active" || raw === "healthy") return "";
  if (raw.indexOf("pup") !== -1) return "PUP";
  if (raw.indexOf("suspend") !== -1) return "SUS";
  if (raw === "ir" || raw.indexOf("injured reserve") !== -1 || raw.indexOf("injury_reserve") !== -1) return "IR";
  if (raw.indexOf("out") !== -1) return "O";
  if (raw.indexOf("doubt") !== -1) return "D";
  if (raw.indexOf("question") !== -1) return "Q";
  return "";
}

function espnInjury(status) {
  const s = String(status || "").toUpperCase();
  if (s === "QUESTIONABLE") return "Q";
  if (s === "OUT") return "O";
  if (s === "DOUBTFUL") return "D";
  if (s === "INJURY_RESERVE" || s === "IR") return "IR";
  if (s === "SUSPENSION" || s === "SUSPENDED") return "SUS";
  if (s === "PUP") return "PUP";
  return "";
}

async function grab(url, opts) {
  const timeout = (opts && opts.timeout) || 60000;
  const ctrl = new AbortController();
  const timer = setTimeout(function () { ctrl.abort(); }, timeout);
  try {
    const res = await fetch(url, {
      signal: ctrl.signal,
      headers: Object.assign({
        "User-Agent": UA,
        "Accept": "application/json, text/html;q=0.9"
      }, (opts && opts.headers) || {})
    });
    const text = await res.text();
    if (!res.ok) {
      const err = new Error(res.status + " for " + url);
      err.status = res.status;
      err.body = text.slice(0, 180);
      throw err;
    }
    if (opts && opts.raw) return text;
    return JSON.parse(text);
  } finally {
    clearTimeout(timer);
  }
}

function realTeam(team) {
  const t = M.canonTeam(team);
  if (!t || t === "FA" || t === "NONE") return "";
  return t;
}

function loadRosters() {
  const dir = path.join(ROOT, "data", "hq", "rosters");
  const index = JSON.parse(fs.readFileSync(path.join(dir, "index.json"), "utf8"));
  const entries = [];
  (index.teams || []).forEach(function (id) {
    const doc = JSON.parse(fs.readFileSync(path.join(dir, id + ".json"), "utf8"));
    const roster = doc.roster || {};
    const ir = {};
    (roster.IR || []).forEach(function (name) { ir[M.normName(name)] = true; });
    Object.keys(roster).forEach(function (slot) {
      const pos = M.groupPos(slot);
      (roster[slot] || []).forEach(function (name) {
        const key = M.normName(name);
        if (!key) return;
        entries.push({
          norm: key,
          pos: pos,
          avail: id === "eddies" ? "eddies" : "other",
          club: doc.teamName || id,
          ir: slot === "IR" || !!ir[key]
        });
      });
    });
  });
  return function owned(name, pos) {
    const key = M.normName(name);
    const exact = entries.filter(function (e) { return e.norm === key && e.pos === pos; });
    if (exact.length) return exact[0];
    const irOnly = entries.filter(function (e) { return e.norm === key && !e.pos; });
    if (irOnly.length === 1 && entries.filter(function (e) { return e.norm === key; }).length === 1) return irOnly[0];
    return null;
  };
}

function extractEcr(html) {
  const marker = "var ecrData = ";
  const at = html.indexOf(marker);
  if (at < 0) throw new Error("no ecrData");
  const start = html.indexOf("{", at);
  let depth = 0;
  let inStr = false;
  let esc = false;
  for (let i = start; i < html.length; i++) {
    const c = html[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === "\\") esc = true;
      else if (c === "\"") inStr = false;
      continue;
    }
    if (c === "\"") { inStr = true; continue; }
    if (c === "{") depth += 1;
    else if (c === "}") {
      depth -= 1;
      if (depth === 0) return JSON.parse(html.slice(start, i + 1));
    }
  }
  throw new Error("unclosed ecrData");
}

function blankPlayer(name, pos) {
  return {
    key: M.normName(name) + "|" + pos,
    name: name,
    pos: pos,
    team: "",
    injury: "",
    sleeperPts: null,
    espnPts: null,
    recentPts: null,
    recentN: 0,
    fp: null
  };
}

function idpIndex(pos, vol) {
  if (!vol) return null;
  if (pos === "DL") return M.round1(vol.sacks * 8 + vol.plays * 0.15);
  if (pos === "DB") return M.round1(vol.passAtt);
  return M.round1(vol.plays);
}

async function main() {
  const now = new Date();
  const season = envNum("SEASON") || defaultSeason(now);
  const week = envNum("WEEK") || WUWeek.fantraxWeek(now);
  const scoring = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "scoring.json"), "utf8"));
  const rosters = loadRosters();
  const sources = [];
  const players = new Map();

  function source(id, name, ok, kind, detail) {
    sources.push({ id: id, name: name, ok: !!ok, kind: kind, detail: detail || "" });
    console.log((ok ? "ok  " : "miss") + " " + name + (detail ? " — " + detail : ""));
  }

  function take(name, pos) {
    const grouped = M.groupPos(pos);
    const keyName = M.normName(name);
    if (!grouped || !keyName) return null;
    const key = keyName + "|" + grouped;
    let row = players.get(key);
    if (!row) {
      row = blankPlayer(name, grouped);
      players.set(key, row);
    }
    return row;
  }

  let sleeperPlayers = null;
  try {
    sleeperPlayers = await grab("https://api.sleeper.app/v1/players/nfl", { timeout: 120000 });
    let kept = 0;
    Object.keys(sleeperPlayers).forEach(function (id) {
      const p = sleeperPlayers[id];
      if (!p || typeof p !== "object") return;
      const pos = M.groupPos(p.position || (p.fantasy_positions && p.fantasy_positions[0]));
      const name = p.full_name || ((p.first_name || "") + " " + (p.last_name || "")).trim();
      if (!pos || !name) return;
      const row = take(name, pos);
      if (!row) return;
      const incomingTeam = realTeam(p.team || "");
      if (row.sleeperId && row.team && !incomingTeam) return;
      row.sleeperId = id;
      row.team = realTeam(incomingTeam) || row.team;
      row.injury = injuryCode([p.injury_status, p.status]) || row.injury;
      kept += 1;
    });
    source("sleeper-players", "Sleeper player list", true, "identity", kept + " league-position players");
  } catch (err) {
    source("sleeper-players", "Sleeper player list", false, "identity", err.message);
  }

  const byId = {};
  players.forEach(function (row) {
    if (row.sleeperId) byId[row.sleeperId] = row;
  });

  try {
    const proj = await grab("https://api.sleeper.app/v1/projections/nfl/regular/" + season + "/" + week, { timeout: 60000 });
    let n = 0;
    Object.keys(proj).forEach(function (id) {
      const row = byId[id];
      if (!row) return;
      const line = M.sleeperLine(proj[id]);
      if (!M.hasCountingStat(line)) return;
      row.sleeperPts = WUScore.scoreLine(line, row.pos, scoring);
      n += 1;
    });
    source("sleeper", "Sleeper projections", n > 0, "stats", n + " stat lines rescored");
  } catch (err) {
    source("sleeper", "Sleeper projections", false, "stats", err.message);
  }

  const recentBuckets = {};
  const allowed = {};
  const volume = {};
  let statsOk = 0;
  let statsFail = 0;
  const pastNotes = [];
  for (let w = 1; w < week; w++) {
    let stats = null;
    let slate = null;
    try {
      stats = await grab("https://api.sleeper.app/v1/stats/nfl/regular/" + season + "/" + w, { timeout: 60000 });
      statsOk += 1;
    } catch (err) {
      statsFail += 1;
      pastNotes.push("week " + w + " stats " + err.message);
    }
    try {
      slate = await grab("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week=" + w + "&dates=" + season, { timeout: 45000 });
    } catch (err) {
      pastNotes.push("week " + w + " schedule " + err.message);
    }
    if (stats) {
      const offensePts = {};
      const offenseVol = {};
      Object.keys(stats).forEach(function (id) {
        const who = byId[id];
        const raw = stats[id];
        if (!who || !raw) return;
        const line = M.sleeperLine(raw);
        const played = Number(raw.gp) > 0 || M.hasCountingStat(line);
        if (!played) return;
        const pts = WUScore.scoreLine(line, who.pos, scoring);
        if (!recentBuckets[id]) recentBuckets[id] = [];
        recentBuckets[id].push({ week: w, pts: pts });
        const team = who.team;
        if (!team) return;
        if (!offensePts[team]) offensePts[team] = {};
        offensePts[team][who.pos] = (offensePts[team][who.pos] || 0) + pts;
        if (!offenseVol[team]) offenseVol[team] = { plays: 0, passAtt: 0, sacks: 0 };
        const rush = Number(raw.rush_att) || 0;
        const att = Number(raw.pass_att) || 0;
        const sack = Number(raw.pass_sack) || 0;
        offenseVol[team].plays += rush + att + sack;
        offenseVol[team].passAtt += att;
        offenseVol[team].sacks += sack;
      });
      const games = parseScoreboard(slate);
      games.forEach(function (game) {
        [game.home, game.away].forEach(function (team, idx) {
          const vol = offenseVol[team];
          if (!vol || vol.plays <= 0) return;
          if (!volume[team]) volume[team] = [];
          volume[team].push(vol);
          const defense = idx === 0 ? game.away : game.home;
          const pts = offensePts[team] || {};
          if (!allowed[defense]) allowed[defense] = {};
          POS_LIST.forEach(function (pos) {
            if (!allowed[defense][pos]) allowed[defense][pos] = [];
            allowed[defense][pos].push(pts[pos] || 0);
          });
        });
      });
    }
  }
  let recentN = 0;
  Object.keys(recentBuckets).forEach(function (id) {
    const row = byId[id];
    if (!row) return;
    const last = recentBuckets[id].sort(function (a, b) { return b.week - a.week; }).slice(0, 3);
    if (!last.length) return;
    row.recentPts = M.round1(avg(last.map(function (g) { return g.pts; })));
    row.recentN = last.length;
    recentN += 1;
  });
  if (week <= 1) source("recent", "Last 3 weeks", false, "stats", "No earlier week yet");
  else source("recent", "Last 3 weeks", recentN > 0, "stats", recentN + " players, " + statsOk + " stat weeks" + (statsFail ? ", " + statsFail + " missing" : ""));

  const fpa = {};
  const volAvg = {};
  Object.keys(allowed).forEach(function (team) {
    fpa[team] = {};
    POS_LIST.forEach(function (pos) {
      const xs = (allowed[team] && allowed[team][pos]) || [];
      if (xs.length) fpa[team][pos] = M.round1(avg(xs));
    });
  });
  Object.keys(volume).forEach(function (team) {
    const rows = volume[team];
    volAvg[team] = {
      plays: M.round1(avg(rows.map(function (r) { return r.plays; }))),
      passAtt: M.round1(avg(rows.map(function (r) { return r.passAtt; }))),
      sacks: M.round1(avg(rows.map(function (r) { return r.sacks; })))
    };
  });
  const matchupOk = Object.keys(fpa).length >= 4 && Object.keys(volAvg).length >= 4;
  source("matchups", "Matchup grades", matchupOk, "matchup", matchupOk ? Object.keys(fpa).length + " defenses from earlier weeks" : (pastNotes.join("; ") || "not enough weeks"));

  let espnTeams = {};
  try {
    const teamsDoc = await grab("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams?limit=40");
    ((teamsDoc.sports && teamsDoc.sports[0].leagues[0].teams) || []).forEach(function (wrap) {
      const t = wrap.team || wrap;
      espnTeams[String(t.id)] = M.canonTeam(t.abbreviation);
    });
  } catch (err) {
    espnTeams = {};
  }

  try {
    const filter = JSON.stringify({ players: { limit: 1500, sortPercOwned: { sortPriority: 1, sortAsc: false } } });
    const doc = await grab(
      "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/" + season + "/segments/0/leaguedefaults/3?scoringPeriodId=" + week + "&view=kona_player_info",
      { timeout: 120000, headers: { "X-Fantasy-Filter": filter } }
    );
    const posById = { 1: "QB", 2: "RB", 3: "WR", 4: "TE" };
    let n = 0;
    (doc.players || []).forEach(function (wrap) {
      const p = wrap.player || wrap;
      const pos = posById[p.defaultPositionId];
      if (!pos || !p.fullName) return;
      const stat = (p.stats || []).filter(function (s) {
        return s.statSourceId === 1 && s.statSplitTypeId === 1 && s.seasonId === season && s.scoringPeriodId === week;
      })[0];
      if (!stat || !stat.stats) return;
      const line = M.espnLine(stat.stats);
      if (!M.hasCountingStat(line)) return;
      const row = take(p.fullName, pos);
      if (!row) return;
      if (!row.sleeperId) row.name = p.fullName;
      if (!row.team) row.team = realTeam(espnTeams[String(p.proTeamId)] || "");
      if (!row.injury) row.injury = espnInjury(p.injuryStatus);
      row.espnPts = WUScore.scoreLine(line, pos, scoring);
      n += 1;
    });
    source("espn", "ESPN projections", n > 0, "stats", n + " offensive lines rescored. ESPN's public board has no IDP.");
  } catch (err) {
    source("espn", "ESPN projections", false, "stats", err.message);
  }

  const fpMissing = [];
  let fpCount = 0;
  let fpBlocked = false;
  for (let i = 0; i < FP_PAGES.length; i++) {
    if (fpBlocked) break;
    if (i > 0) await sleep(5500);
    const slug = FP_PAGES[i][0];
    const pos = FP_PAGES[i][1];
    const url = "https://www.fantasypros.com/nfl/rankings/" + slug + ".php?week=" + week;
    try {
      const html = await grab(url, { timeout: 45000, raw: true });
      if (/Just a moment|cf-browser-verification|Attention Required/i.test(html.slice(0, 2500))) {
        fpBlocked = true;
        fpMissing.push(slug);
        continue;
      }
      const data = extractEcr(html);
      (data.players || []).forEach(function (p) {
        const row = take(p.player_name, p.player_position_id || pos);
        if (!row) return;
        const rank = Number(p.rank_ecr);
        if (!Number.isFinite(rank)) return;
        if (row.fp && row.fp.rank <= rank) return;
        row.fp = {
          rank: rank,
          low: Number(p.rank_min),
          high: Number(p.rank_max)
        };
        if (!row.team) row.team = realTeam(p.player_team_id || "");
        fpCount += 1;
      });
    } catch (err) {
      fpMissing.push(slug);
      if (err.status === 401 || err.status === 403 || err.status === 429) fpBlocked = true;
    }
  }
  if (!fpCount) {
    source("fantasypros", "FantasyPros ECR", false, "ranks", fpBlocked
      ? "Blocked automation. Dropped."
      : "No ranks. Missing " + (fpMissing.join(", ") || "all pages"));
  } else {
    source("fantasypros", "FantasyPros ECR", true, "ranks", fpCount + " ranks" + (fpMissing.length ? ". Missing pages: " + fpMissing.join(", ") : "") + (fpBlocked ? ". Later pages were blocked." : ""));
    if (fpMissing.length) sources[sources.length - 1].partial = true;
  }

  let slate = null;
  try {
    slate = await grab("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week=" + week + "&dates=" + season);
    const games = parseScoreboard(slate);
    source("espn-schedule", "ESPN schedule and odds", games.length > 0, "schedule", games.length + " games");
  } catch (err) {
    source("espn-schedule", "ESPN schedule and odds", false, "schedule", err.message);
  }
  const games = parseScoreboard(slate);
  const byTeam = {};
  games.forEach(function (game) {
    const implied = M.impliedTeamTotals(game.spread, game.total);
    byTeam[game.home] = {
      opp: game.away,
      home: true,
      bye: false,
      played: game.final,
      neutral: game.neutral,
      site: game.neutral ? game.city : "",
      spread: game.spread,
      total: game.total,
      implied: implied ? implied.home : null,
      weather: null,
      venue: game.venue,
      city: game.city,
      indoor: game.indoor,
      kickoff: game.kickoff
    };
    byTeam[game.away] = {
      opp: game.home,
      home: false,
      bye: false,
      played: game.final,
      neutral: game.neutral,
      site: game.neutral ? game.city : "",
      spread: game.spread == null ? null : M.round1(-game.spread),
      total: game.total,
      implied: implied ? implied.away : null,
      weather: null,
      venue: game.venue,
      city: game.city,
      indoor: game.indoor,
      kickoff: game.kickoff
    };
  });

  await addWeather(games, byTeam, source);

  const gradePools = { offense: {}, idp: {} };
  POS_LIST.forEach(function (pos) {
    const pool = [];
    Object.keys(fpa).forEach(function (team) {
      if (fpa[team][pos] != null) pool.push(fpa[team][pos]);
    });
    gradePools.offense[pos] = pool;
  });
  ["DL", "LB", "DB"].forEach(function (pos) {
    const pool = [];
    Object.keys(volAvg).forEach(function (team) {
      const idx = idpIndex(pos, volAvg[team]);
      if (idx != null) pool.push(idx);
    });
    gradePools.idp[pos] = pool;
  });

  const kept = [];
  players.forEach(function (row) {
    const owned = rosters(row.name, row.pos);
    const worth = (row.sleeperPts != null && row.sleeperPts > 1) ||
      (row.espnPts != null && row.espnPts > 1) ||
      (row.recentPts != null && row.recentPts > 1) ||
      row.fp || owned;
    if (!worth) return;
    if (!row.team && !owned) return;
    kept.push(row);
  });

  const byPos = {};
  POS_LIST.forEach(function (pos) { byPos[pos] = []; });
  kept.forEach(function (row) { if (byPos[row.pos]) byPos[row.pos].push(row); });

  const out = [];
  POS_LIST.forEach(function (pos) {
    const list = byPos[pos];
    const pointRows = list.filter(function (row) {
      return M.projectionConsensus(row.sleeperPts, row.espnPts, row.recentPts, !byTeam[row.team]).pts != null;
    }).map(function (row) {
      const c = M.projectionConsensus(row.sleeperPts, row.espnPts, row.recentPts, !byTeam[row.team]);
      return { key: row.key, name: row.name, pts: c.pts, floor: c.floor, ceil: c.ceil, n: c.n };
    });
    const consensusRank = M.ordinalRanks(pointRows, function (row) { return row.pts; });
    const sleeperRank = M.ordinalRanks(list.filter(function (r) { return r.sleeperPts != null; }).map(pack("sleeperPts")), function (r) { return r.pts; });
    const espnRank = M.ordinalRanks(list.filter(function (r) { return r.espnPts != null; }).map(pack("espnPts")), function (r) { return r.pts; });
    const recentRank = M.ordinalRanks(list.filter(function (r) { return r.recentPts != null; }).map(pack("recentPts")), function (r) { return r.pts; });
    const onlyRank = list.filter(function (row) { return consensusRank[row.key] == null; })
      .sort(function (a, b) {
        return ((a.fp && a.fp.rank) || 999) - ((b.fp && b.fp.rank) || 999) || a.name.localeCompare(b.name);
      });
    let next = pointRows.length;
    onlyRank.forEach(function (row) { consensusRank[row.key] = ++next; });
    const pointsByKey = {};
    pointRows.forEach(function (row) { pointsByKey[row.key] = row; });

    list.forEach(function (row) {
      const c = pointsByKey[row.key] || { pts: null, floor: null, ceil: null, n: 0 };
      const src = {};
      if (row.sleeperPts != null) src.sleeper = { pts: row.sleeperPts, rank: sleeperRank[row.key] || null };
      if (row.espnPts != null) src.espn = { pts: row.espnPts, rank: espnRank[row.key] || null };
      if (row.recentPts != null) src.recent = { pts: row.recentPts, rank: recentRank[row.key] || null, weeks: row.recentN };
      if (row.fp) src.fantasypros = { rank: row.fp.rank, low: numOrNull(row.fp.low), high: numOrNull(row.fp.high) };
      const gap = pos === "QB" ? 8 : 12;
      const cap = (pos === "QB" || pos === "TE") ? 24 : 36;
      const ranks = [src.sleeper && src.sleeper.rank, src.espn && src.espn.rank, src.fantasypros && src.fantasypros.rank];
      const finiteRanks = ranks.filter(function (n) { return n != null; });
      const bestRank = finiteRanks.length ? Math.min.apply(null, finiteRanks) : null;
      const pts = [row.sleeperPts, row.espnPts];
      const game = byTeam[row.team];
      const owned = rosters(row.name, row.pos);
      const player = {
        name: row.name,
        pos: row.pos,
        team: row.team || "",
        opp: game ? game.opp : "",
        home: game ? game.home : null,
        bye: !game,
        injury: row.injury || "",
        played: game ? !!game.played : false,
        pts: c.pts,
        floor: c.floor,
        ceil: c.ceil,
        rank: consensusRank[row.key] || null,
        split: M.isSplit(bestRank != null && bestRank <= cap ? ranks : [], pts, gap),
        sources: src,
        matchup: matchupFor(row, game, fpa, volAvg, gradePools),
        vegas: game && game.spread != null && game.implied != null ? { spread: game.spread, total: game.total, implied: game.implied } : null,
        weather: game ? game.weather : null,
        avail: owned ? owned.avail : "fa",
        club: owned ? owned.club : ""
      };
      if (game && game.neutral) player.site = game.site || game.city || "";
      out.push(player);
    });
  });

  out.sort(function (a, b) {
    return POS_LIST.indexOf(a.pos) - POS_LIST.indexOf(b.pos) || (a.rank || 999) - (b.rank || 999) || a.name.localeCompare(b.name);
  });

  const asOf = now.toISOString();
  const doc = {
    season: season,
    week: week,
    asOf: asOf,
    scoring: "Wheels Up. Stat lines are rescored with data/scoring.json. Source PPR totals are not used.",
    weights: "Equal-weight average of Sleeper, ESPN, and last-3 actuals when those lines exist.",
    sources: sources,
    players: out
  };
  const dir = path.join(ROOT, "data", "rankings");
  fs.mkdirSync(dir, { recursive: true });
  const file = season + "-wk" + week + ".json";
  fs.writeFileSync(path.join(dir, file), JSON.stringify(doc, null, 2) + "\n");
  fs.writeFileSync(path.join(dir, "latest.json"), JSON.stringify({ season: season, week: week, file: file, asOf: asOf }, null, 2) + "\n");
  console.log("wrote " + out.length + " players to data/rankings/" + file);
  if (!out.length) process.exitCode = 1;
}

function pack(field) {
  return function (row) { return { key: row.key, name: row.name, pts: row[field] }; };
}

function numOrNull(n) {
  return Number.isFinite(n) ? n : null;
}

function parseScoreboard(doc) {
  if (!doc || !doc.events) return [];
  return doc.events.map(function (event) {
    const comp = (event.competitions && event.competitions[0]) || {};
    const sides = {};
    (comp.competitors || []).forEach(function (c) {
      sides[c.homeAway] = M.canonTeam(c.team && c.team.abbreviation);
    });
    const odds = (comp.odds && comp.odds[0]) || null;
    const venue = comp.venue || {};
    const status = (event.status && event.status.type) || {};
    const spread = odds && odds.spread != null ? Number(odds.spread) : null;
    const total = odds && odds.overUnder != null ? Number(odds.overUnder) : null;
    return {
      home: sides.home || "",
      away: sides.away || "",
      neutral: !!comp.neutralSite,
      indoor: !!(venue.indoor),
      venue: venue.fullName || "",
      city: (venue.address && venue.address.city) || "",
      kickoff: event.date || "",
      final: !!(status.completed || status.state === "post"),
      spread: Number.isFinite(spread) ? spread : null,
      total: Number.isFinite(total) ? total : null
    };
  }).filter(function (g) { return g.home && g.away; });
}

function matchupFor(row, game, fpa, volAvg, pools) {
  if (!game) return null;
  const idp = row.pos === "DL" || row.pos === "LB" || row.pos === "DB";
  if (!idp) {
    const value = fpa[game.opp] && fpa[game.opp][row.pos];
    const graded = M.matchupGrade(value, pools.offense[row.pos] || []);
    if (value == null && !graded) return null;
    return {
      grade: graded ? graded.grade : null,
      kind: "offense",
      fpa: value == null ? null : value,
      place: graded ? graded.place : null,
      of: graded ? graded.of : null,
      note: value == null ? "" : "Allows " + value + " WU per game to " + row.pos
    };
  }
  const vol = volAvg[game.opp];
  const value = idpIndex(row.pos, vol);
  const graded = M.matchupGrade(value, pools.idp[row.pos] || []);
  if (!vol && !graded) return null;
  return {
    grade: graded ? graded.grade : null,
    kind: "idp",
    fpa: null,
    place: graded ? graded.place : null,
    of: graded ? graded.of : null,
    plays: vol ? vol.plays : null,
    passAtt: vol ? vol.passAtt : null,
    sacksAllowed: vol ? vol.sacks : null,
    note: vol ? vol.plays + " plays, " + vol.passAtt + " pass att, " + vol.sacks + " sacks allowed per game" : ""
  };
}

async function addWeather(games, byTeam, source) {
  if (!games.length) {
    source("weather", "Weather", false, "weather", "No schedule to attach weather to");
    return;
  }
  const outdoor = [];
  const seen = {};
  games.forEach(function (game) {
    const spot = byTeam[game.home];
    if (!spot) return;
    if (game.indoor || roofed(game.venue)) {
      spot.weather = { indoor: true, text: "Dome" };
      const away = byTeam[game.away];
      if (away) away.weather = { indoor: true, text: "Dome" };
      return;
    }
    if (game.final) {
      spot.weather = { indoor: false, text: "Outdoor" };
      const away = byTeam[game.away];
      if (away) away.weather = { indoor: false, text: "Outdoor" };
      return;
    }
    const key = game.venue || game.city || game.home;
    if (!seen[key]) {
      seen[key] = [];
      outdoor.push(key);
    }
    seen[key].push(game);
  });
  if (!outdoor.length) {
    source("weather", "Weather", true, "weather", "Indoor or already played");
    return;
  }
  let got = 0;
  const errors = [];
  for (let i = 0; i < outdoor.length; i++) {
    const group = seen[outdoor[i]];
    const game = group[0];
    let weather = { indoor: false, text: "Outdoor" };
    try {
      weather = { indoor: false, text: (await forecastAt(game)).text };
      got += 1;
    } catch (err) {
      errors.push((game.venue || game.city) + ": " + err.message);
    }
    group.forEach(function (g) { stampWeather(byTeam, g, weather); });
    if (i < outdoor.length - 1) await sleep(300);
  }
  source("weather", "Weather", got > 0, "weather", got + " outdoor forecasts" + (errors.length ? ". " + errors.slice(0, 3).join("; ") : ""));
}

function roofed(venue) {
  const name = String(venue || "").toLowerCase();
  return name === "sofi stadium" || name === "allegiant stadium";
}

function stampWeather(byTeam, game, weather) {
  [game.home, game.away].forEach(function (team) {
    if (byTeam[team]) byTeam[team].weather = weather;
  });
}

async function forecastAt(game) {
  const geo = await geocode(game.venue) || await geocode(game.city);
  if (!geo) throw new Error("no geocode");
  const url = "https://api.open-meteo.com/v1/forecast?latitude=" + geo.lat + "&longitude=" + geo.lon +
    "&hourly=temperature_2m,wind_speed_10m,precipitation_probability&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=UTC&forecast_days=7";
  const doc = await grab(url, { timeout: 30000 });
  const times = (doc.hourly && doc.hourly.time) || [];
  const kick = Date.parse(game.kickoff);
  let best = 0;
  let bestDiff = Infinity;
  times.forEach(function (stamp, i) {
    const diff = Math.abs(Date.parse(stamp + "Z") - kick);
    if (diff < bestDiff) { bestDiff = diff; best = i; }
  });
  if (!times.length || bestDiff > 3 * 3600000) throw new Error("no hour near kickoff");
  const temp = doc.hourly.temperature_2m[best];
  const wind = doc.hourly.wind_speed_10m[best];
  const pop = doc.hourly.precipitation_probability[best];
  let text = Math.round(temp) + "°F, wind " + Math.round(wind) + " mph";
  if (wind >= 15) text += ", windy";
  if (pop >= 50) text += ", rain likely";
  return { text: text };
}

async function geocode(name) {
  if (!name) return null;
  const url = "https://geocoding-api.open-meteo.com/v1/search?name=" + encodeURIComponent(name) + "&count=3&language=en&format=json";
  const doc = await grab(url, { timeout: 20000 });
  const hit = (doc.results || [])[0];
  if (!hit) return null;
  return { lat: hit.latitude, lon: hit.longitude };
}

main().catch(function (err) {
  console.error(err);
  process.exitCode = 1;
});
