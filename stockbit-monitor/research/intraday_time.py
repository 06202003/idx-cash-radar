"""Riset jam intraday (2026-11-22). Bar 5 menit Yahoo ±60 hari, saham likuid (median nilai 20h
>= Rp1 M) & harga >= Rp50. Argumen: dir_m5. Semua jam WIB. t-stat per hari bursa.
Slot: '09:00' = bar 09:00-09:05. Bar 16:00 = lelang penutupan (pre-closing)."""
import json,os,sys,statistics as st,collections
from datetime import datetime,timezone,timedelta
sys.path.insert(0,'/home/testing-bcai/stockbit-monitor'); from papertrade import tick
W=timezone(timedelta(hours=7)); D=sys.argv[1]
def load(f):
    days=collections.defaultdict(list)
    for t,o,h,l,c,v in json.load(open(f"{D}/{f}")):
        dt=datetime.fromtimestamp(t,W); days[dt.strftime("%Y-%m-%d")].append((dt.strftime("%H:%M"),o,h,l,c,v))
    return days
def tstat(by):
    d=[st.mean(v) for v in by.values() if v]
    if len(d)<3 or st.stdev(d)==0: return None,None,len(d)
    return st.mean(d), st.mean(d)/(st.stdev(d)/len(d)**.5), len(d)
slot_rng=collections.defaultdict(list); slot_ret=collections.defaultdict(lambda: collections.defaultdict(list))
slot_val=collections.defaultdict(list); slot_be=collections.defaultdict(list)
o30=[]; auc=collections.defaultdict(list); lunch=collections.defaultdict(list)
for f in os.listdir(D):
    if f.startswith("_"): continue
    for day,bars in load(f).items():
        bars=[b for b in bars if b[0]<="16:00"]
        if len(bars)<40: continue
        tot=sum(b[4]*b[5] for b in bars)
        if tot<=0: continue
        op=bars[0][1]; prev=op
        for hm,o,h,l,c,v in bars:
            if c<=0: continue
            slot_rng[hm].append((h-l)/c); slot_val[hm].append(c*v/tot)
            slot_be[hm].append((h-l)/c/(tick(c)/c+0.004))
            slot_ret[hm][day].append(c/prev-1); prev=c
        m={b[0]:b for b in bars}
        if "09:25" in m and "15:45" in m and "16:00" in m:
            a=m["09:25"][4]/op-1; r=m["15:45"][4]/m["09:25"][4]-1
            o30.append((day,a,r))
            auc[day].append(m["16:00"][4]/m["15:45"][4]-1)
        s1=[b for b in bars if b[0]<"12:00"]; s2=[b for b in bars if b[0]>="13:30"]
        if s1 and s2: lunch[day].append(s2[0][1]/s1[-1][4]-1)
print("== Per slot: range 5 mnt (median), range/titik impas (median), porsi nilai harian, arah rata2 [t] ==")
key=["09:00","09:05","09:10","09:15","09:30","10:00","10:30","11:00","11:30","11:55","13:30","13:35","14:00","14:30","15:00","15:30","15:45","16:00"]
for hm in key:
    if hm not in slot_rng: continue
    m,t,n=tstat(slot_ret[hm])
    print(f"  {hm}  range {st.median(slot_rng[hm])*100:.2f}%  range/impas {st.median(slot_be[hm]):.2f}  porsi nilai {st.mean(slot_val[hm])*100:4.1f}%  arah {m*100:+.3f}% [t {t:+.1f}]")
print("\n== Kumulatif porsi nilai transaksi ==")
cum=0
for hm in sorted(slot_val):
    cum+=st.mean(slot_val[hm])
    if hm in ("09:25","10:00","11:00","11:55","14:00","15:00","15:45","16:00"): print(f"  s.d. {hm}: {cum*100:.0f}%")
print("\n== 30 menit pertama (open->09:30) vs sisa hari (09:30->15:50), dibanding saham lain hari yg sama ==")
byday=collections.defaultdict(list)
for d,a,r in o30: byday[d].append((a,r))
q=collections.defaultdict(lambda: collections.defaultdict(list))
for d,v in byday.items():
    if len(v)<50: continue
    v=sorted(v); n=len(v); mr=st.mean(r for _,r in v)
    for i,(a,r) in enumerate(v): q[i*5//n][d].append(r-mr)
for k in range(5):
    m,t,n=tstat(q[k]); print(f"  kuintil {k+1} ({'paling turun' if k==0 else 'paling naik' if k==4 else ''}) sisa hari vs rata2: {m*100:+.2f}% [t {t:+.1f}] ({n} hari)")
m,t,n=tstat(auc); print(f"\n== Lelang penutupan (15:50->16:00) rata2: {m*100:+.3f}% [t {t:+.1f}] ({n} hari)")
m,t,n=tstat(lunch); print(f"== Lintas istirahat (close sesi 1 -> open sesi 2) rata2: {m*100:+.3f}% [t {t:+.1f}] ({n} hari)")
