const test = require("node:test");
const assert = require("node:assert/strict");
const vor = require("../js/vor.js");
const score = require("../js/scoring.js");
const draft = require("../js/draft-order.js");
const week = require("../js/week.js");
const scoring = require("../data/scoring.json");
const season2026 = require("../data/draft/2026.json");

const LINE = { QB: 1, RB: 1, WR: 1, TE: 1, RWT: 3, DL: 1, LB: 1, DB: 2, ID: 3 };

test("blend is 60% season and 40% last 3", function () {
  const b = vor.blendRate(10, 20);
  assert.equal(b.rate, 14);
  assert.equal(b.seasonWeight, 0.6);
  assert.equal(b.last3Weight, 0.4);
  assert.equal(b.usedLast3, true);
  const only = vor.blendRate(10, null);
  assert.equal(only.rate, 10);
  assert.equal(only.usedLast3, false);
  assert.equal(only.seasonWeight, 1);
});

test("flex spots go to the higher scores", function () {
  const ctx = vor.computeReplacement({
    teamCount: 1,
    scarcity: false,
    useWaiver: false,
    lineup: { QB: 0, RB: 1, WR: 1, TE: 1, RWT: 2, DL: 0, LB: 0, DB: 0, ID: 0 },
    rostered: [
      { name: "RB1", pos: "RB", ppg: 40 },
      { name: "RB2", pos: "RB", ppg: 30 },
      { name: "RB3", pos: "RB", ppg: 25 },
      { name: "WR1", pos: "WR", ppg: 15 },
      { name: "TE1", pos: "TE", ppg: 14 }
    ]
  });
  assert.equal(ctx.counts.RB, 3);
  assert.equal(ctx.replacement.RB.rostered, 25);
  assert.equal(ctx.replacement.RB.starters, 3);
  assert.equal(ctx.counts.WR, 1);
  assert.equal(ctx.replacement.WR.rostered, 15);
  assert.equal(ctx.counts.TE, 1);
});

test("waiver baseline wins when the wire is better than the last starter", function () {
  const ctx = vor.computeReplacement({
    teamCount: 2,
    scarcity: false,
    lineup: { QB: 0, RB: 0, WR: 0, TE: 0, RWT: 0, DL: 0, LB: 1, DB: 0, ID: 0 },
    rostered: [
      { name: "LB1", pos: "LB", ppg: 15 },
      { name: "LB2", pos: "LB", ppg: 11 }
    ],
    freeAgents: [
      { player: "Wire", pos: "LB", fpg: 12, last3Fpg: 12, rosteredPct: 0 },
      { player: "Owned", pos: "LB", fpg: 40, last3Fpg: 40, rosteredPct: 100 }
    ]
  });
  assert.equal(ctx.replacement.LB.source, "waiver");
  assert.equal(ctx.replacement.LB.rostered, 11);
  assert.equal(ctx.replacement.LB.waiver, 12);
  assert.equal(ctx.replacement.LB.used, 12);
  assert.equal(ctx.vorFor(13, "LB"), 1);
});

test("a stale or closed wire is ignored", function () {
  const ctx = vor.computeReplacement({
    teamCount: 2,
    scarcity: false,
    useWaiver: false,
    lineup: { QB: 0, RB: 0, WR: 0, TE: 0, RWT: 0, DL: 0, LB: 1, DB: 0, ID: 0 },
    rostered: [
      { name: "LB1", pos: "LB", ppg: 15 },
      { name: "LB2", pos: "LB", ppg: 11 }
    ],
    freeAgents: [{ player: "Wire", pos: "LB", fpg: 14, rosteredPct: 0 }]
  });
  assert.equal(ctx.replacement.LB.source, "rostered");
  assert.equal(ctx.replacement.LB.used, 11);
});

test("steep positions get a higher scarcity premium than a flat pool", function () {
  const ctx = vor.computeReplacement({
    teamCount: 2,
    lineup: { QB: 0, RB: 0, WR: 0, TE: 1, RWT: 0, DL: 0, LB: 0, DB: 1, ID: 0 },
    rostered: [
      { name: "TE1", pos: "TE", ppg: 25 },
      { name: "TE2", pos: "TE", ppg: 20 },
      { name: "TE3", pos: "TE", ppg: 8 },
      { name: "TE4", pos: "TE", ppg: 7 },
      { name: "DB1", pos: "DB", ppg: 20 },
      { name: "DB2", pos: "DB", ppg: 15 },
      { name: "DB3", pos: "DB", ppg: 14 },
      { name: "DB4", pos: "DB", ppg: 13 }
    ],
    freeAgents: []
  });
  const te = ctx.priced.find(function (p) { return p.name === "TE1"; });
  const db = ctx.priced.find(function (p) { return p.name === "DB1"; });
  assert.ok(ctx.replacement.TE.scarcity > ctx.replacement.DB.scarcity);
  assert.equal(ctx.replacement.TE.used, 20);
  assert.equal(ctx.replacement.DB.used, 15);
  assert.ok(te.vor > db.vor);
  assert.equal(te.rank, 1);
  assert.equal(db.rank, 1);
});

