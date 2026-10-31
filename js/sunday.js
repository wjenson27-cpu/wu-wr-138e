/* Sunday Command Center math. No network, no roster files, no names of people. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.WUSunday = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var STALE_MS = 45 * 60 * 1000;
  var REFRESH_MS = 5 * 60 * 1000;
  var REFRESH_MINUTES = 5;
  var STALE_MINUTES = 45;
  var FEATURED_NAME = "Eagleridge Eddie's";

  function num(v) {
    var n = typeof v === "number" ? v : parseFloat(v);
    return isFinite(n) ? n : 0;
  }

  function round1(n) {
    return Math.round(num(n) * 10) / 10;
  }

  function oneDecimal(n) {
    return round1(n).toFixed(1);
  }

  /* Abramowitz and Stegun 7.1.26, via the erf approximation. */
  function normalCdf(z) {
    if (z === 0) return 0.5;
    if (z === Infinity) return 1;
    if (z === -Infinity) return 0;
    if (!isFinite(z)) return 0.5;
    var sign = z < 0 ? -1 : 1;
    var x = Math.abs(z) / Math.SQRT2;
    var a1 = 0.254829592;
    var a2 = -0.284496736;
    var a3 = 1.421413741;
    var a4 = -1.453152027;
    var a5 = 1.061405429;
    var t = 1 / (1 + 0.3275911 * x);
    var erf = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
    return 0.5 * (1 + sign * erf);
  }

  /*
   * P(featured finishes ahead).
   * μ = (score + remaining) − (oppScore + oppRemaining)
   * σ = √(remaining + oppRemaining)   variance = remaining projection, each side
   * P = Φ(μ / σ)
   * Both lineups finished (σ = 0): 1, 0, or 0.5 on a tie.
   * Negative remaining is treated as 0.
   */
  function winProbability(score, oppScore, remaining, oppRemaining) {
    var r = Math.max(0, num(remaining));
    var orr = Math.max(0, num(oppRemaining));
    var mean = (num(score) + r) - (num(oppScore) + orr);
    var variance = r + orr;
    if (variance <= 0) {
      if (mean > 0) return 1;
      if (mean < 0) return 0;
      return 0.5;
    }
    return normalCdf(mean / Math.sqrt(variance));
  }

  function isStale(updatedAt, now, staleMs) {
    var limit = staleMs == null ? STALE_MS : Number(staleMs);
    if (!isFinite(limit) || limit < 0) limit = STALE_MS;
    var t = typeof updatedAt === "number" ? updatedAt : Date.parse(updatedAt);
    if (!isFinite(t)) return true;
    var clock;
    if (now == null) clock = Date.now();
    else if (now instanceof Date) clock = now.getTime();
    else clock = Number(now);
    if (!isFinite(clock)) return true;
    return clock - t > limit;
  }

  function normStatus(status) {
    return String(status || "").toLowerCase().replace(/[\s_-]+/g, "");
  }

  function statusKind(status) {
    var s = normStatus(status);
    if (s === "live" || s === "inprogress" || s === "inprog") return "live";
    if (s === "final" || s === "finished" || s === "complete" || s === "completed") return "final";
    return "not_started";
  }

  function statusLabel(status) {
    var k = statusKind(status);
    if (k === "live") return "Live";
    if (k === "final") return "Final";
    return "Not started";
  }

  function injuryCode(injury) {
    var s = String(injury || "").trim().toUpperCase();
    if (!s || s === "NONE" || s === "ACTIVE" || s === "OK" || s === "PROBABLE" || s === "P") return "";
    if (s === "Q" || s === "QUESTIONABLE") return "Q";
    if (s === "D" || s === "DOUBTFUL") return "D";
    if (s === "O" || s === "OUT") return "OUT";
    if (s === "IR" || s === "INJUREDRESERVE") return "IR";
    return s;
  }

  function injuryPhrase(code) {
    if (code === "OUT") return "OUT";
    if (code === "D") return "Doubtful";
    if (code === "Q") return "Questionable";
    if (code === "IR") return "IR";
    return code || "";
  }

  function isLockInjury(injury) {
    var c = injuryCode(injury);
    return c === "OUT" || c === "D" || c === "IR";
  }

  function remainingOf(player) {
    if (!player) return 0;
    if (player.remainingProj == null || player.remainingProj === "") {
      if (statusKind(player.status) === "final") return 0;
      return Math.max(0, num(player.projection) - num(player.points));
    }
    return Math.max(0, num(player.remainingProj));
  }

  function teamTotals(team) {
    var score = 0;
    var remaining = 0;
    var projection = 0;
    var starters = (team && team.starters) || [];
    starters.forEach(function (p) {
      score += num(p.points);
      remaining += remainingOf(p);
      projection += num(p.projection);
    });
    return {
      score: round1(score),
      remaining: round1(remaining),
      projection: round1(projection),
      projectedFinal: round1(score + remaining)
    };
  }

  /* Points plus what's left, minus the full projection. Hidden before kickoff.
     Final games (remaining 0) reduce to points − projection. */
  function paceDelta(player) {
    if (statusKind(player && player.status) === "not_started") return null;
    return round1(num(player.points) + remainingOf(player) - num(player.projection));
  }

  function deltaTone(delta) {
    if (delta == null || !isFinite(delta)) return "none";
    if (delta > 0.05) return "up";
    if (delta < -0.05) return "down";
    return "flat";
  }

  function formatDelta(delta) {
    if (delta == null || !isFinite(delta)) return "";
    var n = round1(delta);
    if (n > 0) return "+" + n.toFixed(1);
    return n.toFixed(1);
  }

  function cleanSwap(swap) {
    if (!swap || !swap.player) return null;
    return {
      player: String(swap.player),
      pos: swap.pos ? String(swap.pos) : "",
      nflTeam: swap.nflTeam ? String(swap.nflTeam) : "",
      note: swap.note ? String(swap.note) : ""
    };
  }

  function starterRow(p) {
    var kind = statusKind(p.status);
    var delta = paceDelta(p);
    var inj = injuryCode(p.injury);
    return {
      player: p.player || "",
      pos: p.pos || "",
      nflTeam: p.nflTeam || "",
      slot: p.slot || "",
      status: kind,
      statusLabel: statusLabel(p.status),
      injury: inj,
      points: round1(p.points),
      projection: round1(p.projection),
      remaining: round1(remainingOf(p)),
      pointsLabel: kind === "not_started" ? "—" : oneDecimal(p.points),
      delta: delta,
      deltaLabel: formatDelta(delta),
      deltaTone: deltaTone(delta),
      swap: cleanSwap(p.swap)
    };
  }

  function lockAlerts(starters, teamName) {
    var out = [];
    (starters || []).forEach(function (p) {
      if (!p || p.starter === false) return;
      if (statusKind(p.status) !== "not_started") return;
      if (!isLockInjury(p.injury)) return;
      var code = injuryCode(p.injury);
      out.push({
        team: teamName || "",
        player: p.player || "",
        pos: p.pos || "",
        nflTeam: p.nflTeam || "",
        slot: p.slot || "",
        injury: code,
        injuryLabel: injuryPhrase(code),
        swap: cleanSwap(p.swap)
      });
    });
    return out;
  }

  function normalizeResult(raw) {
    var s = String(raw == null ? "" : raw).trim().toLowerCase();
    if (s === "yes" || s === "y" || s === "hit") return "Yes";
    if (s === "no" || s === "n" || s === "miss") return "No";
    if (s === "n/a" || s === "na") return "N/A";
    return "pending";
  }

  function parlayPicks(doc, week) {
    var picks = [];
    if (!doc || typeof doc !== "object") return picks;
    if (Array.isArray(doc.picks)) {
      doc.picks.forEach(function (p) {
        var pick = p.pick || p.player || "";
        if (!pick) return;
        picks.push({
          week: Number(p.week),
          participant: p.participant || p.name || "",
          pick: pick,
          result: normalizeResult(p.result != null ? p.result : p.td)
        });
      });
    } else {
      var groups = doc.participants || doc.owners;
      if (Array.isArray(groups)) {
        groups.forEach(function (g) {
          var who = (g && (g.participant || g.name || g.id)) || "";
          var weeks = (g && g.weeks) || {};
          Object.keys(weeks).forEach(function (w) {
            var cell = weeks[w] || {};
            var pick = cell.pick || cell.player || "";
            if (!pick) return;
            picks.push({
              week: Number(w),
              participant: who,
              pick: pick,
              result: normalizeResult(cell.result != null ? cell.result : cell.td)
            });
          });
        });
      }
    }
    if (week != null && week !== "") {
      picks = picks.filter(function (p) { return Number(p.week) === Number(week); });
    }
    return picks;
  }

  function parlayStatus(picks) {
    var active = (picks || []).filter(function (p) {
      return p && p.pick && p.result !== "N/A";
    });
    var yes = 0;
    var no = 0;
    var pending = 0;
    active.forEach(function (p) {
      if (p.result === "Yes") yes += 1;
      else if (p.result === "No") no += 1;
      else pending += 1;
    });
    var state = "empty";
    if (!active.length) state = "empty";
    else if (no > 0) state = "dead";
    else if (pending === 0) state = "hit";
    else state = "alive";
    return {
      state: state,
      alive: state === "alive",
      yes: yes,
      no: no,
      pending: pending,
      active: active.length
    };
  }

  function formatPt(iso) {
    var t = typeof iso === "number" ? iso : Date.parse(iso);
    if (!isFinite(t)) return "";
    var fmt = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Los_Angeles",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true
    });
    return fmt.format(new Date(t)).replace(/[\u202f\u2009]/g, " ") + " PT";
  }

  function findTeam(teams, id) {
    if (!id) return null;
    var want = String(id);
    for (var i = 0; i < teams.length; i++) {
      if (teams[i] && String(teams[i].id) === want) return teams[i];
    }
    return null;
  }

  function sideModel(team, displayName) {
    var totals = teamTotals(team);
    var name = displayName || (team && team.name) || "";
    return {
      id: (team && team.id) || "",
      name: name,
      record: (team && team.record) || "",
      score: totals.score,
      scoreLabel: oneDecimal(totals.score),
      remaining: totals.remaining,
      projectedFinal: totals.projectedFinal,
      projectedLabel: oneDecimal(totals.projectedFinal),
      starters: ((team && team.starters) || []).map(starterRow)
    };
  }

  function percentLabel(p) {
    if (!isFinite(p)) return "—";
    return (Math.round(p * 1000) / 10).toFixed(1) + "%";
  }

  function winTone(p) {
    if (p >= 0.55) return "good";
    if (p >= 0.45) return "mid";
    return "bad";
  }

  function buildModel(live, parlay, config, now) {
    live = live || {};
    config = config || {};
    var teams = Array.isArray(live.teams) ? live.teams : [];
    var featuredId = config.featuredTeam || live.featuredTeam;
    var featuredTeam = findTeam(teams, featuredId);
    var oppId = live.opponent || config.opponent;
    var oppTeam = findTeam(teams, oppId);
    if (!oppTeam) {
      for (var i = 0; i < teams.length; i++) {
        if (teams[i] && String(teams[i].id) !== String(featuredId)) {
          oppTeam = teams[i];
          break;
        }
      }
    }
    if (!featuredTeam || !oppTeam) {
      return { ok: false, error: "Matchup is missing a featured team or an opponent." };
    }
    var featuredName = config.featuredName || live.featuredName || FEATURED_NAME;
    var featured = sideModel(featuredTeam, featuredName);
    var opponent = sideModel(oppTeam, oppTeam.name || "Opponent");
    var winProb = winProbability(featured.score, opponent.score, featured.remaining, opponent.remaining);
    var staleMs = STALE_MS;
    if (config.staleMinutes != null && num(config.staleMinutes) > 0) staleMs = num(config.staleMinutes) * 60 * 1000;
    var refreshMinutes = config.refreshMinutes != null ? num(config.refreshMinutes) : REFRESH_MINUTES;
    if (refreshMinutes < 1) refreshMinutes = 1;
    var week = live.week;
    var picks = parlayPicks(parlay, week);
    var status = parlayStatus(picks);
    var alerts = lockAlerts(featuredTeam.starters, featured.name)
      .concat(lockAlerts(oppTeam.starters, opponent.name));
    return {
      ok: true,
      error: null,
      sample: !!live.sample,
      parlaySample: !!(parlay && parlay.sample),
      season: live.season,
      week: week,
      updatedAt: live.updatedAt,
      updatedLabel: formatPt(live.updatedAt),
      stale: isStale(live.updatedAt, now, staleMs),
      refreshMinutes: refreshMinutes,
      featured: featured,
      opponent: opponent,
      winProb: winProb,
      winPctLabel: percentLabel(winProb),
      winTone: winTone(winProb),
      alerts: alerts,
      parlay: {
        week: week,
        note: (parlay && (parlay.note || (parlay.weekNotes && parlay.weekNotes[String(week)]))) || "",
        picks: picks,
        state: status.state,
        alive: status.alive,
        yes: status.yes,
        no: status.no,
        pending: status.pending
      }
    };
  }

  return {
    STALE_MS: STALE_MS,
    REFRESH_MS: REFRESH_MS,
    REFRESH_MINUTES: REFRESH_MINUTES,
    STALE_MINUTES: STALE_MINUTES,
    FEATURED_NAME: FEATURED_NAME,
    normalCdf: normalCdf,
    winProbability: winProbability,
    isStale: isStale,
    statusKind: statusKind,
    statusLabel: statusLabel,
    injuryCode: injuryCode,
    remainingOf: remainingOf,
    teamTotals: teamTotals,
    paceDelta: paceDelta,
    lockAlerts: lockAlerts,
    normalizeResult: normalizeResult,
    parlayPicks: parlayPicks,
    parlayStatus: parlayStatus,
    formatPt: formatPt,
    buildModel: buildModel,
    percentLabel: percentLabel
  };
});
