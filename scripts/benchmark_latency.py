"""
Gate 4 Performance Benchmarking Script.
Measures local SQLite query latency for diagnostic queries.
Target: Latency < 50ms per ticker lookup.
"""

import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.bot.main import explainer, format_bot_response_for_ticker, news_radar  # noqa: E402
from src.db.repository import FinancialRepository  # noqa: E402


def benchmark_diagnostic_query(ticker: str, iterations: int = 50) -> float:
    # Measure local deterministic SQLite query and rendering speed without external network jitter
    explainer._client = None
    news_radar.fetch_live_news_rss = lambda *args, **kwargs: []
    repo = FinancialRepository()
    latencies_ms = []

    # Warmup
    _ = format_bot_response_for_ticker(ticker, repo)

    for _ in range(iterations):
        t0 = time.perf_counter()
        _ = format_bot_response_for_ticker(ticker, repo)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies_ms.append(elapsed_ms)

    avg_ms = sum(latencies_ms) / len(latencies_ms)
    p95_ms = sorted(latencies_ms)[int(len(latencies_ms) * 0.95)]
    min_ms = min(latencies_ms)
    max_ms = max(latencies_ms)

    print(f"--- Benchmark Results for /cek {ticker} ({iterations} iterations) ---")
    print(f"Average Latency : {avg_ms:.2f} ms")
    print(f"P95 Latency     : {p95_ms:.2f} ms")
    print(f"Min / Max       : {min_ms:.2f} ms / {max_ms:.2f} ms")
    print(f"Target (<50 ms) : {'PASSED (EXCELLENT)' if p95_ms < 50.0 else 'FAILED'}")
    return p95_ms


if __name__ == "__main__":
    benchmark_diagnostic_query("WIKA")
    print()
    benchmark_diagnostic_query("BBCA")
