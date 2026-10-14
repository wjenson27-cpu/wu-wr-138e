#!/usr/bin/env python3
"""Build data/contingency.json (injury + bye contingency board). Read-only on inputs."""
import json, statistics as st
W='/workspace'
BYE={'ARI':14,'ATL':11,'BAL':13,'BUF':7,'CAR':5,'CHI':10,'CIN':6,'CLE':11,'DAL':14,'DEN':10,'DET':6,'GB':11,'HOU':8,'IND':13,'JAX':7,'KC':5,'LV':13,'LAC':7,'LAR':11,'MIA':6,'MIN':6,'NE':11,'NO':8,'NYG':8,'NYJ':13,'PHI':10,'PIT':9,'SF':8,'SEA':11,'TB':10,'TEN':9,'WAS':7}
raw=open(f'{W}/fantrax-shots-2026-10-13-pm/rosters-raw.txt').read().split('## eddies')[1].split('##')[0]
rows=[l.split('|') for l in raw.strip().splitlines()[1:] if l.count('|')==5]
roster=[dict(st=r[0].split('-')[-1] if False else r[0][-1],slot=r[1],player=r[2],pos=r[3],team=r[4],inj=r[5]) for r in rows]
pv={p['name']:p for p in json.load(open('data/player-values.json'))['players']}
wk={}
for w,f in [(3,'fantrax-week3-box-details-PARTIAL-2026-09-29.json'),(4,'fantrax-week4-box-details-2026-10-06.json'),(5,'fantrax-week5-box-details-2026-10-13.json')]:
  for m in json.load(open(f'{W}/{f}'))['matchups']:
    for p in m.get('players',[]):
      if p.get('team')=='Eagle Ridge Eddies': wk.setdefault(p['player'],{})[f'W{w}']=p['pts']
fa={p['player']:p for p in json.load(open('data/free-agents.json'))['players']}
claims=[c for c in json.load(open(f'{W}/wheels-up-hq-ghpages/data/faab.json'))['claims'] if c.get('kind')=='claim' and c.get('amount',0)>0]
def rng(pos):
  v=sorted(c['amount'] for c in claims if (c.get('pos') or '').split(',')[0].split('(')[0].split('/')[0]==pos)
  q=st.quantiles(v,n=4) if len(v)>=4 else [min(v),st.median(v),max(v)]
  return dict(winningBidsN=len(v),min=v[0],p25=round(q[0]),median=round(q[1]),p75=round(q[2]),max=v[-1])
usage={ # from data/warroom.json lineup/idp notes + data/green-dots.json (Woellert W5) + news
 'Trevor Lawrence':'W5 36 FP (Fantrax). Locked QB1; no QB on bench.',
 'Breece Hall':'No games since W3; has not practiced since W3 (NBC Oct 13 "out indefinitely").',
 'Garrett Wilson':'11 targets W5; alpha share with Mitchell out.',
 'Brock Bowers':'TE1, 2 games in Sleeper sample; W3-W5 Fantrax 41.5/25.5/34.5.',
 'Jalen Coker':'Missed W4-W5 (quad); practiced Tue Oct 13, Canales "looked great".',
 'Rhamondre Stevenson':'Lead back with Henderson (high ankle) out; 18 FP W5.',
 'Tyler Warren':'Every-week TE2 in flex; 19.5/12.5/26.5 W3-W5.',
 'Tuli Tuipulotu':'Every-down edge; 16 FP W5.',
 'Fred Warner':'Green dot, 60/60 snaps W5.',
 'Julian Love':'Starting S; 14/15 FP W4-W5.',
 'Evan Williams':'Starting S; 36/28 FP W4-W5.',
 'Cedric Gray':'Base-only, 39.7% snaps W5 (Woellert) - first cut.',
 'Quentin Lake':'Cleared (hip), played MNF W5; 12/13 FP W4-W5.',
 'Trenton Simpson':'56.2% snaps W5, 7 tkl + sack (Woellert): lower floor than totals suggest.',
}
# in-roster backup per starter (judged on slot eligibility, bye, health)
inb={'Trevor Lawrence':(None,'No backup QB rostered - W7 (JAX bye) needs a waiver QB.'),
 'Breece Hall':('Brian Robinson Jr.','Reserve; W4 27, W5 8 as starter; KR yards. ATL bye W11.'),
 'Garrett Wilson':('Kendrick Bourne','12 FP W5 as flex; Sleeper 3.8 FP/G thru W4. ARI bye W14.'),
 'Brock Bowers':('Tyler Warren','Already starting in flex; slide to TE and fill flex with Robinson Jr. Same W13 bye (IND/LV).'),
 'Jalen Coker':('Brian Robinson Jr.','Next RWT; then Chimere Dike (10.0 FP/G thru W4, TEN bye W9).'),
 'Rhamondre Stevenson':('Brian Robinson Jr.','Reserve RB; Croskey-Merritt (7.7 FP/G) next.'),
 'Tyler Warren':('Brian Robinson Jr.','No 3rd TE; RB/WR fill the flex.'),
 'Tuli Tuipulotu':('Leonard Williams','Only bench DL; Q (ankle), SEA bye W11. 12.9 FP/G thru W4, W4 1 FP dud.'),
 'Fred Warner':('Jordyn Brooks','19.6 FP/G thru W4; MIA bye W6, foot DNP Tue.'),
 'Julian Love':(None,'No bench DB; Brooks can cover an ID slot only, not DB.'),
 'Evan Williams':(None,'No bench DB.'),
 'Cedric Gray':('Jordyn Brooks','Brooks back from bye W7; clear upgrade on Gray.'),
 'Quentin Lake':('Jordyn Brooks','Covers the ID slot (not a DB slot).'),
 'Trenton Simpson':('Jordyn Brooks','ID flex swap from W7.'),
}
# waiver backup: player, suggested bid (warroom bid sheet where it exists), why
wv={'QB':('Jacoby Brissett',4,'21.3 FP/G last 3, ARI bye W14 (covers W7). Watson CLE is the alt (bye W11).'),
 'RB':('Kimani Vidal',5,'16.0 last-3 trend; LAC bye W7.'),
 'WR':('Tyquan Thornton',3,'19.0 last 3; KC bye already used.'),
 'TE':('Pat Freiermuth',2,'14.4 FP/G, PIT bye W9; TE premium.'),
 'DL':('Carl Granderson',6,'War Room bid sheet #3; NO bye W8, DL PD = 4.'),
 'LB':('Elijah Ponder',4,'Sack/TFL-dependent edge LB; Landry return is a snap risk.'),
 'DB':('Mansoor Delane',11,'War Room bid sheet #1; KC bye used; 30.5 last 3.'),
 'DB2':('Jacob Parrish',7,'War Room bid sheet #2; TB bye W10.')}
