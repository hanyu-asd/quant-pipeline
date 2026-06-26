"""Tests for joint entry/exit optimizer."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from alphaevo.models.enums import MarketType, StrategyCategory
from alphaevo.models.execution import SampleBatch
from alphaevo.models.strategy import (
    StopLossConfig,
    Strategy,
    StrategyCondition,
    StrategyEntry,
    StrategyExit,
    StrategyMeta,
    TakeProfitConfig,
)
from alphaevo.optimizer import JointOptimizer


def _make_ohlcv(n: int = 80) -> pd.DataFrame:
    rows = []
    price = 100.0
    for idx in range(n):
        price *= 1.004 if idx % 13 < 8 else 0.99
        rows.append(
            {
                "date": date(2025, 1, 1) + timedelta(days=idx),
                "open": round(price * 0.998, 2),
                "high": round(price * 1.012, 2),
                "low": round(price * 0.988, 2),
                "close": round(price, 2),
                "volume": 1_000_000 + idx * 1000,
                "prev_close": round(price / 1.004, 2),
            }
        )
    return pd.DataFrame(rows)


def _make_strategy(strategy_id: str) -> Strategy:
    return Strategy(
        meta=StrategyMeta(
            id=strategy_id,
            name="Joint Optimizer Test",
            market=MarketType.US,
            category=StrategyCategory.TREND,
        ),
        description="Always-on strategy for joint optimizer tests.",
        entry=StrategyEntry(
            conditions=[
                StrategyCondition(indicator="rsi_14", op=">", value=0),
            ],
        ),
        exit=StrategyExit(
            stop_loss=StopLossConfig(type="pct", value=0.08),
            take_profit=TakeProfitConfig(type="rr", value=2.0),
            max_holding_days=10,
        ),
        market_rules={},
    )


def test_joint_optimizer_combines_seed_exit_rankings() -> None:
    first = _make_strategy("seed_one")
    second = _make_strategy("seed_two")
    second.exit.max_holding_days = 5
    batch = SampleBatch(
        batch_id="batch",
        strategy_id="base",
        symbols=["TEST"],
        date_range=(date(2025, 1, 1), date(2025, 3, 31)),
    )

    result = JointOptimizer(slippage=0.0, commission=0.0, min_data_days=15).optimize(
        "base",
        [first, second],
        {"TEST": _make_ohlcv()},
        batch,
        spaces=["takeprofit", "holding"],
        max_candidates_per_seed=6,
        objective="quality",
    )

    assert result.base_strategy_id == "base_joint"
    assert result.objective == "quality"
    assert len(result.candidates) > 6
    assert result.best_candidate is not None
    assert any(candidate.candidate_id.startswith("seed_one") for candidate in result.candidates)
    assert any(candidate.candidate_id.startswith("seed_two") for candidate in result.candidates)
