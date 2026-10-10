/* Load JSON from the league site, then this phone, then a snapshot in the repo. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.WUData = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var HQ = "https://wjenson27-cpu.github.io/wheels-up-league-hq/data/";

  function cacheKey(url) {
    return "wu-cache:" + url;
  }

  async function fetchJson(url) {
    var res = await fetch(url, { cache: "no-cache" });
    if (!res.ok) throw new Error(String(res.status));
    return res.json();
  }

  async function load(url, fallback) {
    try {
      var data = await fetchJson(url);
      try {
        localStorage.setItem(cacheKey(url), JSON.stringify({ savedAt: Date.now(), data: data }));
      } catch (e) { /* private mode or a full phone */ }
      return { data: data, from: "live" };
    } catch (err) {
      try {
        var cached = JSON.parse(localStorage.getItem(cacheKey(url)) || "null");
        if (cached && cached.data) return { data: cached.data, from: "phone", error: String(err.message || err) };
      } catch (e2) {}
      if (fallback && fallback !== url) {
        try {
          var snap = await fetchJson(fallback);
          return { data: snap, from: "snapshot", error: String(err.message || err) };
        } catch (e3) {}
      }
      return { data: null, from: "missing", error: String(err.message || err) };
    }
  }

  function hq(file) {
    return load(HQ + file, "data/hq/" + file);
  }

  return { HQ: HQ, load: load, hq: hq };
});
