/* In-season War Room. Live league files, plus Eddie's plan in data/warroom.json. */
(function () {
  var POS = ["QB", "RB", "WR", "TE", "DL", "LB", "DB"];
  var state = {
    week: 1,
    teamsDoc: null,
    eddies: null,
    schedule: null,
    scores: null,
    weekScores: null,
    faab: null,
    trades: null,
    tx: null,
    rankings: null,
    plan: null,
    rosters: {},
    values: null,
    freeAgents: null,
    sources: {}
  };

  function $(id) { return document.getElementById(id); }
  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function parseTime(value) {
    if (!value) return null;
    var direct = Date.parse(value);
    if (Number.isFinite(direct)) return direct;
    var m = String(value).match(/(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2})\s*(AM|PM)?)?/i);
    if (!m) return null;
    var h = m[4] ? +m[4] : 12;
    var min = m[5] ? +m[5] : 0;
    var ap = (m[6] || "").toUpperCase();
    if (ap === "PM" && h < 12) h += 12;
    if (ap === "AM" && h === 12) h = 0;
    if (!m[4]) h = 12;
    return WUWeek.utcFromPt(+m[1], +m[2], +m[3], h, min).getTime();
  }

  function fmtPt(ms) {
    if (!ms) return "";
    return new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Los_Angeles",
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit"
    }).format(new Date(ms)) + " PT";
  }

  function ageHours(ms) {
    if (!ms) return Infinity;
    return (Date.now() - ms) / 36e5;
  }

  function teamById(id) {
    var teams = (state.teamsDoc && state.teamsDoc.teams) || [];
    for (var i = 0; i < teams.length; i++) if (teams[i].id === id) return teams[i];
    return null;
  }

  function norm(s) {
    return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  }

  function sameTeam(label, team) {
    if (!team || !label) return false;
    var n = norm(label);
    return [team.id, team.name, team.abbrev, team.owner].some(function (part) { return norm(part) === n; })
      || n.indexOf(norm(team.name)) !== -1
      || norm(team.name).indexOf(n) !== -1;
  }

  function eddiesTeam() {
    return teamById("eddies") || { id: "eddies", name: "Eagle Ridge Eddies", record: "", faab: null };
  }

  function opponent() {
    var fromPlan = state.plan && state.plan.opponent;
    var week = state.week;
    var games = state.schedule && state.schedule.perTeam && state.schedule.perTeam.eddies;
    var found = (games || []).filter(function (g) { return g.week === week; })[0];
    var id = (found && found.opponentId) || (fromPlan && fromPlan.teamId) || "";
    var team = teamById(id);
    return {
      id: id,
      name: (team && team.name) || (found && found.opponent) || (fromPlan && fromPlan.name) || "Opponent",
      record: (team && team.record) || (fromPlan && fromPlan.record) || ""
    };
  }

  function liveScore() {
    var pack = null;
    if (state.weekScores && state.weekScores.week === state.week) pack = state.weekScores;
    else if (state.scores && state.scores.week === state.week) pack = state.scores;
    if (!pack) return null;
    var me = eddiesTeam();
    var opp = opponent();
    var match = (pack.matchups || []).filter(function (m) {
      return sameTeam(m.home, me) || sameTeam(m.away, me);
    })[0];
    if (!match) return null;
    var homeMe = sameTeam(match.home, me);
    return {
      mine: homeMe ? match.homeScore : match.awayScore,
      theirs: homeMe ? match.awayScore : match.homeScore,
      status: match.status || pack.weekStatus || "",
      oppName: opp.name
    };
  }

  function faabLeft() {
    if (state.eddies && state.eddies.faabLeft != null) return state.eddies.faabLeft;
    var me = eddiesTeam();
    if (me.faab != null) return me.faab;
    var row = ((state.faab && state.faab.teamBalances) || []).filter(function (t) { return t.id === "eddies"; })[0];
    return row ? row.remaining : null;
  }

  function planStamp() {
    var plan = state.plan || {};
    return parseTime(plan.asOf) || parseTime(plan.freshness && plan.freshness.plan);
  }

  function rosterStamp() {
    return parseTime(state.eddies && (state.eddies.asOf || state.eddies.updated));
  }

  function stale() {
    return ageHours(planStamp()) > 24 || ageHours(rosterStamp()) > 24;
  }

  function tick() {
    var when = WUWeek.nextWaiver(new Date());
    var el = $("claims");
    if (el) el.textContent = "Claims " + WUWeek.countdown(when, new Date());
    var el2 = $("claimsBig");
    if (el2) el2.textContent = WUWeek.countdown(when, new Date());
  }

  function flags() {
    var doc = state.eddies || {};
    return doc.injuryFlags || doc.flags || [];
  }

  function flagFor(name) {
    var list = flags();
    var n = name.toLowerCase();
    for (var i = 0; i < list.length; i++) {
      if (String(list[i]).toLowerCase().indexOf(n) === 0 || String(list[i]).toLowerCase().indexOf(n) !== -1) {
        if (String(list[i]).toLowerCase().indexOf(n) !== -1) return list[i];
      }
    }
    return "";
  }

  function bucketOf(name) {
    var ir = ((state.eddies && state.eddies.roster && state.eddies.roster.IR) || []);
    if (ir.indexOf(name) !== -1) return "IR";
    var flag = flagFor(name);
    if (/\(reserve/i.test(flag)) return "RESERVE";
    if (/\(IR/i.test(flag) || /IR slot/i.test(flag)) return "IR";
    var notes = (state.eddies && state.eddies.notes) || "";
    var at = notes.toLowerCase().indexOf(name.toLowerCase());
    if (at !== -1 && /reserve/i.test(notes.slice(at, at + 48))) return "RESERVE";
    return "ACTIVE";
  }

  function rosterRows() {
    var roster = (state.eddies && state.eddies.roster) || {};
    var rows = [];
    var seen = {};
    POS.forEach(function (pos) {
      (roster[pos] || []).forEach(function (name) {
        rows.push({ name: name, pos: pos, bucket: bucketOf(name), flag: flagFor(name) });
        seen[name] = true;
      });
    });
    (roster.IR || []).forEach(function (name) {
      if (seen[name]) return;
      rows.push({ name: name, pos: "IR", bucket: "IR", flag: flagFor(name) });
    });
    return rows;
  }

  function verdictClass(v) {
    var map = { START: "START", SIT: "SIT", SWAP: "SWAP", WATCH: "WATCH" };
    return map[v] || "WATCH";
  }

  function renderWeek() {
    var me = eddiesTeam();
    var opp = opponent();
    var score = liveScore();
    var plan = state.plan || {};
    var sample = !!plan.sample;
    var bad = stale();
    var stamp = planStamp();
    var html = "";
    if (sample) html += '<div class="banner">Sample plan. Eddie has not filled this week yet.</div>';
    html += '<div class="card"><div class="statgrid">';
    html += '<div class="stat"><span>Week</span><b>' + esc(state.week) + "</b></div>";
    html += '<div class="stat"><span>Eddies</span><b>' + esc(me.record || "—") + "</b></div>";
    html += '<div class="stat"><span>Opponent</span><b>' + esc(opp.name) + "</b><span>" + esc(opp.record || "") + "</span></div>";
    html += '<div class="stat"><span>FAAB</span><b>' + (faabLeft() == null ? "—" : "$" + esc(faabLeft())) + "</b></div>";
    html += "</div>";
    if (score) {
      html += '<p class="scoreline" style="margin-top:10px">' + esc(score.mine) + ' <em>vs</em> ' + esc(score.theirs) +
        ' <em>' + esc(score.status || "") + "</em></p>";
    } else {
      html += '<p class="tiny" style="margin-top:8px">No score posted for this week yet.</p>';
    }
    html += '<p style="margin-top:8px">Claims <b id="claimsBig">' + esc(WUWeek.countdown(WUWeek.nextWaiver(new Date()), new Date())) +
      '</b> <span class="tiny">until Wed 9:00 AM PT</span></p>';
    html += '<p class="tiny">Updated ' + esc(fmtPt(stamp) || "—") +
      (bad ? ' <span class="badge stale">STALE</span>' : ' <span class="badge ok">FRESH</span>') +
      (sample ? ' <span class="badge sample">SAMPLE</span>' : "") + "</p>";
    var locks = plan.lockTimes || [];
    if (locks.length) {
      html += '<p class="tiny">' + locks.map(function (l) {
        return esc(l.label) + " " + esc(fmtPt(parseTime(l.at)) || l.at || "");
      }).join(" · ") + "</p>";
    }
    html += "</div>";

    var lineup = plan.lineup || [];
    ["START", "SWAP", "WATCH", "SIT"].forEach(function (group) {
      var rows = lineup.filter(function (r) { return r.verdict === group; });
      if (!rows.length) return;
      html += '<div class="sec">' + group + "</div>";
      rows.forEach(function (r) {
        var injury = r.injury ? " · " + r.injury : "";
        var practice = r.practice ? " · " + r.practice : "";
        html += '<div class="row t1"><div class="rank t1">' + esc(r.slot) + '</div><div class="info"><div class="name">' +
          esc(r.player) + '</div><div class="meta">' + esc(r.nflTeam || "") + " " + esc(r.pos || "") + esc(injury) + esc(practice) +
          '</div><div class="note">' + esc(r.reason || "") + '</div></div><div class="verdict ' + verdictClass(r.verdict) + '">' +
          esc(r.verdict) + "</div></div>";
      });
    });

    var watch = plan.injuryWatch || [];
    if (watch.length) {
      html += '<div class="sec">Injury watch</div>';
      watch.forEach(function (w) {
        html += '<div class="row"><div class="info"><div class="name">' + esc(w.player) + '</div><div class="meta">' +
          esc(w.tag || "") + (w.practice ? " · " + esc(w.practice) : "") + '</div><div class="note">' + esc(w.note || "") +
          "</div></div></div>";
      });
    }
    var byes = plan.byes || [];
    if (byes.length) {
      html += '<div class="sec">Byes</div><div class="card">';
      byes.forEach(function (b) {
        var names = (b.players || []).map(function (p) {
          return esc(p.player) + " " + esc(p.pos || "") + " " + esc(p.nflTeam || "");
        }).join(", ");
        html += "<p><b>Week " + esc(b.week) + ".</b> " + (names || "None listed.") + "</p>";
      });
      html += "</div>";
    }
    $("pweek").innerHTML = html;
  }

  function renderRoster() {
    var rows = rosterRows();
    var html = "";
    if (!rows.length) {
      $("proster").innerHTML = '<div class="card"><p>Roster did not load.</p></div>';
      return;
    }
    html += '<p class="tiny">' + esc((state.eddies && state.eddies.notes) || "") + "</p>";
    ["ACTIVE", "RESERVE", "IR"].forEach(function (bucket) {
      var list = rows.filter(function (r) { return r.bucket === bucket; });
      html += '<div class="sec">' + bucket + " · " + list.length + "</div>";
      if (!list.length) html += '<p class="tiny">None.</p>';
      list.forEach(function (r) {
        var detail = r.flag ? r.flag.replace(r.name, "").replace(/^[\s—–-]+/, "") : "";
        html += '<div class="row"><div class="pos ' + esc(r.pos) + '">' + esc(r.pos) + '</div><div class="info"><div class="name">' +
          esc(r.name) + '</div>' + (detail ? '<div class="note">' + esc(detail) + "</div>" : "") +
          '</div><div class="verdict ' + (bucket === "IR" ? "SIT" : bucket === "RESERVE" ? "WATCH" : "START") + '">' + bucket + "</div></div>";
      });
    });
    $("proster").innerHTML = html;
  }

  function renderWaivers() {
    var rows = (state.plan && state.plan.waivers) || [];
    var drops = (state.plan && state.plan.drops) || [];
    var ideas = (state.plan && state.plan.trades) || [];
    var html = "";
    if (state.plan && state.plan.sample) html += '<div class="banner">Sample bid sheet. Eddie has not filled this week yet.</div>';
    html += '<div class="scroll"><table class="sheet"><thead><tr><th>#</th><th>Player</th><th>Why</th><th>Recent</th><th>FAAB</th><th>Bid</th><th>Drop</th><th></th></tr></thead><tbody>';
    if (!rows.length) html += '<tr><td colspan="8">No targets yet.</td></tr>';
    rows.forEach(function (r) {
      html += "<tr><td>" + esc(r.rank) + "</td><td><b>" + esc(r.player) + "</b><div class=\"tiny\">" + esc(r.pos) + " " + esc(r.nflTeam) +
        "</div></td><td>" + esc(r.why) + "</td><td>" + esc(r.stats) + "</td><td>$" + esc(r.faabMin) + "–" + esc(r.faabMax) +
        "</td><td>$" + esc(r.bid) + "</td><td>" + esc(r.drop) + '</td><td><span class="verdict ' + esc(r.tag) + '">' + esc(r.tag) + "</span></td></tr>";
    });
    html += "</tbody></table></div>";
    html += '<div class="sec">Drop candidates</div>';
    drops.forEach(function (d) {
      html += '<div class="row"><div class="rank">' + esc(d.rank) + '</div><div class="info"><div class="name">' + esc(d.player) +
        '</div><div class="note">' + esc(d.reason) + "</div></div><div class=\"pos " + esc(d.pos) + "\">" + esc(d.pos) + "</div></div>";
    });
    if (ideas.length) {
      html += '<div class="sec">Trade ideas</div>';
      ideas.forEach(function (t) {
        html += '<div class="card"><h3>' + esc(t.with) + "</h3><p>Give " + esc((t.give || []).join(", ")) + ". Get " +
          esc((t.get || []).join(", ")) + ".</p><p>" + esc(t.why) + "</p></div>";
      });
    }
    $("pwaivers").innerHTML = html;
  }

  function renderIdp() {
    var plan = state.plan || {};
    var html = "";
    if (plan.sample) html += '<div class="banner">Sample green-dot list. Eddie has not filled this week yet.</div>';
    html += '<div class="card"><h3>Green-dot tracker</h3><div class="scroll"><table class="idp-table"><thead><tr><th>Team</th><th>Green dot</th><th>Notes</th></tr></thead><tbody>';
    (plan.idp || []).forEach(function (r) {
      html += '<tr><td class="team">' + esc(r.nflTeam) + '</td><td class="dot">' + esc(r.greenDot) + '</td><td class="note">' + esc(r.notes) + "</td></tr>";
    });
    html += "</tbody></table></div></div>";
    html += '<div class="sec">Box safeties</div>';
    (plan.boxSafety || []).forEach(function (r) {
      html += '<div class="row"><div class="info"><div class="name">' + esc(r.player) + '</div><div class="meta">' + esc(r.nflTeam) +
        '</div><div class="note">' + esc(r.note) + "</div></div></div>";
    });
    $("pidp").innerHTML = html;
  }

  function renderNews() {
    var items = (state.plan && state.plan.news) || [];
    var html = "";
    if (state.plan && state.plan.sample) html += '<div class="banner">Sample wire. Eddie has not filled this week yet.</div>';
    if (!items.length) html += '<div class="card"><p>No news yet.</p></div>';
    items.forEach(function (n) {
      html += '<div class="card"><p class="tiny">' + esc(n.source || "") + " · " + esc(fmtPt(parseTime(n.time)) || n.time || "") +
        "</p><p>" + esc(n.text) + "</p></div>";
    });
    $("pnews").innerHTML = html;
  }

  function renderLeague() {
    var teams = ((state.teamsDoc && state.teamsDoc.teams) || []).slice().sort(function (a, b) {
      return (a.standingsRank || 99) - (b.standingsRank || 99);
    });
    var html = '<div class="scroll"><table class="sheet"><thead><tr><th>#</th><th>Team</th><th>W-L</th><th>PF</th><th>PA</th><th>FAAB</th></tr></thead><tbody>';
    teams.forEach(function (t) {
      var mine = t.id === "eddies" ? ' style="background:#0c2416"' : "";
      html += "<tr" + mine + "><td>" + esc(t.standingsRank) + "</td><td><b>" + esc(t.name) + "</b><div class=\"tiny\">" + esc(t.owner) +
        "</div></td><td>" + esc(t.record) + "</td><td>" + esc(t.pointsFor) + "</td><td>" + esc(t.pointsAgainst) + "</td><td>$" + esc(t.faab) + "</td></tr>";
    });
    html += "</tbody></table></div>";
    var moves = ((state.tx && state.tx.items) || []).slice().sort(function (a, b) {
      return String(b.date).localeCompare(String(a.date));
    }).slice(0, 12);
    html += '<div class="sec">Recent moves</div>';
    moves.forEach(function (m) {
      html += '<div class="row"><div class="info"><div class="name">' + esc(m.team) + " · " + esc(m.type) +
        '</div><div class="meta">' + esc(m.date) + (m.time ? " " + esc(m.time) : "") + '</div><div class="note">' + esc(m.summary) +
        "</div></div></div>";
    });
    var trades = ((state.trades && state.trades.trades) || []).slice(0, 5);
    if (trades.length) {
      html += '<div class="sec">Recent trades</div>';
      trades.forEach(function (t) {
        html += '<div class="card"><h3>' + esc(t.teamA) + " and " + esc(t.teamB) + "</h3><p>" + esc(t.summary) + "</p></div>";
      });
    }
    $("pleague").innerHTML = html;
  }

  function renderChrome() {
    var me = eddiesTeam();
    var opp = opponent();
    var bad = stale();
    var sample = state.plan && state.plan.sample;
    $("weekBadge").textContent = "WEEK " + state.week;
    var badges = $("headBadges");
    badges.innerHTML = (sample ? '<span class="badge sample">SAMPLE</span>' : "") + (bad ? '<span class="badge stale">STALE</span>' : "");
    var score = liveScore();
    var scoreBit = score ? " · " + score.mine + "–" + score.theirs : "";
    $("strip").innerHTML = "Week " + esc(state.week) + " · " + esc(me.record || "—") + " vs " + esc(opp.name) + " " + esc(opp.record || "") +
      esc(scoreBit) + " · FAAB " + (faabLeft() == null ? "—" : "$" + esc(faabLeft())) + ' · <span id="claims"></span>';
    tick();
  }

  function renderAll() {
    renderChrome();
    renderWeek();
    renderRoster();
    renderWaivers();
    renderIdp();
    renderNews();
    renderLeague();
  }

  function show(id) {
    document.querySelectorAll("nav button").forEach(function (b) { b.classList.toggle("active", b.getAttribute("data-p") === id); });
    document.querySelectorAll(".panel").forEach(function (p) { p.classList.toggle("active", p.id === id); });
  }

  async function boot() {
    state.week = WUWeek.fantraxWeek(new Date());
    var jobs = await Promise.all([
      WUData.hq("teams.json"),
      WUData.hq("roster-eddies.json"),
      WUData.hq("rosters/eddies.json"),
      WUData.hq("schedule.json"),
      WUData.hq("scores.json"),
      WUData.hq("faab.json"),
      WUData.hq("trades.json"),
      WUData.hq("transactions.json"),
      WUData.hq("rankings.json"),
      WUData.load("data/warroom.json"),
      WUData.load("data/player-values.json"),
      WUData.load("data/free-agents.json"),
      WUData.hq("rosters/index.json")
    ]);
    state.teamsDoc = jobs[0].data;
    state.eddies = jobs[2].data || jobs[1].data;
    state.schedule = jobs[3].data;
    state.scores = jobs[4].data;
    state.weekScores = null;
    state.faab = jobs[5].data;
    state.trades = jobs[6].data;
    state.tx = jobs[7].data;
    state.rankings = jobs[8].data;
    state.plan = jobs[9].data;
    state.values = jobs[10].data;
    state.freeAgents = jobs[11].data;
    if (state.plan && state.plan.week) state.week = state.plan.week;
    else if (!(state.week > 0)) state.week = WUWeek.fantraxWeek(new Date());
    var ids = (jobs[12].data && jobs[12].data.teams) || ((state.teamsDoc && state.teamsDoc.teams) || []).map(function (t) { return t.id; });
    var rosterLoads = await Promise.all(ids.map(function (id) { return WUData.hq("rosters/" + id + ".json"); }));
    ids.forEach(function (id, i) { if (rosterLoads[i].data) state.rosters[id] = rosterLoads[i].data; });
    if (!state.rosters.eddies && state.eddies) state.rosters.eddies = state.eddies;
    renderAll();
    setInterval(tick, 30000);
    if (window.WUTrade) {
      WUTrade.mount({
        teams: (state.teamsDoc && state.teamsDoc.teams) || [],
        rosters: state.rosters,
        values: state.values,
        freeAgents: state.freeAgents
      });
    }
    document.querySelectorAll("nav button").forEach(function (b) {
      b.addEventListener("click", function () { show(b.getAttribute("data-p")); });
    });
  }

  boot().catch(function (err) {
    var el = $("pweek");
    if (el) el.innerHTML = '<div class="card"><p>The War Room could not load. If you have opened it before, the last copy should still be on this phone.</p></div>';
    console.error(err);
  });
})();
