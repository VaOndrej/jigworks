"""CLI flags map onto Config; the host is always 127.0.0.1.

Contract: ``cli.parse_args(argv) -> Config``.
"""

from decimal import Decimal as D


def test_defaults_are_binance_feed_port_8000_no_bots_and_localhost():
    from btc_paper_trader.cli import parse_args

    cfg = parse_args([])
    assert cfg.feed == "binance"
    assert cfg.port == 8000
    assert cfg.bots == 0
    assert cfg.host == "127.0.0.1"
    assert cfg.open_browser is True
    assert cfg.binance_base == "https://api.binance.com"
    assert cfg.sim_tick_ms == 500


def test_flags_are_parsed_into_the_config(tmp_path):
    from btc_paper_trader.cli import parse_args

    db = tmp_path / "x.db"
    cfg = parse_args(
        [
            "--feed", "sim", "--seed", "11", "--port", "9123", "--db", str(db), "--bots", "1000",
            "--no-browser", "--binance-base", "https://binance-base.example", "--sim-tick-ms", "250",
            "--house-usd", "50000", "--house-btc", "1.5", "--house-levels", "4", "--house-spread-bps", "20",
        ]
    )
    assert cfg.feed == "sim"
    assert cfg.seed == 11
    assert cfg.port == 9123
    assert str(cfg.db) == str(db)
    assert cfg.bots == 1000
    assert cfg.open_browser is False
    assert cfg.binance_base == "https://binance-base.example"
    assert cfg.sim_tick_ms == 250
    assert D(cfg.house_usd) == D("50000")
    assert D(cfg.house_btc) == D("1.5")
    assert cfg.house_levels == 4
    assert cfg.house_spread_bps == 20
    assert cfg.host == "127.0.0.1"


def test_there_is_no_flag_to_bind_another_host():
    import pytest

    from btc_paper_trader.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--host", "0.0.0.0"])  # nosec B104 - asserting that it is refused


def test_default_database_lives_in_the_package_data_folder():
    from btc_paper_trader.cli import parse_args

    cfg = parse_args([])
    assert cfg.db.name == "exchange.db"
    assert cfg.db.parent.name == "data"
    assert cfg.db.parent.parent.name == "btc-paper-trader"
