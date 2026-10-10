/* Mike Woellert's green-dot and full-time linebackers.
   Name matching uses the same normalization as the rankings board. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (typeof document !== "undefined") {
    document.addEventListener("click", function (ev) {
      var dot = ev.target.closest && ev.target.closest(".gdot");
      if (!dot) {
        document.querySelectorAll(".gdot.open").forEach(function (el) { el.classList.remove("open"); });
        return;
      }
      ev.preventDefault();
      ev.stopPropagation();
      var was = dot.classList.contains("open");
      document.querySelectorAll(".gdot.open").forEach(function (el) { el.classList.remove("open"); });
      if (!was) dot.classList.add("open");
    }, true);
  }
  root.WUGreen = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var MAX_AGE = 10 * 86400000;

  function normName(name) {
    if (typeof WURankMath !== "undefined" && WURankMath.normName) return WURankMath.normName(name);
    try {
      var math = require("./rankings-math.js");
      return math.normName(name);
    } catch (e) {
      return String(name || "").toLowerCase();
    }
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c];
    });
  }

  function asOfLabel(iso) {
    var t = Date.parse(iso);
    if (!Number.isFinite(t)) return "";
    try {
      return new Date(t).toLocaleString("en-US", {
        timeZone: "America/Los_Angeles",
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZoneName: "short"
      });
    } catch (e2) {
      return String(iso || "");
    }
  }

  function fresh(doc, now) {
    if (!doc || !Array.isArray(doc.teams) || !doc.asOf) return false;
    var t = Date.parse(doc.asOf);
    if (!Number.isFinite(t)) return false;
    var clock = now == null ? Date.now() : (now instanceof Date ? now.getTime() : Number(now));
    return clock - t <= MAX_AGE && clock >= t - 86400000;
  }

  /* fresh: false hides every badge. Roles are keyed by the rankings name key. */
  function prepare(doc, now) {
    var ok = fresh(doc, now);
    var byNorm = {};
    if (ok) {
      (doc.teams || []).forEach(function (team) {
        function add(name, kind) {
          var key = normName(name);
          if (!key) return;
          if (!byNorm[key]) byNorm[key] = { name: name, team: team.team || "", green: false, full: false };
          byNorm[key][kind] = true;
          if (team.team) byNorm[key].team = team.team;
        }
        if (team.greenDot) add(team.greenDot, "green");
        (team.fullTime || []).forEach(function (name) { add(name, "full"); });
      });
    }
    return {
      fresh: ok,
      sample: !!(doc && doc.sample),
      source: (doc && doc.source) || "Mike Woellert",
      sourceUrl: (doc && doc.sourceUrl) || "",
      asOf: (doc && doc.asOf) || "",
      asOfLabel: asOfLabel(doc && doc.asOf),
      week: doc && doc.week,
      teams: ok && doc ? doc.teams : [],
      byNorm: byNorm
    };
  }

  function role(prepared, name) {
    if (!prepared || !prepared.fresh) return null;
    return prepared.byNorm[normName(name)] || null;
  }

  function tip(prepared) {
    return (prepared.source || "Mike Woellert") + (prepared.asOfLabel ? " · " + prepared.asOfLabel : "");
  }

  function mark(prepared, name, only) {
    var hit = role(prepared, name);
    if (!hit) return "";
    var label = tip(prepared);
    var html = "";
    if (hit.green && only !== "full") {
      html += '<span class="gdot" role="img" tabindex="0" title="' + esc(label) + '" data-tip="' + esc(label) + '" aria-label="Green dot, ' + esc(label) + '"></span>';
    }
    if (hit.full && only !== "green") {
      html += '<span class="gdot ft" role="img" tabindex="0" title="' + esc(label) + '" data-tip="' + esc(label) + '" aria-label="Full time, ' + esc(label) + '">FT</span>';
    }
    return html;
  }

  function note(prepared) {
    if (!prepared) return '<p class="tiny gdot-note">No green-dot list yet.</p>';
    if (prepared.fresh) return "";
    if (prepared.asOf) return '<p class="tiny gdot-note">Green-dot list is more than 10 days old.</p>';
    return '<p class="tiny gdot-note">No green-dot list yet.</p>';
  }

  return {
    MAX_AGE: MAX_AGE,
    normName: normName,
    fresh: fresh,
    prepare: prepare,
    role: role,
    mark: mark,
    note: note,
    asOfLabel: asOfLabel
  };
});
