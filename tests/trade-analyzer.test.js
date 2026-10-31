const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ta = require("../js/trade-analyzer.js");

const root = path.join(__dirname, "..");

function read(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8");
}

test("local roster, ranking, score, lineup, and color files are the ones in this repo", function () {
  [ta.LOCAL.rosterIndex, ta.LOCAL.rankings, ta.LOCAL.scoring, ta.LOCAL.teams, ta.LOCAL.scores, ta.rosterPath("eddies")].forEach(function (rel) {
    assert.equal(fs.existsSync(path.join(root, rel)), true, rel);
  });
  assert.equal(ta.HQ, "https://wjenson27-cpu.github.io/wheels-up-league-hq/data/");
  const week = ta.weekScoreRequest(7);
  assert.equal(week.local, "data/hq/scores-w7-2026.json");
  assert.equal(week.remote, ta.HQ + "scores-w7-2026.json");
  assert.equal(ta.weekScoreRequest("../../../trades"), null);
});

test("the featured club is Eagleridge Eddie's and TTAB stays a club label", function () {
  const eddies = require("../data/hq/rosters/eddies.json");
  const ttab = require("../data/hq/rosters/ttab.json");
  const featured = ta.teamRecord("eddies", eddies, { color: "#69BE28", abbrev: "ERE" }, { rank: 5, pf: 982 }, ta.FEATURED);
  const other = ta.teamRecord("ttab", ttab, { color: "#111111", abbrev: "TTAB" }, null, ta.FEATURED);
  assert.equal(ta.FEATURED, "Eagleridge Eddie's");
  assert.equal(featured.name, "Eagleridge Eddie's");
  assert.equal(other.name, "TTAB");
  assert.equal(JSON.stringify(featured).includes(eddies.owner), false);
  assert.equal(JSON.stringify(other).includes(ttab.owner), false);
  assert.equal(JSON.stringify(other).includes(ttab.teamName), false);
  assert.equal(Object.hasOwn(featured, "owner"), false);
  assert.equal(Object.hasOwn(featured, "pendingClaim"), false);
  const irName = eddies.roster.IR[0];
  assert.equal(featured.players.find(function (player) { return player.name === irName; }).ir, true);
});

test("contact strings and pending bid fields stay off the club record", function () {
  const dirty = ta.teamRecord("lab", {
    teamName: "Little Ass Boys",
    owner: "secret@example.com",
    phone: "555-010-0199",
    pendingClaims: [{ bid: 12 }],
    pendingTrades: [{ status: "pending" }],
    roster: {
      QB: ["secret@example.com", "555-010-0199", "C.J. Stroud"],
      IR: []
    }
  }, { color: "not-a-color", abbrev: "Little Ass Boys" }, { rank: 3, pf: 10 }, ta.FEATURED);
  assert.deepEqual(dirty.players.map(function (player) { return player.name; }), ["C.J. Stroud"]);
  assert.equal(JSON.stringify(dirty).includes("secret@example.com"), false);
  assert.equal(JSON.stringify(dirty).includes("555-010-0199"), false);
  assert.equal(JSON.stringify(dirty).includes("pending"), false);
  assert.equal(dirty.color, "#69BE28");
  assert.equal(dirty.abbrev, "LAB");
});

test("color and power-rank indexes keep rank, points, and color only", function () {
  const teams = require("../data/hq/teams.json");
  const rankings = require("../data/hq/rankings.json");
  const colors = ta.colorIndex(teams);
  const ranks = ta.rankIndex(rankings);
  const color = colors.get("eddies");
  const rank = ranks.get("eddies");
  assert.deepEqual(Object.keys(color).sort(), ["abbrev", "color"]);
  assert.deepEqual(Object.keys(rank).sort(), ["pf", "rank"]);
  assert.equal(JSON.stringify(color).includes(teams.teams.find(function (team) { return team.id === "eddies"; }).owner), false);
});

test("the lineup rules come from the scoring file already in the repo", function () {
  const scoring = require("../data/scoring.json");
  assert.deepEqual(ta.lineupFromScoring(scoring), {
    QB: 1, RB: 1, WR: 1, TE: 1, RWT: 3, DL: 1, LB: 1, DB: 2, ID: 3
  });
});

