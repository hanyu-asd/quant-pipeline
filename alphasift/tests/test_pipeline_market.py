import pytest

from alphasift.config import Config
from alphasift.pipeline import screen


def test_screen_rejects_hk_market():
    # No HK universe or ticker configuration path exists yet, so hk must
    # fail fast instead of silently screening the US pool.
    with pytest.raises(ValueError, match="Unsupported market"):
        screen("dual_low", market="hk", config=Config())


def test_screen_rejects_unknown_market():
    with pytest.raises(ValueError, match="Unsupported market"):
        screen("dual_low", market="jp", config=Config())


def test_screen_enforces_strategy_market_scope():
    # market="us" passes the market gate but cn-scoped strategies reject it.
    with pytest.raises(ValueError, match="does not support market"):
        screen("dual_low", market="us", config=Config())
