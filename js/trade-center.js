/* Season trade grades for the War Room. Uses the trade analyzer's
   replacement model and current rest-of-season prices. Owner names,
   pending offers, and bids are never shown. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.WUTradeCenter = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var SOURCE_FILE = "data/hq/trades.json";
  var VALUES_FILE = "data/player-values.json";
  var SCORE_SCALE = 60;
  var FEATURED = "Eagleridge Eddie's";
  var SUFFIX = { jr: 1, sr: 1, ii: 1, iii: 1, iv: 1, v: 1 };
  var VALUE_POS = ["QB", "RB", "WR", "TE", "DL", "LB", "DB"];
  var TEAM_ALIAS = {
    "eagle ridge eddies": "eddies",
    "eagleridge eddies": "eddies",
    "towner top aga bottom": "ttab",
    "ttab": "ttab"
  };

  function analyzer() {
    var host = typeof globalThis !== "undefined" ? globalThis : {};
    return host.WUTradeAnalyzer || null;
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function round1(n) {
    if (!Number.isFinite(n)) return null;
    return Math.round(n * 10) / 10;
  }

  function signed1(n) {
    var rounded = round1(n);
    if (rounded == null) return "—";
    if (rounded > 0) return "+" + rounded.toFixed(1);
    return rounded.toFixed(1);
  }

  function normPlayer(name) {
    var parts = String(name || "")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/'/g, "")
      .replace(/\./g, "")
      .replace(/-/g, " ")
      .replace(/[^a-z\s]/g, " ")
      .split(/\s+/)
      .filter(function (part) { return part && !SUFFIX[part]; });
    var joined = [];
    parts.forEach(function (part) {
      var prev = joined[joined.length - 1];
      if (part.length === 1 && prev && prev.length <= 2) joined[joined.length - 1] = prev + part;
      else joined.push(part);
    });
    return joined.join(" ");
  }

  function teamKey(name) {
    return String(name || "")
      .replace(/\s*\([^)]*\)\s*/g, " ")
      .toLowerCase()
      .replace(/['’]/g, "")
      .replace(/[^a-z0-9]+/g, " ")
      .trim()
      .replace(/\s+/g, " ");
  }

  function displayName(id, fallback) {
    if (id === "eddies") return FEATURED;
    if (id === "ttab") return "TTAB";
    var text = String(fallback || "").replace(/\s*\([^)]*\)\s*/g, " ").replace(/\s+/g, " ").trim();
    return text || id || "Club";
  }

  function teamDirectory(teams) {
    var byId = {};
    var byKey = {};
    (teams || []).forEach(function (team) {
      if (!team || !team.id) return;
      byId[team.id] = team;
      byKey[teamKey(team.name)] = team.id;
    });
    Object.keys(TEAM_ALIAS).forEach(function (key) {
      if (byId[TEAM_ALIAS[key]]) byKey[key] = TEAM_ALIAS[key];
    });
    return { byId: byId, byKey: byKey };
  }

  function resolveTeam(raw, directory) {
    var key = teamKey(raw);
    var id = directory.byKey[key] || TEAM_ALIAS[key] || "";
    if (!id) {
      return { id: "", name: displayName("", String(raw || "").replace(/\s*\([^)]*\)\s*/g, " ")) };
    }
    var team = directory.byId[id];
    return { id: id, name: displayName(id, team && team.name) };
  }

  function gamesLeftOf(valuesFile) {
    var weeks = Number(valuesFile && valuesFile.weeksRemaining);
    var bye = Number(valuesFile && valuesFile.byeWeeksAssumedLeft);
    if (!(weeks > 0)) return null;
    var left = weeks - (bye > 0 ? bye : 0);
    return left > 0 ? left : null;
  }

  function valueBook(valuesFile) {
    var byNorm = new Map();
    function add(name, row) {
      var key = normPlayer(name);
      if (!key || !row) return;
      if (!byNorm.has(key)) byNorm.set(key, []);
      byNorm.get(key).push(row);
    }
    ((valuesFile && valuesFile.players) || []).forEach(function (row) {
      add(row.name, row);
      (row.aliases || []).forEach(function (alias) { add(alias, row); });
    });
    var ppd = Number(valuesFile && valuesFile.faab && valuesFile.faab.pointsPerDollar);
    return {
      byNorm: byNorm,
      pointsPerDollar: Number.isFinite(ppd) ? ppd : null,
      gamesLeft: gamesLeftOf(valuesFile),
      asOf: valuesFile && valuesFile.asOf ? String(valuesFile.asOf) : ""
    };
  }

  function dedupe(rows) {
    var out = [];
    var seen = new Set();
    (rows || []).forEach(function (row) {
      var id = (row && row.name) + "|" + (row && row.position);
      if (!row || seen.has(id)) return;
      seen.add(id);
      out.push(row);
    });
    return out;
  }

  function findPlayer(asset, book) {
    var key = normPlayer(asset.name);
    var hits = dedupe(book.byNorm.get(key) || []);
    if (!hits.length) {
      var squash = key.replace(/ /g, "");
      var found = [];
      book.byNorm.forEach(function (rows, nameKey) {
        if (nameKey.replace(/ /g, "") === squash) found = found.concat(rows);
      });
      hits = dedupe(found);
    }
    if (asset.pos) {
      var posHits = hits.filter(function (row) { return row.position === asset.pos; });
      if (posHits.length === 1) return posHits[0];
      if (posHits.length > 1) return null;
      if (hits.length === 1 && hits[0].position !== asset.pos) return null;
    }
    return hits.length === 1 ? hits[0] : null;
  }

  function parseAsset(raw) {
    var text = String(raw || "").trim();
    var faab = text.match(/^\$(\d+(?:\.\d+)?)\s*FAAB\b/i);
    if (faab) {
      return { kind: "faab", dollars: Number(faab[1]), label: "$" + faab[1] + " FAAB" };
    }
    if (/\bdraft picks?\b|\bpick swap\b|\bchairs?\b/i.test(text)) {
      return { kind: "pick", label: text.replace(/\s+/g, " ") };
    }
    var pos = null;
    var name = text;
    var match = text.match(/^(.*)\s+\(([A-Z]{1,4})\)$/);
    if (match) {
      name = match[1].trim();
      pos = match[2];
    }
    return { kind: "player", name: name, pos: pos, label: name };
  }

  function scoreFromNet(net) {
    if (!Number.isFinite(net)) return null;
    var score = Math.round(50 + 50 * Math.tanh(net / SCORE_SCALE));
    if (score < 0) return 0;
    if (score > 100) return 100;
    return score;
  }

  function letterGrade(score) {
    if (!Number.isFinite(score)) return "";
    if (score >= 85) return "A";
    if (score >= 70) return "B";
    if (score >= 45) return "C";
    if (score >= 25) return "D";
    return "F";
  }

  function buildPlan(rosters, valuesFile, freeAgents) {
    var ta = analyzer();
    if (!ta) return null;
    var rates = ta.rateIndex(valuesFile);
    var rosteredKeys = new Set();
    var teams = [];
    Object.keys(rosters || {}).forEach(function (id) {
      var players = ta.rosterPlayers(rosters[id]);
      ta.attachRates(players, rates, null);
      players.forEach(function (player) {
        if (player.key) rosteredKeys.add(player.key);
      });
      teams.push({
        id: id,
        players: players.map(function (player) {
          var pos = VALUE_POS.indexOf(player.valuePos) !== -1 ? player.valuePos : player.pos;
          return { key: player.key, name: player.name, pos: pos, ppg: player.ppg, ir: player.ir };
        })
      });
    });
    var fas = ta.freeAgentRates(freeAgents, rosteredKeys);
    return ta.replacementPlan(teams, fas, ta.BILL_LINEUP, ta.TEAM_COUNT);
  }

  function pricePlayer(row, plan) {
    var ta = analyzer();
    var ppg = Number(row && row.ppg);
    var ros = Number(row && row.value);
    var vor = null;
    if (ta && plan && Number.isFinite(ppg) && VALUE_POS.indexOf(row.position) !== -1) {
      vor = ta.playerVor({ ppg: ppg, pos: row.position, valuePos: row.position }, plan);
    }
    return {
      name: row.name,
      pos: row.position,
      ppg: Number.isFinite(ppg) ? ppg : null,
      vor: Number.isFinite(vor) ? vor : null,
      ros: Number.isFinite(ros) ? ros : null,
      injury: row.injury ? String(row.injury) : ""
    };
  }

  function priceList(list, book, plan) {
    var rows = [];
    var vor = 0;
    var ros = 0;
    var missing = false;
    var unpriced = false;
    (list || []).forEach(function (raw) {
      var asset = parseAsset(raw);
      if (asset.kind === "faab") {
        var rosBit = null;
        var vorBit = null;
        if (Number.isFinite(book.pointsPerDollar) && Number.isFinite(book.gamesLeft)) {
          rosBit = asset.dollars * book.pointsPerDollar;
          vorBit = rosBit / book.gamesLeft;
          ros += rosBit;
          vor += vorBit;
        } else missing = true;
        rows.push({
          kind: "faab",
          label: asset.label,
          pos: "",
          dollars: asset.dollars,
          vor: vorBit,
          ros: rosBit,
          missing: rosBit == null
        });
        return;
      }
      if (asset.kind === "pick") {
        unpriced = true;
        rows.push({ kind: "pick", label: asset.label, pos: "PICK", vor: null, ros: null, unpriced: true });
        return;
      }
      var hit = findPlayer(asset, book);
      if (!hit) {
        missing = true;
        rows.push({ kind: "player", label: asset.label, pos: asset.pos || "", vor: null, ros: null, missing: true });
        return;
      }
      var priced = pricePlayer(hit, plan);
      if (priced.vor == null || priced.ros == null) missing = true;
      else {
        vor += priced.vor;
        ros += priced.ros;
      }
      rows.push({
        kind: "player",
        label: priced.name,
        pos: priced.pos,
        vor: priced.vor,
        ros: priced.ros,
        injury: priced.injury,
        missing: priced.vor == null || priced.ros == null
      });
    });
    return {
      rows: rows,
      vor: missing ? null : vor,
      ros: missing ? null : ros,
      missing: missing,
      unpriced: unpriced
    };
  }

  function isCompleted(trade, season) {
    if (!trade || String(trade.status || "").toLowerCase() !== "completed") return false;
    if (trade.official === false) return false;
    if (trade.pending === true) return false;
    var year = String(trade.date || "").slice(0, 4);
    if (season && year && year !== String(season)) return false;
    return true;
  }

  function tradeSortKey(trade) {
    var date = String(trade.date || "");
    var time = String(trade.time || "");
    var match = time.match(/(\d{1,2}):(\d{2})\s*(AM|PM)/i);
    var minutes = 0;
    if (match) {
      var hour = Number(match[1]) % 12;
      if (String(match[3]).toUpperCase() === "PM") hour += 12;
      minutes = hour * 60 + Number(match[2]);
    }
    return date + " " + String(minutes).padStart(4, "0");
  }

  function winnerOf(sideA, sideB) {
    if (!sideA || !sideB || sideA.score == null || sideB.score == null) {
      return { kind: "incomplete", name: "", text: "Value missing" };
    }
    if (Math.abs(sideA.netRos - sideB.netRos) < 1) {
      return { kind: "even", name: "", text: "Even" };
    }
    var win = sideA.score >= sideB.score ? sideA : sideB;
    return { kind: "win", name: win.name, id: win.id, text: win.name + " wins" };
  }

  function gradeTrade(trade, book, plan, directory) {
    var teamA = resolveTeam(trade.teamA, directory);
    var teamB = resolveTeam(trade.teamB, directory);
    var sentA = priceList(trade.givesA, book, plan);
    var sentB = priceList(trade.givesB, book, plan);
    var missing = sentA.missing || sentB.missing;
    function side(team, sent, got) {
      var netVor = missing ? null : got.vor - sent.vor;
      var netRos = missing ? null : got.ros - sent.ros;
      var score = scoreFromNet(netRos);
      return {
        id: team.id,
        name: team.name,
        sent: sent.rows,
        received: got.rows,
        netVor: netVor,
        netRos: netRos,
        score: score,
        grade: letterGrade(score),
        unpriced: !!(sent.unpriced || got.unpriced)
      };
    }
    var a = side(teamA, sentA, sentB);
    var b = side(teamB, sentB, sentA);
    return {
      date: trade.date || "",
      time: trade.time || "",
      week: trade.week == null ? null : trade.week,
      sides: [a, b],
      winner: winnerOf(a, b),
      complete: !missing
    };
  }

  function leaderboard(trades, teams) {
    var rows = {};
    (teams || []).forEach(function (team) {
      if (!team || !team.id) return;
      rows[team.id] = {
        id: team.id,
        name: displayName(team.id, team.name),
        trades: 0,
        netVor: 0,
        scoreSum: 0,
        scored: 0
      };
    });
    function bucket(id, name) {
      if (!rows[id]) {
        rows[id] = { id: id, name: name, trades: 0, netVor: 0, scoreSum: 0, scored: 0 };
      }
      return rows[id];
    }
    (trades || []).forEach(function (trade) {
      trade.sides.forEach(function (side) {
        if (!side.id) return;
        var row = bucket(side.id, side.name);
        row.trades += 1;
        if (trade.complete && side.netVor != null && side.score != null) {
          row.netVor += side.netVor;
          row.scoreSum += side.score;
          row.scored += 1;
        }
      });
    });
    return Object.keys(rows).map(function (id) {
      var row = rows[id];
      var avg = row.scored ? row.scoreSum / row.scored : null;
      return {
        id: row.id,
        name: row.name,
        trades: row.trades,
        netVor: row.scored ? row.netVor : (row.trades ? null : 0),
        avgScore: avg == null ? null : Math.round(avg * 10) / 10,
        avgGrade: avg == null ? "" : letterGrade(Math.round(avg))
      };
    }).sort(function (a, b) {
      var av = a.netVor == null ? -Infinity : a.netVor;
      var bv = b.netVor == null ? -Infinity : b.netVor;
      if (bv !== av) return bv - av;
      var as = a.avgScore == null ? -1 : a.avgScore;
      var bs = b.avgScore == null ? -1 : b.avgScore;
      if (bs !== as) return bs - as;
      return String(a.name).localeCompare(String(b.name));
    });
  }

  function lopsided(trades, count) {
    return (trades || []).filter(function (trade) { return trade.complete; }).slice().sort(function (a, b) {
      var gapA = Math.abs(a.sides[0].netRos);
      var gapB = Math.abs(b.sides[0].netRos);
      if (gapB !== gapA) return gapB - gapA;
      return String(b.date).localeCompare(String(a.date));
    }).slice(0, count || 3);
  }

  function formatSourceStamp(raw) {
    var text = String(raw || "").trim();
    if (!text) return "";
    if (/PT$/i.test(text)) return text.replace(/\s*PT\s*$/i, " PT");
    var parsed = Date.parse(text);
    if (Number.isFinite(parsed) && /T|\d{1,2}:\d{2}/.test(text)) {
      var parts = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Los_Angeles",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "numeric",
        minute: "2-digit",
        hour12: true
      }).formatToParts(new Date(parsed));
      function bit(type) {
        var found = parts.filter(function (part) { return part.type === type; })[0];
        return found ? found.value : "";
      }
      return bit("year") + "-" + bit("month") + "-" + bit("day") + " " +
        bit("hour") + ":" + bit("minute") + " " + bit("dayPeriod").toUpperCase() + " PT";
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text + " PT";
    return /PT/i.test(text) ? text : text + " PT";
  }

  function sourceStamp(doc) {
    if (!doc) return "";
    return formatSourceStamp(doc.lastSynced || doc.updated || "");
  }

  function seasonReport(doc, context) {
    var ctx = context || {};
    var directory = teamDirectory(ctx.teams);
    var book = valueBook(ctx.values);
    var plan = ctx.plan || buildPlan(ctx.rosters, ctx.values, ctx.freeAgents);
    var season = doc && doc.season;
    var all = (doc && doc.trades) || [];
    var trades = all.filter(function (trade) { return isCompleted(trade, season); }).slice().sort(function (a, b) {
      return tradeSortKey(b).localeCompare(tradeSortKey(a));
    }).map(function (trade) {
      return gradeTrade(trade, book, plan, directory);
    });
    var handshakes = all.filter(function (trade) {
      return trade && String(trade.status || "").toLowerCase() === "completed" && trade.official === false;
    }).length;
    var ta = analyzer();
    return {
      sourceFile: SOURCE_FILE,
      valuesFile: VALUES_FILE,
      asOf: sourceStamp(doc),
      valuesAsOf: book.asOf,
      pointsPerDollar: book.pointsPerDollar,
      gamesLeft: book.gamesLeft,
      count: trades.length,
      handshakesExcluded: handshakes,
      pendingExcluded: ((doc && doc.pending) || []).length,
      plan: plan,
      formula: ta ? ta.formulaNote(plan) : "",
      leaderboard: leaderboard(trades, ctx.teams),
      lopsided: lopsided(trades, 3),
      trades: trades
    };
  }

  function assetLine(row) {
    var pos = row.pos ? '<span class="pos ' + esc(row.pos) + '">' + esc(row.pos) + "</span>" : "";
    var extra = "";
    if (row.missing) extra = '<span class="xmiss">No price</span>';
    else if (row.unpriced) extra = '<span class="xmiss">Not priced</span>';
    else extra = '<span class="xnums">VOR ' + esc(signed1(row.vor)) + " · ROS " + esc(signed1(row.ros)) + "</span>";
    var flag = row.injury ? '<span class="tc-flag">' + esc(row.injury) + "</span>" : "";
    return "<li>" + pos + '<span class="xname">' + esc(row.label) + "</span>" + flag + extra + "</li>";
  }

  function sideBlock(side) {
    var you = side.id === "eddies" ? " you" : "";
    var grade = side.grade
      ? '<span class="rk-grade g' + esc(side.grade) + '">' + esc(side.grade) + "</span>"
      : '<span class="rk-grade">—</span>';
    var score = side.score == null ? "—" : String(side.score);
    return '<div class="xside' + you + '"><div class="xside-top"><h3>' + esc(side.name) + "</h3>" + grade +
      '<b class="xscore">' + esc(score) + '</b></div><p class="xnet">Net VOR ' + esc(signed1(side.netVor)) +
      " · ROS " + esc(signed1(side.netRos)) + '</p><p class="xgot">Received</p><ul class="xassets">' +
      (side.received.length ? side.received.map(assetLine).join("") : "<li>Nothing</li>") +
      '</ul><p class="xgot">Sent</p><ul class="xassets">' +
      (side.sent.length ? side.sent.map(assetLine).join("") : "<li>Nothing</li>") + "</ul></div>";
  }

  function tradeCard(trade) {
    var when = trade.date || "Undated";
    if (trade.time) when += " · " + trade.time;
    if (trade.week != null) when += " · Week " + trade.week;
    var tone = trade.winner.kind === "win" ? "win" : (trade.winner.kind === "even" ? "even" : "miss");
    var note = trade.sides.some(function (side) { return side.unpriced; })
      ? '<p class="tiny">Draft picks are not on the current value board.</p>'
      : "";
    if (trade.complete && trade.winner.kind === "win") {
      var sideA = trade.sides[0];
      var vorName = sideA.netVor > 0.05 ? sideA.name : (sideA.netVor < -0.05 ? trade.sides[1].name : "");
      if (vorName && vorName !== trade.winner.name) {
        note += '<p class="tiny">Points per game and the rest-of-season grade point different ways. The winner is the grade.</p>';
      }
    }
    return '<article class="card xtrade"><div class="xtrade-top"><h3>' + esc(when) +
      '</h3><span class="xwin ' + tone + '">' + esc(trade.winner.text) + "</span></div><div class=\"xsides\">" +
      trade.sides.map(sideBlock).join("") + "</div>" + note + "</article>";
  }

  function boardRow(row) {
    var you = row.id === "eddies" ? " you" : "";
    var grade = row.avgGrade
      ? '<span class="rk-grade g' + esc(row.avgGrade) + '">' + esc(row.avgGrade) + "</span>"
      : "—";
    var avg = row.avgScore == null ? "—" : row.avgScore.toFixed(1);
    return "<tr class=\"" + you.trim() + "\"><td>" + esc(row.name) + "</td><td>" + row.trades +
      "</td><td>" + esc(signed1(row.netVor)) + "</td><td>" + grade + " " + esc(avg) + "</td></tr>";
  }

  function render(report) {
    if (!report) {
      return '<div class="card"><p>The trade log has not loaded.</p></div>';
    }
    var note = "Grades use current rest-of-season values from " + VALUES_FILE +
      (report.valuesAsOf ? " (as of " + report.valuesAsOf + ")" : "") +
      ", not each player's value on the day of the trade. Net VOR is points per game over the analyzer replacement line: 14 teams, 1 QB, 1 RB, 1 WR, 1 TE, and 3 non-QB flex, plus 1 DL, 1 LB, 2 DB, and 3 IDP flex, with free agents in the pool. A score of 50 is an even deal. FAAB is included" +
      (Number.isFinite(report.pointsPerDollar) ? " at " + report.pointsPerDollar + " rest-of-season points per dollar" : "") +
      (report.gamesLeft ? ", spread across " + report.gamesLeft + " games left on that board." : ".");
    var html = '<div class="card"><h2>Trade Center</h2><p class="xsource">Source: ' + esc(report.sourceFile) +
      " · as of " + esc(report.asOf || "unknown PT") + "</p><p>" + esc(note) + "</p><p class=\"tiny\">" +
      report.count + " completed 2026 trades. " + report.handshakesExcluded +
      " handshake rows that never posted are left out. Pending offers and bids are not shown.</p></div>";
    html += '<div class="card"><h2>Season leaderboard</h2><p class="tiny">Total net trade VOR, trade count, and average grade. Sorted by net VOR.</p><div class="scroll"><table class="sheet xboard"><thead><tr><th>Team</th><th>Trades</th><th>Net VOR</th><th>Avg grade</th></tr></thead><tbody>';
    html += report.leaderboard.map(boardRow).join("");
    html += "</tbody></table></div></div>";
    html += '<div class="sec">Most lopsided</div>';
    html += report.lopsided.map(tradeCard).join("");
    html += '<div class="sec">Every completed trade</div>';
    html += report.trades.map(tradeCard).join("");
    if (report.formula) html += '<p class="tiny xformula">' + esc(report.formula) + "</p>";
    return html;
  }

  function mount(bundle) {
    var rootEl = document.getElementById("pcenter");
    if (!rootEl) return null;
    var report = seasonReport(bundle && bundle.trades, {
      teams: bundle && bundle.teams,
      rosters: bundle && bundle.rosters,
      values: bundle && bundle.values,
      freeAgents: bundle && bundle.freeAgents
    });
    rootEl.innerHTML = render(report);
    return report;
  }

  return {
    SOURCE_FILE: SOURCE_FILE,
    VALUES_FILE: VALUES_FILE,
    FEATURED: FEATURED,
    SCORE_SCALE: SCORE_SCALE,
    normPlayer: normPlayer,
    teamKey: teamKey,
    displayName: displayName,
    parseAsset: parseAsset,
    scoreFromNet: scoreFromNet,
    letterGrade: letterGrade,
    formatSourceStamp: formatSourceStamp,
    sourceStamp: sourceStamp,
    isCompleted: isCompleted,
    valueBook: valueBook,
    findPlayer: findPlayer,
    buildPlan: buildPlan,
    priceList: priceList,
    gradeTrade: gradeTrade,
    leaderboard: leaderboard,
    lopsided: lopsided,
    seasonReport: seasonReport,
    render: render,
    mount: mount
  };
});
