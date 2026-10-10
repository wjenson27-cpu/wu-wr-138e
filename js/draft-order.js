/* Snake order. Traded picks are a list of from/to rules so 2026 can be replayed
   and a later year can ignore them. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.WUDraft = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function applySwaps(origOwner, round, swaps) {
    var owner = origOwner;
    var currentRules = [];
    (swaps || []).forEach(function (rule) {
      if (!rule.rounds || rule.rounds.indexOf(round) === -1) return;
      if (rule.on === "current") {
        currentRules.push(rule);
        return;
      }
      if (origOwner === rule.from) owner = rule.to;
    });
    for (var i = 0; i < currentRules.length; i++) {
      if (owner === currentRules[i].from) return currentRules[i].to;
    }
    return owner;
  }

  function buildPicks(season) {
    var teams = (season.teams || []).slice();
    var rounds = season.rounds || 16;
    var n = teams.length || 1;
    var swaps = season.straightSnake ? [] : (season.pickSwaps || []);
    var picks = [];
    for (var rnd = 1; rnd <= rounds; rnd++) {
      var order = rnd % 2 === 1 ? teams.slice() : teams.slice().reverse();
      order.forEach(function (orig, i) {
        var owner = applySwaps(orig.owner, rnd, swaps);
        var team = null;
        for (var t = 0; t < teams.length; t++) if (teams[t].owner === owner) team = teams[t];
        if (!team) team = orig;
        picks.push({
          overall: (rnd - 1) * n + i + 1,
          round: rnd,
          pick: i + 1,
          team: team.name,
          owner: team.owner,
          short: team.short || team.owner
        });
      });
    }
    return picks;
  }

  function userPicks(season) {
    var owner = season.user && season.user.owner;
    return buildPicks(season).filter(function (p) { return p.owner === owner; }).map(function (p) { return p.overall; });
  }

  /* Move the user's club to a 1-based slot in the round-1 order. */
  function setUserSlot(season, slot) {
    var teams = (season.teams || []).slice();
    var owner = season.user && season.user.owner;
    var idx = teams.findIndex(function (t) { return t.owner === owner; });
    if (idx < 0) return teams;
    var team = teams.splice(idx, 1)[0];
    var at = Math.max(0, Math.min(teams.length, (slot || 1) - 1));
    teams.splice(at, 0, team);
    return teams;
  }

  return { applySwaps: applySwaps, buildPicks: buildPicks, userPicks: userPicks, setUserSlot: setUserSlot };
});
