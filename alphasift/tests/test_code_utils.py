from alphasift.normalize import normalize_code


def test_normalize_code_accepts_numeric_suffixed_and_prefixed_codes():
    assert normalize_code(1.0) == "000001"
    assert normalize_code("SZ000001") == "000001"
    assert normalize_code("000001.SZ") == "000001"
    assert normalize_code("sh600000") == "600000"
    assert normalize_code("证券代码:300750") == "300750"


def test_normalize_code_drops_tickers_by_default():
    assert normalize_code("AAPL") == ""
    assert normalize_code("BRK-B") == ""


def test_normalize_code_allow_ticker_passes_us_tickers_through():
    assert normalize_code("AAPL", allow_ticker=True) == "AAPL"
    assert normalize_code("brk-b", allow_ticker=True) == "BRK-B"


def test_normalize_code_allow_ticker_keeps_a_share_rules_first():
    assert normalize_code("SZ000001", allow_ticker=True) == "000001"
    assert normalize_code("000001.SZ", allow_ticker=True) == "000001"
    assert normalize_code("sh600000", allow_ticker=True) == "600000"
    assert normalize_code(1.0, allow_ticker=True) == "000001"


def test_normalize_code_allow_ticker_rejects_non_ascii_text():
    assert normalize_code("亏损", allow_ticker=True) == ""
    assert normalize_code("暂无", allow_ticker=True) == ""
