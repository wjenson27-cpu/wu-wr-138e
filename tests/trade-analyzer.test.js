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
