const test = require("node:test");
const assert = require("node:assert/strict");
const dots = require("../js/green-dots.js");
const sample = require("../data/green-dots.json");

const NOW = Date.parse("2026-10-10T12:00:00-07:00");

test("initials, apostrophes, and junior suffixes match", function () {
  const doc = {
    asOf: "2026-10-06T09:00:00-07:00",
    week: 4,
    source: "Mike Woellert",
    teams: [
      { team: "CHI", greenDot: "T.J. Edwards", fullTime: ["T.J. Edwards"] },
      { team: "LAC", greenDot: null, fullTime: ["Del'Shawn Phillips"] },
      { team: "NYJ", greenDot: "Jamien Sherwood Jr.", fullTime: [] }
    ]
  };
  const prepared = dots.prepare(doc, NOW);
  assert.equal(dots.role(prepared, "TJ Edwards").green, true);
  assert.equal(dots.role(prepared, "DelShawn Phillips").full, true);
  assert.equal(dots.role(prepared, "DelShawn Phillips").green, false);
  assert.equal(dots.role(prepared, "Jamien Sherwood").green, true);
  assert.equal(dots.role(prepared, "Someone Else"), null);
  const nate = dots.prepare({
    asOf: "2026-10-06T09:00:00-07:00",
    teams: [{ team: "LAR", greenDot: "Nathan Landman", fullTime: ["Nathan Landman"] }]
  }, NOW);
  assert.equal(dots.role(nate, "Nate Landman").green, true);
  assert.equal(dots.role(nate, "Nate Landman").full, true);
});

test("an unsettled green dot matches nobody", function () {
  const doc = {
    asOf: "2026-10-06T09:00:00-07:00",
    teams: [{ team: "ATL", greenDot: null, fullTime: [], notes: "Divine Deablo/Kendal Daniels" }]
  };
  const prepared = dots.prepare(doc, NOW);
  assert.equal(dots.role(prepared, "Divine Deablo"), null);
  assert.equal(dots.role(prepared, "Kendal Daniels"), null);
});

test("a list older than 10 days or a missing file hides every match", function () {
  const old = dots.prepare({
    asOf: "2026-09-01T09:00:00-07:00",
    teams: [{ team: "SF", greenDot: "Fred Warner", fullTime: ["Fred Warner"] }]
  }, NOW);
  assert.equal(old.fresh, false);
  assert.equal(dots.role(old, "Fred Warner"), null);
  assert.equal(dots.mark(old, "Fred Warner"), "");
  const missing = dots.prepare(null, NOW);
  assert.equal(missing.fresh, false);
  assert.match(dots.note(missing), /No green-dot list/);
  assert.match(dots.note(old), /10 days/);
  assert.equal(dots.note(dots.prepare(sample, NOW)), "");
});

test("the Week 4 sample keeps the posted green dots", function () {
  const prepared = dots.prepare(sample, NOW);
  assert.equal(prepared.fresh, true);
  assert.equal(sample.sample, true);
  assert.equal(prepared.byNorm[dots.normName("Fred Warner")].green, true);
  assert.equal(prepared.byNorm[dots.normName("Fred Warner")].full, true);
  assert.equal(prepared.byNorm[dots.normName("Jordyn Brooks")].green, false);
  assert.equal(prepared.byNorm[dots.normName("Jordyn Brooks")].full, true);
  assert.equal(dots.role(prepared, "Mack Wilson").team, "ARI");
  const atlanta = sample.teams.filter(function (t) { return t.team === "ATL"; })[0];
  const dallas = sample.teams.filter(function (t) { return t.team === "DAL"; })[0];
  assert.equal(atlanta.greenDot, null);
  assert.equal(dallas.greenDot, null);
  assert.match(dots.mark(prepared, "Fred Warner"), /class="gdot"/);
  assert.match(dots.mark(prepared, "Jordyn Brooks"), /gdot ft/);
  assert.doesNotMatch(dots.mark(prepared, "Jordyn Brooks"), /aria-label="Green dot/);
});
