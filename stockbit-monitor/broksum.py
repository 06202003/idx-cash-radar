"""Broker summary (broksum) harian per saham dari Stockbit + rekap sore.

Running trade nggak ada kode broker, jadi alert lonjakan nggak bisa bilang SIAPA yang
beli/jual. Broksum bisa -- tapi baru lengkap setelah bursa tutup. Modul ini:
  - ambil broksum 1 saham 1 hari, diringkas (top-5 akum/distribusi, net ritel, net asing,
    net per broker), disimpan di data/broksum/TANGGAL.json biar nggak perlu ditarik ulang
  - hitung "akumulator 5 hari": 3 broker dengan net beli terbesar 5 hari bursa sebelumnya,
    lalu lihat hari ini mereka masih beli atau malah jualan
  - hitung "konsentrasi 10 hari": berapa persen nilai transaksi 10 hari yang diserap
    3 broker net beli terbesar (= siapa penggerak/penampungnya)
  - susun rekap sore buat saham yang paling sering kena alert hari itu
  - screening "dijaga & sepi": saham likuid yang konsentrasinya tinggi tapi harga belum gerak

Angka "historis" di teks penilaian = hasil studi 9.156 saham-hari (16 Sep - 13 Nov 2026,
216 saham likuid, return relatif pasar, di luar hari ARA/ARB). Satu periode, pasar lagi
turun -- panduan, bukan kepastian. Daftar broker ritel di bawah klasifikasi sendiri.

Soal "akumulasi diam-diam": di data itu konsentrasi tinggi TIDAK menaikkan peluang saham
ngacir (peluang naik >=10% dalam 10 hari malah sedikit lebih rendah dari rata-rata). Yang
terbukti: saham terkonsentrasi lebih TAHAN TURUN (+3,4% vs pasar per 10 hari, tapi secara
absolut masih minus waktu pasar anjlok), dan efeknya hilang waktu pasar lagi naik kencang.
Jadi screening di sini = daftar saham yang ada penjaganya, bukan ramalan kapan terbang.

PERINGATAN: endpoint internal Stockbit, sama seperti running trade.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime, timedelta

log = logging.getLogger("broksum")

RETAIL_BROKERS = {"YP", "PD", "XC", "XL", "CC", "NI", "KK", "EP", "SQ", "CP", "AZ", "GR", "DR", "IF", "AI", "BQ"}

PRIOR_DAYS = 5  # jendela "akumulator 5 hari"
CONC_DAYS = 10  # jendela konsentrasi (termasuk hari ini)
CONC_MIN_DAYS = 8
CONC_HIGH = 0.45  # top-3 net beli >= 45% nilai 10 hari = terkonsentrasi/dijaga
CONC_LOW = 0.20  # < 20% = pembeli menyebar
QUIET_MOVE = 0.03  # "sepi": gerak harga 10 hari relatif pasar maksimal segini
QUIET_VALUE_RATIO = 1.2  # ...dan rata-rata nilai transaksi maksimal segini x biasanya
MIN_PRIOR_DAYS = 3  # minimal histori biar akumulator bisa dinilai
ADV_MAX_DAYS = 20


def _path(day: str) -> str:
    return f"/marketdetectors/{{sym}}?from={day}&to={day}&transaction_type=TRANSACTION_TYPE_NET" \
           "&market_board=MARKET_BOARD_REGULER&investor_type=INVESTOR_TYPE_ALL&limit=25"


def parse(payload: dict) -> dict | None:
    """Respons mentah -> ringkasan kecil. None kalau hari itu nggak ada transaksi/data."""
    d = (payload or {}).get("data") or {}
    bd = d.get("bandar_detector") or {}
    bs = d.get("broker_summary") or {}
    val = float(bd.get("value") or 0)
    if val <= 0:
        return None
    net: dict[str, float] = {}
    foreign = 0.0
    for side, key in (("brokers_buy", "bval"), ("brokers_sell", "sval")):
        for x in bs.get(side) or []:
            code = x.get("netbs_broker_code") or "?"
            v = float(x.get(key) or 0)
            net[code] = net.get(code, 0.0) + v
            if x.get("type") == "Asing":
                foreign += v
    top5 = bd.get("top5") or {}
    return {
        "val": val,
        "avg": float(bd.get("average") or 0),  # harga rata-rata hari itu
        "top5": float(top5.get("percent") or 0),  # % nilai; + = akumulasi, - = distribusi
        "acc5": top5.get("accdist") or "",
        "retail": sum(v for c, v in net.items() if c in RETAIL_BROKERS) / val,
        "foreign": foreign / val,
        "net": {c: round(v) for c, v in net.items()},
    }


class BroksumStore:
    """Cache broksum per hari di disk: data/broksum/YYYY-MM-DD.json -> {saham: ringkasan|null}."""

    def __init__(self, base_dir: str):
        self.dir = os.path.join(base_dir, "broksum")
        self.adv_path = os.path.join(base_dir, "adv.json")
        os.makedirs(self.dir, exist_ok=True)
        self._days: dict[str, dict] = {}
        self.adv: dict[str, float] = {}
        try:
            with open(self.adv_path, encoding="utf-8") as f:
                self.adv = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass

    def _load_day(self, day: str) -> dict:
        if day not in self._days:
            try:
                with open(os.path.join(self.dir, f"{day}.json"), encoding="utf-8") as f:
                    self._days[day] = json.load(f)
            except (OSError, json.JSONDecodeError):
                self._days[day] = {}
        return self._days[day]

    def _save_day(self, day: str) -> None:
        path = os.path.join(self.dir, f"{day}.json")
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._days[day], f)
        os.replace(tmp, path)

    def has(self, sym: str, day: str) -> bool:
        return sym in self._load_day(day)

    def get(self, sym: str, day: str) -> dict | None:
        return self._load_day(day).get(sym)

    def put(self, sym: str, day: str, row: dict | None) -> None:
        self._load_day(day)[sym] = row
        self._save_day(day)

    def fetch(self, auth, sym: str, day: str, final: bool = True) -> dict | None:
        """Tarik 1 saham 1 hari (blocking). final=False -> jangan disimpan (data hari
        berjalan belum lengkap)."""
        resp = auth._authed_get(_path(day).format(sym=sym))
        resp.raise_for_status()
        row = parse(resp.json())
        if final:
            self.put(sym, day, row)
        return row

    def ensure(self, auth, sym: str, days: list[str]) -> int:
        """Lengkapi cache buat hari-hari yang belum ada. Return jumlah request."""
        n = 0
        for day in days:
            if self.has(sym, day):
                continue
            self.fetch(auth, sym, day)
            n += 1
            time.sleep(random.uniform(1.0, 1.8))  # pelan-pelan, jangan kayak robot
        return n

    def update_adv(self, sym: str, days: list[str]) -> None:
        vals = [r["val"] for r in (self.get(sym, d) for d in days[-ADV_MAX_DAYS:]) if r]
        if vals:
            self.adv[sym] = sum(vals) / len(vals)

    def save_adv(self) -> None:
        tmp = f"{self.adv_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.adv, f)
        os.replace(tmp, self.adv_path)


def prior_trading_days(day: str, n: int, is_trading_day) -> list[str]:
    """n hari bursa SEBELUM `day` (urut lama -> baru)."""
    out = []
    d = datetime.strptime(day, "%Y-%m-%d")
    for _ in range(n * 4 + 10):
        d -= timedelta(days=1)
        if is_trading_day(d):
            out.append(d.strftime("%Y-%m-%d"))
            if len(out) == n:
                break
    return out[::-1]


def accumulators(store: BroksumStore, sym: str, prior_days: list[str], today_row: dict) -> dict | None:
    """3 broker net beli terbesar di prior_days, dan apa yang mereka lakukan hari ini.
    None kalau histori kurang dari MIN_PRIOR_DAYS."""
    rows = [r for r in (store.get(sym, d) for d in prior_days) if r]
    if len(rows) < MIN_PRIOR_DAYS:
        return None
    cum: dict[str, float] = {}
    tv = 0.0
    for r in rows:
        tv += r["val"]
        for c, v in r["net"].items():
            cum[c] = cum.get(c, 0.0) + v
    top = [(c, v) for c, v in sorted(cum.items(), key=lambda kv: -kv[1])[:3] if v > 0]
    if not top or tv <= 0:
        return None
    return {
        "codes": [c for c, _ in top],
        "inv": sum(v for _, v in top) / tv,  # akumulasi mereka 5 hari / nilai transaksi 5 hari
        "today": sum(today_row["net"].get(c, 0) for c, _ in top) / today_row["val"],
        "n_days": len(rows),
    }


def concentration(store: BroksumStore, sym: str, days: list[str]) -> dict | None:
    """Top-3 broker net beli kumulatif di `days` (hari ini termasuk) dibanding nilai transaksi.
    Ini jawaban "siapa penggeraknya": broker yang paling banyak nampung barang."""
    rows = [r for r in (store.get(sym, d) for d in days) if r]
    if len(rows) < CONC_MIN_DAYS:
        return None
    cum: dict[str, float] = {}
    tv = sum(r["val"] for r in rows)
    for r in rows:
        for c, v in r["net"].items():
            cum[c] = cum.get(c, 0.0) + v
    ranked = sorted(cum.items(), key=lambda kv: -kv[1])
    top = [(c, v) for c, v in ranked[:3] if v > 0]
    if not top or tv <= 0:
        return None
    first, last = rows[0].get("avg") or 0, rows[-1].get("avg") or 0
    return {
        "conc": sum(v for _, v in top) / tv,
        "buyers": top,
        "sellers": [(c, -v) for c, v in ranked[::-1][:3] if v < 0],
        "n_days": len(rows),
        "avg_val": tv / len(rows),
        "move": last / first - 1 if first > 0 and last > 0 else None,  # gerak harga rata-rata selama jendela
    }


def assess(row: dict, acc: dict | None, n_buy: int = 0, n_sell: int = 0,
           conc: dict | None = None) -> list[tuple[int, str]]:
    """Daftar (skor, teks). Skor < 0 = sinyal jelek, > 0 = sinyal bagus."""
    out = []
    if conc and conc["conc"] >= CONC_HIGH:
        out.append((2, "🛡️ Dijaga — 3 broker serap 45%+ nilai 10 hari. Historis +3,4% vs pasar per 10 hari "
                       "(lebih tahan turun, bukan tanda mau ngacir)"))
    elif conc and conc["conc"] < CONC_LOW:
        out.append((-1, "🌫️ Tanpa penampung — pembeli menyebar 10 hari terakhir. Historis −1,4% vs pasar "
                        "per 10 hari"))
    buy_dom = (n_buy + n_sell) >= 3 and n_buy >= 2 * n_sell
    retail, top5 = row["retail"], row["top5"]
    a_today = acc["today"] if acc else None

    if a_today is not None and a_today < -0.05 and retail > 0.05:
        out.append((-3, "🚪 Akumulator jualan — ritel yang nampung. Historis −1,1% dalam 5 hari"))
    elif a_today is not None and a_today < -0.02:
        out.append((-2, "🚪 Akumulator mulai jualan — historis −0,6% dalam 5 hari"))
    elif a_today is not None and a_today > 0.25:
        out.append((2, "🟢 Akumulator masih beli — historis +0,7% dalam 5 hari"))

    if buy_dom and top5 <= -10:
        out.append((-3, "⛔ HAKA palsu — alert beli dominan tapi top-5 broker distribusi. Historis −0,85% besok, −1,9% dalam 5 hari"))
    elif buy_dom and retail > 0.05:
        out.append((-3, "⛔ HAKA ritel — alert beli dominan dan pembelinya ritel. Historis −1,7% dalam 5 hari"))
    elif buy_dom:
        out.append((-1, "⚠️ Alert beli dominan — historis −0,6% besok walau broksum netral/akumulasi"))

    if retail > 0.15:
        out.append((-1, "👥 Ritel menampung — historis −0,2% besok, −0,4% dalam 5 hari"))
    elif retail < -0.15:
        out.append((1, "👥 Ritel melepas — barang pindah ke non-ritel. Historis +0,4% besok, +0,5% dalam 5 hari"))
    return out


def _pct(x: float) -> str:
    return f"{x * 100:+.0f}%"


def _rp(v: float) -> str:
    if abs(v) >= 1e12:
        return f"Rp{v / 1e12:.1f} T".replace(".", ",")
    if abs(v) >= 1e9:
        return f"Rp{v / 1e9:.1f} M".replace(".", ",")
    return f"Rp{v / 1e6:.0f} jt"


TOP5_LABEL = {"Big Acc": "akumulasi besar", "Acc": "akumulasi", "Neutral": "netral", "Dist": "distribusi",
              "Big Dist": "distribusi besar"}


def _bold_label(text: str) -> str:
    label, sep, desc = text.partition(" — ")
    icon, space, name = label.partition(" ")
    return f"{icon} <b>{name}</b> — {desc}" if sep and space else text


def format_stock(sym: str, row: dict, acc: dict | None, verdicts: list[tuple[int, str]],
                 n_buy: int = 0, n_sell: int = 0, detail: bool = False, conc: dict | None = None,
                 tech: str = "") -> str:
    """Blok 1 saham: penilaian dulu (yang perlu dibaca), angka pendukung di bawahnya (miring)."""
    head = f"<b>{sym}</b>"
    if n_buy or n_sell:
        head += f"  ·  alert {n_buy} beli / {n_sell} jual"
    lines = [head]
    lines += [_bold_label(t) for _, t in verdicts] or ["➖ Tidak ada sinyal broksum yang teruji"]
    if detail:
        lines.append("")
    facts = [f"Nilai {_rp(row['val'])} · top-5 {TOP5_LABEL.get(row['acc5'], row['acc5'] or '-')} · "
             f"ritel {_pct(row['retail'])} · asing {_pct(row['foreign'])}"]
    if conc:
        amount = (lambda c, v: f"{c} {_rp(v)}") if detail else (lambda c, v: c)
        line = (f"Penggerak {conc['n_days']} hari: " + ", ".join(amount(c, v) for c, v in conc["buyers"])
                + f" (serap {conc['conc'] * 100:.0f}% nilai)")
        if conc["sellers"]:
            line += " · lawan " + ", ".join(amount(c, v) for c, v in conc["sellers"])
        facts.append(line)
    if acc and detail:
        facts.append(f"Akumulator {acc['n_days']} hari: {', '.join(acc['codes'])} · hari ini {_pct(acc['today'])}")
    if detail:
        net = sorted(row["net"].items(), key=lambda kv: -kv[1])
        buyers = ", ".join(f"{c} {_rp(v)}" for c, v in net[:5] if v > 0)
        sellers = ", ".join(f"{c} {_rp(-v)}" for c, v in net[::-1][:5] if v < 0)
        facts.append(f"Beli hari ini: {buyers or '-'}")
        facts.append(f"Jual hari ini: {sellers or '-'}")
    if tech:
        facts.append(f"Teknikal: {tech}")
    if detail:
        return "\n".join(lines + facts)
    return "\n".join(lines + [f"<i>{f}</i>" for f in facts])


def lookup(store: BroksumStore, auth, sym: str, day: str, is_trading_day, final: bool,
           n_buy: int = 0, n_sell: int = 0, detail: bool = False, tech: str = "") -> tuple[str | None, int]:
    """Tarik + nilai 1 saham. Return (teks | None kalau nggak ada data, skor terendah/tertinggi)."""
    row = store.get(sym, day) if store.has(sym, day) else store.fetch(auth, sym, day, final=final)
    if not row:
        return None, 0
    prior = prior_trading_days(day, CONC_DAYS - 1, is_trading_day)
    store.ensure(auth, sym, prior)
    acc = accumulators(store, sym, prior[-PRIOR_DAYS:], row)
    conc = _concentration_with_today(store, sym, prior, day, row)
    if final:
        store.update_adv(sym, prior_trading_days(day, ADV_MAX_DAYS - 1, is_trading_day) + [day])
    verdicts = assess(row, acc, n_buy, n_sell, conc)
    score = sum(s for s, _ in verdicts)
    return format_stock(sym, row, acc, verdicts, n_buy, n_sell, detail, conc, tech), score


def _concentration_with_today(store: BroksumStore, sym: str, prior: list[str], day: str, row: dict) -> dict | None:
    """Sama seperti concentration(), tapi baris hari ini boleh belum tersimpan (hari berjalan)."""
    if store.has(sym, day):
        return concentration(store, sym, prior + [day])
    store._load_day(day)[sym] = row  # cuma di memori, nggak di-save
    try:
        return concentration(store, sym, prior + [day])
    finally:
        del store._load_day(day)[sym]


def build_screen(store: BroksumStore, auth, day: str, universe: list[str], is_trading_day,
                 top_n: int = 10) -> list[str]:
    """Screening sore (blocking, ~5 menit kalau cache hari ini masih kosong): saham likuid
    yang terkonsentrasi DAN masih sepi. Return daftar pesan Telegram."""
    days = prior_trading_days(day, CONC_DAYS - 1, is_trading_day) + [day]
    fails = 0
    for sym in universe:
        if store.has(sym, day):
            continue
        try:
            store.fetch(auth, sym, day)
        except Exception as e:  # noqa: BLE001
            log.warning("Screening: broksum %s gagal: %s", sym, e)
            fails += 1
            if fails >= 8:  # kemungkinan diblok/sesi habis -- berhenti, jangan maksa
                break
        time.sleep(random.uniform(1.0, 1.8))

    cands = []
    for sym in universe:
        c = concentration(store, sym, days)
        if c and c["move"] is not None:
            store.update_adv(sym, prior_trading_days(day, ADV_MAX_DAYS - 1, is_trading_day) + [day])
            cands.append((sym, c))
    store.save_adv()
    if len(cands) < 30:
        return [f"🛡️ <b>Dijaga dan masih sepi</b> · {day}\nData broksum belum cukup ({len(cands)} saham)."
                + (f" {fails} gagal ditarik." if fails else "")]
    mkt_move = sum(c["move"] for _, c in cands) / len(cands)
    prev_days = prior_trading_days(day, CONC_DAYS, is_trading_day)
    picks = []
    for sym, c in cands:
        adv = store.adv.get(sym) or c["avg_val"]
        rel = c["move"] - mkt_move
        if c["conc"] >= CONC_HIGH and abs(rel) <= QUIET_MOVE and c["avg_val"] <= QUIET_VALUE_RATIO * adv:
            prev = concentration(store, sym, prev_days)
            today = store.get(sym, day)
            now_net = sum(today["net"].get(code, 0) for code, _ in c["buyers"]) / today["val"] if today else 0.0
            picks.append((c["conc"], sym, c, rel, bool(prev and prev["conc"] < CONC_HIGH), now_net))
    picks.sort(reverse=True)
    n_high = sum(1 for _, c in cands if c["conc"] >= CONC_HIGH)
    lines = [
        f"🛡️ <b>Dijaga dan masih sepi</b> · {day}",
        f"{len(picks)} lolos dari {len(cands)} saham ({n_high} dijaga)",
    ]
    for conc, sym, c, rel, is_new, now_net in picks[:top_n]:
        today_word = "masih beli" if now_net > 0.05 else "jualan" if now_net < -0.05 else "diam"
        lines += [
            "",
            f"<b>{sym}</b>{' 🆕' if is_new else ''}  ·  " + ", ".join(code for code, _ in c["buyers"])
            + f" serap {conc * 100:.0f}%",
            f"<i>harga {rel * 100:+.0f}% vs pasar · hari ini mereka {today_word} ({_pct(now_net)})</i>".replace("-0%", "0%").replace("+0%", "0%"),
        ]
    if not picks:
        lines += ["", "Tidak ada yang lolos hari ini."]
    lines += [
        "",
        "<i>Dijaga = 3 broker serap 45%+ nilai 10 hari. Sepi = harga ±3% vs pasar, volume normal. "
        "Historis lebih tahan turun (+4,1% vs pasar per 10 hari), bukan lebih sering ngacir. "
        "🆕 baru masuk hari ini.</i>",
    ]
    return ["\n".join(lines)]


def build_recap(store: BroksumStore, auth, day: str, alert_counts: dict[str, dict[str, int]],
                is_trading_day, min_alerts: int = 3, max_stocks: int = 25, tech_line=None) -> list[str]:
    """Rekap sore (blocking, bisa beberapa menit). Return daftar pesan Telegram."""
    cands = sorted(
        ((s, c.get("buy", 0), c.get("sell", 0)) for s, c in alert_counts.items()
         if c.get("buy", 0) + c.get("sell", 0) >= min_alerts),
        key=lambda t: -(t[1] + t[2]),
    )[:max_stocks]
    if not cands:
        return [f"📒 <b>Rekap broksum</b> · {day}\nTidak ada saham dengan {min_alerts}+ alert hari ini."]

    scored, skipped = [], 0
    for sym, n_buy, n_sell in cands:
        try:
            tech = tech_line(sym) if tech_line else ""
            text, score = lookup(store, auth, sym, day, is_trading_day, True, n_buy, n_sell, tech=tech)
        except Exception as e:  # noqa: BLE001
            log.warning("Broksum %s gagal: %s", sym, e)
            skipped += 1
            if skipped >= 5:
                break
            continue
        if text:
            scored.append((score, text))
        time.sleep(random.uniform(1.0, 1.8))
    store.save_adv()

    bad = [t for s, t in sorted(scored, key=lambda x: x[0]) if s < 0]
    good = [t for s, t in sorted(scored, key=lambda x: -x[0]) if s > 0]
    flat = len(scored) - len(bad) - len(good)
    msgs = []
    header = (f"📒 <b>Rekap broksum</b> · {day}\n"
              f"{len(scored)} saham teramai: 🔴 {len(bad)} hati-hati · 🟢 {len(good)} dijaga · ➖ {flat} netral"
              + (f" · {skipped} gagal ditarik" if skipped else ""))
    for title, items in (("🔴 HATI-HATI, JANGAN DIBAWA MENGINAP", bad), ("🟢 MASIH DIJAGA", good)):
        chunk = f"{header}\n\n━━ <b>{title}</b> ━━" if not msgs else f"━━ <b>{title}</b> ━━"
        for t in items:
            if len(chunk) + len(t) > 3500:  # batas pesan Telegram 4096
                msgs.append(chunk)
                chunk = f"━━ <b>{title}</b> (lanjutan) ━━"
            chunk += "\n\n" + t
        if items or not msgs:
            msgs.append(chunk)
    msgs[-1] += "\n\n<i>Angka historis: studi Sep-Nov 2026, relatif pasar, sebelum biaya.</i>"
    return msgs
