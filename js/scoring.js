/* Turn a stat line into Wheels Up points.
   Uses the numbers in scoring.json. String rules are read the way that file describes them. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.WUScore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function num(v) {
    var n = Number(v);
    return Number.isFinite(n) ? n : 0;
  }

  function passYardBonus(yards) {
    var bonus = 0;
    [300, 400, 500, 600].forEach(function (mark) {
      if (yards >= mark) bonus += 6;
    });
    return bonus;
  }

  function hundredBonus(yards) {
    if (yards < 100) return 0;
    return Math.floor(yards / 100) * 6;
  }

  function scoreLine(stats, pos, scoring) {
    var s = stats || {};
    var o = (scoring && scoring.offense) || {};
    var idp = (scoring && scoring.idp) || {};
    var passing = o.passing || {};
    var rushing = o.rushing || {};
    var receiving = o.receiving || {};
    var pts = 0;
    var passYds = num(s.passYds);
    var rushYds = num(s.rushYds);
    var recYds = num(s.recYds);
    var solo = num(s.solo);
    var ast = num(s.assisted);
    var tackles = solo + ast;

    pts += passYds * 0.04;
    pts += passYardBonus(passYds);
    pts += num(s.passTd) * num(passing.passTD || 6);
    pts += num(s.interceptions) * num(passing.interceptionThrown != null ? passing.interceptionThrown : -3);

    pts += rushYds * 0.1;
    pts += hundredBonus(rushYds);
    pts += num(s.rushTd) * num(rushing.rushTD || 6);
    pts += Math.min(7, Math.floor(num(s.carries) / 7));

    var recPts = pos === "TE" ? num(receiving.receptionTE || 1.5) : num(receiving.reception || 1);
    pts += num(s.receptions) * recPts;
    if (pos === "TE") pts += num(s.teFirstDowns) * num(receiving.receivingFirstDownTE || 0.5);
    pts += recYds * 0.1;
    pts += hundredBonus(recYds);
    pts += num(s.recTd) * num(receiving.recTD || 6);
    pts += num(s.krYds) * 0.1;
    pts += num(s.prYds) * 0.1;
    pts += (num(s.krTd) + num(s.prTd)) * num(o.returns && o.returns.returnTD || 6);
    var fum = (o.fumbles && o.fumbles.fumbleLost != null) ? o.fumbles.fumbleLost : -3;
    pts += num(s.fumbleLost) * num(fum);
    var two = (passing.twoPointPass != null) ? passing.twoPointPass : 2;
    pts += (num(s.passTwo) + num(s.rushTwo) + num(s.recTwo)) * num(two);

    pts += solo * num(idp.soloTackle != null ? idp.soloTackle : 2);
    pts += ast * num(idp.assistedTackle != null ? idp.assistedTackle : 1);
    pts += Math.floor(Math.min(tackles, 40) / 5) * 3;
    pts += num(s.tfl) * num(idp.tackleForLoss != null ? idp.tackleForLoss : 3);
    pts += num(s.sacks) * 6;
    var pd = num(idp.passDefensed != null ? idp.passDefensed : 3);
    if (pos === "DL") pd = num(idp.passDefensedDL != null ? idp.passDefensedDL : 4);
    pts += num(s.pd) * pd;
    pts += num(s.defInt) * num(idp.interception != null ? idp.interception : 6);
    pts += num(s.qbHit) * num(idp.qbHit != null ? idp.qbHit : 1);
    pts += num(s.forcedFumble) * num(idp.forcedFumble != null ? idp.forcedFumble : 3);
    pts += num(s.safety) * num(idp.safety != null ? idp.safety : 6);
    pts += num(s.blockedKick) * num(idp.blockedKick != null ? idp.blockedKick : 6);
    return Math.round(pts * 10) / 10;
  }

  function hasStats(row) {
    var keys = ["passYds", "passTd", "interceptions", "rushYds", "rushTd", "carries", "receptions", "recYds", "recTd", "teFirstDowns", "solo", "assisted", "sacks", "tfl", "pd", "defInt"];
    return keys.some(function (k) { return row[k] != null && row[k] !== ""; });
  }

  return { scoreLine: scoreLine, hasStats: hasStats };
});
