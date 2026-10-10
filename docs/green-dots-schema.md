# Green dots

Eddie fills `data/green-dots.json` once a week from Mike Woellert's list (@Mike_Woellert on X, and the weekly Substack post). The War Room reads that file. It does not fetch X or Substack on its own.

The badges use the same name matching as the rankings board: accents come off, apostrophes and periods drop, hyphens become spaces, and jr, sr, ii, iii, iv, and v drop. `T.J. Edwards` matches `TJ Edwards`. A short first name matches its formal name, so `Nate Landman` matches `Nathan Landman`. That step is the first name only. Chris does not match Christian, and Jon does not match John.

## When the badges show

`asOf` is a Pacific time stamp, ISO 8601, with the offset included (`2026-10-06T09:00:00-07:00`).

If the file is missing, or `asOf` is more than 10 days before now, every green-dot and full-time badge stays hidden. Each of the Rankings, IDP, Roster, Waivers, and Trade screens shows a short note instead. A `sample: true` file still shows badges while it is inside those 10 days.

## The file

```json
{
  "sample": true,
  "asOf": "2026-10-06T09:00:00-07:00",
  "week": 4,
  "source": "Mike Woellert",
  "sourceUrl": "https://mikewoellert.substack.com/p/2026-week-4-green-dot-and-full-time-linebackers",
  "teams": [
    {
      "team": "SF",
      "greenDot": "Fred Warner",
      "fullTime": ["Fred Warner"],
      "notes": "Wore the dot and played every snap."
    }
  ]
}
```

- `team` is the NFL abbreviation (`WAS`, not `WSH`).
- `greenDot` is the linebacker who wore the communication helmet. Use `null` when the post says the dot rotated or is unsettled, and put both names in `notes`.
- `fullTime` is the every-down linebackers the post actually names. A green-dot wearer who also played every snap is listed in both places. He gets the green circle and the smaller FT mark.
- `notes` is one short line from the post.

The sample file is Week 4, taken from the free text of that post. Eddie replaces it with the current week and removes `sample`.
