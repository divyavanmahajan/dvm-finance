"""End-to-end tests for the QR icon of the navigation and the sample data.

The QR icon opens ``/export?share=1``. The page then starts a share with a POST
and removes ``share=1`` from the address. The sample data flow loads the data
from the empty Transactions page and removes it on the Import page.
"""

from __future__ import annotations

import pytest

from .conftest import SCREENSHOT_DIR

pytestmark = pytest.mark.e2e


def test_qr_icon_shows_a_qr_code_after_one_click(live_app, page):
    page.goto(live_app.url("/trends"))
    page.click("[data-testid=nav-share-to-phone]")
    page.wait_for_selector("#share-qr img[alt^='QR code for http://']")
    assert page.url.endswith("/export")
    page.screenshot(path=str(SCREENSHOT_DIR / "nav-share-to-phone.png"), full_page=True)

    # A reload starts no second share: the QR area stays empty.
    page.reload()
    page.wait_for_load_state("networkidle")
    assert page.locator("#share-qr img").count() == 0
    page.request.post(live_app.url("/snapshots/share/stop"))


def test_sample_data_load_and_remove(live_app, page):
    page.goto(live_app.url("/"))
    page.click("#empty-offer button[type=submit]")
    # HX-Refresh reloads the page, and the reloaded page has no offer.
    page.wait_for_selector("#empty-offer", state="detached")
    assert "Albert Heijn" in page.locator("table.txn-table").inner_text()

    page.goto(live_app.url("/import"))
    page.click("#sample-data button:has-text('Remove sample data')")
    page.wait_for_selector("#sample-data [role=status]")
    assert "Removed" in page.locator("#sample-data").inner_text()
    page.goto(live_app.url("/"))
    page.wait_for_selector("#empty-offer")
