/* Arrival-board helpers for the War Room.
   Split-flap markup follows the live HQ departures board.
   Stamps use timestamps already stored on each section. */
(function (root) {
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c];
    });
  }

  function wallToUtc(y, mo, d, h, mi) {
    var fmt = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Los_Angeles",
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
    function parts(ms) {
      var map = {};
      fmt.formatToParts(new Date(ms)).forEach(function (p) { map[p.type] = p.value; });
      return Date.UTC(+map.year, +map.month - 1, +map.day, +map.hour % 24, +map.minute);
    }
    var guess = Date.UTC(y, mo - 1, d, h, mi);
    return guess - (parts(guess) - Date.UTC(y, mo - 1, d, h, mi));
  }

  function parseMs(value) {
    if (value == null || value === "") return null;
    if (typeof value === "number" && Number.isFinite(value)) return value;
    var s = String(value).trim();
    if (/^[A-Z][a-z]{2}\s+\d{1,2},\s+\d{1,2}:\d{2}\s+(AM|PM)\s+PT$/i.test(s)) return null;
    var dateOnly = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (dateOnly) return wallToUtc(+dateOnly[1], +dateOnly[2], +dateOnly[3], 12, 0);
    var wall = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?(?:\s*(AM|PM))?(?:\s*(PT|PDT|PST))?$/i);
    if (wall && !/[zZ]$|[+-]\d{2}:?\d{2}$/.test(s)) {
      var h = +wall[4];
      var ap = (wall[7] || "").toUpperCase();
      if (ap === "PM" && h < 12) h += 12;
      if (ap === "AM" && h === 12) h = 0;
      return wallToUtc(+wall[1], +wall[2], +wall[3], h, +wall[5]);
    }
    var shortIso = s.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})([+-]\d{2}:\d{2})$/);
    if (shortIso) s = shortIso[1] + ":00" + shortIso[2];
    var t = Date.parse(s);
    return Number.isFinite(t) ? t : null;
  }

  function formatPt(value) {
    if (value == null || value === "") return "";
    var s = String(value).trim().replace(/[\u202f\u2009]/g, " ");
    if (/^[A-Z][a-z]{2}\s+\d{1,2},\s+\d{1,2}:\d{2}\s+(AM|PM)\s+PT$/i.test(s)) return s;
    var dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(s);
    var ms = parseMs(value);
    if (ms == null) return "";
    var opts = dateOnly
      ? { timeZone: "America/Los_Angeles", month: "short", day: "numeric" }
      : { timeZone: "America/Los_Angeles", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", hour12: true };
    return new Intl.DateTimeFormat("en-US", opts).format(new Date(ms)).replace(/[\u202f\u2009]/g, " ") + " PT";
  }

  function newest(values) {
    var best = null;
    var bestMs = -Infinity;
    (values || []).forEach(function (value) {
      var ms = parseMs(value);
      if (ms != null && ms > bestMs) {
        bestMs = ms;
        best = value;
      }
    });
    return best;
  }

  function flaps(value, extra) {
    var text = value == null || value === "" ? "—" : String(value);
    if (text === "—" || text === "–" || text === "-") {
      return '<span class="dep-blank">—</span>';
    }
    var tiles = Array.from(text).map(function (ch, i) {
      var narrow = /[,.'’:+\-]/.test(ch) ? " is-narrow" : "";
      var gap = ch === " " ? " is-gap" : "";
      return '<span class="flap-char' + narrow + gap + '" style="--i:' + Math.min(i, 14) + '">' + esc(ch) + "</span>";
    }).join("");
    var extraCls = extra ? " " + extra : "";
    return '<span class="flap-group' + extraCls + '" role="img" aria-label="' + esc(text) + '"><span class="flap-tiles" aria-hidden="true">' + tiles + "</span></span>";
  }

  function chip(label, kind) {
    if (!label) return "";
    var k = kind || "ontime";
    return '<span class="dep-chip is-' + esc(k) + '">' + esc(label) + "</span>";
  }

  function code(name, size) {
    var letters = String(name || "").replace(/[^A-Za-z0-9]/g, "");
    var n = size || 3;
    return (letters.slice(0, n) || "VS").toUpperCase();
  }

  function flightCode(week) {
    var n = Number(week);
    var wk = Number.isFinite(n) ? String(n).padStart(2, "0") : "00";
    return "WU" + wk;
  }

  function stamp(value) {
    var text = formatPt(value);
    if (!text) return "";
    var ms = parseMs(value);
    var dt = ms == null ? "" : ' datetime="' + esc(new Date(ms).toISOString()) + '"';
    return '<p class="updated">Updated <time' + dt + ">" + esc(text) + "</time></p>";
  }

  function matchup(opts) {
    opts = opts || {};
    var status = chip(opts.statusLabel, opts.statusKind);
    return '<section class="card dep-game"><div class="dep-game-head"><span>Flight</span><span>Gate</span><span class="dep-head-match">Matchup</span><span>Status</span></div>' +
      '<div class="dep-game-top"><div class="dep-codes">' +
      '<div class="dep-flight"><span class="dep-k">Flight</span>' + flaps(opts.flight || "—") + "</div>" +
      '<div class="dep-gate"><span class="dep-k">Gate</span>' + flaps(opts.gate || "—") + "</div>" +
      '</div><div class="dep-status">' + status + '</div><div class="dep-dest">' + (opts.body || "") + "</div></div></section>";
  }

  function bindTabs(bar) {
    if (!bar || bar.getAttribute("data-tabs-ready") === "1") return;
    var nav = bar.querySelector("nav");
    if (!nav) return;
    bar.setAttribute("data-tabs-ready", "1");
    var cue = document.createElement("button");
    cue.type = "button";
    cue.className = "tab-cue";
    cue.setAttribute("aria-label", "More sections");
    cue.innerHTML = '<span aria-hidden="true">›</span>';
    cue.addEventListener("click", function () {
      nav.scrollBy({ left: Math.max(140, Math.round(nav.clientWidth * 0.7)), behavior: "smooth" });
    });
    bar.appendChild(cue);
    function sync() {
      var extra = nav.scrollWidth - nav.clientWidth;
      var more = extra > 8 && nav.scrollLeft < extra - 8;
      bar.classList.toggle("has-more", more);
    }
    nav.addEventListener("scroll", sync, { passive: true });
    nav.addEventListener("focusin", function (ev) {
      var el = ev.target.closest("button, a");
      if (el && el.scrollIntoView) el.scrollIntoView({ inline: "nearest", block: "nearest" });
    });
    window.addEventListener("resize", sync);
    if (typeof ResizeObserver === "function") new ResizeObserver(sync).observe(nav);
    sync();
  }

  function boot() {
    document.querySelectorAll("[data-tabs]").forEach(bindTabs);
  }

  root.WUArrival = {
    esc: esc,
    parseMs: parseMs,
    formatPt: formatPt,
    newest: newest,
    flaps: flaps,
    chip: chip,
    code: code,
    flightCode: flightCode,
    stamp: stamp,
    matchup: matchup,
    bindTabs: bindTabs
  };

  if (root.document) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
