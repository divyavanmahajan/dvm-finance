"""Generate parity fixtures from the real Python implementation.

Output: parity.json — input/expected pairs the Swift tests assert against.
"""
import json
from datetime import date
from decimal import Decimal

from abn_combined.core.utils import (
    calculate_transaction_hash_components,
    normalize_category,
    normalize_string_for_matching,
)
from abn_combined.core.dedup import generate_transaction_id

out = {}

norm_cases = [
    None, "", "   ", "Albert Heijn 1234", "WERO/Payment To John",
    "WERO /Payment", "  SEPA  Overboeking\tIBAN: NL91ABNA0417164300  ",
    "MiXeD CaSe", "wero/lower", "Ümlaut Ströße", "a  b\nc\td",
]
out["normalize_string_for_matching"] = [
    {"input": c, "expected": normalize_string_for_matching(c)} for c in norm_cases
]

cat_cases = [None, "", "  ", "Groceries", "Food, Groceries", " FIXED-Insurance-Life ",
             "a,,b", ", ,", "Transfer-Wise"]
out["normalize_category"] = [
    {"input": c, "expected": normalize_category(c)} for c in cat_cases
]

hash_cases = [
    dict(date_value=date(2026, 1, 15), description="Albert Heijn 1234", amount=Decimal("-12.30"), account="NL91ABNA0417164300"),
    dict(date_value=date(2026, 1, 15), description=None, amount=None, account=None),
    dict(date_value=None, description="WERO/Pay", amount="12", account="acct 1"),
    dict(date_value="2026-02-03", description="x", amount="abc", account="A"),
    dict(date_value=date(2025, 12, 31), description="Ümlaut", amount=Decimal("100"), account="SE1"),
]
out["transaction_hash"] = [
    {
        "date": str(c["date_value"]) if c["date_value"] else None,
        "description": c["description"],
        "amount": str(c["amount"]) if c["amount"] is not None else None,
        "account": c["account"],
        "expected": calculate_transaction_hash_components(**c),
    }
    for c in hash_cases
]

id_cases = [
    {"accountNumber": "NL91ABNA0417164300", "transactiondate": date(2026, 1, 15), "amount": Decimal("-12.30"), "description": "Albert Heijn 1234"},
    {"accountNumber": "NL91ABNA0417164300", "transactiondate": date(2026, 1, 15), "amount": Decimal("-12.30"), "description": ""},
    {"accountNumber": "ACC", "transactiondate": date(2026, 6, 1), "amount": Decimal("100.00"), "description": "Ümlaut Ströße"},
    {"accountNumber": "ACC", "transactiondate": date(2026, 6, 1), "amount": Decimal("100"), "description": "same amount different string"},
    {"accountNumber": "paypal@x.com", "paypal_transaction_id": "9AB12345CD", "transactiondate": date(2026, 3, 1), "amount": Decimal("5"), "description": "d"},
    {"accountNumber": "wiseacct", "wise_transaction_id": "TRANSFER-123", "transactiondate": date(2026, 3, 1), "amount": Decimal("5"), "description": "d"},
    {"accountNumber": "sebacct", "seb_voucher_id": "V-77", "transactiondate": date(2026, 3, 1), "amount": Decimal("5"), "description": "d"},
    {"accountNumber": "", "transactiondate": None, "amount": None, "description": None},
]
def _ser(c):
    d = {k: (str(v) if isinstance(v, (date, Decimal)) else v) for k, v in c.items()}
    d["expected"] = generate_transaction_id(c)
    return d
out["transaction_id"] = [_ser(c) for c in id_cases]

with open("parity.json", "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(json.dumps(out, indent=2, ensure_ascii=False)[:3000])
