/* Fantrax weeks run Thursday to Wednesday, Pacific Time.
   Week 1 of 2026 started Thursday Sep 10. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.WUWeek = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var WEEK1 = { y: 2026, m: 9, d: 10 };

  function ptParts(date) {
    var fmt = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Los_Angeles",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      weekday: "short",
      hourCycle: "h23"
    });
    var out = {};
    fmt.formatToParts(date).forEach(function (p) {
      if (p.type !== "literal") out[p.type] = p.value;
    });
    if (out.hour === "24") out.hour = "00";
    return out;
  }

  function utcFromPt(y, m, d, h, min) {
    var guess = Date.UTC(y, m - 1, d, h + 7, min);
    for (var i = 0; i < 4; i++) {
      var p = ptParts(new Date(guess));
      var got = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute);
      var want = Date.UTC(y, m - 1, d, h, min);
      var diff = want - got;
      if (diff === 0) break;
      guess += diff;
    }
    return new Date(guess);
  }

  function fantraxWeek(date, week1) {
    var start = week1 || WEEK1;
    var p = ptParts(date || new Date());
    var today = Date.UTC(+p.year, +p.month - 1, +p.day);
    var origin = Date.UTC(start.y, start.m - 1, start.d);
    var days = Math.floor((today - origin) / 86400000);
    if (days < 0) return 1;
    return 1 + Math.floor(days / 7);
  }

  /* Next Wednesday 9:00 AM PT. At 9:00 the clock hits zero. After that, the following Wednesday. */
  function nextWaiver(date) {
    var p = ptParts(date || new Date());
    var map = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
    var dow = map[p.weekday];
    var add = (3 - dow + 7) % 7;
    var hour = +p.hour;
    var minute = +p.minute;
    if (add === 0 && (hour > 9 || (hour === 9 && minute > 0))) add = 7;
    var base = new Date(Date.UTC(+p.year, +p.month - 1, +p.day));
    base.setUTCDate(base.getUTCDate() + add);
    return utcFromPt(base.getUTCFullYear(), base.getUTCMonth() + 1, base.getUTCDate(), 9, 0);
  }

  function countdown(target, now) {
    var ms = target.getTime() - (now || new Date()).getTime();
    if (ms <= 0) return "now";
    var mins = Math.floor(ms / 60000);
    var days = Math.floor(mins / 1440);
    var hours = Math.floor((mins - days * 1440) / 60);
    var m = mins - days * 1440 - hours * 60;
    if (days > 0) return days + "d " + hours + "h";
    if (hours > 0) return hours + "h " + m + "m";
    return m + "m";
  }

  return { ptParts: ptParts, fantraxWeek: fantraxWeek, nextWaiver: nextWaiver, countdown: countdown, utcFromPt: utcFromPt };
});
