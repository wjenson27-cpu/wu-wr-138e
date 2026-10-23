/* Track Record panel: how Eddie's past calls scored. Reads data/recs-summary.json (built by scripts/score_recs.py). */
(function () {
  var TYPES = { waiver_add: "Waiver adds", start_sit: "Start/sit", trade: "Trades", faab: "FAAB", green_dot: "Green dots" };
  function esc(v) {
    return String(v == null ? "" : v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function pct(r) { return r && r.hitRate != null ? Math.round(r.hitRate * 100) + "%" : "—"; }
  function pts(v) { return v == null ? "—" : (Math.round(v * 10) / 10).toString(); }
  function callRow(r) {
    var tag = r.result === "hit" ? "HIT" : r.result === "miss" ? "MISS" : r.result === "push" ? "PUSH" : "OPEN";
    var cls = r.result === "hit" ? "START" : r.result === "miss" ? "SIT" : "LIKE";
    return '<div class="row rt-row ' + (r.result === "hit" ? "t1" : r.result === "miss" ? "fade" : "") + '">' +
      '<div class="info"><div class="name">' + esc(r.player) + (r.alternative ? ' <span class="rt-vs">over ' + esc(r.alternative) + "</span>" : "") + "</div>" +
      '<div class="meta">W' + esc(r.week) + " · " + esc(TYPES[r.type] || r.type) + " · " + esc(r.call) + "</div>" +
      (r.status === "scored" ? '<div class="note">' + pts(r.pts_player) + " vs " + pts(r.pts_alt) + " pts" +
        (r.verified === "VERIFIED" ? "" : " · unverified") + "</div>" : '<div class="note">Not scored yet</div>') +
      '</div><span class="verdict ' + cls + '">' + tag + "</span></div>";
  }
  function render(el, s) {
    if (!s) { el.innerHTML = '<div class="card"><p>No track record yet.</p></div>'; return; }
    var o = s.overall || {};
    var html = '<div class="card rt-hero"><h2>Eddie\'s track record</h2>' +
      '<div class="rt-big"><b>' + pct(o) + '</b><span>hit rate · ' + (o.hits || 0) + "–" + (o.misses || 0) +
      (o.pushes ? "–" + o.pushes : "") + " on " + (o.scored || 0) + " scored calls</span></div>" +
      '<p class="rt-sub">' + s.total + " calls logged · " + s.verified + " verified from Fantrax · " + s.unverified + " still open or unverified. Only past or completed decisions.</p></div>";
    html += '<div class="card"><h3>By type</h3><div class="rt-types">';
    Object.keys(TYPES).forEach(function (t) {
      var r = (s.byType || {})[t] || {};
      var w = r.hitRate != null ? Math.round(r.hitRate * 100) : 0;
      html += '<div class="rt-type"><div class="rt-tl"><span>' + TYPES[t] + "</span><b>" + pct(r) + '</b></div>' +
        '<div class="rt-bar"><i style="width:' + w + '%"></i></div><div class="rt-tn">' +
        (r.scored ? (r.hits + "–" + r.misses + (r.pushes ? "–" + r.pushes : "")) : "none scored") + " · " + (r.total || 0) + " logged</div></div>";
    });
    html += "</div></div>";
    if (s.latestLearning) {
      html += '<div class="card rt-learn"><h3>What I\'m learning · Week ' + esc(s.latestLearning.week) + "</h3><p>" + esc(s.latestLearning.note) +
        '</p><p class="rt-adj"><b>Change:</b> ' + esc(s.latestLearning.adjustment) + "</p></div>";
    }
    html += '<div class="card"><h3>Best calls</h3>' + ((s.best || []).length ? s.best.map(callRow).join("") : "<p>None scored yet.</p>") + "</div>";
    html += '<div class="card"><h3>Worst calls</h3>' + ((s.worst || []).length ? s.worst.map(callRow).join("") : "<p>None scored yet.</p>") + "</div>";
    html += '<div class="card"><h3>Every call</h3>' + (s.recs || []).slice().reverse().map(callRow).join("") + "</div>";
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