slotmap={'R/W/T':'RB/WR/TE flex','ID':'IDP flex'}
starters=[r for r in roster if r['st']=='A']
out=[]; dbn=0
for r in starters:
  p=r['player']; pos=r['pos'].split(',')[0]
  key=pos
  if pos=='DB': key='DB' if dbn==0 else 'DB2'; dbn+=1
  if p=='Jalen Coker' or p=='Garrett Wilson': key='WR'
  if p in('Breece Hall','Rhamondre Stevenson'): key='RB'
  wname,bid,why=wv[key]; f=fa[wname]; R=rng(pos if pos!='DB2' else 'DB')
  v=pv.get(p,{})
  ev={'fpgComputed':v.get('ppg'),'fpgBasis':f"league-scored Sleeper stats thru W4, {v.get('games')} G (data/player-values.json)" if v else None,
      'fantraxStarterPts':wk.get(p,{}),'usage':usage[p]}
  ib,ibn=inb[p]
  out.append(dict(player=p,position=r['pos'],slot=slotmap.get(r['slot'],r['slot']),nflTeam=r['team'],byeWeek=BYE[r['team']],
    byePassed=BYE[r['team']]<6,injury=('Q (Quadriceps) on Fantrax; NBC Oct 13: out indefinitely, no practice since W3 - treat as OUT' if p=='Breece Hall' else r['inj']),
    inRosterBackup=dict(player=ib,note=ibn, byeWeek=BYE[next(x['team'] for x in roster if x['player']==ib)] if ib else None),
    waiverBackup=dict(player=wname,pos=f['pos'],nflTeam=f['team'],byeWeek=BYE[f['team']],fpg=f['fpg'],last3Fpg=f['last3Fpg'],rosteredPct=f['rosteredPct'],
      faabRange=dict(low=R['p25'],high=R['p75'],basis=f"{R['winningBidsN']} winning {pos} claims in HQ faab.json: min ${R['min']}, median ${R['median']}, max ${R['max']}; range = 25th-75th pct"),
      suggestedBid=bid,why=why,evidence='actual Fantrax FP/G (data/free-agents.json, as of Oct 13 3:10 PM PT)'),
    evidence=ev))
bench=[r for r in roster if r['st']=='R']
weeks=[]
for w in range(6,15):
  o=[s['player'] for s in out if s['byeWeek']==w]
  weeks.append(dict(week=w,startersOnBye=o,count=len(o),benchOnBye=[b['player'] for b in bench if BYE[b['team']]==w],
    stacked=len(o)>=3,beforeDeadline=w<=9))
doc=dict(asOf='2026-10-13T17:30:00-07:00',team='Eagle Ridge Eddies',currentWeek=6,faabLeft=68,
 lineupSource='Fantrax Active slots, roster sync Oct 13 ~4 PM PT (fantrax-shots-2026-10-13-pm/rosters-raw.txt). No lineup changes made.',
 note='War Room plan (data/warroom.json) already moves Hall out and Robinson Jr. in for W6; this board lists the Fantrax Active lineup as it stands.',
 byeSource=dict(name='NFL.com: 2026 NFL schedule release, every team\'s bye week',url='https://www.nfl.com/_amp/2026-nfl-schedule-release-every-team-bye-week',crossCheck='https://www.foxsports.com/stories/nfl/2026-nfl-bye-weeks-schedule-all-32-teams'),
 deadlines=dict(nfl=dict(date='2026-11-10',time='4:00 PM ET / 1:00 PM PT',fantasyWeek=9,source='https://www.nfl.com/news/2026-27-national-football-league-important-dates'),
   fantrax=dict(date=None,note='No Fantrax league trade deadline found in HQ data (wheels-up-hq-ghpages, wheels-up-league-hq). Check Fantrax League Rules before relying on one.')),
 projectionNote='No starter evidence here rests on a projection; every number is actual. Items would be labeled "projection only" otherwise.',
 starters=out,byWeek=weeks,
 summary=dict(biggestStackedBye='W13 (Hall, Wilson, Bowers, Warren, Simpson - 5 starters); W11 has 4. Before the deadline the peak is W7 (Lawrence + Tuipulotu, with no backup QB).'))
json.dump(doc,open('data/contingency.json','w'),indent=2)
print(json.dumps(weeks))
