"""End-to-end browser tests for the five main user flows (spec §User Flows / Testing).

Flow (e) — snapshot export A → import B — is covered by
``tests/test_snapshots_e2e.py`` (two live servers, real browser download/upload,
incoming-wins verified); it is intentionally not duplicated here.

Each test drives a real app (``live_app`` fixture in conftest.py) with a real
Chromium (pytest-playwright, headless). Screenshots land under
docs/phase/init/13-e2e-and-release/screenshots/.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from .conftest import SCREENSHOT_DIR, seed_rule, seed_transaction

pytestmark = pytest.mark.e2e

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(autouse=True, scope="module")
def _screenshot_dir():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def test_flow_a_upload_shows_categorized_transactions(live_app, page):
    """(a) Upload a statement fixture; imported transactions appear, categorized."""
    db = live_app.session()
    seed_rule(db, match_value="kinoheld", category="entertainment")
    db.commit()
    db.close()

    page.goto(live_app.url("/upload"))
    page.set_input_files("#upload-form input[type=file]", str(FIXTURES / "paypal_sample.TXT"))
    page.select_option("#upload-form select[name=format]", "paypal")
    page.click("#upload-form button[type=submit]")

    # The htmx inline summary confirms the import and its categorized count.
    page.wait_for_selector("#upload-result article")
    summary = page.locator("#upload-result").inner_text()
    assert "89 new transactions" in summary
    assert "2 categorized by rules" in summary
    page.screenshot(path=str(SCREENSHOT_DIR / "flow-a-upload-summary.png"), full_page=True)

    # Follow the deep-link to the imported transactions.
    page.click("#upload-result a[role=button]")
    page.wait_for_selector("table.txn-table")

    # The categorized transactions are visible when filtered to their category.
    page.goto(live_app.url("/?category=entertainment"))
    page.wait_for_selector("table.txn-table")
    cats = page.locator("table.txn-table td.cat")
    assert cats.filter(has_text="entertainment").count() == 2


def test_flow_b_create_rule_from_uncategorized(live_app, page):
    """(b) Filter Uncategorized → create rule from a txn → preview → save → History."""
    db = live_app.session()
    seed_transaction(
        db, id="e2e-ah", description="Albert Heijn Amsterdam",
        amount=-24.99, txn_date=date(2026, 3, 1),
    )
    db.commit()
    db.close()

    # Filter to Uncategorized (filter state in the URL — Golden Principle 8).
    page.goto(live_app.url("/?category=uncategorized"))
    page.wait_for_selector("#txn-row-e2e-ah")

    # Create a rule from this transaction.
    page.click("#txn-row-e2e-ah a.create-rule")
    page.wait_for_selector("form.rule-form")
    page.fill("input[name=match_value]", "albert heijn")
    page.fill("input[name=category]", "groceries")

    # Preview the draft — nothing saved yet.
    page.click("#preview-btn")
    page.wait_for_selector("#preview-panel article.rule-preview")
    assert "Matched: 1" in page.locator("#preview-panel").inner_text()
    page.screenshot(path=str(SCREENSHOT_DIR / "flow-b-preview.png"), full_page=True)

    # Save → redirect to the rules list.
    page.click("form.rule-form button[type=submit]")
    page.wait_for_url("**/rules")

    # The transaction is now categorized by the new rule.
    db = live_app.session()
    from abn_combined.core.models import Transaction

    txn = db.get(Transaction, "e2e-ah")
    assert txn.category == "groceries"
    db.close()

    # The change report is visible in History.
    page.goto(live_app.url("/rules/history"))
    page.wait_for_selector(".rule-report")
    assert page.locator(".rule-report .action-create").count() >= 1
    page.screenshot(path=str(SCREENSHOT_DIR / "flow-b-history.png"), full_page=True)


def test_flow_c_trends_cell_clickthrough_sums(live_app, page):
    """(c) Click a Trends cell → the filtered list sums to the cell value."""
    db = live_app.session()
    # One dining txn with a unique amount, plus another category in the same month.
    seed_transaction(
        db, id="e2e-dining", description="Restaurant De Kas", amount=-52.43,
        txn_date=date(2026, 3, 15), category="dining",
    )
    seed_transaction(
        db, id="e2e-groc", description="Jumbo", amount=-11.00,
        txn_date=date(2026, 3, 10), category="groceries",
    )
    db.commit()
    db.close()

    # Explicit March-2026 window so a single cell isolates the dining transaction.
    page.goto(live_app.url("/trends?date_from=2026-03-01&date_to=2026-03-31&granularity=month"))
    page.wait_for_selector("table.trends-table")
    page.screenshot(path=str(SCREENSHOT_DIR / "flow-c-trends.png"), full_page=True)

    # The dining row's cell shows the summed value; capture it, then click through.
    dining_row = page.locator("table.trends-table tr").filter(
        has=page.locator("th.cat-col a", has_text="dining")
    ).first
    cell_link = dining_row.locator("td.num a", has_text="-52.43")
    assert cell_link.count() == 1
    cell_value = cell_link.inner_text().strip()
    assert cell_value == "-52.43"
    cell_link.click()

    # The click-through lands on a filtered transactions list summing to the cell.
    page.wait_for_selector("table.txn-table")
    rows = page.locator("table.txn-table tr[id^=txn-row]")
    assert rows.count() == 1
    amount_text = rows.first.locator("td.num").first.inner_text()
    assert "-52.43" in amount_text


def test_flow_d_edit_rule_preview_diff_save_history(live_app, page):
    """(d) Edit a rule → preview shows the diff → save → the change is in History."""
    db = live_app.session()
    rule = seed_rule(db, match_value="spotify", category="music", priority=50)
    db.flush()
    for i in range(2):
        seed_transaction(
            db, id=f"e2e-spot-{i}", description=f"Spotify AB payment {i}",
            amount=-10.99, txn_date=date(2026, 2, 1 + i),
            category="music", categorization_source=str(rule.id),
        )
    db.commit()
    rule_id = rule.id
    db.close()

    # Rules tab lists the rule; open its editor.
    page.goto(live_app.url("/rules"))
    page.wait_for_selector(f"#rule-row-{rule_id}")
    page.click(f"#rule-row-{rule_id} a[href='/rules/{rule_id}/edit']")
    page.wait_for_selector("form.rule-form")

    # Change the category and preview the diff (gains/losses/changes for an edit).
    page.fill("input[name=category]", "entertainment")
    page.click("#preview-btn")
    page.wait_for_selector("#preview-panel article.rule-preview")
    preview = page.locator("#preview-panel").inner_text()
    assert "Would change: 2" in preview
    page.screenshot(path=str(SCREENSHOT_DIR / "flow-d-preview-diff.png"), full_page=True)

    # Save → redirect to the rules list.
    page.click("form.rule-form button[type=submit]")
    page.wait_for_url("**/rules")

    # The update is recorded in History.
    page.goto(live_app.url(f"/rules/{rule_id}/history"))
    page.wait_for_selector(".rule-report")
    assert page.locator(".rule-report .action-update").count() >= 1
    page.screenshot(path=str(SCREENSHOT_DIR / "flow-d-history.png"), full_page=True)

    # And the transactions were recategorized.
    db = live_app.session()
    from abn_combined.core.models import Transaction

    txn = db.get(Transaction, "e2e-spot-0")
    assert txn.category == "entertainment"
    db.close()
