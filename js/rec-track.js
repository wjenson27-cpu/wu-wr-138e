/* Track Record panel: how Eddie's past calls scored. Reads data/recs-summary.json (built by scripts/score_recs.py). */
(function () {
  var TYPES = { waiver_add: "Waiver adds", start_sit: "Start/sit", trade: "Trades", faab: "FAAB", green_dot: "Green dots" };
  function esc(v) {
    return String(v == null ? "" : v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function pct(r) { return r && r.hitRate != null ? Math.round(r.hitRate * 100) + "%" : "—"; }
  function tone(r) { return !r || r.hitRate == null ? "rt-none" : r.hitRate >= 0.5 ? "rt-good" : "rt-low"; }
  function rec(r) { return r ? r.hits + "–" + r.misses + (r.pushes ? "–" + r.pushes : "") : "0–0"; }
  function pts(v) { return v == null ? "—" : (Math.round(v * 10) / 10).toString(); }
  function badges(r) {
    var b = [];
    if (r.basis === "derived") b.push('<span class="rt-badge der">derived</span>');
    if (r.basis === "inferred" || r.basis_alt === "inferred") b.push('<span class="rt-badge inf">inferred alt</span>');
    if (r.basis_player === "fantrax_note" || r.basis_alt === "fantrax_note") b.push('<span class="rt-badge bench">bench, if started</span>');
    if (r.status === "scored" && r.verified !== "VERIFIED") b.push('<span class="rt-badge unv">unverified</span>');
    return b.join("");
  }
  function callRow(r) {
    var tag = r.result === "hit" ? "HIT" : r.result === "miss" ? "MISS" : r.result === "push" ? "PUSH" : "OPEN";
    var cls = r.result === "hit" ? "START" : r.result === "miss" ? "SIT" : "LIKE";
    var m = r.status === "scored" ? r.pts_player - r.pts_alt : null;
    var margin = m == null ? "" : '<span class="rt-margin ' + (m > 0 ? "up" : m < 0 ? "down" : "") + '">' + (m > 0 ? "+" : m < 0 ? "−" : "±") + pts(Math.abs(m)) + "</span>";
    var detail = r.status === "scored" ? pts(r.pts_player) + " vs " + pts(r.pts_alt) + " pts" :
      (r.type === "faab" ? "Not graded (FAAB)" : "Not graded yet");
    return '<div class="row rt-row ' + (r.result === "hit" ? "t1" : r.result === "miss" ? "fade" : "") + '">' +
      '<div class="info"><div class="name">' + esc(r.player) + (r.alternative ? ' <span class="rt-vs">over ' + esc(r.alternative) + "</span>" : "") + "</div>" +
      '<div class="rt-meta">W' + esc(r.week) + " · " + esc(TYPES[r.type] || r.type) + " · " + esc(r.call) + "</div>" +
      '<div class="rt-pts">' + detail + " " + badges(r) + "</div>" +
      '</div><div class="rt-right">' + margin + '<span class="verdict ' + cls + '">' + tag + "</span></div></div>";
  }
  function render(el, s) {
    if (!s) {
      el.innerHTML = '<div class="card"><h2>Eddie\'s track record</h2><p>Withheld for now. The privacy check couldn\'t confirm that nothing pending would show, so this page stays empty until it can.</p></div>';
      return;
    }
    var o = s.overall || {}, oa = s.overallAll || {};
    var html = '<div class="card rt-hero ' + tone(o) + '"><h2>Eddie\'s track record</h2>' +
      '<div class="rt-big"><b>' + pct(o) + '</b><span>' + rec(o) + " on " + (o.scored || 0) + " verified calls</span></div>" +
      '<p class="rt-sub">Verified means both sides come from a Fantrax box score or a Fantrax bench note. Counting derived and inferred calls too: <b>' +
      rec(oa) + " (" + pct(oa) + ")</b> on " + (oa.scored || 0) + " graded calls. " + s.total + " calls logged, past weeks only.</p></div>";
    var full = [], empty = [];
    Object.keys(TYPES).forEach(function (t) { var r = (s.byType || {})[t] || {}; ((r.all && r.all.scored) ? full : empty).push(t); });
    html += '<div class="card"><h3>By type</h3><div class="rt-types">';
    full.forEach(function (t) {
      var r = s.byType[t], w = r.hitRate != null ? Math.round(r.hitRate * 100) : 0;
      html += '<div class="rt-type ' + tone(r) + '"><div class="rt-tl"><span>' + TYPES[t] + "</span><b>" + pct(r) + '</b></div>' +
        '<div class="rt-bar"><i style="width:' + w + '%"></i></div><div class="rt-tn">Verified ' + rec(r) + " · all " + rec(r.all) + " · " + r.total + " logged</div></div>";
    });
    html += "</div>";
    if (empty.length) html += '<p class="rt-empty">Nothing graded yet: ' + empty.map(function (t) {
      var n = (s.byType[t] || {}).total || 0; return TYPES[t] + (n ? " (" + n + " logged)" : ""); }).join(", ") + ".</p>";
    html += '<p class="rt-empty">FAAB claims are graded only when we have the dropped player\'s points for that week. Usually we don\'t, so they stay open.</p></div>';
    if (s.latestLearning) {
      html += '<div class="card rt-learn"><h3>What I\'m learning · Week ' + esc(s.latestLearning.week) + "</h3><p>" + esc(s.latestLearning.note) +
        '</p><p class="rt-adj"><b>Change:</b> ' + esc(s.latestLearning.adjustment) + "</p></div>";
    }
    var shown = {};
    function list(rs) { rs.forEach(function (r) { shown[r.id] = 1; }); return rs.map(callRow).join(""); }
    html += '<div class="card"><h3>Best calls</h3>' + ((s.best || []).length ? list(s.best) : "<p>None graded yet.</p>") + "</div>";
    html += '<div class="card"><h3>Worst calls</h3>' + ((s.worst || []).length ? list(s.worst) : "<p>None graded yet.</p>") + "</div>";
    var rest = (s.recs || []).filter(function (r) { return !shown[r.id]; });
    var weeks = {};
    rest.forEach(function (r) { (weeks[r.week] = weeks[r.week] || []).push(r); });
    var ks = Object.keys(weeks).sort(function (a, b) { return b - a; });
    if (ks.length) {
      html += '<div class="card"><h3>Other calls</h3>' + ks.map(function (k, i) {
        return '<details class="rt-week"' + (i === 0 ? " open" : "") + '><summary>Week ' + esc(k) + " · " + weeks[k].length + " call" + (weeks[k].length > 1 ? "s" : "") + "</summary>" +
          weeks[k].map(callRow).join("") + "</details>";
      }).join("") + "</div>";
    }
    el.innerHTML = html;
  }
  async function boot() {
    var el = document.getElementById("precord");
    if (!el) return;
    var got = window.WUData ? await WUData.load("data/recs-summary.json") : { data: null };
    render(el, got.data);
  }
  if (typeof module === "object" && module.exports) module.exports = { render: render };
  else boot();
})();
