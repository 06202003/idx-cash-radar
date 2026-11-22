import json,os,sys,statistics as st
from collections import defaultdict
sys.path.insert(0,'/home/testing-bcai/stockbit-monitor'); import technical
D=sys.argv[1]
ih={b[0]:b for b in json.load(open(f"{D}/_JKSE.json"))}
idays=sorted(ih)
def ihsg_state(day):
    i=idays.index(day)
    if i<50: return None
    c=[ih[d][4] for d in idays[:i+1]]
    ma20=sum(c[-20:])/20; ma50=sum(c[-50:])/50
    tr="up" if c[-1]>ma20>ma50 else "down" if c[-1]<ma20<ma50 else "side"
    ch=c[-1]/c[-2]-1
    col="merah" if ch<-0.005 else "hijau" if ch>0.005 else "datar"
    return tr,col
state={d:ihsg_state(d) for d in idays}
stocks={}
for f in os.listdir(D):
    if f.startswith("_"): continue
    stocks[f[:-5]]=json.load(open(f"{D}/{f}"))
# return pasar (equal weight) per (hari sinyal, horizon)
fwd=defaultdict(dict)  # (sym) -> {day:(r1,r5)}
for s,b in stocks.items():
    for t in range(len(b)-6):
        o=b[t+1][1]
        if o<=0: continue
        fwd[s][b[t][0]]=(b[t+1][4]/o-1, b[t+5][4]/o-1)
mkt=defaultdict(lambda:[[],[]])
for s in fwd:
    for d,(r1,r5) in fwd[s].items(): mkt[d][0].append(r1); mkt[d][1].append(r5)
mkt={d:(st.mean(a),st.mean(b)) for d,(a,b) in mkt.items() if len(a)>=50}
ev=defaultdict(list)  # (rule, regime_key) -> [(day, rel, raw)]
for s,b in stocks.items():
    for t in range(56,len(b)-6):
        d=b[t][0]
        if d not in mkt or d not in fwd[s] or not state.get(d): continue
        ind=technical.indicators(b[:t+1]); 
        if not ind: continue
        tr=technical.trend(ind); r1,r5=fwd[s][d]; m1,m5=mkt[d]
        gap=b[t+1][1]/b[t][4]-1
        if ind["ret"]>=0.19 or gap>=0.19: continue  # ARA / gap limit: tidak bisa dibeli wajar
        rules=[]
        if tr=="up" and ind["rsi"]>70: rules.append(("uptrend+RSI>70",5))
        if tr=="down": rules.append(("downtrend",5))
        if ind["vr"]>=3 and ind["ret"]>=0.03: rules.append(("lonjakan volume",1))
        for name,h in rules:
            rel=(r5-m5) if h==5 else (r1-m1); raw=r5 if h==5 else r1
            itr,icol=state[d]
            half="H1" if d<"2026-01-01" else "H2"
            for key in ("semua","IHSG trend "+itr,"IHSG hari "+icol,half+" trend "+itr):
                ev[(name,key)].append((d,rel,raw))
def summ(x):
    byday=defaultdict(list)
    for d,rel,raw in x: byday[d].append((rel,raw))
    dm=[st.mean(v[0] for v in vs) for vs in byday.values()]
    dr=[st.mean(v[1] for v in vs) for vs in byday.values()]
    t=st.mean(dm)/(st.stdev(dm)/len(dm)**0.5) if len(dm)>2 and st.stdev(dm)>0 else float('nan')
    return len(x),len(dm),st.mean(dm)*100,t,st.mean(dr)*100
order=["H1 trend up","H1 trend down","H2 trend up","H2 trend down","semua","IHSG trend up","IHSG trend side","IHSG trend down","IHSG hari hijau","IHSG hari datar","IHSG hari merah"]
print("periode",idays[50],"s.d.",idays[-1]); print("kondisi IHSG 5 hari terakhir:",[(d,state[d]) for d in idays[-5:]])
from collections import Counter
print("hari per kondisi:",Counter(v[0] for v in state.values() if v),Counter(v[1] for v in state.values() if v))
for name in ("uptrend+RSI>70","downtrend","lonjakan volume"):
    print(f"\n== {name} ==   (n sinyal, n hari, relatif pasar, t, return mentah)")
    for k in order:
        x=ev.get((name,k))
        if not x: continue
        n,nd,m,t,raw=summ(x)
        print(f"  {k:18s} n={n:5d} hari={nd:3d}  rel={m:+.2f}%  t={t:+.1f}  mentah={raw:+.2f}%")
