const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");

require("../js/trade-analyzer.js");
const tc = require("../js/trade-center.js");

const root = path.join(__dirname, "..");

function read(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8");
}

function load(rel) {
  return JSON.parse(read(rel));
}

const tradesDoc = load("data/hq/trades.json");
const values = load("data/player-values.json");
const teams = load("data/hq/teams.json").teams;
const freeAgents = load("data/free-agents.json");
const rosters = {};
teams.forEach(function (team) {
  rosters[team.id] = load("data/hq/rosters/" + team.id + ".json");
});

function report() {
  return tc.seasonReport(tradesDoc, {
    teams: teams,
    rosters: rosters,
    values: values,
    freeAgents: freeAgents
  });
}

test("a score of 50 is an even deal and the letter bands sit on that center", function () {
  assert.equal(tc.SCORE_SCALE, 60);
  assert.equal(tc.scoreFromNet(0), 50);
  assert.equal(tc.scoreFromNet(60), Math.round(50 + 50 * Math.tanh(1)));
  assert.equal(tc.scoreFromNet(-60), Math.round(50 + 50 * Math.tanh(-1)));
  assert.equal(tc.scoreFromNet(1000), 100);
  assert.equal(tc.scoreFromNet(-1000), 0);
  assert.equal(tc.scoreFromNet(null), null);
  assert.equal(tc.letterGrade(100), "A");
  assert.equal(tc.letterGrade(85), "A");
  assert.equal(tc.letterGrade(84), "B");
  assert.equal(tc.letterGrade(70), "B");
  assert.equal(tc.letterGrade(69), "C");
  assert.equal(tc.letterGrade(50), "C");
  assert.equal(tc.letterGrade(45), "C");
  assert.equal(tc.letterGrade(44), "D");
  assert.equal(tc.letterGrade(25), "D");
  assert.equal(tc.letterGrade(24), "F");
  assert.equal(tc.letterGrade(0), "F");
});

test("FAAB moves both the rest-of-season grade and the VOR net", function () {
  const book = tc.valueBook({
    weeksRemaining: 10,
    byeWeeksAssumedLeft: 1,
    faab: { pointsPerDollar: 0.744 },
    players: [
      { name: "Keeper Back", position: "RB", ppg: 22, value: 90 },
      { name: "Spare Back", position: "RB", ppg: 14, value: 18 }
    ]
  });
  const plan = {
    replacement: { RB: { ppg: 12 }, WR: { ppg: 12 }, QB: { ppg: 18 }, TE: { ppg: 10 }, DL: { ppg: 8 }, LB: { ppg: 10 }, DB: { ppg: 10 } }
  };
  const directory = {
    byId: { eddies: { id: "eddies", name: "Eagle Ridge Eddies" }, saltese: { id: "saltese", name: "Saltese Slamm" } },
    byKey: { "eagle ridge eddies": "eddies", "eagleridge eddies": "eddies", "saltese slamm": "saltese" }
  };
  const trade = tc.gradeTrade({
    date: "2026-10-01",
    status: "completed",
    official: true,
    teamA: "Eagle Ridge Eddies (Bill)",
    teamB: "Saltese Slamm (Larry)",
    givesA: ["Keeper Back (RB)", "$10 FAAB"],
    givesB: ["Spare Back (RB)"]
  }, book, plan, directory);
  assert.equal(trade.sides[0].name, "Eagleridge Eddie's");
  assert.equal(trade.sides[1].name, "Saltese Slamm");
  assert.equal(JSON.stringify(trade).includes("Bill"), false);
  assert.equal(JSON.stringify(trade).includes("Larry"), false);
  const faabRos = 10 * 0.744;
  const faabVor = faabRos / 9;
  assert.ok(Math.abs(trade.sides[0].netRos - ((18) - (90 + faabRos))) < 1e-9);
  assert.ok(Math.abs(trade.sides[0].netVor - ((14 - 12) - ((22 - 12) + faabVor))) < 1e-9);
  assert.equal(trade.sides[0].score + trade.sides[1].score >= 99, true);
  assert.equal(trade.sides[0].score + trade.sides[1].score <= 101, true);
  assert.equal(trade.winner.name, "Saltese Slamm");
  assert.equal(trade.winner.text, "Saltese Slamm wins");
  assert.equal(trade.sides[0].grade, tc.letterGrade(trade.sides[0].score));
});

