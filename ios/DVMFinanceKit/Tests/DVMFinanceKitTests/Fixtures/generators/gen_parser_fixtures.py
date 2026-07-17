"""Run each Python parser on its repo fixture and dump full expected output
JSON for Swift parity tests."""
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from abn_combined.parsers import (
    parse_mt940_file, parse_paypal_file, parse_seb_file, parse_wise_file,
)

FIX = Path("/home/user/dvm-finance/tests/fixtures")

def ser(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return str(o)
    raise TypeError(f"{type(o)}: {o!r}")

out = {}
out["mt940_sample.STA"] = parse_mt940_file(FIX / "mt940_sample.STA")
out["paypal_sample.TXT"] = parse_paypal_file(FIX / "paypal_sample.TXT")
out["seb_sample.csv"] = parse_seb_file(FIX / "seb_sample.csv")
out["wise_sample.csv"] = parse_wise_file(FIX / "wise_sample.csv")

# Record python type names for numeric/date fields of the first txn of each,
# so the Swift port knows exactly which str() rendering feeds transaction ids.
types = {}
for name, txns in out.items():
    if txns:
        types[name] = {k: type(v).__name__ for k, v in txns[0].items()}
print(json.dumps(types, indent=2))

with open("parser_expected.json", "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False, default=ser)

for name, txns in out.items():
    print(name, "->", len(txns), "transactions")
