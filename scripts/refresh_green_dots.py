#!/usr/bin/env python3
"""Check Mike Woellert's Substack for a newer green-dot post and rebuild data/green-dots.json for it.
Only FREE posts (audience == "everyone") are parsed; paid posts are never fetched past the public API
metadata, so there is no paywall bypass. If nothing newer and free is found, green-dots.json is left as-is and
data/green-dots-status.json gets stale: true.
Usage: refresh_green_dots.py [--data-dir DIR] [--now ISO] [--archive FILE --post FILE]  (files = test fixtures)"""
import argparse, html, json, os, re, sys, urllib.request
from datetime import datetime
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
from warroom_common import load_json, write_json, iso_pt, now_pt, parse_now, week_for, PT

BASE = "https://mikewoellert.substack.com"
TEAMS = {"Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF",
 "Carolina Panthers": "CAR", "Chicago Bears": "CHI", "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE",
 "Dallas Cowboys": "DAL", "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
 "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX", "Kansas City Chiefs": "KC",
 "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC", "Los Angeles Rams": "LAR", "Miami Dolphins": "MIA",
 "Minnesota Vikings": "MIN", "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
 "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT", "San Francisco 49ers": "SF",
 "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB", "Tennessee Titans": "TEN", "Washington Commanders": "WAS"}
TITLE = re.compile(r"week\s*(\d+).*green\s*dot", re.I)

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "wu-warroom-green-dots/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def text(h):
    h = re.sub(r"<(figure|svg|picture|button)[\s\S]*?</\1>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()

# A name token is an initial pair ("D.J."), or a capitalized word that ends in a lowercase letter, so
# "Woods." (end of sentence) never runs into the next word.
TOK = r"(?:[A-Z]\.(?:[A-Z]\.)?|[A-Z][A-Za-z'\u2019\-]*[a-z])"
NAME = r"(" + TOK + r" " + TOK + r"(?: (?:Jr\.|Sr\.|Jr|Sr|II|III|IV))?)"

FINISH = re.compile(NAME + r" (?:finished (?:the game )?with|ended (?:the game )?with|took over|wore|inherited|took) the (?:green )?dot")
BYE = re.compile(r"Green\s*Dot:\s*Bye\b(?!\s*week\s*\?)(?!\s*\?)", re.I)
def known_players(data_dir):
    """Names we accept as green-dot wearers: IDP rankings (all positions), HQ rosters, the previous green-dot file."""
    sys.path.insert(0, os.path.dirname(__file__))
    from warroom_common import norm
    d = Path(data_dir); names = set()
    r = load_json(d / "idp-rankings.json", {}) or {}
    for lst in (r.get("positions") or {}).values():
        names |= {norm(p.get("player")) for p in lst if isinstance(p, dict)}
    names |= {norm(p.get("player")) for p in r.get("eddies") or [] if isinstance(p, dict)}
    for f in list((d / "hq" / "rosters").glob("*.json")) + [d / "hq" / "roster-eddies.json"]:
        try:
            x = json.loads(f.read_text())
        except Exception:
            continue
        for p in (x.get("players") if isinstance(x, dict) else []) or []:
            if isinstance(p, dict):
                names.add(norm(p.get("player") or p.get("name")))
    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("name") or o.get("player"), str):
                names.add(norm(o.get("name") or o.get("player")))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk((load_json(d / "player-values.json", {}) or {}).get("players"))
    latest = (load_json(d / "rankings" / "latest.json", {}) or {}).get("file")
    if latest:
        walk(load_json(d / "rankings" / Path(latest).name, {}))
    for t in (load_json(d / "green-dots.json", {}) or {}).get("teams", []):
        names |= {norm(t.get("greenDot"))} | {norm(n) for n in t.get("fullTime") or []}
    names.discard("")
    return names