test("an even cash swap grades 50 and a missing player is not scored as zero", function () {
  const book = tc.valueBook({
    weeksRemaining: 9,
    byeWeeksAssumedLeft: 0,
    faab: { pointsPerDollar: 1 },
    players: [{ name: "Priced Back", position: "RB", ppg: 20, value: 40 }]
  });
  const plan = { replacement: { RB: { ppg: 10 } } };
  const directory = {
    byId: { a: { id: "a", name: "Alpha" }, b: { id: "b", name: "Beta" } },
    byKey: { alpha: "a", beta: "b" }
  };
  const even = tc.gradeTrade({
    status: "completed",
    official: true,
    date: "2026-09-01",
    teamA: "Alpha",
    teamB: "Beta",
    givesA: ["$8 FAAB"],
    givesB: ["$8 FAAB"]
  }, book, plan, directory);
  assert.equal(even.sides[0].score, 50);
  assert.equal(even.sides[0].grade, "C");
  assert.equal(even.winner.kind, "even");
  assert.equal(even.sides[0].netVor, 0);
  const picks = tc.gradeTrade({
    status: "completed",
    official: true,
    date: "2026-08-28",
    teamA: "Alpha",
    teamB: "Beta",
    givesA: ["5 draft picks (swap package)"],
    givesB: ["5 draft picks (swap package)"]
  }, book, plan, directory);
  assert.equal(picks.winner.text, "Even");
  assert.equal(picks.sides[0].score, 50);
  assert.equal(picks.sides[0].unpriced, true);
  const missing = tc.gradeTrade({
    status: "completed",
    official: true,
    date: "2026-09-02",
    teamA: "Alpha",
    teamB: "Beta",
    givesA: ["Nobody Special (RB)"],
    givesB: ["Priced Back (RB)"]
  }, book, plan, directory);
  assert.equal(missing.complete, false);
  assert.equal(missing.winner.text, "Value missing");
  assert.equal(missing.sides[0].score, null);
  assert.equal(missing.sides[1].netVor, null);
});

test("the leaderboard sums net VOR, counts trades, and averages the grade", function () {
  const graded = [
    {
      complete: true,
      sides: [
        { id: "eddies", name: "Eagleridge Eddie's", netVor: 4, score: 80 },
        { id: "ttab", name: "TTAB", netVor: -4, score: 20 }
      ]
    },
    {
      complete: true,
      sides: [
        { id: "eddies", name: "Eagleridge Eddie's", netVor: 2, score: 60 },
        { id: "saltese", name: "Saltese Slamm", netVor: -2, score: 40 }
      ]
    },
    {
      complete: false,
      sides: [
        { id: "eddies", name: "Eagleridge Eddie's", netVor: null, score: null },
        { id: "ultron", name: "Ultron", netVor: null, score: null }
      ]
    }
  ];
  const board = tc.leaderboard(graded, [
    { id: "eddies", name: "Eagle Ridge Eddies" },
    { id: "ttab", name: "Towner Top Aga Bottom" },
    { id: "saltese", name: "Saltese Slamm" },
    { id: "goats", name: "Valley Old Goats" }
  ]);
  assert.deepEqual(board.map(function (row) { return row.name; }), [
    "Eagleridge Eddie's",
    "Valley Old Goats",
    "Saltese Slamm",
    "TTAB",
    "Ultron"
  ]);
  assert.equal(board[4].netVor, null);
  assert.equal(board[4].trades, 1);
  const eddies = board[0];
  assert.equal(eddies.trades, 3);
  assert.equal(eddies.netVor, 6);
  assert.equal(eddies.avgScore, 70);
  assert.equal(eddies.avgGrade, "B");
  assert.equal(board[1].trades, 0);
  assert.equal(board[1].netVor, 0);
  assert.equal(board[1].avgGrade, "");
  const sum = board.reduce(function (total, row) { return total + (row.netVor || 0); }, 0);
  assert.equal(sum, 0);
  assert.equal(board.find(function (row) { return row.id === "ttab"; }).name, "TTAB");
});

