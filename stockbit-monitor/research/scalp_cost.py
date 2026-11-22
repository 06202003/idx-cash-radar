import json,os,sys,statistics as st
sys.path.insert(0,'/home/testing-bcai/stockbit-monitor'); from papertrade import tick
D=sys.argv[1]; FEES=0.004
rows=[]
for f in os.listdir(D):
    if f.startswith("_"): continue
    b=json.load(open(f"{D}/{f}"))[-60:]
    if len(b)<40: continue
    c=b[-1][4]
    rng=[(x[2]-x[3])/x[4] for x in b if x[4]>0]
    val=sorted(x[4]*x[5] for x in b[-20:])[10]
    t=tick(c)/c
    be=t+FEES   # balik modal: lewati spread 1 tick + fee beli 0,15% & jual 0,25%
    mr=st.median(rng)
    rows.append(dict(s=f[:-5],c=c,tick=t,be=be,rng=mr,ratio=be/mr if mr>0 else 99,val=val))
rows.sort(key=lambda r:r['ratio'])
bands=[(0,200),(200,500),(500,2000),(2000,5000),(5000,1e9)]
print("n saham",len(rows))
print("Per pita harga: tick%, titik impas, median range harian, rasio impas/range")
for lo,hi in bands:
    g=[r for r in rows if lo<=r['c']<hi]
    if g: print(f"  Rp{lo:>5}-{hi if hi<1e9 else '∞':>5}: n={len(g):3d} tick {st.median(r['tick'] for r in g)*100:.2f}%  impas {st.median(r['be'] for r in g)*100:.2f}%  range {st.median(r['rng'] for r in g)*100:.1f}%  rasio {st.median(r['ratio'] for r in g):.2f}")
liq=[r for r in rows if r['val']>=10e9]
print("\nLikuid (median nilai 20h >= Rp10 M):",len(liq))
print("Paling layak (rasio impas/range terkecil):")
for r in liq[:15]: print(f"  {r['s']:5} Rp{r['c']:>6.0f} tick {r['tick']*100:.2f}% impas {r['be']*100:.2f}% range {r['rng']*100:.1f}% rasio {r['ratio']:.2f} nilai {r['val']/1e9:.0f}M")
print("Paling tidak layak (likuid tapi rasio besar):")
for r in liq[-8:]: print(f"  {r['s']:5} Rp{r['c']:>6.0f} tick {r['tick']*100:.2f}% impas {r['be']*100:.2f}% range {r['rng']*100:.1f}% rasio {r['ratio']:.2f} nilai {r['val']/1e9:.0f}M")
print("\nSemua rasio: >=0.5:",sum(r['ratio']>=0.5 for r in rows)," 0.25-0.5:",sum(0.25<=r['ratio']<0.5 for r in rows)," <0.25:",sum(r['ratio']<0.25 for r in rows))
json.dump(rows,open(sys.argv[2],"w"))
