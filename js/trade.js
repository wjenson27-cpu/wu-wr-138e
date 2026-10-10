/* Trade tab. Same replacement math as js/vor.js, drawn in the War Room. */
(function (root) {
  var POS = ["QB", "RB", "WR", "TE", "DL", "LB", "DB"];
  var state = {
    teams: [],
    rosters: {},
    values: null,
    byKey: {},
    freeAgents: [],
    waiverOn: false,
    waiverSample: false,
    waiverNote: "",
    valuesStale: false,
    a: "eddies",
    b: "",
    aSend: [],
    bSend: [],
    aFaab: 0,
    bFaab: 0,
    context: true,
    open: "",
    query: { a: "", b: "" },
    ctx: null
  };

  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function fmt(n) {
    var num = Number(n);
    if (!Number.isFinite(num)) return "0.0";
    return num.toFixed(1);
  }

  function signed(n) {
    var num = Number(n) || 0;
    return (num > 0 ? "+" : "") + num.toFixed(1);
  }

  function normName(name) {
    if (typeof WURankMath !== "undefined" && WURankMath.normName) return WURankMath.normName(name);
    return String(name || "").toLowerCase();
  }

  function lookup(name) {
    return state.byKey[normName(name)] || null;
  }

  function teamById(id) {
    for (var i = 0; i < state.teams.length; i++) if (state.teams[i].id === id) return state.teams[i];
    return null;
  }

  function sideLabel(team) {
    if (!team) return "That club";
    if (/eddies/i.test(team.name || "")) return "Eddies";
    return team.name;
  }

  function blendOf(season, last3) {
    return WUVor.blendRate(season, last3, WUVor.WEIGHTS);
  }

  function cannotStart(name, doc) {
    var flags = [].concat(doc.injuryFlags || [], doc.flags || []);
    var n = String(name || "").toLowerCase();
    for (var i = 0; i < flags.length; i++) {
      var line = String(flags[i]).toLowerCase();
      if (line.indexOf(n) === -1) continue;
      if (/\(reserve/.test(line) || /\(ir/.test(line)) return true;
    }
    return false;
  }

  function rosterRows(teamId) {
    var doc = state.rosters[teamId] || {};
    var roster = doc.roster || {};
    var ir = {};
    (roster.IR || []).forEach(function (name) { ir[name] = true; });
    var rows = [];
    var seen = {};
    POS.forEach(function (pos) {
      (roster[pos] || []).forEach(function (name) {
        var valued = lookup(name);
        var blend = blendOf(valued ? valued.ppg : null, valued ? valued.last3Ppg : null);
        var reserve = !ir[name] && cannotStart(name, doc);
        rows.push({
          name: name,
          pos: pos,
          ir: !!ir[name],
          reserve: reserve,
          ineligible: !!ir[name] || reserve,
          ppg: valued ? blend.rate : 0,
          seasonPpg: valued ? valued.ppg : null,
          last3Ppg: valued ? valued.last3Ppg : null,
          games: valued ? valued.games : null,
          nflTeam: valued ? valued.nflTeam : "",
          injury: valued ? valued.injury || "" : "",
          unvalued: !valued,
          usedLast3: blend.usedLast3
        });
        seen[name] = true;
      });
    });
    (roster.IR || []).forEach(function (name) {
      if (seen[name]) return;
      var valued = lookup(name);
      var pos = valued ? valued.position : "RB";
      if (POS.indexOf(pos) === -1) pos = "RB";
      var blend = blendOf(valued ? valued.ppg : null, valued ? valued.last3Ppg : null);
      rows.push({
        name: name, pos: pos, ir: true, reserve: false, ineligible: true, ppg: valued ? blend.rate : 0,
        nflTeam: valued ? valued.nflTeam : "", injury: valued ? valued.injury || "" : "",
        unvalued: !valued, games: valued ? valued.games : null, usedLast3: blend.usedLast3
      });
    });
    return rows;
  }

  function buildBoard() {
    var rostered = [];
    var seen = {};
    state.teams.forEach(function (team) {
      rosterRows(team.id).forEach(function (row) {
        if (row.ir || row.unvalued) return;
        var key = row.pos + "|" + normName(row.name);
        if (seen[key]) return;
        seen[key] = true;
        rostered.push({ name: row.name, pos: row.pos, ppg: row.seasonPpg, last3Ppg: row.last3Ppg });
      });
    });
    state.ctx = WUVor.computeReplacement({
      rostered: rostered,
      freeAgents: state.waiverOn ? state.freeAgents : [],
      lineup: WUVor.DEFAULT_LINEUP,
      teamCount: 14,
      useWaiver: state.waiverOn,
      scarcity: true
    });
  }

  function priced(row) {
    if (!state.ctx || row.unvalued) return { vor: null, rank: null, rate: row.ppg };
    var hit = null;
    state.ctx.priced.forEach(function (p) {
      if (p.name === row.name && p.pos === row.pos) hit = p;
    });
    if (hit) return hit;
    return { vor: state.ctx.vorFor(row.ppg, row.pos), rank: null, rate: row.ppg };
  }

  function faabLeft(teamId) {
    var team = teamById(teamId);
    if (team && team.faab != null && team.faab !== "") return Number(team.faab) || 0;
    var doc = state.rosters[teamId];
    return doc && doc.faabLeft != null ? Number(doc.faabLeft) || 0 : 0;
  }

  function findOnRoster(teamId, name) {
    var rows = rosterRows(teamId);
    for (var i = 0; i < rows.length; i++) if (rows[i].name === name) return rows[i];
    return null;
  }

  function packageOf(names) {
    var players = names.map(function (name) {
      var row = null;
      state.teams.forEach(function (team) {
        if (!row) row = findOnRoster(team.id, name);
      });
      row = row || { name: name, pos: "?", ppg: 0, unvalued: true };
      var price = priced(row);
      return Object.assign({}, row, { vor: price.vor, rank: price.rank });
    });
    var vor = 0;
    players.forEach(function (p) { if (p.vor != null) vor += p.vor; });
    return { players: players, vor: vor };
  }

  function deltaFor(teamId, send, incoming) {
    var base = rosterRows(teamId);
    var drop = {};
    send.forEach(function (name) { drop[name] = true; });
    var next = base.filter(function (p) { return !drop[p.name]; }).concat(incoming);
    var before = WUVor.optimizeLineup(base, WUVor.DEFAULT_LINEUP);
    var after = WUVor.optimizeLineup(next, WUVor.DEFAULT_LINEUP);
    return { before: before, after: after, delta: after.total - before.total, next: next, base: base };
  }

  function fairBand(a, b) {
    return Math.max(1.5, 0.08 * Math.max(Math.abs(a), Math.abs(b), 8));
  }

  function toneOf(aDelta, bDelta) {
    var gap = Math.abs(aDelta - bDelta);
    var band = fairBand(aDelta, bDelta);
    if (gap < band) return { tone: "fair", label: "Fair" };
    if (gap < band * 2.2) return { tone: "edge", label: "Slight edge" };
    return { tone: "clear", label: "Clear win" };
  }

  function headline(ctx) {
    var aName = sideLabel(teamById(state.a));
    var bName = sideLabel(teamById(state.b));
    var vorLine = "Packages: " + aName + " " + fmt(ctx.bPack.vor) + " VOR, " + bName + " " + fmt(ctx.aPack.vor) + " VOR.";
    if (!state.context) return { main: vorLine, side: "Lineup fit is off, so this is the raw package only." };
    var aDelta = ctx.aDelta.delta;
    var bDelta = ctx.bDelta.delta;
    var verb = aDelta >= -0.05 ? "gain" : "lose";
    var aBit = aDelta >= -0.05 ? signed(aDelta) : Math.abs(aDelta).toFixed(1);
    var main = aName + " " + verb + " " + aBit + " starter pts/wk; " + bName + " " + signed(bDelta) + ".";
    return { main: main, side: vorLine };
  }

  function dealContext() {
    var aPack = packageOf(state.bSend);
    var bPack = packageOf(state.aSend);
    var aIncoming = state.bSend.map(function (name) { return findOnRoster(state.b, name); }).filter(Boolean);
    var bIncoming = state.aSend.map(function (name) { return findOnRoster(state.a, name); }).filter(Boolean);
    return {
      aPack: aPack,
      bPack: bPack,
      aDelta: deltaFor(state.a, state.aSend, aIncoming),
      bDelta: deltaFor(state.b, state.bSend, bIncoming)
    };
  }

  function hasDeal() {
    return state.a && state.b && state.a !== state.b && (state.aSend.length || state.bSend.length || state.aFaab || state.bFaab);
  }

  function playerBits(row) {
    var price = priced(row);
    var injury = row.injury ? '<span class="tc-flag">' + esc(row.injury) + "</span>" : "";
    var ir = row.ir ? '<span class="tc-flag">IR</span>' : (row.reserve ? '<span class="tc-flag">RES</span>' : "");
    var score = row.unvalued
      ? '<span class="tc-novalue">No 2026 score</span>'
      : '<span class="tc-val">' + fmt(row.ppg) + " · VOR " + fmt(price.vor) + (price.rank ? " · " + row.pos + price.rank : "") + "</span>";
    var sub = row.unvalued
      ? esc(row.pos)
      : esc(row.nflTeam || "") + " · " + fmt(row.ppg) + " pts/g" + (row.games ? " · " + row.games + "g" : "");
    var mark = window.WUGreen ? WUGreen.mark(state.greenDots, row.name) : "";
    return '<span class="tc-pos">' + esc(row.pos) + '</span><span class="tc-who"><span class="tc-pname">' +
      esc(row.name) + mark + " " + ir + injury + '</span><span class="tc-psub">' + sub + "</span></span>" + score;
  }

  function resultItems(which, query) {
    var teamId = state[which];
    if (!teamId) return "";
    var send = {};
    (which === "a" ? state.aSend : state.bSend).forEach(function (n) { send[n] = true; });
    var needle = normName(query);
    var rows = rosterRows(teamId).filter(function (p) { return !send[p.name]; });
    if (needle) {
      rows = rows.filter(function (p) {
        return normName(p.name).indexOf(needle) !== -1 || p.pos.toLowerCase().indexOf(needle) !== -1;
      });
    }
    rows.sort(function (a, b) {
      return POS.indexOf(a.pos) - POS.indexOf(b.pos) || b.ppg - a.ppg || a.name.localeCompare(b.name);
    });
    if (!rows.length) return '<li class="tiny">No match on this roster.</li>';
    return rows.map(function (p) {
      return '<li><button type="button" class="tc-result" data-add="' + which + '" data-name="' + esc(p.name) + '">' +
        playerBits(p) + "</button></li>";
    }).join("");
  }

  function renderSide(which) {
    var teamId = state[which];
    var other = which === "a" ? state.b : state.a;
    var send = which === "a" ? state.aSend : state.bSend;
    var faab = which === "a" ? state.aFaab : state.bFaab;
    var options = state.teams.map(function (team) {
      var selected = team.id === teamId ? " selected" : "";
      var disabled = team.id === other ? " disabled" : "";
      return '<option value="' + esc(team.id) + '"' + selected + disabled + ">" + esc(team.name) + "</option>";
    }).join("");
    var team = teamById(teamId);
    var meta = team
      ? esc(team.owner || "") + (team.record ? " · " + esc(team.record) : "") + " · $" + faabLeft(teamId) + " FAAB"
      : "Choose a club.";
    var added = send.map(function (name) {
      var row = findOnRoster(teamId, name) || { name: name, pos: "?", ppg: 0, unvalued: true };
      return '<li class="tc-chip-row">' + playerBits(row) +
        '<button type="button" class="tc-remove" data-remove="' + which + '" data-name="' + esc(name) + '" aria-label="Remove">×</button></li>';
    }).join("");
    var open = state.open === which;
    return '<div class="card"><label class="tc-label" for="tcTeam-' + which + '">' + (which === "a" ? "Your side" : "Other side") +
      '</label><select id="tcTeam-' + which + '">' + (which === "a" ? "" : '<option value="">Select a team</option>') + options +
      '</select><p class="tc-meta">' + meta + '</p><label class="tc-label">Add a player</label><div class="tc-picker">' +
      '<input class="tc-search" data-side="' + which + '" type="search" placeholder="' + (teamId ? "Search this roster" : "Pick a team first") +
      '" ' + (teamId ? "" : "disabled") + ' value="' + esc(state.query[which] || "") + '" autocomplete="off">' +
      '<ul class="tc-results" id="tcList-' + which + '"' + (open ? "" : " hidden") + ">" + (open ? resultItems(which, state.query[which] || "") : "") +
      "</ul></div><ul class=\"tc-added\">" + (added || '<li class="tiny">Nobody added yet.</li>') +
      '</ul><label class="tc-label" for="tcFaab-' + which + '">FAAB included</label>' +
      '<input id="tcFaab-' + which + '" data-side="' + which + '" class="tc-faab" inputmode="numeric" type="number" min="0" max="' +
      (teamId ? faabLeft(teamId) : 0) + '" step="1" value="' + faab + '"' + (teamId ? "" : " disabled") + "></div>";
  }

  function replacementTable() {
    if (!state.ctx) return "";
    var rows = POS.map(function (pos) {
      var r = state.ctx.replacement[pos];
      if (!r) return "";
      return "<tr><td>" + pos + "</td><td>" + fmt(r.rostered) + "</td><td>" + (r.waiver == null ? "—" : fmt(r.waiver)) +
        "</td><td>" + (r.source === "waiver" ? "Wire" : "Rostered") +
        "</td><td>" + r.scarcity.toFixed(2) + "</td><td>" + r.starters + "</td></tr>";
    }).join("");
    return '<div class="card"><h3>Replacement level</h3><p class="tiny">The line is whichever is higher: the last starter already rostered, or the best free agent. Scarcity bumps a position when the next tier falls off.</p>' +
      '<div class="scroll"><table class="sheet"><thead><tr><th>Pos</th><th>Rostered</th><th>Wire</th><th>Used</th><th>Scarcity</th><th>Starters</th></tr></thead><tbody>' +
      rows + "</tbody></table></div></div>";
  }

  function renderVerdict() {
    if (!state.a || !state.b || state.a === state.b) {
      return '<div class="card"><h3>The verdict</h3><p>' + (state.a === state.b && state.b ? "Pick two different clubs." : "Pick the other club to start.") + "</p></div>";
    }
    if (!hasDeal()) {
      return '<div class="card"><h3>The verdict</h3><p>Add a player from either roster. The headline is starter points per week. The package VOR sits next to it.</p></div>';
    }
    var ctx = dealContext();
    var words = headline(ctx);
    var tone = toneOf(ctx.aDelta.delta, ctx.bDelta.delta);
    var scale = fairBand(ctx.aDelta.delta, ctx.bDelta.delta) * 3 || 1;
    var net = state.context ? (ctx.aDelta.delta - ctx.bDelta.delta) : (ctx.bPack.vor - ctx.aPack.vor);
    var tilt = Math.max(-1, Math.min(1, net / scale));
    var knob = 50 + tilt * 42;
    var color = net >= 0 ? ((teamById(state.a) || {}).color || "#69BE28") : ((teamById(state.b) || {}).color || "#7eb6ff");
    var fill = knob >= 50
      ? "left:50%;width:" + (knob - 50) + "%;background:" + color
      : "left:" + knob + "%;width:" + (50 - knob) + "%;background:" + color;
    var fit = state.context
      ? '<p class="tiny">' + esc(sideLabel(teamById(state.a))) + " starters " + fmt(ctx.aDelta.before.total) + " → " + fmt(ctx.aDelta.after.total) +
        ". " + esc(sideLabel(teamById(state.b))) + " starters " + fmt(ctx.bDelta.before.total) + " → " + fmt(ctx.bDelta.after.total) + ".</p>"
      : "";
    return '<div class="card"><h3>The verdict</h3><p class="tc-plain">' + esc(words.main) + '</p><p class="tiny">' + esc(words.side) + "</p>" +
      '<div class="tc-meter"><div class="tc-packages"><span>' + esc((teamById(state.a) || {}).abbrev || "A") +
      '</span><span class="tc-tone tc-tone-' + tone.tone + '">' + tone.label + "</span><span>" +
      esc((teamById(state.b) || {}).abbrev || "B") + '</span></div><div class="tc-meter-track"><span class="tc-meter-fill" style="' +
      fill + '"></span><span class="tc-meter-mid"></span><span class="tc-meter-knob" style="left:' + knob + '%"></span></div></div>' +
      fit + rosterCompare(ctx) + "</div>";
  }

  function rosterCompare(ctx) {
    var positions = {};
    ctx.aPack.players.concat(ctx.bPack.players).forEach(function (p) {
      if (p.pos === "RB" || p.pos === "WR" || p.pos === "TE") { positions.RB = positions.WR = positions.TE = true; }
      else if (p.pos === "DL" || p.pos === "LB" || p.pos === "DB") { positions.DL = positions.LB = positions.DB = true; }
      else positions[p.pos] = true;
    });
    function block(title, base, next, before, after) {
      var html = "<h3>" + esc(title) + "</h3>";
      POS.forEach(function (pos) {
        if (!positions[pos]) return;
        html += '<div class="sec">' + pos + '</div><div class="tc-ba">' + col("Before", base, before, pos) + col("After", next, after, pos) + "</div>";
      });
      return html;
    }
    return block(sideLabel(teamById(state.a)), ctx.aDelta.base, ctx.aDelta.next, ctx.aDelta.before, ctx.aDelta.after) +
      block(sideLabel(teamById(state.b)), ctx.bDelta.base, ctx.bDelta.next, ctx.bDelta.before, ctx.bDelta.after);
  }

  function col(label, players, line, pos) {
    var rows = players.filter(function (p) { return p.pos === pos; }).sort(function (a, b) {
      var as = line.slotOf[a.name] ? 1 : 0;
      var bs = line.slotOf[b.name] ? 1 : 0;
      return bs - as || b.ppg - a.ppg;
    });
    var body = rows.length ? rows.map(function (p) {
      var slot = line.slotOf[p.name];
      var badge = p.ir ? '<span class="tc-badge tc-badge-ir">IR</span>' : (p.ineligible ? '<span class="tc-badge tc-badge-bench">RES</span>' : (slot ? '<span class="tc-badge">' + esc(slot) + "</span>" : '<span class="tc-badge tc-badge-bench">Bench</span>'));
      var mark = window.WUGreen ? WUGreen.mark(state.greenDots, p.name) : "";
      return "<li><span>" + esc(p.name) + mark + "</span>" + badge + "<span class=\"tc-val\">" + (p.unvalued ? "—" : fmt(p.ppg)) + "</span></li>";
    }).join("") : '<li class="tiny">Empty</li>';
    return "<div><p class=\"tiny\">" + label + '</p><ul class="tc-rlist">' + body + "</ul></div>";
  }

  function weightsLine() {
    var w = WUVor.WEIGHTS;
    var asOf = state.values && state.values.asOf ? state.values.asOf : "";
    var last3 = state.ctx ? state.ctx.last3Count : 0;
    return "Rates are " + Math.round(w.season * 100) + "% season and " + Math.round(w.last3 * 100) +
      "% last 3 weeks when a last-3 rate is present (" + last3 + " rates in this load). The season rate already counts each older week at " +
      Math.round(w.decay * 100) + "%. Values as of " + asOf + ".";
  }

  function badges() {
    var html = "";
    if (state.valuesStale) html += '<span class="badge stale">STALE</span>';
    if (state.waiverSample) html += '<span class="badge sample">SAMPLE WIRE</span>';
    if (!state.waiverOn) html += '<span class="badge stale">WIRE OFF</span>';
    return html;
  }

  function render() {
    var host = document.getElementById("tradeRoot");
    if (!host) return;
    try { localStorage.setItem("wu-trade-v1", JSON.stringify({ a: state.a, b: state.b, aSend: state.aSend, bSend: state.bSend, aFaab: state.aFaab, bFaab: state.bFaab, context: state.context })); } catch (e) {}
    host.innerHTML =
      '<div class="card"><h2>Trade calculator ' + badges() + '</h2><p class="tiny">' + esc(weightsLine()) + "</p><p class=\"tiny\">" + esc(state.waiverNote) + "</p>" +
      (window.WUGreen ? WUGreen.note(state.greenDots) : "") +
      '<label class="hide-drafted"><input type="checkbox" id="tcContext"' + (state.context ? " checked" : "") + "> Count lineup fit</label></div>" +
      '<div class="tc-sides">' + renderSide("a") + renderSide("b") + "</div>" +
      renderVerdict() + replacementTable() +
      '<details class="card"><summary>How the numbers work</summary><p>A player is worth his points per game over the replacement line, times a scarcity bump when that position drops off fast. The line is the higher of the last starter the league already rosters and the best player on the wire. IR cannot start. A bench player who would not crack the lineup adds nothing to the headline. Filling an empty spot adds his full weekly points.</p></details>';
  }

  function onClick(event) {
    if (event.target.closest(".gdot")) return;
    var add = event.target.closest("[data-add]");
    if (add) {
      var which = add.getAttribute("data-add");
      var name = add.getAttribute("data-name");
      var key = which === "a" ? "aSend" : "bSend";
      if (state[key].indexOf(name) === -1 && findOnRoster(state[which], name)) state[key].push(name);
      state.open = "";
      state.query[which] = "";
      render();
      return;
    }
    var remove = event.target.closest("[data-remove]");
    if (remove) {
      var side = remove.getAttribute("data-remove");
      var drop = remove.getAttribute("data-name");
      var list = side === "a" ? "aSend" : "bSend";
      state[list] = state[list].filter(function (n) { return n !== drop; });
      render();
      return;
    }
    var search = event.target.closest(".tc-search");
    if (search) {
      var side = search.getAttribute("data-side");
      state.open = side;
      var openList = document.getElementById("tcList-" + side);
      if (openList) {
        openList.hidden = false;
        openList.innerHTML = resultItems(side, search.value);
      }
      return;
    }
    if (!event.target.closest(".tc-picker")) {
      state.open = "";
      ["a", "b"].forEach(function (side) {
        var list = document.getElementById("tcList-" + side);
        if (list) list.hidden = true;
      });
    }
  }

  function onChange(event) {
    if (event.target.id === "tcTeam-a" || event.target.id === "tcTeam-b") {
      var which = event.target.id.slice(-1);
      state[which] = event.target.value;
      state[which === "a" ? "aSend" : "bSend"] = [];
      state[which === "a" ? "aFaab" : "bFaab"] = 0;
      state.open = "";
      render();
    }
    if (event.target.id === "tcContext") {
      state.context = event.target.checked;
      render();
    }
    if (event.target.classList && event.target.classList.contains("tc-faab")) {
      var side = event.target.getAttribute("data-side");
      var cap = faabLeft(state[side]);
      var n = Math.max(0, Math.min(cap, Math.round(Number(event.target.value) || 0)));
      state[side === "a" ? "aFaab" : "bFaab"] = n;
      render();
    }
  }

  function onInput(event) {
    if (event.target.classList && event.target.classList.contains("tc-search")) {
      var which = event.target.getAttribute("data-side");
      state.open = which;
      state.query[which] = event.target.value;
      var list = document.getElementById("tcList-" + which);
      if (list) {
        list.hidden = false;
        list.innerHTML = resultItems(which, event.target.value);
      }
      return;
    }
  }

  function mount(bundle) {
    state.teams = (bundle.teams || []).slice().sort(function (a, b) { return a.name.localeCompare(b.name); });
    state.rosters = bundle.rosters || {};
    state.values = bundle.values || {};
    state.byKey = {};
    ((state.values && state.values.players) || []).forEach(function (player) {
      [player.name].concat(player.aliases || []).forEach(function (alias) {
        var key = normName(alias);
        var prev = state.byKey[key];
        if (!prev || (player.games || 0) > (prev.games || 0)) state.byKey[key] = player;
      });
    });
    var fa = bundle.freeAgents;
    state.freeAgents = (fa && fa.players) || [];
    state.waiverSample = !!(fa && fa.sample);
    var stale = !fa || !fa.asOf || WUVor.isStale(fa.asOf, 3, new Date());
    state.waiverOn = !!(fa && fa.players && fa.players.length && !stale);
    state.greenDots = bundle.greenDots || null;
    state.waiverNote = state.waiverOn
      ? "Wire file " + (fa.asOf || "") + (state.waiverSample ? ". These free agents are sample names until Eddie writes the real list." : ".")
      : "Free-agent list is missing or older than 3 days, so the line is the rostered baseline only.";
    state.valuesStale = WUVor.isStale(state.values && state.values.asOf, 7, new Date());
    try {
      var saved = JSON.parse(localStorage.getItem("wu-trade-v1") || "null");
      if (saved && saved.a) {
        state.a = saved.a;
        state.b = saved.b || "";
        state.aSend = saved.aSend || [];
        state.bSend = saved.bSend || [];
        state.aFaab = saved.aFaab || 0;
        state.bFaab = saved.bFaab || 0;
        if (typeof saved.context === "boolean") state.context = saved.context;
      }
    } catch (e) {}
    if (!teamById(state.a)) state.a = "eddies";
    if (state.a === "eddies" && !teamById("eddies") && state.teams[0]) state.a = state.teams[0].id;
    buildBoard();
    var host = document.getElementById("tradeRoot");
    if (!host || host.dataset.bound) { render(); return; }
    host.dataset.bound = "1";
    host.addEventListener("click", onClick);
    host.addEventListener("change", onChange);
    host.addEventListener("input", onInput);
    render();
  }

  root.WUTrade = { mount: mount };
})(typeof globalThis !== "undefined" ? globalThis : this);
