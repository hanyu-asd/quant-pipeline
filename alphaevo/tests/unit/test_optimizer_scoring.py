"""Tests for shared optimizer scoring utilities."""

from __future__ import annotations

from types import SimpleNamespace

from alphaevo.models.execution import (
    AntiFitMetrics,
    EvaluationReport,
    OverallMetrics,
    WalkForwardFoldMetrics,
)
from alphaevo.optimizer.scoring import (
    candidate_sort_key,
    normalize_objective,
    profit_quality_score,
    quality_score,
    robust_profit_quality_score,
)
from alphaevo.optimizer.summary import select_high_win_return_candidate


def _report(
    *,
    win_rate: float,
    avg_return: float,
    profit_loss_ratio: float,
    max_drawdown: float,
    signal_count: int,
    total_return: float = 0.0,
    anti_overfit: AntiFitMetrics | None = None,
    walk_forward: list[WalkForwardFoldMetrics] | None = None,
) -> EvaluationReport:
    return EvaluationReport(
        strategy_id="score_test",
        overall=OverallMetrics(
            win_rate=win_rate,
            avg_return=avg_return,
            profit_loss_ratio=profit_loss_ratio,
            max_drawdown=max_drawdown,
            signal_count=signal_count,
            total_return=total_return,
        ),
        confidence_score=0.2,
        anti_overfit=anti_overfit or AntiFitMetrics(),
        walk_forward=walk_forward or [],
    )


def test_quality_score_prefers_positive_payoff_over_win_rate_only() -> None:
    high_win_negative_payoff = _report(
        win_rate=0.57,
        avg_return=-0.0003,
        profit_loss_ratio=0.74,
        max_drawdown=0.275,
        signal_count=58,
    )
    lower_win_positive_payoff = _report(
        win_rate=0.48,
        avg_return=0.021,
        profit_loss_ratio=2.45,
        max_drawdown=0.119,
        signal_count=25,
    )

    assert quality_score(lower_win_positive_payoff) > quality_score(high_win_negative_payoff)
    assert candidate_sort_key(
        lower_win_positive_payoff,
        passed_gate=False,
        objective="quality",
    ) > candidate_sort_key(
        high_win_negative_payoff,
        passed_gate=False,
        objective="quality",
    )


def test_quality_score_penalizes_tiny_signal_samples() -> None:
    tiny_sample = _report(
        win_rate=0.50,
        avg_return=0.03,
        profit_loss_ratio=2.8,
        max_drawdown=0.03,
        signal_count=6,
    )
    adequate_sample = _report(
        win_rate=0.45,
        avg_return=0.011,
        profit_loss_ratio=1.9,
        max_drawdown=0.27,
        signal_count=31,
    )

    assert quality_score(adequate_sample) > quality_score(tiny_sample)


def test_quality_objective_aliases() -> None:
    assert normalize_objective("quality") == "quality"
    assert normalize_objective("balanced") == "quality"
    assert normalize_objective("expectancy") == "profit_quality"
    assert normalize_objective("profit") == "profit_quality"
    assert normalize_objective("robust") == "robust_profit_quality"
    assert normalize_objective("stable-profit") == "robust_profit_quality"


def test_profit_quality_prioritizes_return_depth() -> None:
    thin_high_win = _report(
        win_rate=0.58,
        avg_return=0.004,
        profit_loss_ratio=1.05,
        max_drawdown=0.09,
        signal_count=35,
        total_return=0.14,
    )
    stronger_return = _report(
        win_rate=0.51,
        avg_return=0.012,
        profit_loss_ratio=1.45,
        max_drawdown=0.14,
        signal_count=35,
        total_return=0.48,
    )

    assert profit_quality_score(stronger_return) > profit_quality_score(thin_high_win)
    assert candidate_sort_key(
        stronger_return,
        passed_gate=False,
        objective="profit_quality",
    ) > candidate_sort_key(
        thin_high_win,
        passed_gate=False,
        objective="profit_quality",
    )


def test_robust_profit_quality_penalizes_overfit_return() -> None:
    overfit_return = _report(
        win_rate=0.52,
        avg_return=0.02,
        profit_loss_ratio=2.0,
        max_drawdown=0.17,
        signal_count=45,
        total_return=0.80,
        anti_overfit=AntiFitMetrics(train_val_gap=0.30, val_test_gap=0.25),
    )
    stable_return = _report(
        win_rate=0.50,
        avg_return=0.016,
        profit_loss_ratio=1.8,
        max_drawdown=0.17,
        signal_count=45,
        total_return=0.60,
        anti_overfit=AntiFitMetrics(
            train_val_gap=0.04,
            val_test_gap=0.03,
            walk_forward_gap=0.05,
            walk_forward_pass_rate=0.80,
        ),
        walk_forward=[
            WalkForwardFoldMetrics(
                fold_num=1,
                train_win_rate=0.52,
                test_win_rate=0.49,
                gap=0.03,
            )
        ],
    )

    assert robust_profit_quality_score(stable_return) > robust_profit_quality_score(
        overfit_return
    )
    assert candidate_sort_key(
        stable_return,
        passed_gate=False,
        objective="robust_profit_quality",
    ) > candidate_sort_key(
        overfit_return,
        passed_gate=False,
        objective="robust_profit_quality",
    )


def test_select_high_win_return_candidate_balances_win_and_return() -> None:
    thin_high_win = SimpleNamespace(
        evaluation=_report(
            win_rate=0.62,
            avg_return=0.003,
            profit_loss_ratio=1.05,
            max_drawdown=0.08,
            signal_count=40,
            total_return=0.10,
        ),
        passed_gate=True,
    )
    stronger_payoff = SimpleNamespace(
        evaluation=_report(
            win_rate=0.53,
            avg_return=0.018,
            profit_loss_ratio=1.85,
            max_drawdown=0.12,
            signal_count=40,
            total_return=0.62,
        ),
        passed_gate=True,
    )

    assert select_high_win_return_candidate([thin_high_win, stronger_payoff]) is stronger_payoff
