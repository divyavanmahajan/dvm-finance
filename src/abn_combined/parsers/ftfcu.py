"""First Tech Federal Credit Union OFX parser.

Parses the OFX export from First Tech online banking
(``MyAccountsV2/Export`` with ``format=56``, file ``ExportedTransactions.ofx``).
See ``protocol/firsttechfed.com-protocol.md`` for the capture.

File format
-----------
OFX 1.02 SGML. One file holds one ``<STMTTRNRS>`` block for each account. The
credit card is also in ``<BANKMSGSRSV1>``, with ``<ACCTTYPE>CREDITLINE``.
``ofxtools`` reads the SGML. It gives each amount as a ``Decimal`` (the OFX
decimal separator is always a period) and each date as a UTC datetime.

The QFX export (``format=58``) gives the same transactions other FITIDs. The
parser refuses a QFX file, so that a QFX import cannot add a duplicate of an
OFX import.

Account number
--------------
``ftfcu:<last 4 digits>``. The full ``<ACCTID>`` of the card is the card
number, so the parser never stores the full ``<ACCTID>``.

EUR conversion strategy
-----------------------
Every transaction is stored in EUR, as for SEB. The native USD amount is
preserved in description_structured. The EUR/USD reference rates come from the
ECB feed; see ``parsers/fx.py``. If all fetches fail, transactions are stored
in USD as best-effort.

Deduplication
-------------
The FITID is unique for each transaction. It holds spaces and commas
(``20261113 100002 1,049 7,693``), and the transaction id goes into URL paths.
``ftfcu_fitid`` therefore holds the FITID without commas, with ``-`` between
its parts (``20261113-100002-1049-7693``). The raw FITID stays in
description_structured.
"""

import json
import warnings
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from .fx import best_rate, build_rate_cache, to_eur

_ACCOUNT_PREFIX = "ftfcu:"
_FID = "3169"
_ORG_MARKER = "first tech"


def normalize_fitid(fitid: str) -> str:
    """Return the FITID without commas, with ``-`` between its parts."""
    return "-".join(fitid.replace(",", "").split())


def _load_ofx(file_path: Path):
    from ofxtools.Parser import OFXTree

    tree = OFXTree()
    try:
        # ofxtools warns about a NAME longer than 32 characters and about
        # private tags. Neither stops the parse.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree.parse(str(file_path))
            return tree.convert()
    except Exception as exc:  # noqa: BLE001 - ofxtools raises several error types
        raise ValueError(
            f"Cannot read First Tech OFX file {file_path.name}: {exc}. "
            "Is this an OFX export from First Tech?"
        ) from exc


def _check_institution(ofx: Any) -> None:
    fi = getattr(getattr(getattr(ofx, "signonmsgsrsv1", None), "sonrs", None), "fi", None)
    fid = str(getattr(fi, "fid", "") or "")
    org = str(getattr(fi, "org", "") or "")
    if fid != _FID and _ORG_MARKER not in org.lower():
        raise ValueError(
            f"This OFX file comes from {org or 'an unknown institution'} (FID {fid or '?'}), "
            "not from First Tech Federal Credit Union."
        )


def parse_ftfcu_file(file_path: Path) -> list[dict[str, Any]]:
    """Parse a First Tech OFX export and return standardised transactions.

    Args:
        file_path: Path to the First Tech OFX export.

    Returns:
        List of transaction dicts matching the standard transaction schema.
        All transactions are converted from USD to EUR where a rate is
        available. Native amounts and the rate used are stored in
        description_structured.
    """
    file_path = Path(file_path)
    if file_path.suffix.lower() == ".qfx":
        raise ValueError(
            "First Tech QFX files use other transaction ids than OFX files. "
            "Download the OFX format instead."
        )

    ofx = _load_ofx(file_path)
    _check_institution(ofx)

    statements = list(ofx.statements)
    native_dates: dict[str, list[date]] = {}
    for stmt in statements:
        native_dates.setdefault(stmt.curdef, []).extend(
            tx.dtposted.date() for tx in stmt.transactions
        )
    rate_caches = {
        currency: build_rate_cache(dates, currency)
        for currency, dates in native_dates.items()
        if currency != "EUR" and dates
    }

    transactions: list[dict[str, Any]] = []
    line = 0
    for stmt in statements:
        acct = stmt.account
        last4 = str(acct.acctid)[-4:]
        account_type = getattr(acct, "accttype", None) or "CREDITCARD"
        native_currency = stmt.curdef

        for tx in stmt.transactions:
            line += 1
            posted = tx.dtposted.date()
            amount: Decimal = tx.trnamt
            fitid = str(tx.fitid)
            name = " ".join((tx.name or "").split())
            memo = " ".join((tx.memo or "").split())

            structured: dict[str, Any] = {
                "format": "ftfcu",
                "fitid": fitid,
                "trntype": tx.trntype,
                "name": name or None,
                "memo": memo or None,
                "checknum": tx.checknum,
                "account_type": account_type,
                "account_last4": last4,
                "native_amount": float(amount),
                "native_currency": native_currency,
            }

            rate = None
            if native_currency != "EUR":
                rate = best_rate(rate_caches.get(native_currency, {}), posted)
            if rate and rate > 0:
                stored_amount = to_eur(amount, rate)
                stored_currency = "EUR"
                structured["eur_rate_used"] = rate
            else:
                stored_amount = float(amount)
                stored_currency = native_currency

            transactions.append({
                "accountNumber": f"{_ACCOUNT_PREFIX}{last4}",
                "transactiondate": posted,
                "valuedate": posted,
                "amount": stored_amount,
                "currency": stored_currency,
                "description": name or memo,
                "description_structured": json.dumps(structured, ensure_ascii=False),
                "endsaldo": None,
                "source_file": file_path.name,
                "source_line": line,
                "transaction_type_code": tx.trntype,
                "transaction_reference": fitid,
                "ftfcu_fitid": normalize_fitid(fitid),
            })

    return transactions
