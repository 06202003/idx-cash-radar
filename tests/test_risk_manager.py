"""Tests for Risk:Reward ratio, IDX tick rounding, and Money Management sizing."""

from __future__ import annotations

from pathlib import Path

from src.db.store import AlertStore
from src.engine.risk_manager import (
    compute_risk_reward_plan,
    format_risk_reward_block,
    format_risk_reward_compact,
    round_idx_tick,
)


def test_idx_tick_rounding() -> None:
    assert round_idx_tick(153, "nearest") == 153
    assert round_idx_tick(347, "down") == 346
    assert round_idx_tick(1253, "up") == 1255
    assert round_idx_tick(3052, "nearest") == 3050
    assert round_idx_tick(5712, "up") == 5725


def test_risk_reward_and_money_management() -> None:
    # Modal Rp 100 Jt, 1% max risk = Rp 1 Jt
    # Entry 3060, Support 3010 -> SL 3000 (risk Rp 60/lembar = Rp 6.000/lot)
    # Resistance 3200 -> TP 3200 (reward Rp 140/lembar) -> R:R = 1 : 2.33
    # Max lots by 1% risk = 1.000.000 // 6.000 = 166 lot
    # Max lots by 25% cap = 25.000.000 // 306.000 = 81 lot -> capped at 81 lot!
    plan = compute_risk_reward_plan(
        entry_price=3060,
        support_price=3010,
        resistance_price=3200,
        capital_idr=100_000_000.0,
    )
    assert plan is not None
    assert plan["stop_loss"] == 3000
    assert plan["take_profit"] == 3200
    assert plan["rr_ratio"] == 2.33
    assert plan["is_favorable"] is True
    assert plan["recommended_lots"] == 81

    block = "\n".join(format_risk_reward_block(plan))
    assert "RISK:REWARD & MONEY MANAGEMENT" in block
    assert "1 : 2.33" in block
    assert "81 lot" in block

    compact = format_risk_reward_compact(plan)
    assert "1:2.33" in compact
    assert "81 lot" in compact


def test_store_user_capital(tmp_path: Path) -> None:
    store = AlertStore(db_path=tmp_path / "test_cap.db")
    assert store.get_capital(999) == 100_000_000.0
    store.set_capital(999, 50_000_000.0)
    assert store.get_capital(999) == 50_000_000.0