test("lineup optimizer skips IR, ignores a pure bench add, and pays for filling a hole", function () {
  const lineup = { QB: 1, RB: 1, WR: 1, TE: 1, RWT: 1, DL: 0, LB: 1, DB: 0, ID: 0 };
  const roster = [
    { name: "QB", pos: "QB", ppg: 20 },
    { name: "RB1", pos: "RB", ppg: 18 },
    { name: "RB2", pos: "RB", ppg: 12 },
    { name: "WR", pos: "WR", ppg: 15 },
    { name: "TE", pos: "TE", ppg: 11 },
    { name: "LB", pos: "LB", ppg: 16 }
  ];
  const before = vor.optimizeLineup(roster, lineup);
  assert.equal(before.total, 92);
  const bench = vor.optimizeLineup(roster.concat([{ name: "RB3", pos: "RB", ppg: 9 }]), lineup);
  assert.equal(bench.total, 92);
  assert.equal(bench.slotOf.RB3, undefined);
  const hole = roster.filter(function (p) { return p.pos !== "LB"; });
  const open = vor.optimizeLineup(hole, lineup);
  assert.equal(open.total, 76);
  const filled = vor.optimizeLineup(hole.concat([{ name: "NewLB", pos: "LB", ppg: 14 }]), lineup);
  assert.equal(filled.total, 90);
  assert.equal(Math.round((filled.total - open.total) * 10) / 10, 14);
  const ir = vor.optimizeLineup([
    { name: "IRB", pos: "RB", ppg: 40, ir: true },
    { name: "OK", pos: "RB", ppg: 10 }
  ], { QB: 0, RB: 1, WR: 0, TE: 0, RWT: 0, DL: 0, LB: 0, DB: 0, ID: 0 });
  assert.equal(ir.total, 10);
  assert.equal(ir.slotOf.OK, "RB");
  assert.equal(ir.slotOf.IRB, undefined);
  const reserve = vor.optimizeLineup([
    { name: "Hall", pos: "RB", ppg: 30, ineligible: true },
    { name: "OK2", pos: "RB", ppg: 10 }
  ], { QB: 0, RB: 1, WR: 0, TE: 0, RWT: 0, DL: 0, LB: 0, DB: 0, ID: 0 });
  assert.equal(reserve.total, 10);
  assert.equal(reserve.slotOf.Hall, undefined);
});

test("freshness windows", function () {
  const now = new Date("2026-10-10T00:00:00Z");
  assert.equal(vor.isStale("2026-10-01T00:00:00Z", 3, now), true);
  assert.equal(vor.isStale("2026-10-08T00:00:00Z", 3, now), false);
  assert.equal(vor.isStale("2026-10-01", 7, now), true);
  assert.equal(vor.isStale("2026-10-08", 7, now), false);
  assert.equal(vor.isStale("not-a-date", 3, now), true);
});

test("TE premium and IDP scoring", function () {
  const te = score.scoreLine({ receptions: 6, recYds: 70 }, "TE", scoring);
  const wr = score.scoreLine({ receptions: 6, recYds: 70 }, "WR", scoring);
  assert.equal(te, 16);
  assert.equal(wr, 13);
  assert.ok(te > wr);
  const lb = score.scoreLine({ solo: 7, assisted: 3 }, "LB", scoring);
  assert.equal(lb, 23);
  assert.equal(score.scoreLine({ pd: 1 }, "DL", scoring), 4);
  assert.equal(score.scoreLine({ pd: 1 }, "DB", scoring), 3);
  assert.equal(score.scoreLine({ sacks: 1 }, "DL", scoring), 6);
});

test("2026 snake gives Bill the archived pick numbers", function () {
  assert.deepEqual(
    draft.userPicks(season2026),
    [10, 21, 32, 47, 66, 75, 94, 105, 122, 131, 150, 159, 178, 187, 206, 215]
  );
});

test("a straight snake follows the slot", function () {
  const season = {
    rounds: 2,
    straightSnake: true,
    user: { owner: "Bill" },
    teams: [
      { name: "A", owner: "Ann", short: "A" },
      { name: "B", owner: "Bill", short: "B" },
      { name: "C", owner: "Cam", short: "C" },
      { name: "D", owner: "Dee", short: "D" }
    ],
    pickSwaps: [{ rounds: [1], from: "Bill", to: "Ann", on: "original" }]
  };
  assert.deepEqual(draft.userPicks(season), [2, 7]);
});

test("Fantrax week and Wednesday waiver clock", function () {
  assert.equal(week.fantraxWeek(new Date("2026-09-10T17:00:00Z")), 1);
  assert.equal(week.fantraxWeek(new Date("2026-10-10T01:00:00Z")), 5);
  assert.equal(week.fantraxWeek(new Date("2026-10-15T07:30:00Z")), 6);
  const friday = new Date("2026-10-10T01:00:00Z");
  assert.equal(week.nextWaiver(friday).toISOString(), "2026-10-14T16:00:00.000Z");
  const wedMorning = new Date("2026-10-14T15:00:00Z");
  assert.equal(week.nextWaiver(wedMorning).toISOString(), "2026-10-14T16:00:00.000Z");
  const wedAfter = new Date("2026-10-14T17:00:00Z");
  assert.equal(week.nextWaiver(wedAfter).toISOString(), "2026-10-21T16:00:00.000Z");
});

test("league lineup constants match the 14-team IDP roster", function () {
  assert.equal(LINE.QB * 14, 14);
  assert.equal(LINE.RWT * 14, 42);
  assert.equal(LINE.DB * 14, 28);
  assert.equal(LINE.ID * 14, 42);
  assert.equal(scoring.roster.startingLineup.TE, 1);
  assert.equal(scoring.offense.receiving.receptionTE, 1.5);
});
