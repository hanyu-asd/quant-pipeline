"""Tests for TencentAshareAdapter."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from alphaevo.data.adapters.tencent import TencentAshareAdapter, normalize_tencent_symbol
from alphaevo.models.enums import MarketType


def test_normalize_tencent_symbol_variants() -> None:
    assert normalize_tencent_symbol("600519") == "sh600519"
    assert normalize_tencent_symbol("000001.SZ") == "sz000001"
    assert normalize_tencent_symbol("600519.XSHG") == "sh600519"
    assert normalize_tencent_symbol("bj830799") == "bj830799"


def test_normalize_daily_payload_prefers_qfqday() -> None:
    payload = {
        "data": {
            "sz000001": {
                "qfqday": [
                    ["2024-01-02", "10", "10.5", "10.8", "9.9", "1000", "2000"],
                    ["2024-01-03", "10.5", "10.2", "10.6", "10.0", "900", "1800"],
                ]
            }
        }
    }

    df = TencentAshareAdapter._normalize_daily_payload(payload, "sz000001")

    assert list(df.columns) == [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "prev_close",
    ]
    assert df["date"].tolist() == [date(2024, 1, 2), date(2024, 1, 3)]
    assert df["close"].tolist() == [10.5, 10.2]
    assert df["amount"].tolist() == [2000, 1800]
    assert pd.isna(df["prev_close"].iloc[0])
    assert df["prev_close"].iloc[1] == 10.5


@pytest.mark.asyncio
async def test_get_stock_list_is_empty_for_direct_kline_source() -> None:
    adapter = TencentAshareAdapter()

    assert await adapter.get_stock_list(MarketType.A_SHARE) == []


def test_parse_quote_text() -> None:
    fields = [""] * 40
    fields[1] = "平安银行"
    fields[3] = "10.25"
    fields[6] = "123456"
    fields[30] = "20240102150102"
    fields[32] = "1.23"
    fields[37] = "456789"
    quote = TencentAshareAdapter._parse_quote_text(
        'v_sz000001="' + "~".join(fields) + '";',
        "sz000001",
    )

    assert quote is not None
    assert quote.symbol == "sz000001"
    assert quote.name == "平安银行"
    assert quote.price == 10.25
    assert quote.change_pct == 1.23
    assert quote.volume == 123456
    assert quote.amount == 456789
