const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const board = require("../js/robot-scoreboard.js");

const root = path.join(__dirname, "..");
const NAME = "B" + "ill";
const LAST = "J" + "enson";

function round1(value) {
  return Math.round(value * 10) / 10;
}

function publishedWeeks() {
  const dir = path.join(root, "data", "robot-vs-bill");
  const seasonDoc = JSON.parse(fs.readFileSync(path.join(dir, "season.json"), "utf8"));
  const weeks = fs.readdirSync(dir)
    .filter(function (name) { return /^w\d\d\.json$/.test(name); })
    .map(function (name) {
      return {
        name: name,
        doc: JSON.parse(fs.readFileSync(path.join(dir, name), "utf8"))
      };
    })
    .sort(function (a, b) { return a.doc.week - b.doc.week; });
  return { season: seasonDoc, weeks: weeks };
}

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

test("published weeks are pending with null points or final with numeric points", function () {
  const published = publishedWeeks();
  const seasonDoc = published.season;
  const weeks = published.weeks;
  assert.ok(weeks.length >= 1);
  const byWeek = {};
  weeks.forEach(function (item) {
    const doc = item.doc;
    assert.equal(typeof doc.week, "number");
    assert.ok(doc.week >= board.FIRST_WEEK);
    assert.equal(item.name, "w" + String(doc.week).padStart(2, "0") + ".json");
    byWeek[doc.week] = doc;
    const rows = (doc.robot || []).concat(doc.actual || []);
    if (doc.status === "pending") {
      rows.forEach(function (row) { assert.equal(row.points, null, item.name); });
      assert.equal(doc.totals.robot, null, item.name);
      assert.equal(doc.totals.eddies, null, item.name);
      assert.equal(doc.margin, null, item.name);
      assert.equal(doc.result, null, item.name);
      assert.equal(doc.winner, null, item.name);
      (doc.decisions || []).forEach(function (decision) {
        assert.equal(decision.swing, null, item.name);
      });
      return;
    }
    assert.equal(doc.status, "final", item.name);
    assert.equal(doc.robot.length, 14, item.name);
    assert.equal(doc.actual.length, 14, item.name);
    assert.equal(typeof doc.robotLockedAt, "string", item.name);
    rows.forEach(function (row) {
      assert.equal(typeof row.points, "number", item.name);
      assert.equal(Number.isFinite(row.points), true, item.name);
    });
    const robotTotal = round1(doc.robot.reduce(function (sum, row) { return sum + row.points; }, 0));
    const eddiesTotal = round1(doc.actual.reduce(function (sum, row) { return sum + row.points; }, 0));
    assert.equal(doc.totals.robot, robotTotal, item.name);
    assert.equal(doc.totals.eddies, eddiesTotal, item.name);
    assert.equal(doc.margin, round1(robotTotal - eddiesTotal), item.name);
    if (doc.margin > 0) {
      assert.equal(doc.result, "W", item.name);
      assert.equal(doc.winner, "Robot", item.name);
    } else if (doc.margin < 0) {
      assert.equal(doc.result, "L", item.name);
      assert.equal(doc.winner, "Eddies", item.name);
    } else {
      assert.equal(doc.result, "T", item.name);
      assert.equal(doc.winner, "tie", item.name);
    }
    const swing = round1((doc.decisions || []).reduce(function (sum, decision) {
      assert.equal(typeof decision.swing, "number", item.name);
      assert.equal(decision.swing, round1(decision.robotPoints - decision.eddiesPoints), item.name);
      return sum + decision.swing;
    }, 0));
    assert.equal(swing, doc.margin, item.name);
  });

  const week9 = byWeek[9];
  assert.ok(week9, "week 9 is published");
  assert.equal(week9.status, "final");
  assert.equal(typeof week9.robotLockedAt, "string");
  assert.equal(week9.robot.length, 14);
  week9.robot.concat(week9.actual).forEach(function (row) {
    assert.equal(typeof row.points, "number");
  });

  const finals = weeks.map(function (item) { return item.doc; }).filter(function (doc) {
    return doc.status === "final";
  });
  const wins = finals.filter(function (doc) { return doc.result === "W"; }).length;
  const losses = finals.filter(function (doc) { return doc.result === "L"; }).length;
  const ties = finals.filter(function (doc) { return doc.result === "T"; }).length;
  assert.equal(seasonDoc.record.wins, wins);
  assert.equal(seasonDoc.record.losses, losses);
  assert.equal(seasonDoc.record.ties, ties);
  assert.equal(seasonDoc.record.label, wins + "-" + losses + "-" + ties);
  assert.equal(seasonDoc.firstWeek, 9);
  assert.deepEqual(seasonDoc.sides, { robot: "Robot", eddies: "Eddies" });
  const robotPts = finals.length ? round1(finals.reduce(function (sum, doc) { return sum + doc.totals.robot; }, 0)) : 0;
  const eddiesPts = finals.length ? round1(finals.reduce(function (sum, doc) { return sum + doc.totals.eddies; }, 0)) : 0;
  assert.equal(seasonDoc.points.robot, robotPts);
  assert.equal(seasonDoc.points.eddies, eddiesPts);
  assert.equal(seasonDoc.points.margin, round1(robotPts - eddiesPts));
  assert.deepEqual(seasonDoc.weeks.map(function (row) { return row.week; }), weeks.map(function (item) { return item.doc.week; }));
  seasonDoc.weeks.forEach(function (summary, index) {
    const item = weeks[index];
    const doc = item.doc;
    const locked = !!(doc.robotLockedAt || (doc.robot && doc.robot.length));
    assert.equal(summary.file, item.name);
    assert.equal(summary.status, doc.status);
    assert.equal(summary.locked, locked);
    assert.equal(summary.result, doc.result);
    assert.equal(summary.winner, doc.winner);
    assert.equal(summary.robotPoints, doc.totals.robot);
    assert.equal(summary.eddiesPoints, doc.totals.eddies);
    assert.equal(summary.margin, doc.margin);
  });

  const docs = weeks.map(function (item) { return item.doc; });
  const model = board.buildModel(seasonDoc, docs);
  const current = docs[docs.length - 1];
  assert.equal(model.recordLabel, seasonDoc.record.label);
  assert.equal(model.wins, wins);
  assert.equal(model.losses, losses);
  assert.equal(model.ties, ties);
  assert.equal(model.current.week, current.week);
  assert.equal(model.current.locked, !!(current.robotLockedAt || current.robot.length));
  assert.equal(model.history.length, Math.max(0, docs.length - 1));
  if (current.status === "final") {
    assert.equal(model.current.pointsCaption, "Final");
    assert.equal(model.current.rows.length, current.robot.length);
    model.current.rows.forEach(function (row) {
      assert.notEqual(row.robot.pointsLabel, "\u2014");
      if (row.eddies) assert.notEqual(row.eddies.pointsLabel, "\u2014");
    });
  } else if (!model.current.locked) {
    assert.equal(model.current.statusLabel, "Not yet locked");
    assert.equal(model.current.rows.length, 0);
  } else {
    assert.equal(model.current.pointsCaption, "Live");
    assert.equal(model.current.rows[0].robot.pointsLabel, "\u2014");
  }

  const html = board.render(model);
  assert.equal(html.includes("<table"), false);
  assert.equal(html.includes(NAME), false);
  assert.match(html, new RegExp("W " + wins + " · L " + losses + " · T " + ties));
  if (!model.current.locked) {
    assert.match(html, /not locked a lineup/i);
    assert.match(html, /No finished weeks yet/);
  } else if (current.status === "final") {
    assert.match(html, /Final/);
    assert.equal(/not locked a lineup/i.test(html), false);
    if (docs.length === 1) assert.match(html, /Earlier weeks are not on this board/);
  } else {
    assert.match(html, /Points stay blank until this week is final/);
  }
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

  const live = board.buildModel({
    record: { wins: 0, losses: 0, ties: 0, label: "0-0-0" },
    points: { robot: 0, eddies: 0, margin: 0 },
    weeks: [{ week: 9 }]
  }, [{
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
  fs.readdirSync(path.join(root, "data", "robot-vs-bill")).forEach(function (name) {
    if (!name.endsWith(".json")) return;
    const rel = "data/robot-vs-bill/" + name;
    if (files.indexOf(rel) < 0) files.push(rel);
  });
  files.forEach(function (rel) {
    const cleaned = scrub(fs.readFileSync(path.join(root, rel), "utf8"));
    assert.equal(new RegExp("\\b" + NAME + "\\b", "i").test(cleaned), false, rel);
    assert.equal(cleaned.toLowerCase().includes(LAST.toLowerCase()), false, rel);
  });
  fs.readdirSync(path.join(root, "data", "robot-vs-bill")).filter(function (name) {
    return name.endsWith(".json");
  }).map(function (name) {
    return "data/robot-vs-bill/" + name;
  }).forEach(function (rel) {
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
