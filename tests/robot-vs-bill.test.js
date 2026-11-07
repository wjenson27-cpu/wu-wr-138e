const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const board = require("../js/robot-scoreboard.js");

const root = path.join(__dirname, "..");
const season = require("../data/robot-vs-bill/season.json");
const week9 = require("../data/robot-vs-bill/w09.json");
const NAME = "B" + "ill";
const LAST = "J" + "enson";

function scrub(text) {
  return text.replace(/robot-vs-bill/g, "FEATURE").replace(/score_robot_vs_bill/g, "SCORE");
}

test("Week 9 lock time is labeled in PT", function () {
  assert.equal(board.formatPt("2026-11-05T09:30:00-08:00"), "Nov 5, 9:30 AM PT");
  assert.equal(board.pointsLabel(null), "\u2014");
  assert.equal(board.pointsLabel(22), "22.0");
  assert.equal(board.marginLabel(-14), "\u221214.0");
  assert.equal(board.marginLabel(11), "+11.0");
  assert.equal(board.FIRST_WEEK, 9);
  assert.equal(board.SLOTS.length, 14);
  assert.deepEqual(board.SLOTS.slice(0, 4), ["QB", "RB", "WR", "TE"]);
});

test("Week 9 is locked pending with null points", function () {
  assert.equal(week9.week, 9);
  assert.equal(week9.status, "pending");
  assert.notEqual(week9.robotLockedAt, null);
  assert.equal(week9.robot.length, 14);
  assert.deepEqual(week9.actual, []);
  assert.equal(week9.totals.robot, null);
  assert.equal(week9.result, null);
  assert.equal(week9.robot.every(function (row) { return row.points === null; }), true);
  assert.equal(week9.window.start, "2026-11-05");
  assert.equal(week9.window.end, "2026-11-09");
  const model = board.buildModel(season, [week9]);
  assert.equal(model.recordLabel, "0-0-0");
  assert.equal(model.wins, 0);
  assert.equal(model.losses, 0);
  assert.equal(model.ties, 0);
  assert.equal(model.current.locked, true);
  assert.equal(model.current.status, "pending");
  assert.notEqual(model.current.status, "final");
  assert.equal(model.current.statusLabel, "Pending");
  assert.equal(model.current.pointsCaption, "Live");
  assert.equal(model.current.awaitingEddies, true);
  assert.equal(model.current.rows.length, 14);
  assert.equal(model.current.rows[0].robot.player, week9.robot[0].player);
  model.current.rows.forEach(function (row) {
    assert.equal(row.robot.pointsLabel, "\u2014");
    assert.equal(row.eddies, null);
  });
  assert.equal(model.history.length, 0);
  const html = board.render(model);
  assert.match(html, /Points stay blank until this week is final/);
  assert.match(html, /not in yet/i);
  assert.match(html, /No finished weeks yet/);
  assert.match(html, /W 0 · L 0 · T 0/);
  assert.equal(html.includes(week9.robot[0].player), true);
  assert.equal(html.includes("<table"), false);
  assert.equal(html.includes(NAME), false);
  assert.equal(html.toLowerCase().includes(LAST.toLowerCase()), false);
});