test("sending the only quarterback opens a starter hole and logs the posted weeks", function () {
  const lineup = { QB: 1, RB: 0, WR: 0, TE: 0, RWT: 0, DL: 0, LB: 1, DB: 0, ID: 0 };
  function player(name, pos) {
    return { name: name, key: ta.playerKey(name), pos: pos, ir: false };
  }
  const sideA = [player("Keeper QB", "QB"), player("Fred Warner", "LB"), player("Extra LB", "LB")];
  const sideB = [player("Caleb Williams", "QB"), player("Other LB", "LB")];
  const send = [sideA[1]];
  const recv = [sideB[0]];
  const afterA = ta.applyDeal(sideA, new Set(["fred warner"]), recv);
  const afterB = ta.applyDeal(sideB, new Set(["caleb williams"]), send);
  const edge = ta.depthEdge(
    ta.depthReport(ta.activeCounts(sideA), lineup),
    ta.depthReport(ta.activeCounts(afterA), lineup),
    ta.depthReport(ta.activeCounts(sideB), lineup),
    ta.depthReport(ta.activeCounts(afterB), lineup)
  );
  assert.equal(edge.side, "a");
  assert.equal(edge.startersB, -1);
  const store = new Map();
  ta.addWeekLogs(store, { week: 1, matchups: [{ home: "A", away: "B" }] });
  ta.addWeekLogs(store, { week: 7, matchups: [{ topScorers: [{ player: "Fred Warner", pts: 33 }, { player: "Caleb Williams", pts: 31 }] }] });
  ta.addWeekLogs(store, { week: 6, matchups: [{ topScorers: [{ player: "Caleb Williams", pts: 24 }] }] });
  const ptsA = ta.dealPoints(store, send);
  const ptsB = ta.dealPoints(store, recv);
  assert.equal(ptsA.sum, 33);
  assert.equal(ptsB.sum, 55);
  assert.equal(ta.pointsEdge(ptsA, ptsB).side, "b");
  assert.equal(ta.formatPts(ta.pointsEdge(ptsA, ptsB).diff), "22");
});

test("replacement bases are 14 times Bill's required starters", function () {
  assert.deepEqual(ta.BILL_LINEUP, {
    QB: 1, RB: 1, WR: 1, TE: 1, RWT: 3, DL: 1, LB: 1, DB: 2, ID: 3
  });
  assert.deepEqual(ta.replacementBases(ta.BILL_LINEUP, 14), {
    QB: 14, RB: 14, WR: 14, TE: 14, DL: 14, LB: 14, DB: 28
  });
  assert.equal(ta.BILL_LINEUP.RWT * 14, 42);
  assert.equal(ta.BILL_LINEUP.ID * 14, 42);
  assert.deepEqual(ta.resolveLineup(require("../data/scoring.json")), ta.BILL_LINEUP);
  const wrong = {
    roster: {
      startingLineup: {
        QB: 2, RB: 2, WR: 2, TE: 2, RWT_flex_RB_WR_TE: 0,
        DL: 2, LB: 2, DB: 1, ID_flex_any_IDP: 0
      }
    }
  };
  assert.deepEqual(ta.resolveLineup(wrong), ta.BILL_LINEUP);
  assert.deepEqual(ta.lineupFromScoring(wrong), {
    QB: 2, RB: 2, WR: 2, TE: 2, RWT: 0, DL: 2, LB: 2, DB: 1, ID: 0
  });
});

test("flex spots follow a greedy club lineup and final ranks add those spots", function () {
  const teams = [];
  for (let i = 0; i < 14; i++) {
    const players = [];
    function add(pos, n, ppg) {
      for (let k = 0; k < n; k++) {
        players.push({ key: i + "-" + pos + "-" + k, name: pos + " " + i + " " + k, pos: pos, ppg: ppg - k, ir: false });
      }
    }
    add("QB", 1, 20);
    add("RB", 2, 18);
    add("WR", 4, 30);
    add("TE", 1, 12);
    add("DL", 2, 16);
    add("LB", 2, 15);
    add("DB", 3, 14);
    teams.push({ id: "t" + i, players: players });
  }
  const plan = ta.replacementPlan(teams, [], ta.BILL_LINEUP, 14);
  assert.deepEqual(plan.bases, { QB: 14, RB: 14, WR: 14, TE: 14, DL: 14, LB: 14, DB: 28 });
  assert.equal(plan.flex.RB + plan.flex.WR + plan.flex.TE, 42);
  assert.equal(plan.flex.DL + plan.flex.LB + plan.flex.DB, 42);
  assert.equal(plan.flex.WR, 42);
  assert.equal(plan.flex.RB, 0);
  assert.equal(plan.flex.TE, 0);
  assert.equal(plan.flex.DL, 14);
  assert.equal(plan.flex.LB, 14);
  assert.equal(plan.flex.DB, 14);
  assert.deepEqual(plan.ranks, { QB: 14, RB: 14, WR: 56, TE: 14, DL: 28, LB: 28, DB: 42 });
  assert.match(ta.formulaNote(plan), /Final ranks: QB 14, RB 14, WR 56, TE 14, DL 28, LB 28, DB 42/);
});

