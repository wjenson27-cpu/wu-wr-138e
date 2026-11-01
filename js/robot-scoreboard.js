/* Robot vs. The Eddies scoreboard view. No network. No personal names. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.WURobot = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "FLEX", "FLEX", "DL", "LB", "DB", "DB", "IDP", "IDP", "IDP"];
  var FIRST_WEEK = 9;
  var CLUB = "Eagleridge Eddie's";

  function num(value) {
    var n = typeof value === "number" ? value : parseFloat(value);
    return isFinite(n) ? n : null;
  }

  function pointsLabel(value) {
    var n = num(value);
    if (n == null) return "\u2014";
    return (Math.round(n * 10) / 10).toFixed(1);
  }

  function marginLabel(value) {
    var n = num(value);
    if (n == null) return "\u2014";
    var body = (Math.round(Math.abs(n) * 10) / 10).toFixed(1);
    if (n > 0) return "+" + body;
    if (n < 0) return "\u2212" + body;
    return "0.0";
  }

  function norm(name) {
    return String(name || "").toLowerCase().replace(/\s+/g, " ").trim();
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

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function resultWords(doc, locked) {
    if (!doc || !doc.result) return locked ? "Pending" : "Not yet locked";
    if (doc.result === "W") return "Robot win";
    if (doc.result === "L") return "Eddies win";
    if (doc.result === "T") return "Tie";
    return "Pending";
  }

  function tone(result) {
    if (result === "W") return "win";
    if (result === "L") return "loss";
    if (result === "T") return "tie";
    return "pending";
  }

  function summaryToDoc(summary) {
    summary = summary || {};
    return {
      week: summary.week,
      window: summary.window || null,
      status: summary.status || "pending",
      robotLockedAt: summary.robotLockedAt || null,
      locked: !!summary.locked,
      robot: [],
      actual: [],
      totals: { robot: summary.robotPoints, eddies: summary.eddiesPoints },
      margin: summary.margin,
      result: summary.result || null,
      winner: summary.winner || null,
      decisions: summary.decisions || []
    };
  }

  function sideBits(row) {
    if (!row) return null;
    return {
      player: row.player,
      pos: row.pos,
      team: row.team,
      pointsLabel: pointsLabel(row.points)
    };
  }

  function decisionView(row) {
    var swing = num(row.swing);
    return {
      slot: row.slot,
      index: row.index,
      robotPlayer: row.robotPlayer,
      robotPos: row.robotPos,
      robotTeam: row.robotTeam,
      robotPoints: pointsLabel(row.robotPoints),
      eddiesPlayer: row.eddiesPlayer,
      eddiesPos: row.eddiesPos,
      eddiesTeam: row.eddiesTeam,
      eddiesPoints: pointsLabel(row.eddiesPoints),
      swingLabel: marginLabel(row.swing),
      swingTone: swing == null ? "flat" : swing > 0 ? "up" : swing < 0 ? "down" : "flat"
    };
  }

  function weekView(doc) {
    doc = doc || {};
    var robot = doc.robot || [];
    var actual = doc.actual || [];
    var locked = !!(doc.robotLockedAt || robot.length || doc.locked);
    var status = doc.status === "final" ? "final" : "pending";
    var swingByIndex = {};
    (doc.decisions || []).forEach(function (d) {
      if (d && d.index != null) swingByIndex[d.index] = d.swing;
    });
    var rows = [];
    if (locked && robot.length) {
      var n = Math.max(robot.length, actual.length);
      for (var i = 0; i < n; i++) {
        var r = robot[i] || null;
        var a = actual[i] || null;
        var differ = !!(r && a && norm(r.player) !== norm(a.player));
        var swing = differ ? swingByIndex[i] : null;
        rows.push({
          slot: (r || a).slot,
          index: i,
          differ: differ,
          swingLabel: differ ? marginLabel(swing) : "",
          swingTone: num(swing) == null ? "flat" : num(swing) > 0 ? "up" : num(swing) < 0 ? "down" : "flat",
          robot: sideBits(r),
          eddies: sideBits(a)
        });
      }
    }
    var totals = doc.totals || {};
    return {
      week: doc.week,
      windowLabel: doc.window && doc.window.label ? doc.window.label : "",
      locked: locked,
      lockLabel: doc.robotLockedAt ? formatPt(doc.robotLockedAt) : "Not yet locked",
      status: status,
      statusLabel: resultWords(doc, locked),
      tone: tone(doc.result),
      pointsCaption: !locked ? "" : status === "final" ? "Final" : "Live",
      robotTotal: pointsLabel(totals.robot != null ? totals.robot : doc.robotPoints),
      eddiesTotal: pointsLabel(totals.eddies != null ? totals.eddies : doc.eddiesPoints),
      marginLabel: marginLabel(doc.margin),
      result: doc.result || null,
      rows: rows,
      decisions: (doc.decisions || []).map(decisionView),
      awaitingEddies: !!(locked && robot.length && !actual.length)
    };
  }

  function buildModel(season, weeks) {
    season = season || {};
    var byWeek = {};
    (weeks || []).forEach(function (doc) {
      if (doc && doc.week != null) byWeek[doc.week] = doc;
    });
    var numbers = [];
    (season.weeks || []).forEach(function (summary) {
      numbers.push(summary.week);
      if (!byWeek[summary.week]) byWeek[summary.week] = summaryToDoc(summary);
    });
    Object.keys(byWeek).forEach(function (key) {
      var n = Number(key);
      if (numbers.indexOf(n) < 0) numbers.push(n);
    });
    var docs = numbers.map(function (n) { return byWeek[n]; });
    docs = docs.filter(function (doc) { return doc && doc.week != null && doc.week >= FIRST_WEEK; });
    docs.sort(function (a, b) { return a.week - b.week; });
    var currentDoc = docs.length ? docs[docs.length - 1] : summaryToDoc({ week: season.firstWeek || FIRST_WEEK, status: "pending" });
    var history = docs.slice(0, -1).reverse().map(weekView);
    var current = weekView(currentDoc);
    var record = season.record || { wins: 0, losses: 0, ties: 0, label: "0-0-0" };
    var points = season.points || { robot: 0, eddies: 0, margin: 0 };
    var historyEmpty = history.length
      ? ""
      : current.status === "final"
        ? "Earlier weeks are not on this board. It starts with Week 9."
        : "No finished weeks yet. This board starts with Week 9.";
    return {
      ok: true,
      club: season.club || CLUB,
      recordLabel: record.label || (record.wins + "-" + record.losses + "-" + record.ties),
      wins: record.wins || 0,
      losses: record.losses || 0,
      ties: record.ties || 0,
      robotPoints: pointsLabel(points.robot),
      eddiesPoints: pointsLabel(points.eddies),
      marginLabel: marginLabel(points.margin == null ? 0 : points.margin),
      current: current,
      history: history,
      historyEmpty: historyEmpty
    };
  }

  function sideHtml(kind, side, missing) {
    var label = kind === "robot" ? "Robot" : "Eddies";
    if (!side) {
      return '<div class="rv-side ' + kind + '"><span class="rv-tag">' + label +
        '</span><div class="rv-who"><span class="rv-player muted">' + esc(missing) +
        '</span></div><b class="rv-pts">\u2014</b></div>';
    }
    var meta = [side.pos, side.team].filter(Boolean).join(" · ");
    var metaHtml = meta ? '<span class="rv-meta">' + esc(meta) + "</span>" : "";
    return '<div class="rv-side ' + kind + '"><span class="rv-tag">' + label +
      '</span><div class="rv-who"><span class="rv-player">' + esc(side.player) +
      "</span>" + metaHtml + '</div><b class="rv-pts">' +
      esc(side.pointsLabel) + "</b></div>";
  }

  function decisionHtml(d) {
    return '<div class="rv-dec"><div class="rv-slot-h"><span>' + esc(d.slot) +
      '</span><span class="rv-swing ' + esc(d.swingTone) + '">' + esc(d.swingLabel) +
      "</span></div>" +
      sideHtml("robot", {
        player: d.robotPlayer,
        pos: d.robotPos,
        team: d.robotTeam,
        pointsLabel: d.robotPoints
      }, "Not locked") +
      sideHtml("eddies", d.eddiesPlayer ? {
        player: d.eddiesPlayer,
        pos: d.eddiesPos,
        team: d.eddiesTeam,
        pointsLabel: d.eddiesPoints
      } : null, "No starter") +
      "</div>";
  }

  function rowHtml(row) {
    var swing = row.differ
      ? '<span class="rv-swing ' + esc(row.swingTone) + '">' + esc(row.swingLabel) + "</span>"
      : "";
    var flag = row.differ ? '<span class="rv-flag">Differ</span>' : "";
    return '<article class="rv-slot' + (row.differ ? " differ" : "") + '"><div class="rv-slot-h"><span>' +
      esc(row.slot) + " " + flag + '</span>' + swing + "</div>" +
      sideHtml("robot", row.robot, "Not locked") +
      sideHtml("eddies", row.eddies, "Not in yet") +
      "</article>";
  }

  function weekCard(week, heading, compact) {
    var when = week.locked
      ? "Locked " + week.lockLabel
      : "Not yet locked";
    var caption = week.pointsCaption
      ? '<span class="rv-pill ' + esc(week.tone) + '">' + esc(week.pointsCaption) + "</span>"
      : "";
    var score = week.locked
      ? '<div class="rv-score"><div><span>Robot</span><b>' + esc(week.robotTotal) +
        '</b></div><div class="rv-mid">' + esc(week.result || "·") +
        '</div><div class="rv-right"><span>Eddies</span><b>' + esc(week.eddiesTotal) +
        "</b></div></div>"
      : "";
    var subBits = [when];
    if (week.locked) subBits.push(week.statusLabel);
    if (week.marginLabel && week.marginLabel !== "\u2014") subBits.push("margin " + week.marginLabel);
    var sub = '<p class="rv-sub">' + esc(subBits.join(" · ")) + "</p>";
    var body = "";
    if (!week.locked) {
      body = '<p class="rv-empty">The Robot has not locked a lineup for this week.</p>' +
        '<div class="rv-chips">' + SLOTS.map(function (slot) {
          return "<span>" + esc(slot) + "</span>";
        }).join("") + "</div>";
    } else {
      if (week.status !== "final") {
        body += '<p class="tiny">Points stay blank until this week is final.</p>';
      }
      if (week.awaitingEddies) {
        body += '<p class="tiny">The Eddies lineup is not in yet.</p>';
      } else if (!week.decisions.length) {
        body += "<p class=\"tiny\">No differing decisions. Both sides started the same players.</p>";
      } else {
        body += '<h3>Decisions that differed</h3>' + week.decisions.map(decisionHtml).join("");
      }
      if (!compact && week.rows.length) {
        body += '<h3>Lineups <span class="rv-caption">' + esc(week.pointsCaption) + " points</span></h3>" +
          week.rows.map(rowHtml).join("");
      }
    }
    var windowBit = week.windowLabel ? " · " + esc(week.windowLabel) : "";
    return '<section class="card rv-card"><div class="rv-head"><h2>' + esc(heading) + " " +
      esc(week.week) + windowBit + "</h2>" + caption + "</div>" + score + sub + body + "</section>";
  }

  function render(model) {
    var tally = '<section class="card rv-tally"><h2>Season tally</h2>' +
      '<div class="statgrid"><div class="stat"><span>W-L-T</span><b>' + esc(model.recordLabel) +
      '</b></div><div class="stat"><span>Margin</span><b>' + esc(model.marginLabel) +
      '</b></div><div class="stat"><span>Robot pts</span><b>' + esc(model.robotPoints) +
      '</b></div><div class="stat"><span>Eddies pts</span><b>' + esc(model.eddiesPoints) +
      "</b></div></div>" +
      '<p class="tiny">W ' + esc(model.wins) + " · L " + esc(model.losses) + " · T " + esc(model.ties) +
      " · margin is Robot minus Eddies · from Week " + FIRST_WEEK + "</p></section>";
    var history = '<section class="rv-history"><h2 class="rv-hist-title">History</h2>';
    if (!model.history.length) {
      history += '<p class="tiny">' + esc(model.historyEmpty) + "</p>";
    } else {
      history += model.history.map(function (week) {
        return weekCard(week, "Week", true);
      }).join("");
    }
    history += "</section>";
    return tally + weekCard(model.current, "Week", false) + history;
  }

  return {
    SLOTS: SLOTS,
    FIRST_WEEK: FIRST_WEEK,
    CLUB: CLUB,
    formatPt: formatPt,
    pointsLabel: pointsLabel,
    marginLabel: marginLabel,
    buildModel: buildModel,
    render: render
  };
});
