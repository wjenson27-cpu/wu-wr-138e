const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const sunday = require("../js/sunday.js");

const root = path.join(__dirname, "..");
const live = require("../data/sunday/live.json");
const config = require("../data/sunday/config.json");
const parlay = require("../data/td-parlay.json");

test("win probability is a normal approximation from projections and remaining points", function () {
  assert.equal(sunday.winProbability(10, 10, 0, 0), 0.5);
  assert.equal(sunday.winProbability(11, 10, 0, 0), 1);
  assert.equal(sunday.winProbability(9, 10, 0, 0), 0);
  assert.equal(sunday.normalCdf(0), 0.5);
  const z = 10 / Math.sqrt(40);
  const ahead = sunday.winProbability(100, 90, 20, 20);
  assert.ok(Math.abs(ahead - sunday.normalCdf(z)) < 1e-12);
  assert.ok(ahead > 0.94 && ahead < 0.95);
  const behind = sunday.winProbability(90, 100, 20, 20);
  assert.ok(Math.abs(ahead + behind - 1) < 1e-9);
  assert.equal(sunday.winProbability(5, 5, -4, -8), 0.5);
  const tiedFinals = sunday.winProbability(80, 70, 10, 20);
  assert.ok(Math.abs(tiedFinals - 0.5) < 1e-12);
});

test("STALE starts once data is more than 45 minutes old", function () {
  const updated = "2026-10-31T12:40:00-07:00";
  const t = Date.parse(updated);
  assert.equal(sunday.STALE_MS, 45 * 60 * 1000);
  assert.equal(sunday.REFRESH_MS, 5 * 60 * 1000);
  assert.equal(sunday.isStale(updated, t + 44 * 60 * 1000), false);
  assert.equal(sunday.isStale(updated, t + 45 * 60 * 1000), false);
  assert.equal(sunday.isStale(updated, t + 45 * 60 * 1000 + 1), true);
  assert.equal(sunday.isStale(updated, t + 46 * 60 * 1000), true);
  assert.equal(sunday.isStale("", t), true);
  assert.equal(sunday.isStale(null, t), true);
  assert.equal(sunday.isStale("not-a-time", t), true);
  const written = Date.parse(live.updatedAt);
  const fresh = sunday.buildModel(live, parlay, config, written + 10 * 60 * 1000);
  const old = sunday.buildModel(live, parlay, config, written + 46 * 60 * 1000);
  assert.equal(fresh.stale, false);
  assert.equal(old.stale, true);
  assert.match(sunday.formatPt(updated), /Oct 31, 12:40 PM PT/);
});

test("the sample Sunday card is the featured club, still-alive parlay, and two lock alerts", function () {
  const t = Date.parse(live.updatedAt) + 5 * 60 * 1000;
  const model = sunday.buildModel(live, parlay, config, t);
  assert.equal(model.ok, true);
  assert.equal(config.featuredTeam, "eddies");
  assert.equal(model.featured.name, "Eagleridge Eddie's");
  assert.equal(model.opponent.name, "Ultron");
  assert.equal(model.sample, true);
  assert.equal(model.alerts.length, 2);
  assert.equal(model.alerts[0].player, "Frankie Luvu");
  assert.equal(model.alerts[0].injury, "OUT");
  assert.equal(model.alerts[0].swap.player, "Cedric Gray");
  assert.equal(model.alerts[1].player, "Dallas Turner");
  assert.equal(model.alerts[1].injury, "D");
  assert.equal(model.alerts[1].swap, null);
  assert.equal(model.parlay.state, "alive");
  assert.equal(model.parlay.alive, true);
  assert.equal(model.parlay.yes, 1);
  assert.equal(model.parlay.no, 0);
  assert.ok(model.parlay.pending >= 1);
  assert.ok(!model.parlay.picks.some(function (p) { return p.pick === "George Kittle"; }));
  assert.ok(model.winProb > 0.5 && model.winProb < 0.75);
  const hall = model.featured.starters.find(function (p) { return p.player === "Breece Hall"; });
  assert.equal(hall.injury, "Q");
  assert.equal(hall.statusLabel, "Live");
  const luvu = model.featured.starters.find(function (p) { return p.player === "Frankie Luvu"; });
  assert.equal(luvu.pointsLabel, "—");
  assert.equal(luvu.delta, null);
  const williams = model.featured.starters.find(function (p) { return p.player === "Evan Williams"; });
  assert.equal(williams.delta, 10.2);
  assert.equal(williams.deltaTone, "up");
});