test("a club that cannot fill flex leaves that spot for the next-best player", function () {
  const lineup = { QB: 1, RB: 1, WR: 1, TE: 0, RWT: 1, DL: 0, LB: 0, DB: 0, ID: 0 };
  const teams = [
    { players: [
      { key: "qa", name: "QA", pos: "QB", ppg: 10, ir: false },
      { key: "ra", name: "RA", pos: "RB", ppg: 30, ir: false },
      { key: "wa", name: "WA", pos: "WR", ppg: 5, ir: false },
      { key: "irb", name: "IRB", pos: "RB", ppg: 99, ir: true }
    ]},
    { players: [
      { key: "qb", name: "QB", pos: "QB", ppg: 9, ir: false },
      { key: "rb1", name: "RB1", pos: "RB", ppg: 20, ir: false },
      { key: "rb2", name: "RB2", pos: "RB", ppg: 12, ir: false },
      { key: "wr1", name: "WR1", pos: "WR", ppg: 25, ir: false },
      { key: "wr2", name: "WR2", pos: "WR", ppg: 15, ir: false }
    ]}
  ];
  const plan = ta.replacementPlan(teams, [], lineup, 2);
  assert.deepEqual(plan.bases, { QB: 2, RB: 2, WR: 2, TE: 0, DL: 0, LB: 0, DB: 0 });
  assert.equal(plan.flex.RB, 1);
  assert.equal(plan.flex.WR, 1);
  assert.equal(plan.ranks.QB, 2);
  assert.equal(plan.ranks.RB, 3);
  assert.equal(plan.ranks.WR, 3);
  assert.equal(plan.replacement.RB.ppg, 12);
  assert.equal(plan.replacement.WR.ppg, 5);
  const withFa = ta.replacementPlan(teams, [{ key: "fa", name: "FA RB", pos: "RB", ppg: 19 }], lineup, 2);
  assert.equal(withFa.replacement.RB.ppg, 19);
  assert.equal(withFa.flex.RB, 1);
  const dup = ta.replacementPlan(teams, [{ key: "rb2", name: "RB2", pos: "RB", ppg: 50 }], lineup, 2);
  assert.equal(dup.replacement.RB.ppg, 12);
  const sent = [{ key: "ra", name: "RA", pos: "RB", ppg: 30, valuePos: "RB" }];
  const got = [{ key: "wr1", name: "WR1", pos: "WR", ppg: 25, valuePos: "WR" }];
  assert.equal(ta.playerVor(sent[0], plan), 18);
  assert.equal(ta.vorChange(sent, got, plan), (25 - 5) - (30 - 12));
});

test("the newer roster timestamp wins and a tie keeps the league site", function () {
  const older = { asOf: "2026-10-28 10:45 AM PT", roster: { QB: ["Old Name"] } };
  const newer = { asOf: "2026-10-30 4:16 PM PT", roster: { QB: ["New Name"] } };
  const picked = ta.pickFresher(older, newer);
  assert.equal(picked.from, "hq");
  assert.equal(picked.file.roster.QB[0], "New Name");
  assert.equal(ta.asOfLine(picked.time.label), "Rosters as of 2026-10-30 4:16 PM PT");
  const tie = ta.pickFresher(newer, { asOf: "2026-10-30 4:16 PM PT", roster: { QB: ["Live"] } });
  assert.equal(tie.from, "hq");
  assert.equal(tie.file.roster.QB[0], "Live");
  const localNewer = ta.pickFresher({ asOf: "2026-10-31 1:00 AM PT", roster: { QB: ["Local"] } }, newer);
  assert.equal(localNewer.from, "local");
  assert.equal(ta.rosterIndexRequest().remote, ta.HQ + "rosters/index.json");
  assert.equal(ta.rosterRequest("ultron").remote, ta.HQ + "rosters/ultron.json");
  assert.equal(ta.rosterRequest("../teams"), null);
});

test("the page is noindex and the war room nav is the only link", function () {
  const page = read("trade-analyzer.html");
  const home = read("index.html");
  assert.match(page, /name="robots" content="noindex, nofollow"/);
  assert.match(page, /name="googlebot" content="noindex, nofollow"/);
  assert.match(page, /name="referrer" content="no-referrer"/);
  assert.equal(/google-analytics|gtag\(|plausible|segment\.com|mixpanel/i.test(page), false);
  assert.match(page, /src="js\/trade-analyzer\.js"/);
  assert.match(home, /href="trade-analyzer\.html"/);
  ["trade-finder.html", "contingency.html", "idp.html", "draft.html", "draft-archive.html"].forEach(function (file) {
    assert.equal(read(file).includes("trade-analyzer.html"), false, file);
  });
});
