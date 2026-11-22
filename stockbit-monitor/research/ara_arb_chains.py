"""Riset ARA/ARB dari data harian. Hari terkunci = O=H=L=C dengan |ret|>=5% (dideteksi dari
data, karena batas auto-reject BEI berubah-ubah selama periode)."""
import json,os,sys,collections,statistics as st
A,B,IH=sys.argv[1],sys.argv[2],sys.argv[3]
bars={}
for d in (B,A):
    for f in os.listdir(d):
        if not f.startswith("_"): bars[f[:-5]]=json.load(open(f"{d}/{f}"))
ih=json.load(open(IH)); ic={x[0]:x[4] for x in ih}; idays=sorted(ic)
def itrend(day):
    p=[ic[d] for d in idays if d<day]
    if len(p)<50: return None
    c,m20,m50=p[-1],sum(p[-20:])/20,sum(p[-50:])/50
    return "up" if c>m20>m50 else "down" if c<m20<m50 else "side"
def lock(b,i):
    o,h,l,c,v=b[i][1:]; p=b[i-1][4]
    if p<=0 or not(o==h==l==c): return 0
    r=c/p-1
    return 1 if r>=0.05 else -1 if r<=-0.05 else 0
def pct(x): return f"{x*100:+.1f}%"
dn_starts=[]; up_chains=[]
for s,b in bars.items():
    n=len(b)
    for i in range(21,n):
        L=lock(b,i)
        if L==-1 and lock(b,i-1)!=-1:
            j=i
            while j+1<n and lock(b,j+1)==-1: j+=1
            k=j-i+1
            base=b[i-1][4]
            val20=st.median(x[4]*x[5] for x in b[i-20:i])
            run20=b[i-1][4]/b[i-21][4]-1
            nxt=j+1
            rec=dict(s=s,day=b[i][0],len=k,complete=nxt<n,val20=val20,run20=run20,ihsg=itrend(b[i][0]),
                     lock_loss=b[j][4]/base-1)
            if nxt<n:
                rec["exit_open"]=b[nxt][1]/base-1          # jual paling cepat: open hari pertama tidak terkunci
                rec["reb1"]=b[nxt][4]/b[nxt][1]-1           # beli open hari lepas kunci -> close hari itu
                if nxt+5<n: rec["reb5"]=b[nxt+5][4]/b[nxt][1]-1
            dn_starts.append(rec)
        if L==1 and lock(b,i-1)!=1:
            j=i
            while j+1<n and lock(b,j+1)==1: j+=1
            k=j-i+1; nxt=j+1
            if nxt<n:
                rec=dict(s=s,day=b[i][0],len=k,val20=st.median(x[4]*x[5] for x in b[i-20:i]),ihsg=itrend(b[i][0]))
                rec["d1"]=b[nxt][4]/b[nxt][1]-1             # beli open hari pertama lepas kunci -> close
                if nxt+5<n: rec["d5"]=b[nxt+5][4]/b[nxt][1]-1
                up_chains.append(rec)
def chain_stats(ev,label):
    lens=collections.Counter(min(e["len"],5) for e in ev)
    tot=len(ev); ge2=sum(e["len"]>=2 for e in ev); ge3=sum(e["len"]>=3 for e in ev)
    print(f"  {label}: n={tot}  P(>=2 hari)={ge2/tot*100:.0f}%  P(>=3)={ge3/tot*100:.0f}%  panjang {dict(sorted(lens.items()))}")
print("== RENTETAN ARB (kunci bawah) ==")
liq=[e for e in dn_starts if e["val20"]>=1e9]; ill=[e for e in dn_starts if e["val20"]<1e9]
chain_stats(dn_starts,"semua"); chain_stats(liq,"likuid (nilai>=Rp1M/hari)"); chain_stats(ill,"tidak likuid")
for lab,g in (("run-up 20h >= +30%",[e for e in liq if e["run20"]>=0.30]),("run-up 20h +10..30%",[e for e in liq if 0.10<=e["run20"]<0.30]),("run-up 20h < +10%",[e for e in liq if e["run20"]<0.10])):
    if g: chain_stats(g,"likuid, "+lab)
for reg in ("up","side","down"):
    g=[e for e in liq if e["ihsg"]==reg]
    if g: chain_stats(g,f"likuid, IHSG {reg}")
c=[e for e in liq if "exit_open" in e]
print(f"  likuid: rugi s.d. bisa jual (open hari pertama lepas kunci, dari close sebelum ARB pertama): median {pct(st.median(e['exit_open'] for e in c))}, terburuk 10% {pct(sorted(e['exit_open'] for e in c)[len(c)//10])}")
for k in (1,2,3):
    g=[e for e in c if (e['len']==k if k<3 else e['len']>=3)]
    if g: print(f"    rentetan {k}{'+' if k==3 else ''} hari: n={len(g)} rugi median {pct(st.median(e['exit_open'] for e in g))}")
r1=[e["reb1"] for e in c]; r5=[e["reb5"] for e in c if "reb5" in e]
print(f"  likuid: beli di open hari lepas kunci -> close hari itu: median {pct(st.median(r1))} rata2 {pct(st.mean(r1))} naik {sum(x>0 for x in r1)/len(r1)*100:.0f}% ; -> 5 hari: rata2 {pct(st.mean(r5))} naik {sum(x>0 for x in r5)/len(r5)*100:.0f}%")
print("\n== RENTETAN ARA (kunci atas) ==")
lu=[e for e in up_chains if e["val20"]>=1e9]
chain_stats(up_chains,"semua"); chain_stats(lu,"likuid")
for k in (1,2,3):
    g=[e for e in lu if (e['len']==k if k<3 else e['len']>=3)]
    if g:
        d1=[e["d1"] for e in g]; d5=[e["d5"] for e in g if "d5" in e]
        print(f"  likuid, sesudah {k}{'+' if k==3 else ''} hari ARA: beli open hari lepas kunci -> close: rata2 {pct(st.mean(d1))} naik {sum(x>0 for x in d1)/len(d1)*100:.0f}% ; 5 hari rata2 {pct(st.mean(d5)) if d5 else '-'} (n={len(g)})")
json.dump({"dn":dn_starts,"up":up_chains},open(sys.argv[4],"w"))