test("a miss kills the parlay and a blank HQ cell stays pending", function () {
  assert.equal(sunday.parlayStatus([{ pick: "A", result: "Yes" }, { pick: "B", result: "pending" }]).state, "alive");
  assert.equal(sunday.parlayStatus([{ pick: "A", result: "Yes" }, { pick: "B", result: "No" }]).state, "dead");
  assert.equal(sunday.parlayStatus([{ pick: "A", result: "Yes" }, { pick: "B", result: "Yes" }]).alive, false);
  assert.equal(sunday.parlayStatus([{ pick: "A", result: "Yes" }, { pick: "B", result: "Yes" }]).state, "hit");
  const hq = {
    participants: [
      { name: "Alpha", weeks: { "8": { player: "Player One", td: "Yes" }, "9": { player: "", td: "" } } },
      { name: "Bravo", weeks: { "8": { player: "Player Two", td: "" } } },
      { name: "Casey", weeks: { "8": { player: "Player Three", td: "N/A" } } }
    ]
  };
  const week8 = sunday.parlayPicks(hq, 8);
  assert.equal(week8.length, 3);
  assert.equal(sunday.parlayStatus(week8).state, "alive");
  assert.equal(sunday.parlayStatus(week8).pending, 1);
  const legacy = {
    owners: [
      { id: "alpha", name: "Alpha", weeks: { "4": { player: "Player Four", td: "No" } } }
    ]
  };
  assert.equal(sunday.parlayStatus(sunday.parlayPicks(legacy, 4)).state, "dead");
  assert.deepEqual(sunday.lockAlerts([
    { player: "Healthy", pos: "RB", nflTeam: "NYJ", status: "not_started", injury: "Q" },
    { player: "Ruled Out", pos: "WR", nflTeam: "DAL", status: "live", injury: "OUT" },
    { player: "Doubt", pos: "DL", nflTeam: "MIN", status: "Not started", injury: "Doubtful", swap: { player: "Backup", pos: "DL", nflTeam: "MIN" } }
  ], "Ultron").map(function (a) { return a.player; }), ["Doubt"]);
});

test("new Sunday files do not name the owner or carry an owner field", function () {
  const files = [
    "sunday.html",
    "js/sunday.js",
    "data/sunday/live.json",
    "data/sunday/config.json",
    "data/td-parlay.json",
    "docs/sunday-command-center.md"
  ];
  const banned = ["B" + "ill", "J" + "enson"];
  files.forEach(function (rel) {
    const text = fs.readFileSync(path.join(root, rel), "utf8");
    const lower = text.toLowerCase();
    banned.forEach(function (word) {
      assert.equal(lower.includes(word.toLowerCase()), false, rel + " contains " + word);
    });
  });
  ["data/sunday/live.json", "data/sunday/config.json", "data/td-parlay.json"].forEach(function (rel) {
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
      assert.equal(/^owners?$/i.test(k), false, rel + " has key " + k);
      assert.equal(/waiver|pendingclaim|pendingtrade|^bids?$|^claims?$/i.test(k), false, rel + " has key " + k);
    });
  });
  const page = fs.readFileSync(path.join(root, "sunday.html"), "utf8");
  assert.match(page, /cache:\s*"no-store"/);
  assert.match(page, /t=/);
  assert.match(page, /WU Sunday Command Center/);
});
