from universe import is_excluded_name, passes_liquidity
import config


def test_exclude_preferred_and_spac():
    assert is_excluded_name("삼성전자우") is True
    assert is_excluded_name("하이제6호스팩") is True
    assert is_excluded_name("삼성전자") is False


def test_liquidity_boundary():
    assert passes_liquidity(config.MIN_MARKET_CAP, config.MIN_TRADING_VALUE) is True
    assert passes_liquidity(config.MIN_MARKET_CAP - 1, config.MIN_TRADING_VALUE) is False
    assert passes_liquidity(config.MIN_MARKET_CAP, config.MIN_TRADING_VALUE - 1) is False
