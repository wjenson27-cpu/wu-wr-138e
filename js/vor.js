/* Replacement value and lineup fit for the War Room trade tab.
   No DOM. The page and the unit tests both load this file. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.WUVor = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var POS = ["QB", "RB", "WR", "TE", "DL", "LB", "DB"];
  var SKILL = ["RB", "WR", "TE"];
  var IDP = ["DL", "LB", "DB"];
  /* Season rate already leans recent (0.72 per older week inside the value file).
     When a last-3 rate exists, blend 60% season and 40% last 3. */
  var WEIGHTS = { season: 0.6, last3: 0.4, decay: 0.72 };
  var SCARCITY_SLOPE = 0.25;
  var SCARCITY_MIN = 0.85;
  var SCARCITY_MAX = 1.4;

  function num(v) {
    if (v == null || v === "") return null;
    var n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function round1(n) {
    return Math.round(n * 10) / 10;
  }

  function round2(n) {
    return Math.round(n * 100) / 100;
  }

  function avg(xs) {
    if (!xs.length) return 0;
    var s = 0;
    for (var i = 0; i < xs.length; i++) s += xs[i];
    return s / xs.length;
  }

  function median(xs) {
    if (!xs.length) return 0;
    var s = xs.slice().sort(function (a, b) { return a - b; });
    var m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }

  function blendRate(season, last3, weights) {
    var w = weights || WEIGHTS;
    var s = num(season);
    var l = num(last3);
    if (s == null && l == null) return { rate: 0, seasonWeight: 0, last3Weight: 0, usedLast3: false };
    if (l == null) return { rate: s, seasonWeight: 1, last3Weight: 0, usedLast3: false };
    if (s == null) return { rate: l, seasonWeight: 0, last3Weight: 1, usedLast3: true };
    return {
      rate: w.season * s + w.last3 * l,
      seasonWeight: w.season,
      last3Weight: w.last3,
      usedLast3: true
    };
  }

  function tierSize(count) {
    if (count >= 8) return 4;
    if (count >= 4) return 2;
    return 1;
  }

  /* Drop from the top tier to the next tier, in points per game. */
  function eliteDrop(rates) {
    var sorted = rates.slice().sort(function (a, b) { return b - a; });
    var size = tierSize(sorted.length);
    if (sorted.length < size * 2) return 0;
    return avg(sorted.slice(0, size)) - avg(sorted.slice(size, size * 2));
  }

  function scarcityMultiplier(drop, drops) {
    var positive = (drops || []).filter(function (d) { return d > 0; });
    var typical = median(positive);
    if (!(typical > 0) || !(drop > 0)) return 1;
    var ratio = drop / typical;
    var mult = 1 + (ratio - 1) * SCARCITY_SLOPE;
    if (mult < SCARCITY_MIN) return SCARCITY_MIN;
    if (mult > SCARCITY_MAX) return SCARCITY_MAX;
    return mult;
  }

  function byPos(players, rateOf) {
    var map = {};
    POS.forEach(function (p) { map[p] = []; });
    players.forEach(function (p) {
      if (map[p.pos]) map[p.pos].push(p);
    });
    POS.forEach(function (pos) {
      map[pos].sort(function (a, b) {
        return rateOf(b) - rateOf(a) || String(a.name).localeCompare(String(b.name));
      });
    });
    return map;
  }

  /* How many players at each position actually start, once flex spots
     go to the higher scores. */
  function starterCounts(grouped, lineup, teamCount, rateOf) {
    var dedicated = {
      QB: (lineup.QB || 0) * teamCount,
      RB: (lineup.RB || 0) * teamCount,
      WR: (lineup.WR || 0) * teamCount,
      TE: (lineup.TE || 0) * teamCount,
      DL: (lineup.DL || 0) * teamCount,
      LB: (lineup.LB || 0) * teamCount,
      DB: (lineup.DB || 0) * teamCount
    };
    var counts = {};
    var remaining = {};
    POS.forEach(function (pos) {
      var list = grouped[pos] || [];
      var take = Math.min(dedicated[pos] || 0, list.length);
      counts[pos] = take;
      remaining[pos] = list.slice(take);
    });
    function fill(positions, slots) {
      var pool = [];
      positions.forEach(function (pos) {
        (remaining[pos] || []).forEach(function (p) {
          pool.push({ pos: pos, rate: rateOf(p), name: p.name });
        });
      });
      pool.sort(function (a, b) {
        return b.rate - a.rate || String(a.name).localeCompare(String(b.name));
      });
      pool.slice(0, slots).forEach(function (p) { counts[p.pos] += 1; });
    }
    fill(SKILL, (lineup.RWT || 0) * teamCount);
    fill(IDP, (lineup.ID || 0) * teamCount);
    return counts;
  }

  function nthRate(sortedPlayers, n, rateOf) {
    if (!sortedPlayers.length || n <= 0) return 0;
    var idx = Math.min(n, sortedPlayers.length) - 1;
    return rateOf(sortedPlayers[idx]);
  }

  function computeReplacement(opts) {
    var lineup = opts.lineup || {};
    var teamCount = opts.teamCount || 14;
    var weights = opts.weights || WEIGHTS;
    var useWaiver = opts.useWaiver !== false;
    var useScarcity = opts.scarcity !== false;
    var rateOf = function (p) { return p._rate; };

    var rostered = (opts.rostered || []).map(function (p) {
      var b = blendRate(p.ppg != null ? p.ppg : p.rate, p.last3Ppg, weights);
      return Object.assign({}, p, { _rate: b.rate, _blend: b });
    }).filter(function (p) { return POS.indexOf(p.pos) !== -1; });

    var fas = [];
    if (useWaiver) {
      fas = (opts.freeAgents || []).filter(function (p) {
        var pct = num(p.rosteredPct);
        return pct == null || pct < 100;
      }).map(function (p) {
        var season = p.fpg != null ? p.fpg : p.ppg;
        var last3 = p.last3Fpg != null ? p.last3Fpg : p.last3Ppg;
        var b = blendRate(season, last3, weights);
        return Object.assign({}, p, { _rate: b.rate, _blend: b });
      }).filter(function (p) { return POS.indexOf(p.pos) !== -1; });
    }

    var grouped = byPos(rostered, rateOf);
    var counts = starterCounts(grouped, lineup, teamCount, rateOf);
    var faGrouped = byPos(fas, rateOf);
    var drops = {};
    POS.forEach(function (pos) { drops[pos] = eliteDrop(grouped[pos].map(rateOf)); });
    var dropList = POS.map(function (pos) { return drops[pos]; });
    var scarcity = {};
    POS.forEach(function (pos) {
      scarcity[pos] = useScarcity ? scarcityMultiplier(drops[pos], dropList) : 1;
    });

    var replacement = {};
    POS.forEach(function (pos) {
      var rosteredBase = nthRate(grouped[pos], counts[pos], rateOf);
      var waiverBase = faGrouped[pos].length ? rateOf(faGrouped[pos][0]) : null;
      var waiverUsed = waiverBase != null && waiverBase > rosteredBase;
      var used = waiverUsed ? waiverBase : rosteredBase;
      replacement[pos] = {
        rosteredRaw: rosteredBase,
        waiverRaw: waiverBase,
        usedRaw: used,
        rostered: round1(rosteredBase),
        waiver: waiverBase == null ? null : round1(waiverBase),
        used: round1(used),
        source: waiverUsed ? "waiver" : "rostered",
        starters: counts[pos],
        scarcity: round2(scarcity[pos]),
        drop: round2(drops[pos])
      };
    });

    function rawVor(rate, pos) {
      var rep = replacement[pos];
      if (!rep) return 0;
      return (rate - rep.usedRaw) * scarcity[pos];
    }

    function vorFor(rate, pos) {
      return round1(rawVor(rate, pos));
    }

    var ranks = {};
    POS.forEach(function (pos) {
      grouped[pos].forEach(function (p, i) { ranks[pos + "|" + p.name] = i + 1; });
    });

    var priced = rostered.map(function (p) {
      return {
        name: p.name,
        pos: p.pos,
        rate: round1(p._rate),
        vor: vorFor(p._rate, p.pos),
        rank: ranks[p.pos + "|" + p.name] || null,
        usedLast3: !!(p._blend && p._blend.usedLast3)
      };
    });

    var last3Count = rostered.filter(function (p) { return p._blend && p._blend.usedLast3; }).length
      + fas.filter(function (p) { return p._blend && p._blend.usedLast3; }).length;

    return {
      replacement: replacement,
      scarcity: scarcity,
      counts: counts,
      weights: weights,
      priced: priced,
      vorFor: vorFor,
      last3Count: last3Count,
      rosteredCount: rostered.length,
      freeAgentCount: fas.length
    };
  }

  var DEFAULT_LINEUP = { QB: 1, RB: 1, WR: 1, TE: 1, RWT: 3, DL: 1, LB: 1, DB: 2, ID: 3 };

  /* Best lineup by weekly points. IR cannot start. Empty slots score 0. */
  function optimizeLineup(players, lineup) {
    var rules = lineup || DEFAULT_LINEUP;
    var active = (players || []).filter(function (p) {
      return !p.ir && !p.ineligible && POS.indexOf(p.pos) !== -1;
    });
    var by = {};
    POS.forEach(function (pos) { by[pos] = []; });
    active.forEach(function (p) { by[p.pos].push(p); });
    POS.forEach(function (pos) {
      by[pos].sort(function (a, b) {
        return (Number(b.ppg) || 0) - (Number(a.ppg) || 0) || String(a.name).localeCompare(String(b.name));
      });
    });
    var used = {};
    var starters = [];
    function take(pos, slot, count) {
      var got = 0;
      (by[pos] || []).forEach(function (p) {
        if (got >= count || used[p.name]) return;
        used[p.name] = true;
        starters.push({ slot: slot, player: p });
        got += 1;
      });
    }
    function takeFlex(positions, slot, count) {
      var pool = [];
      positions.forEach(function (pos) {
        (by[pos] || []).forEach(function (p) { if (!used[p.name]) pool.push(p); });
      });
      pool.sort(function (a, b) {
        return (Number(b.ppg) || 0) - (Number(a.ppg) || 0) || String(a.name).localeCompare(String(b.name));
      });
      pool.slice(0, count).forEach(function (p) {
        used[p.name] = true;
        starters.push({ slot: slot, player: p });
      });
    }
    take("QB", "QB", rules.QB || 0);
    take("RB", "RB", rules.RB || 0);
    take("WR", "WR", rules.WR || 0);
    take("TE", "TE", rules.TE || 0);
    takeFlex(SKILL, "FLEX", rules.RWT || 0);
    take("DL", "DL", rules.DL || 0);
    take("LB", "LB", rules.LB || 0);
    take("DB", "DB", rules.DB || 0);
    takeFlex(IDP, "IDP", rules.ID || 0);
    var total = 0;
    var slotOf = {};
    starters.forEach(function (row) {
      total += Number(row.player.ppg) || 0;
      slotOf[row.player.name] = row.slot;
    });
    return { starters: starters, total: total, slotOf: slotOf };
  }

  function isStale(asOf, maxDays, now) {
    var t = Date.parse(asOf);
    if (!Number.isFinite(t)) return true;
    var clock = now ? now.getTime() : Date.now();
    return clock - t > maxDays * 86400000;
  }

  return {
    POS: POS,
    SKILL: SKILL,
    IDP: IDP,
    WEIGHTS: WEIGHTS,
    DEFAULT_LINEUP: DEFAULT_LINEUP,
    blendRate: blendRate,
    eliteDrop: eliteDrop,
    scarcityMultiplier: scarcityMultiplier,
    tierSize: tierSize,
    starterCounts: starterCounts,
    nthRate: nthRate,
    computeReplacement: computeReplacement,
    optimizeLineup: optimizeLineup,
    isStale: isStale,
    round1: round1
  };
});