test("only official completed trades are graded, and the source stamp is Pacific time", function () {
  assert.equal(tc.isCompleted({ status: "completed", official: true, date: "2026-10-01" }, 2026), true);
  assert.equal(tc.isCompleted({ status: "completed", official: false, date: "2026-08-30" }, 2026), false);
  assert.equal(tc.isCompleted({ status: "pending", official: true, date: "2026-10-01" }, 2026), false);
  assert.equal(tc.isCompleted({ status: "completed", pending: true, official: true, date: "2026-10-01" }, 2026), false);
  assert.equal(tc.isCompleted({ status: "completed", official: true, date: "2025-12-01" }, 2026), false);
  assert.equal(tc.formatSourceStamp("2026-10-30 4:16 PM PT"), "2026-10-30 4:16 PM PT");
  assert.equal(tc.formatSourceStamp("2026-10-28T10:45:00-07:00"), "2026-10-28 10:45 AM PT");
  assert.equal(tc.formatSourceStamp("2026-10-30"), "2026-10-30 PT");
  assert.match(tc.sourceStamp(tradesDoc), /PT$/);
  const baked = report();
  const official = tradesDoc.trades.filter(function (trade) {
    return trade.status === "completed" && trade.official !== false;
  });
  assert.equal(baked.count, official.length);
  assert.equal(baked.count, 36);
  assert.equal(baked.handshakesExcluded, 4);
  assert.equal(baked.pendingExcluded, 0);
  assert.equal(baked.sourceFile, "data/hq/trades.json");
  assert.equal(baked.asOf, "2026-10-30 4:16 PM PT");
  assert.equal(baked.trades.some(function (trade) { return !trade.complete; }), false);
  const names = JSON.stringify(baked.trades) + JSON.stringify(baked.leaderboard);
  assert.equal(names.includes("Bill"), false);
  assert.equal(names.includes("Eagle Ridge Eddies"), false);
  assert.equal(names.includes("Towner Top Aga Bottom"), false);
  assert.equal(names.includes("Eagleridge Eddie's"), true);
  assert.equal(names.includes("TTAB"), true);
  const vorSum = baked.leaderboard.reduce(function (total, row) { return total + row.netVor; }, 0);
  assert.ok(Math.abs(vorSum) < 1e-6);
  const tradeSum = baked.leaderboard.reduce(function (total, row) { return total + row.trades; }, 0);
  assert.equal(tradeSum, 72);
  for (let i = 1; i < baked.leaderboard.length; i++) {
    assert.ok(baked.leaderboard[i - 1].netVor >= baked.leaderboard[i].netVor);
  }
  assert.equal(baked.lopsided.length, 3);
  baked.lopsided.forEach(function (trade) {
    assert.equal(trade.winner.kind, "win");
    assert.ok(trade.sides[0].grade);
    assert.ok(trade.sides[1].grade);
  });
  const page = tc.render(baked);
  assert.match(page, /Source: data\/hq\/trades\.json · as of 2026-10-30 4:16 PM PT/);
  assert.match(page, /not each player's value on the day of the trade/);
  assert.match(page, /rest-of-season/);
  assert.equal(page.includes("Bill"), false);
  assert.equal(page.includes("pending"), false);
  assert.equal(/\$\d+ bid/i.test(page), false);
});

test("the trade center stays on the war room page", function () {
  const home = read("index.html");
  assert.match(home, /data-p="pcenter"/);
  assert.match(home, /id="pcenter"/);
  assert.match(home, /src="js\/trade-center\.js"/);
  ["trade-analyzer.html", "trade-finder.html", "contingency.html", "idp.html", "draft.html", "draft-archive.html"].forEach(function (file) {
    assert.equal(read(file).includes("trade-center"), false, file);
    assert.equal(read(file).includes("pcenter"), false, file);
  });
});
