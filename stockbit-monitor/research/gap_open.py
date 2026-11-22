"""Riset gap pembukaan (2026-11-22). Data harian Yahoo; argumen: dir_2tahun dir_1tahun ihsg.json
Kelompok dibentuk dari gap = open/close kemarin − 1 (diketahui saat open). Hasil:
  oc  = beli open +1 tick, jual close −1 tick, fee 0,4% (hari terkunci ARA = tidak terisi; terkunci ARB
        = baru bisa jual di open besok)
  hold = return open->close tanpa biaya (sudut pandang pemegang barang: jual di open vs tahan s.d. close)
  rel = oc dikurangi rata-rata open->close semua saham hari itu (buang efek pasar)
t-stat per hari bursa (bukan per kejadian)."""
import json,os,sys,statistics as st,collections
sys.path.insert(0,'/home/testing-bcai/stockbit-monitor'); from papertrade import tick, net_return
A,B,IH=sys.argv[1],sys.argv[2],sys.argv[3]
bars={}
for d in (B,A):
    for f in os.listdir(d):
        if not f.startswith("_"): bars[f[:-5]]=json.load(open(f"{d}/{f}"))
ih={x[0]:x for x in json.load(open(IH))}; idays=sorted(ih)
def itrend(day):
    p=[ih[d][4] for d in idays if d<day]
    if len(p)<50: return None
    c,m20,m50=p[-1],sum(p[-20:])/20,sum(p[-50:])/50
    return "up" if c>m20>m50 else "down" if c<m20<m50 else "side"
TR={d:itrend(d) for d in idays}
IHGAP={d:(ih[d][1]/ih[idays[i-1]][4]-1) for i,d in enumerate(idays) if i>0}
rows=[]; daymean=collections.defaultdict(list)
for s,b in bars.items():
    for i in range(21,len(b)-1):
        pc=b[i-1][4]; o,h,l,c,v=b[i][1:]
        if pc<=0 or o<=0: continue
        gap=o/pc-1
        val20=st.median(x[4]*x[5] for x in b[i-20:i])
        locked=(o==h==l==c)
        hold=c/o-1
        daymean[b[i][0]].append(hold)
        if locked and c>pc: oc=None                       # ARA terkunci: beli tidak terisi
        elif locked and c<pc: x=b[i+1][1]; oc=net_return("LONG",o+tick(o),x-tick(x))  # ARB: jual besok open
        else: oc=net_return("LONG",o+tick(o),c-tick(c))
        rows.append(dict(s=s,day=b[i][0],gap=gap,oc=oc,hold=hold,liq=val20>=1e9,big=val20>=10e9,
                         px=o,ih=TR.get(b[i][0]),ihgap=IHGAP.get(b[i][0])))
dm={d:st.mean(v) for d,v in daymean.items() if len(v)>=50}
for r in rows: r["rel"]=(r["oc"]-dm[r["day"]]) if r["oc"] is not None and r["day"] in dm else None
def stat(rs,k):
    by=collections.defaultdict(list)
    for r in rs:
        if r[k] is not None: by[r["day"]].append(r[k])
    d=[st.mean(v) for v in by.values()]
    if len(d)<3: return None
    return st.mean(d), st.mean(d)/(st.stdev(d)/len(d)**.5) if st.stdev(d)>0 else 0, len(d)
B_=[(-1,-0.05,"≤ −5%"),(-0.05,-0.02,"−5..−2%"),(-0.02,-0.005,"−2..−0,5%"),(-0.005,0.005,"±0,5%"),(0.005,0.02,"+0,5..+2%"),(0.02,0.05,"+2..+5%"),(0.05,9,"≥ +5%")]
def table(lab,rs):
    print(f"\n== {lab} ==  (n, hari, beli open→close bersih [t], relatif pasar [t], pemegang open→close mentah, tidak terisi)")
    for lo,hi,name in B_:
        g=[r for r in rs if lo<r["gap"]<=hi] if lo>-1 else [r for r in rs if r["gap"]<=hi]
        if len(g)<30: continue
        a,b_,c=stat(g,"oc"),stat(g,"rel"),stat(g,"hold")
        unf=sum(r["oc"] is None for r in g)/len(g)
        print(f"  gap {name:10s} n={len(g):6d} hari={a[2]:3d}  bersih {a[0]*100:+.2f}% [{a[1]:+.1f}]  rel {b_[0]*100:+.2f}% [{b_[1]:+.1f}]  pemegang {c[0]*100:+.2f}%  tdk terisi {unf*100:.0f}%")
liq=[r for r in rows if r["liq"] and r["px"]>=50]
print("periode",min(r["day"] for r in rows),"s.d.",max(r["day"] for r in rows),"| baris",len(rows),"| likuid&>=Rp50",len(liq))
table("likuid (≥Rp1 M/hari), harga ≥ Rp50",liq)
table("sangat likuid (≥Rp10 M/hari)",[r for r in liq if r["big"]])
table("likuid, paruh 1 (<2026-01)",[r for r in liq if r["day"]<"2026-01-01"])
table("likuid, paruh 2",[r for r in liq if r["day"]>="2026-01-01"])
for reg in ("up","side","down"): table(f"likuid, IHSG tren {reg}",[r for r in liq if r["ih"]==reg])
table("likuid, IHSG sendiri buka gap ≤ −1%",[r for r in liq if r["ihgap"] is not None and r["ihgap"]<=-0.01])
table("likuid, IHSG buka gap ≥ +1%",[r for r in liq if r["ihgap"] is not None and r["ihgap"]>=0.01])