def parse(body_html, week, prev=None, known=None):
    """Returns (teams, unresolved). Each team: team, greenDot, fullTime, notes, and bye: true on a bye week.
    The post's own final wording wins: 'X finished with the dot' overrides the name on the Green Dot line."""
    prev = {t["team"]: t for t in (prev or [])}
    parts = re.split(r"<h[1-4][^>]*>(.*?)</h[1-4]>", body_html)
    teams, unresolved = [], []
    for i in range(1, len(parts) - 1, 2):
        title = text(parts[i])
        if title not in TEAMS:
            continue
        ab, sec = TEAMS[title], text(parts[i + 1]).replace("\u2019", "'")
        if BYE.search(sec):
            p = prev.get(ab) or {}
            teams.append({"team": ab, "bye": True, "greenDot": p.get("greenDot"), "fullTime": p.get("fullTime") or [],
                          "notes": f"Bye in week {week}." + (" Dot carried from the previous list." if p.get("greenDot") else "")})
            continue
        dot, note, shared = None, "", False
        m = re.search(r"Week\s*\d+\s*Green\s*Dot:\s*" + NAME + r"(?:\s*\(([^)]*)\))?", sec)
        if m:
            dot, paren = m.group(1), m.group(2) or ""
            after = sec[m.end():m.end() + 300]
            f = FINISH.search(paren) or FINISH.search(after)
            if f and f.group(1) != dot:
                note = f"Listed {dot}; post says {f.group(1)} ended up with the dot. "
                dot = f.group(1)
            elif re.search(r"shared|split|rotat", paren, re.I):
                # schema: null when the post says the dot rotated; both names go in notes. Counts as resolved.
                note = f"Dot {paren.strip()} ({dot}). "
                dot, shared = None, True
        else:
            f = FINISH.search(sec) or re.search(NAME + r" wore the (?:green )?dot", sec)
            dot = f.group(1) if f else None
        if dot and known is not None:
            from warroom_common import norm
            if norm(dot) not in known:
                note += f"Parsed name '{dot}' not found in roster files. "
                unresolved.append(ab); dot = None
        elif not dot and not shared:
            unresolved.append(ab)
        ft = []
        for mm in re.finditer(NAME + r" played (?:all|every) (?:\d+ )?(?:of the )?snaps", sec):
            ft.append(mm.group(1))
        for mm in re.finditer(NAME + r" played \d+ snaps \((9\d|100)(?:\.\d+)?%\)", sec):
            ft.append(mm.group(1))
        first = re.split(r"(?<=[.!?]) ", sec)[0][:200]
        row = {"team": ab, "greenDot": dot, "fullTime": list(dict.fromkeys(ft)),
               "notes": (f"Week {week} Green Dot: {dot}. " if dot else "") + note + first}
        if shared:
            row["shared"] = True
        teams.append(row)
    missing = sorted(set(TEAMS.values()) - {t["team"] for t in teams})
    return teams, unresolved + missing

def run(data_dir, now, archive=None, post_fetch=None):
    data_dir = Path(data_dir)
    gd = load_json(data_dir / "green-dots.json", {}) or {}
    cur_week = week_for(now)
    have_week = gd.get("week")
    status = {"checkedAt": iso_pt(now), "currentWeek": cur_week, "fileWeek": have_week,
              "fileAsOf": gd.get("asOf"), "sourceUrl": gd.get("sourceUrl"), "latestPost": None,
              "rebuilt": False, "stale": True, "reason": ""}
    try:
        posts = archive if archive is not None else get(BASE + "/api/v1/archive?sort=new&limit=25")
    except Exception as e:
        status["reason"] = f"archive fetch failed: {e}"
        return gd, status
    cands = []
    for p in posts:
        m = TITLE.search(p.get("title") or "")
        if m:
            cands.append((int(m.group(1)), p))
    cands.sort(key=lambda x: (x[0], x[1].get("post_date", "")), reverse=True)
    if not cands:
        status["reason"] = "no green-dot post in archive"
    else:
        wk, p = cands[0]
        status["latestPost"] = {"week": wk, "title": p.get("title"), "url": p.get("canonical_url"),
                                "date": p.get("post_date"), "audience": p.get("audience")}
        if have_week is not None and wk <= have_week:
            status["reason"] = f"newest green-dot post is week {wk}; file already has week {have_week}"
        elif p.get("audience") != "everyone":
            status["reason"] = f"week {wk} post is paid-only; not parsed (no paywall bypass)"
        else:
            body = (post_fetch or (lambda slug: get(f"{BASE}/api/v1/posts/{slug}")))(p.get("slug")).get("body_html") or ""
            teams, unresolved = parse(body, wk, gd.get("teams"), known_players(data_dir))
            status["parse"] = {"teams": len(teams), "bye": sum(1 for t in teams if t.get("bye")),
                               "resolved": sum(1 for t in teams if not t.get("bye") and (t["greenDot"] or t.get("shared"))), "unresolved": unresolved}
            if unresolved:
                status["reason"] = f"week {wk} post found but {len(unresolved)} non-bye team(s) unresolved {unresolved}; refused rebuild"
            else:
                pd = p.get("post_date")
                asof = iso_pt(datetime.fromisoformat(pd.replace("Z", "+00:00"))) if pd else iso_pt(now)
                gd = {"sample": False, "asOf": asof, "week": wk, "source": "Mike Woellert",
                      "sourceUrl": p.get("canonical_url"), "lastUpdated": iso_pt(now), "teams": teams}
                status.update(rebuilt=True, fileWeek=wk, fileAsOf=asof, sourceUrl=p.get("canonical_url"),
                              reason=f"rebuilt from week {wk} post ({len(teams)} teams)")
    # Same convention the newsletter routine used: a list for an earlier week than the current one is STALE.
    status["stale"] = not (status["fileWeek"] is not None and status["fileWeek"] >= cur_week)
    return gd, status

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parent.parent / "data"))
    ap.add_argument("--now"); ap.add_argument("--archive"); ap.add_argument("--post")
    a = ap.parse_args()
    now = parse_now(a.now) if a.now else now_pt()
    arch = load_json(a.archive) if a.archive else None
    pf = (lambda slug: load_json(a.post)) if a.post else None
    gd, st = run(a.data_dir, now, arch, pf)
    if st["rebuilt"]:
        write_json(Path(a.data_dir) / "green-dots.json", gd)
    write_json(Path(a.data_dir) / "green-dots-status.json", st)
    print(f"green-dots: week {st['fileWeek']} stale={st['stale']} ({st['reason']})")

if __name__ == "__main__":
    main()
