/* Consensus points, source ranks, and matchup grades.
   No network. The build script and the unit tests both load this file. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.WURankMath = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var SUFFIX = { jr: 1, sr: 1, ii: 1, iii: 1, iv: 1, v: 1 };
  var POS_GROUP = {
    QB: "QB", RB: "RB", FB: "RB", WR: "WR", TE: "TE",
    DL: "DL", DE: "DL", DT: "DL", NT: "DL",
    LB: "LB", ILB: "LB", OLB: "LB", MLB: "LB",
    DB: "DB", CB: "DB", S: "DB", FS: "DB", SS: "DB"
  };
  var CANON = {
    WSH: "WAS", WAS: "WAS", JAC: "JAX", JAX: "JAX",
    LA: "LAR", LAR: "LAR", OAK: "LV", LV: "LV",
    SD: "LAC", LAC: "LAC"
  };
  /* ESPN public stat ids. Receiving first downs are not in this feed. */
  var ESPN_STAT = {
    3: "passYds",
    4: "passTd",
    20: "interceptions",
    23: "carries",
    24: "rushYds",
    25: "rushTd",
    26: "rushTwo",
    19: "passTwo",
    42: "recYds",
    43: "recTd",
    44: "recTwo",
    53: "receptions",
    72: "fumbleLost"
  };

  function num(v) {
    if (v == null || v === "") return null;
    var n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function round1(n) {
    return Math.round(n * 10) / 10;
  }

  function normName(name) {
    return String(name || "")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/'/g, "")
      .replace(/\./g, "")
      .replace(/-/g, " ")
      .replace(/[^a-z\s]/g, " ")
      .split(/\s+/)
      .filter(function (part) { return part && !SUFFIX[part]; })
      .join(" ");
  }

  function canonTeam(team) {
    var u = String(team || "").toUpperCase().trim();
    return CANON[u] || u;
  }

  function groupPos(pos) {
    return POS_GROUP[String(pos || "").toUpperCase()] || "";
  }

  function sleeperLine(row) {
    var r = row || {};
    return {
      passYds: r.pass_yd,
      passTd: r.pass_td,
      interceptions: r.pass_int,
      rushYds: r.rush_yd,
      rushTd: r.rush_td,
      carries: r.rush_att,
      receptions: r.rec,
      recYds: r.rec_yd,
      recTd: r.rec_td,
      teFirstDowns: r.rec_fd,
      fumbleLost: r.fum_lost,
      passTwo: r.pass_2pt,
      rushTwo: r.rush_2pt,
      recTwo: r.rec_2pt,
      krYds: r.kr_yd,
      prYds: r.pr_yd,
      krTd: r.kr_td,
      prTd: r.pr_td,
      solo: r.idp_tkl_solo,
      assisted: r.idp_tkl_ast,
      sacks: r.idp_sack,
      tfl: r.idp_tkl_loss,
      pd: r.idp_pass_def,
      defInt: r.idp_int,
      forcedFumble: r.idp_ff,
      qbHit: r.idp_qb_hit,
      safety: r.idp_safe,
      blockedKick: r.idp_blk_kick
    };
  }

  function espnLine(stats) {
    var line = {};
    var src = stats || {};
    Object.keys(ESPN_STAT).forEach(function (id) {
      if (src[id] == null && src[String(id)] == null) return;
      line[ESPN_STAT[id]] = src[id] != null ? src[id] : src[String(id)];
    });
    return line;
  }

  function hasCountingStat(line) {
    var keys = ["passYds", "passTd", "rushYds", "rushTd", "carries", "receptions", "recYds", "recTd", "solo", "assisted", "sacks", "tfl", "pd", "defInt", "krYds", "prYds"];
    return keys.some(function (k) { return num(line[k]) > 0.05; });
  }

  /* Projections set the consensus. Last-3 actuals only widen the range.
     A player with nothing but those actuals is not projected this week. */
  function projectionConsensus(sleeper, espn, recent) {
    var proj = consensus([sleeper, espn]);
    var band = consensus([sleeper, espn, recent]);
    if (proj.pts == null) return { pts: null, floor: null, ceil: null, n: 0 };
    return { pts: proj.pts, floor: band.floor, ceil: band.ceil, n: proj.n };
  }

  function consensus(points) {
    var xs = (points || []).map(num).filter(function (n) { return n != null; });
    if (!xs.length) return { pts: null, floor: null, ceil: null, n: 0 };
    var sum = 0;
    var lo = xs[0];
    var hi = xs[0];
    xs.forEach(function (n) {
      sum += n;
      if (n < lo) lo = n;
      if (n > hi) hi = n;
    });
    return { pts: round1(sum / xs.length), floor: round1(lo), ceil: round1(hi), n: xs.length };
  }

  function ordinalRanks(rows, valueOf) {
    var scored = (rows || []).filter(function (row) { return num(valueOf(row)) != null; });
    scored.sort(function (a, b) {
      var diff = valueOf(b) - valueOf(a);
      if (diff) return diff;
      return String(a.name || "").localeCompare(String(b.name || ""));
    });
    var map = {};
    scored.forEach(function (row, i) { map[row.key] = i + 1; });
    return map;
  }

  function isSplit(ranks, points, gap) {
    var rs = (ranks || []).map(num).filter(function (n) { return n != null; });
    var ps = (points || []).map(num).filter(function (n) { return n != null; });
    var rankGap = gap == null ? 12 : gap;
    if (rs.length >= 2 && Math.max.apply(null, rs) - Math.min.apply(null, rs) >= rankGap) return true;
    if (ps.length >= 2 && Math.max.apply(null, ps) - Math.min.apply(null, ps) >= 6) return true;
    return false;
  }

  /* homeSpread is negative when the home team is favored. */
  function impliedTeamTotals(homeSpread, total) {
    var spread = num(homeSpread);
    var tot = num(total);
    if (spread == null || tot == null) return null;
    return {
      home: round1((tot - spread) / 2),
      away: round1((tot + spread) / 2)
    };
  }

  /* Higher value is a better matchup. Needs at least four clubs. */
  function matchupGrade(value, all) {
    var mine = num(value);
    var xs = (all || []).map(num).filter(function (n) { return n != null; });
    if (mine == null || xs.length < 4) return null;
    var higher = 0;
    xs.forEach(function (v) { if (v > mine) higher += 1; });
    var place = higher + 1;
    var pct = (xs.length - higher - 0.5) / xs.length;
    var grade = pct >= 0.8 ? "A" : pct >= 0.6 ? "B" : pct >= 0.4 ? "C" : pct >= 0.2 ? "D" : "F";
    return { grade: grade, place: place, of: xs.length };
  }

  return {
    POS_GROUP: POS_GROUP,
    ESPN_STAT: ESPN_STAT,
    normName: normName,
    canonTeam: canonTeam,
    groupPos: groupPos,
    sleeperLine: sleeperLine,
    espnLine: espnLine,
    hasCountingStat: hasCountingStat,
    consensus: consensus,
    projectionConsensus: projectionConsensus,
    ordinalRanks: ordinalRanks,
    isSplit: isSplit,
    impliedTeamTotals: impliedTeamTotals,
    matchupGrade: matchupGrade,
    round1: round1
  };
});
