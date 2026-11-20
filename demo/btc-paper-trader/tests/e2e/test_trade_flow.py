"""Browser e2e (opt-in, BTC_E2E=1): at 1440x900 with 50 bots, buy $20 from the book and place a
limit sell above the market. Screenshots go to tests/e2e/screenshots/.

Needs lightweight-charts vendored in static/vendor/ and ``uv run playwright install chromium``.
"""

import socket
import subprocess
import sys
import time
from decimal import Decimal as D
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

SHOTS = Path(__file__).parent / "screenshots"
PKG = Path(__file__).resolve().parents[2]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    port = _free_port()
    cmd = [
        str(Path(sys.executable).parent / "btc-paper-trader"), "--feed", "sim", "--seed", "7", "--bots", "50",
        "--no-browser", "--port", str(port), "--db", str(tmp_path / "e2e.db"),
    ]
    proc = subprocess.Popen(cmd, cwd=PKG, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)  # nosec B603
    import httpx

    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{url}/healthz", timeout=1).json().get("status") == "live":
                break
        except Exception:  # noqa: BLE001 - still starting
            pass
        time.sleep(0.25)
    else:
        proc.kill()
        pytest.fail("server did not become live: " + proc.stderr.read().decode()[-2000:])
    yield url
    proc.terminate()
    proc.wait(timeout=10)


def _num(text):
    return D(text.replace("$", "").replace(",", "").replace("%", "").strip())


def test_user_buys_from_the_book_and_places_a_limit_sell(server):
    from playwright.sync_api import expect, sync_playwright

    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(server)
        expect(page.get_by_test_id("chart")).to_be_visible()
        expect(page.get_by_test_id("feed-status")).to_contain_text("live", timeout=15_000)
        expect(page.get_by_test_id("ladder-ask-row").first).to_be_visible(timeout=15_000)
        assert _num(page.get_by_test_id("summary-equity").inner_text()) == D("100")
        page.screenshot(path=str(SHOTS / "01-start-1440.png"))

        page.get_by_test_id("ticket-side-buy").click()
        page.get_by_test_id("ticket-type").select_option("market")
        page.get_by_test_id("ticket-usd").fill("20")
        page.get_by_test_id("ticket-submit").click()
        expect(page.get_by_test_id("summary-btc")).not_to_have_text("0.00000", timeout=10_000)
        assert _num(page.get_by_test_id("summary-available").inner_text()) < D("81")
        page.get_by_test_id("tab-history").click()
        expect(page.get_by_test_id("history-table")).to_contain_text("filled")
        page.screenshot(path=str(SHOTS / "02-after-market-buy-1440.png"))

        btc = page.get_by_test_id("summary-btc").inner_text().strip()
        best_ask = _num(page.get_by_test_id("ladder-ask-row").first.inner_text().split()[0])
        page.get_by_test_id("ticket-side-sell").click()
        page.get_by_test_id("ticket-type").select_option("limit")
        page.get_by_test_id("ticket-price").fill(str((best_ask * D("1.02")).quantize(D("0.01"))))
        page.get_by_test_id("ticket-qty").fill(btc)
        page.get_by_test_id("ticket-submit").click()
        expect(page.get_by_test_id("ticket-error")).to_be_empty()
        page.get_by_test_id("tab-open-orders").click()
        expect(page.get_by_test_id("open-orders-table")).to_contain_text("sell", timeout=10_000)
        page.screenshot(path=str(SHOTS / "03-limit-sell-open-1440.png"))
        browser.close()
