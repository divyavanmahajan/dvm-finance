"""End-to-end browser flow for the hand-entered transactions (task 9.1).

The flow follows one cash payment through its complete life. The user creates
it, sees it in the transactions list and in the cash flow, flags it, sees it
leave both surfaces, and then purges it.

The test drives a real app (the ``live_app`` fixture in conftest.py) with a real
Chromium (pytest-playwright, headless). The screenshots land under
docs/phase/init/13-e2e-and-release/screenshots/.
"""

from __future__ import annotations

import pytest

from .conftest import SCREENSHOT_DIR

pytestmark = pytest.mark.e2e

AMOUNT = "-21.50"
DESCRIPTION = "Market stall cash"
CASH_FLOW_RANGE = "/cash-flow?date_from=2026-01-01&date_to=2026-12-31"


@pytest.fixture(autouse=True, scope="module")
def _screenshot_dir():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _cash_flow_text(page, live_app) -> str:
    """Return the text of the cash flow table for the year 2026."""
    page.goto(live_app.url(CASH_FLOW_RANGE))
    page.wait_for_selector("#cash-flow-table table")
    return page.locator("#cash-flow-table").inner_text()


def _manual_row_id(live_app) -> str:
    """Return the id of the one hand-entered row in the database."""
    from abn_combined.core.models import Transaction

    db = live_app.session()
    try:
        return db.query(Transaction).filter(Transaction.is_manual.is_(True)).one().id
    finally:
        db.close()


def _transaction_count(live_app) -> int:
    """Return the number of the rows in the transactions table."""
    from abn_combined.core.models import Transaction

    db = live_app.session()
    try:
        return db.query(Transaction).count()
    finally:
        db.close()


def test_flow_create_flag_and_purge_a_cash_transaction(live_app, page):
    """Create a cash row, flag it, and then purge it.

    The row leaves the list and the cash flow when the user flags it. The flag
    keeps the row in the database. The purge then removes the row.
    """
    # The user creates the hand-entered transaction.
    page.goto(live_app.url("/manual"))
    page.fill("#manual-date", "2026-03-05")
    page.fill("#manual-amount", AMOUNT)
    page.fill("#manual-description", DESCRIPTION)
    page.fill("#manual-category", "food")
    page.screenshot(path=str(SCREENSHOT_DIR / "manual-a-create-form.png"), full_page=True)
    page.click("form[action='/manual/create'] button[type=submit]")
    assert _transaction_count(live_app) == 1

    # The row appears in the transactions list.
    page.goto(live_app.url("/?account=CASH"))
    page.wait_for_selector("table.txn-table")
    assert DESCRIPTION in page.locator("table.txn-table").inner_text()
    page.screenshot(path=str(SCREENSHOT_DIR / "manual-b-in-list.png"), full_page=True)

    # The row contributes to the cash flow.
    assert "21.50" in _cash_flow_text(page, live_app)

    # The user flags the row for removal.
    page.goto(live_app.url(f"/manual/{_manual_row_id(live_app)}/edit"))
    page.wait_for_selector("form[action$='/flag']")
    page.screenshot(path=str(SCREENSHOT_DIR / "manual-c-edit-page.png"), full_page=True)
    page.click("form[action$='/flag'] button[type=submit]")

    # The row leaves the list and the cash flow. The row stays in the database.
    page.goto(live_app.url("/?account=CASH"))
    page.wait_for_selector("body")
    assert DESCRIPTION not in page.inner_text("body")
    assert "21.50" not in _cash_flow_text(page, live_app)
    assert _transaction_count(live_app) == 1

    # The row waits on the flagged page.
    page.goto(live_app.url("/manual/flagged"))
    page.wait_for_selector("table")
    assert DESCRIPTION in page.inner_text("table")
    page.screenshot(path=str(SCREENSHOT_DIR / "manual-d-flagged-list.png"), full_page=True)

    # The purge removes the row.
    page.check("#purge-confirm")
    page.click("form[action='/manual/purge'] button[type=submit]")
    page.wait_for_selector("body")
    assert DESCRIPTION not in page.inner_text("body")
    assert _transaction_count(live_app) == 0
    page.screenshot(path=str(SCREENSHOT_DIR / "manual-e-after-purge.png"), full_page=True)
