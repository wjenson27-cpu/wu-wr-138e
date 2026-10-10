const test = require("node:test");
const assert = require("node:assert/strict");
const score = require("../js/scoring.js");
const math = require("../js/rankings-math.js");
const scoring = require("../data/scoring.json");

test("passing and the 300-yard bonus rescore from a stat line", function () {
  const pts = score.scoreLine({ passYds: 300, passTd: 2, interceptions: 1 }, "QB", scoring);
  assert.equal(pts, 27);
});

test("tight end premium and first downs come from the stat line", function () {
  const te = score.scoreLine({ receptions: 6, recYds: 70, teFirstDowns: 4 }, "TE", scoring);
  const wr = score.scoreLine({ receptions: 6, recYds: 70, teFirstDowns: 4 }, "WR", scoring);
  assert.equal(te, 18);
  assert.equal(wr, 13);
});

test("fumbles, returns, sacks, and quarterback hits use the league table", function () {
  assert.equal(score.scoreLine({ fumbleLost: 1 }, "RB", scoring), -3);
  assert.equal(score.scoreLine({ krYds: 20, prYds: 10 }, "WR", scoring), 3);
  assert.equal(score.scoreLine({ sacks: 1, qbHit: 2, forcedFumble: 1 }, "DL", scoring), 11);
});

test("Sleeper and ESPN stat ids become the same WU line", function () {
  const fromSleeper = math.sleeperLine({
    pass_yd: 200, pass_td: 1, pass_int: 0, rush_yd: 20, rush_td: 0, rush_att: 4,
    idp_tkl_solo: 0
  });
  const fromEspn = math.espnLine({ 3: 200, 4: 1, 20: 0, 24: 20, 25: 0, 23: 4 });
  assert.equal(score.scoreLine(fromSleeper, "QB", scoring), score.scoreLine(fromEspn, "QB", scoring));
  assert.equal(score.scoreLine(fromSleeper, "QB", scoring), 16);
});

test("a projection consensus ignores a bye that only has recent points", function () {
  const hot = math.projectionConsensus(22.1, 19.5, 33.6, false);
  assert.equal(hot.pts, 20.8);
  assert.equal(hot.floor, 19.5);
  assert.equal(hot.ceil, 33.6);
  const bye = math.projectionConsensus(null, null, 27, true);
  assert.equal(bye.pts, null);
  assert.equal(bye.floor, null);
  const formOnly = math.projectionConsensus(null, null, 14, false);
  assert.equal(formOnly.pts, null);
  assert.equal(formOnly.floor, null);
});

test("consensus is the average, with the low and high kept", function () {
  const c = math.consensus([10, 14, null, 12]);
  assert.equal(c.n, 3);
  assert.equal(c.pts, 12);
  assert.equal(c.floor, 10);
  assert.equal(c.ceil, 14);
  assert.deepEqual(math.consensus([null, ""]), { pts: null, floor: null, ceil: null, n: 0 });
});

test("positional rank follows WU points, and a wide gap is a split", function () {
  const rows = [
    { key: "a", name: "A", pts: 20 },
    { key: "b", name: "B", pts: 10 },
    { key: "c", name: "C", pts: 15 }
  ];
  const ranks = math.ordinalRanks(rows, function (row) { return row.pts; });
  assert.deepEqual(ranks, { a: 1, c: 2, b: 3 });
  assert.equal(math.isSplit([1, 4], [18, 19], 12), false);
  assert.equal(math.isSplit([2, 18], [14, 15], 12), true);
  assert.equal(math.isSplit([3, 5], [8, 15], 12), true);
  assert.equal(math.isSplit([1, 9], [20, 22], 8), true);
});

test("home spread and total become team implied points", function () {
  const line = math.impliedTeamTotals(-7.5, 41.5);
  assert.equal(line.home, 24.5);
  assert.equal(line.away, 17);
  assert.equal(math.impliedTeamTotals(null, 40), null);
});

test("matchup grade ranks a generous defense above a stingy one", function () {
  const allowed = [10, 12, 14, 16, 18, 22, 28];
  const soft = math.matchupGrade(28, allowed);
  const hard = math.matchupGrade(10, allowed);
  assert.equal(soft.grade, "A");
  assert.equal(soft.place, 1);
  assert.equal(hard.grade, "F");
  assert.equal(hard.place, 7);
  assert.equal(math.matchupGrade(14, [1, 2]), null);
});