test("a final week highlights differing slots and a pending week leaves points blank", function () {
  const finalWeek = {
    week: 10,
    window: { start: "2026-11-12", end: "2026-11-16", label: "Nov 12–16" },
    status: "final",
    robotLockedAt: "2026-11-12T09:30:00-08:00",
    robot: [
      { slot: "QB", player: "Alex Example", pos: "QB", team: "CIN", points: 20 },
      { slot: "RB", player: "Riley Example", pos: "RB", team: "ATL", points: 8 }
    ],
    actual: [
      { slot: "QB", player: "Alex Example", pos: "QB", team: "CIN", points: 20 },
      { slot: "RB", player: "Casey Example", pos: "RB", team: "DAL", points: 14 }
    ],
    totals: { robot: 28, eddies: 34 },
    margin: -6,
    result: "L",
    winner: "Eddies",
    decisions: [{
      slot: "RB",
      index: 1,
      robotPlayer: "Riley Example",
      robotPos: "RB",
      robotTeam: "ATL",
      robotPoints: 8,
      eddiesPlayer: "Casey Example",
      eddiesPos: "RB",
      eddiesTeam: "DAL",
      eddiesPoints: 14,
      swing: -6
    }]
  };
  const pending = {
    week: 9,
    window: { label: "Nov 5–9" },
    status: "final",
    result: "W",
    robotLockedAt: "2026-11-05T09:30:00-08:00",
    totals: { robot: 10, eddies: 4 },
    margin: 6,
    decisions: []
  };
  const model = board.buildModel({
    club: "Eagleridge Eddie's",
    record: { wins: 1, losses: 1, ties: 0, label: "1-1-0" },
    points: { robot: 38, eddies: 38, margin: 0 },
    weeks: [{ week: 9 }, { week: 10 }]
  }, [pending, finalWeek]);
  assert.equal(model.current.week, 10);
  assert.equal(model.current.pointsCaption, "Final");
  assert.equal(model.current.rows[0].differ, false);
  assert.equal(model.current.rows[1].differ, true);
  assert.equal(model.current.rows[1].swingLabel, "\u22126.0");
  assert.equal(model.history[0].week, 9);
  const html = board.render(model);
  assert.match(html, /rv-slot differ/);
  assert.match(html, /Differ/);
  assert.match(html, /Riley Example/);
  assert.match(html, /Casey Example/);
  assert.match(html, /Decisions that differed/);
  assert.match(html, /1-1-0/);
  assert.equal(html.includes("<table"), false);
  assert.equal((html.match(/Alex Example/g) || []).length >= 2, true);

  const live = board.buildModel(season, [{
    week: 9,
    status: "pending",
    robotLockedAt: "2026-11-05T09:30:00-08:00",
    window: { label: "Nov 5–9" },
    robot: [{ slot: "QB", player: "Alex Example", pos: "QB", team: "CIN", points: null }],
    actual: [],
    totals: { robot: null, eddies: null },
    decisions: []
  }]);
  assert.equal(live.current.pointsCaption, "Live");
  assert.equal(live.current.rows[0].robot.pointsLabel, "\u2014");
  assert.equal(live.current.awaitingEddies, true);
  const pendingHtml = board.render(live);
  assert.match(pendingHtml, /Points stay blank until this week is final/);
  assert.match(pendingHtml, /not in yet/i);
  assert.match(pendingHtml, /Live/);
});

test("the page and its data do not name the club's person or link from the home page", function () {
  const files = [
    "robot-vs-bill.html",
    "js/robot-scoreboard.js",
    "docs/robot-vs-bill.md",
    "data/robot-vs-bill/schema.json",
    "data/robot-vs-bill/season.json",
    "data/robot-vs-bill/w09.json",
    "scripts/lock_robot_lineup.py",
    "scripts/score_robot_vs_bill.py",
    "scripts/robot_vs_bill.py"
  ];
  files.forEach(function (rel) {
    const cleaned = scrub(fs.readFileSync(path.join(root, rel), "utf8"));
    assert.equal(new RegExp("\\b" + NAME + "\\b", "i").test(cleaned), false, rel);
    assert.equal(cleaned.toLowerCase().includes(LAST.toLowerCase()), false, rel);
  });
  ["data/robot-vs-bill/season.json", "data/robot-vs-bill/w09.json", "data/robot-vs-bill/schema.json"].forEach(function (rel) {
    const keys = [];
    (function walk(o) {
      if (!o || typeof o !== "object") return;
      if (Array.isArray(o)) {
        o.forEach(walk);
        return;
      }
      Object.keys(o).forEach(function (k) {
        keys.push(k);
        walk(o[k]);
      });
    })(JSON.parse(fs.readFileSync(path.join(root, rel), "utf8")));
    keys.forEach(function (k) {
      assert.equal(/^owners?$/i.test(k), false, rel + " " + k);
      assert.equal(/faab|waiver|pendingclaim|pendingtrade|^bids?$|^claims?$|^trades?$/i.test(k), false, rel + " " + k);
    });
  });
  const page = fs.readFileSync(path.join(root, "robot-vs-bill.html"), "utf8");
  assert.match(page, /Robot vs\. The Eddies/);
  assert.match(page, /cache:\s*"no-store"/);
  assert.equal(page.includes("<table"), false);
  const home = fs.readFileSync(path.join(root, "index.html"), "utf8");
  assert.equal(home.includes("robot-vs-bill.html"), false);
});
