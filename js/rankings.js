/* Weekly rankings tab. Reads the file the build script writes. */
(function () {
  var POS_ORDER = { QB: 1, RB: 2, WR: 3, TE: 4, DL: 5, LB: 6, DB: 7 };
  var FLEX = { RB: 1, WR: 1, TE: 1 };
  var IDP = { DL: 1, LB: 1, DB: 1 };
  var GRADES = { A: 5, B: 4, C: 3, D: 2, F: 1 };
  var SOURCE_NAME = { sleeper: "Sleeper", espn: "ESPN", recent: "Last 3", fantasypros: "FantasyPros" };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c];
    });
  }

  function norm(name) {
    return window.WURankMath ? WURankMath.normName(name) : String(name || "").toLowerCase();
  }

  function hardOut(code) {
    return code === "O" || code === "IR" || code === "SUS" || code === "PUP";
  }

  function cannotStart(name, doc) {
    var flags = [].concat((doc && doc.injuryFlags) || [], (doc && doc.flags) || []);
    var n = String(name || "").toLowerCase();
    for (var i = 0; i < flags.length; i++) {
      var line = String(flags[i]).toLowerCase();
      if (line.indexOf(n) === -1) continue;
      if (/\(reserve/.test(line) || /\(ir/.test(line)) return true;
    }
    return false;
  }

  function rosterMap(rosters) {
    var entries = [];
    var loaded = false;
    Object.keys(rosters || {}).forEach(function (id) {
      var doc = rosters[id];
      if (!doc || !doc.roster) return;
      loaded = true;
      var ir = {};
      (doc.roster.IR || []).forEach(function (name) { ir[norm(name)] = true; });
      Object.keys(doc.roster).forEach(function (slot) {
        var pos = window.WURankMath ? WURankMath.groupPos(slot) : "";
        (doc.roster[slot] || []).forEach(function (name) {
          var key = norm(name);
          if (!key) return;
          entries.push({
            norm: key,
            pos: pos,
            avail: id === "eddies" ? "eddies" : "other",
            club: doc.teamName || id,
            ir: slot === "IR" || !!ir[key],
            blocked: cannotStart(name, doc)
          });
        });
      });
    });
    return { entries: entries, loaded: loaded };
  }

  function rosterHit(lookup, player) {
    var key = norm(player.name);
    var exact = lookup.entries.filter(function (e) { return e.norm === key && e.pos === player.pos; });
    if (exact.length) return exact[0];
    var named = lookup.entries.filter(function (e) { return e.norm === key; });
    if (named.length === 1 && !named[0].pos) return named[0];
    return null;
  }

  function decorate(player, lookup) {
    var hit = rosterHit(lookup, player);
    var avail = hit ? hit.avail : (lookup.loaded ? "fa" : (player.avail || "unknown"));
    var club = hit ? hit.club : (avail === "fa" ? "" : (player.club || ""));
    return {
      player: player,
      avail: avail,
      club: club,
      ir: !!(hit && hit.ir),
      blocked: !!(hit && hit.blocked)
    };
  }

  function asOfPt(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString("en-US", {
        timeZone: "America/Los_Angeles",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZoneName: "short"
      });
    } catch (e) {
      return iso;
    }
  }

  function side(player) {
    if (player.bye) return "BYE";
    if (!player.opp) return "";
    var where = player.home ? "vs " : "@ ";
    return where + player.opp + (player.site ? " · " + player.site : "");
  }

  function ptsText(n) {
    return n == null ? "—" : Number(n).toFixed(1);
  }

  function rangeText(player) {
    if (player.pts == null) return "No stat line";
    if (player.floor == null || player.floor === player.ceil) return ptsText(player.pts);
    return ptsText(player.floor) + "–" + ptsText(player.ceil);
  }

  function mount(opts) {
    var root = opts && opts.root;
    if (!root) return;
    var board = opts.board;
    if (!board || !board.players) {
      root.innerHTML = '<div class="card"><h2>Weekly rankings</h2><p>No board is saved for this week yet.</p></div>';
      return;
    }
    var lookup = rosterMap(opts.rosters);
    var rows = board.players.map(function (p) { return decorate(p, lookup); });
    var pos = "ALL";
    var avail = "ALL";
    var sort = "rank";
    var query = "";
    var open = "";

    root.innerHTML =
      '<div id="rankSummary"></div>' +
      '<div class="rk-filters" id="rankFilters"></div>' +
      '<input type="search" id="rankSearch" placeholder="Search players" autocomplete="off">' +
      '<p class="tiny" id="rankCount"></p>' +
      '<div id="rankList"></div>';

    document.getElementById("rankSummary").innerHTML = summaryHtml(board, rows, opts.week, lookup);
    document.getElementById("rankFilters").innerHTML = filtersHtml();
    var filters = document.getElementById("rankFilters");
    var list = document.getElementById("rankList");
    var search = document.getElementById("rankSearch");

    filters.addEventListener("click", function (ev) {
      var b = ev.target.closest("button");
      if (!b) return;
      if (b.getAttribute("data-pos")) pos = b.getAttribute("data-pos");
      if (b.getAttribute("data-avail")) avail = b.getAttribute("data-avail");
      if (b.getAttribute("data-sort")) sort = b.getAttribute("data-sort");
      filters.querySelectorAll("button").forEach(function (btn) {
        var on = (btn.getAttribute("data-pos") && btn.getAttribute("data-pos") === pos) ||
          (btn.getAttribute("data-avail") && btn.getAttribute("data-avail") === avail) ||
          (btn.getAttribute("data-sort") && btn.getAttribute("data-sort") === sort);
        btn.classList.toggle("on", !!on);
      });
      renderList();
    });
    search.addEventListener("input", function () {
      query = search.value || "";
      renderList();
    });
    list.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-key]");
      if (!b) return;
      var key = b.getAttribute("data-key");
      open = open === key ? "" : key;
      renderList();
    });
    renderList();

    function renderList() {
      var q = norm(query);
      var shown = rows.filter(function (row) {
        var p = row.player;
        if (pos === "FLEX" && !FLEX[p.pos]) return false;
        if (pos === "IDP" && !IDP[p.pos]) return false;
        if (pos !== "ALL" && pos !== "FLEX" && pos !== "IDP" && p.pos !== pos) return false;
        if (avail === "EDDIES" && row.avail !== "eddies") return false;
        if (avail === "FA" && row.avail !== "fa") return false;
        if (avail === "OTHER" && row.avail !== "other") return false;
        if (!q) return true;
        var blob = norm(p.name + " " + p.team + " " + p.opp + " " + row.club);
        return blob.indexOf(q) !== -1;
      });
      shown.sort(function (a, b) {
        var pa = a.player;
        var pb = b.player;
        if (sort === "points") return (pb.pts == null ? -1 : pb.pts) - (pa.pts == null ? -1 : pa.pts) || pa.name.localeCompare(pb.name);
        if (sort === "name") return pa.name.localeCompare(pb.name);
        if (sort === "matchup") return gradeScore(pb) - gradeScore(pa) || (pa.rank || 999) - (pb.rank || 999);
        if (pos === "ALL" && POS_ORDER[pa.pos] !== POS_ORDER[pb.pos]) return POS_ORDER[pa.pos] - POS_ORDER[pb.pos];
        return (pa.rank || 999) - (pb.rank || 999) || pa.name.localeCompare(pb.name);
      });
      document.getElementById("rankCount").textContent = shown.length + " players";
      if (!shown.length) {
        list.innerHTML = '<div class="card"><p>No players match.</p></div>';
        return;
      }
      list.innerHTML = shown.map(function (row) { return rowHtml(row, open); }).join("");
    }
  }

  function gradeScore(row) {
    var g = row.player.matchup && row.player.matchup.grade;
    return GRADES[g] || 0;
  }

  function filtersHtml() {
    var posBtns = [
      ["ALL", "All"], ["QB", "QB"], ["RB", "RB"], ["WR", "WR"], ["TE", "TE"], ["FLEX", "Flex"],
      ["DL", "DL"], ["LB", "LB"], ["DB", "DB"], ["IDP", "IDP"]
    ];
    var availBtns = [["ALL", "Everyone"], ["EDDIES", "Eddies"], ["FA", "Free agents"], ["OTHER", "Other teams"]];
    var sortBtns = [["rank", "Rank"], ["points", "Points"], ["matchup", "Matchup"], ["name", "Name"]];
    function group(buttons, attr) {
      return buttons.map(function (pair, i) {
        return '<button type="button" data-' + attr + '="' + pair[0] + '"' + (i === 0 ? ' class="on"' : "") + ">" + pair[1] + "</button>";
      }).join("");
    }
    return '<div class="filters">' + group(posBtns, "pos") + "</div>" +
      '<div class="filters">' + group(availBtns, "avail") + "</div>" +
      '<div class="sorts"><span class="lbl">Sort</span>' + group(sortBtns, "sort") + "</div>";
  }

  function summaryHtml(board, rows, appWeek, lookup) {
    var html = "";
    if (appWeek && board.week && Number(appWeek) !== Number(board.week)) {
      html += '<div class="banner">This board is Week ' + esc(board.week) + ". The War Room week is " + esc(appWeek) + ".</div>";
    }
    var missing = (board.sources || []).filter(function (s) { return !s.ok || s.partial; });
    if (missing.length) {
      html += '<div class="banner">' + missing.map(function (s) {
        return esc(s.name) + (s.ok ? " is partial" : " is missing") + (s.detail ? ": " + esc(s.detail) : "");
      }).join("<br>") + "</div>";
    }
    html += '<div class="card"><h2>Week ' + esc(board.week) + " rankings</h2>";
    html += "<p>Consensus averages the Sleeper and ESPN projections, rescored for Wheels Up. " + esc(asOfPt(board.asOf)) + ".</p>";
    html += '<p class="tiny">ESPN is offense only. Last 3 widens the range and is not the projection. FantasyPros is a rank, not points.</p></div>';
    html += startSitHtml(rows, lookup);
    html += gemsHtml(rows);
    return html;
  }

  function startSitHtml(rows) {
    var byKey = {};
    var byName = {};
    rows.forEach(function (row) {
      if (row.avail !== "eddies") return;
      byKey[norm(row.player.name) + "|" + row.player.pos] = row;
      if (!byName[norm(row.player.name)]) byName[norm(row.player.name)] = [];
      byName[norm(row.player.name)].push(row);
    });
    var doc = window.__wuEddiesDoc || null;
    if (!doc) {
      var names = Object.keys(byName);
      if (!names.length) return "";
    }
    var pool = [];
    var roster = (doc && doc.roster) || {};
    var positions = ["QB", "RB", "WR", "TE", "DL", "LB", "DB"];
    if (doc) {
      positions.forEach(function (pos) {
        (roster[pos] || []).forEach(function (name) {
          var named = byName[norm(name)] || [];
          var hit = byKey[norm(name) + "|" + pos] || (named.length === 1 ? named[0] : null);
          var injury = hit ? hit.player.injury : "";
          var bye = hit ? hit.player.bye : false;
          var blocked = cannotStart(name, doc) || hardOut(injury) || bye || (hit && hit.ir);
          pool.push({
            name: name,
            pos: (hit && hit.player.pos) || pos,
            ppg: hit && hit.player.pts != null ? hit.player.pts : 0,
            ir: false,
            ineligible: blocked,
            injury: injury,
            bye: bye,
            why: bye ? "bye" : (hardOut(injury) ? injury : (cannotStart(name, doc) ? "reserve" : ""))
          });
        });
      });
    } else {
      rows.forEach(function (row) {
        if (row.avail !== "eddies") return;
        var blocked = row.ir || row.blocked || hardOut(row.player.injury) || row.player.bye;
        pool.push({
          name: row.player.name,
          pos: row.player.pos,
          ppg: row.player.pts || 0,
          ir: row.ir,
          ineligible: blocked,
          injury: row.player.injury,
          bye: row.player.bye,
          why: row.player.bye ? "bye" : (row.player.injury || "")
        });
      });
    }
    if (!pool.length || !window.WUVor) return "";
    var plan = WUVor.optimizeLineup(pool, WUVor.DEFAULT_LINEUP);
    var used = {};
    plan.starters.forEach(function (slot) { used[slot.player.name] = slot.slot; });
    var html = '<div class="card rk-start"><h2>Start / sit for Eddies</h2>';
    html += '<p class="scoreline">' + esc((Math.round(plan.total * 10) / 10).toFixed(1)) + '</p><p class="tiny">Best lineup from this week\'s consensus. Questionable and doubtful can start. Out, IR, reserve, and bye cannot.</p>';
    html += plan.starters.map(function (slot) {
      var p = slot.player;
      var tag = p.injury && !hardOut(p.injury) ? " " + p.injury : "";
      return '<div class="rk-slot"><b>' + esc(slot.slot) + "</b><span>" + esc(p.name) + esc(tag) + "</span><em>" + esc(ptsText(p.ppg)) + "</em></div>";
    }).join("");
    var sit = pool.filter(function (p) { return !p.ineligible && !used[p.name]; })
      .sort(function (a, b) { return b.ppg - a.ppg || a.name.localeCompare(b.name); });
    if (sit.length) {
      html += '<p class="sec">Sit</p>';
      html += sit.map(function (p) {
        return '<div class="rk-slot sit"><b>' + esc(p.pos) + "</b><span>" + esc(p.name) + "</span><em>" + esc(ptsText(p.ppg)) + "</em></div>";
      }).join("");
    }
    var cant = pool.filter(function (p) { return p.ineligible; });
    if (cant.length) {
      html += '<p class="tiny">Can\'t start: ' + esc(cant.map(function (p) {
        return p.name + (p.why ? " (" + p.why + ")" : "");
      }).join(", ")) + "</p>";
    }
    var ir = (roster.IR || []);
    if (ir.length) html += '<p class="tiny">IR: ' + esc(ir.join(", ")) + "</p>";
    html += "</div>";
    return html;
  }

  function gemsHtml(rows) {
    var gems = rows.filter(function (row) {
      var p = row.player;
      if (row.avail !== "fa" || p.bye || p.played || hardOut(p.injury)) return false;
      if (p.rank == null) return false;
      var cap = (p.pos === "QB" || p.pos === "TE") ? 18 : 36;
      return p.rank <= cap;
    }).sort(function (a, b) {
      return (a.player.rank || 999) - (b.player.rank || 999) || (b.player.pts || 0) - (a.player.pts || 0);
    }).slice(0, 8);
    if (!gems.length) return "";
    var html = '<div class="card"><h2>On the wire</h2><p class="tiny">Unrostered, ranked inside the useful range, and not out or on a bye.</p>';
    html += gems.map(function (row) {
      var p = row.player;
      return '<div class="rk-slot"><b>' + esc(p.pos) + esc(p.rank) + "</b><span>" + esc(p.name) + " · " + esc(side(p)) + "</span><em>" + esc(ptsText(p.pts)) + "</em></div>";
    }).join("");
    html += "</div>";
    return html;
  }

  function rowHtml(row, open) {
    var p = row.player;
    var key = encodeURIComponent(p.name + "|" + p.pos);
    var cls = "rk-row" + (row.avail === "eddies" ? " you" : "") + (p.played ? " played" : "");
    var chips = "";
    if (p.injury) chips += '<i class="rk-flag ' + (hardOut(p.injury) ? "out" : "q") + '">' + esc(p.injury) + "</i>";
    if (p.bye) chips += '<i class="rk-flag bye">BYE</i>';
    if (p.played && !p.bye) chips += '<i class="rk-flag">Played</i>';
    if (p.split) chips += '<i class="rk-flag split">Split</i>';
    if (row.avail === "fa") chips += '<i class="rk-flag wire">FA</i>';
    var grade = p.matchup && p.matchup.grade ? p.matchup.grade : "";
    var html = '<button type="button" class="' + cls + '" data-key="' + key + '">';
    html += '<span class="rank">' + esc(p.rank == null ? "—" : p.rank) + "</span>";
    html += '<span class="info"><span class="name">' + esc(p.name) + ' <span class="pos ' + esc(p.pos) + '">' + esc(p.pos) + "</span> " + chips + "</span>";
    html += '<span class="meta">' + esc(p.team || "FA") + " " + esc(side(p));
    if (grade) html += " · " + esc(grade);
    if (row.avail === "eddies") html += " · Eddies";
    else if (row.club) html += " · " + esc(row.club);
    if (p.weather && p.weather.text) html += " · " + esc(p.weather.text);
    html += "</span></span>";
    html += '<span class="rk-pts"><b>' + esc(ptsText(p.pts)) + "</b><span>" + esc(rangeText(p)) + "</span></span>";
    if (grade) html += '<span class="rk-grade g' + esc(grade) + '">' + esc(grade) + "</span>";
    html += "</button>";
    if (open === key) html += detailHtml(p);
    return html;
  }

  function detailHtml(p) {
    var order = ["sleeper", "espn", "recent", "fantasypros"];
    var html = '<div class="rk-detail">';
    order.forEach(function (id) {
      var src = p.sources && p.sources[id];
      html += '<div class="rk-src"><b>' + esc(SOURCE_NAME[id]) + "</b>";
      if (!src) {
        html += "<span>—</span>";
      } else if (id === "fantasypros") {
        var band = (src.low != null && src.high != null) ? " (" + src.low + "–" + src.high + ")" : "";
        html += "<span>Rank " + esc(src.rank) + esc(band) + "</span>";
      } else {
        var extra = src.weeks ? " · " + src.weeks + " wk" : "";
        html += "<span>" + esc(ptsText(src.pts)) + " · rank " + esc(src.rank == null ? "—" : src.rank) + esc(extra) + "</span>";
      }
      html += "</div>";
    });
    if (p.matchup) {
      html += '<p class="tiny">' + esc(p.matchup.kind === "idp" ? "IDP matchup" : "Matchup");
      if (p.matchup.grade) html += " " + esc(p.matchup.grade);
      if (p.matchup.place && p.matchup.of) html += " · " + esc(p.matchup.place) + " of " + esc(p.matchup.of);
      if (p.matchup.note) html += " · " + esc(p.matchup.note);
      html += "</p>";
    }
    if (p.vegas) {
      var fav = p.vegas.spread < 0 ? "favored" : "underdog";
      html += '<p class="tiny">Spread ' + esc(p.vegas.spread) + " (" + fav + "), total " + esc(p.vegas.total) + ", implied " + esc(p.vegas.implied) + "</p>";
    }
    if (p.split) html += '<p class="tiny">Sources disagree by a wide rank gap or by 6 or more points.</p>';
    html += "</div>";
    return html;
  }

  window.WURankings = {
    mount: function (opts) {
      window.__wuEddiesDoc = opts && opts.rosters ? opts.rosters.eddies : null;
      mount(opts || {});
    }
  };
})();
