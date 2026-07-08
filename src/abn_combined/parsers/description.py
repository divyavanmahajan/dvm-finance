"""Structured description parsing for various transaction formats."""

import re
from typing import Any


def parse_mt940_description(description: str) -> dict[str, Any] | None:
    """Parse MT940 description into structured JSON format.

    Extracts fields like /TRTP/, /IBAN/, /BIC/, /NAME/, /REMI/, /EREF/, etc.

    Args:
        description: The raw MT940 description string

    Returns:
        Dictionary with parsed fields, or None if no structured data found
    """
    if not description:
        return None

    result = {}

    # Pattern to match MT940 structured fields: /FIELD/VALUE/
    # This pattern matches /FIELD/VALUE/ where VALUE can contain anything except the next /FIELD/ pattern
    # We need to handle both cases: fields followed by another field, and fields at the end
    pattern = r"/([A-Z]+)/([^/]+?)(?=/(?:[A-Z]+)/|/$|$)"
    matches = re.findall(pattern, description)

    if not matches:
        return None

    for field, value in matches:
        field = field.strip()
        value = value.strip()

        if not value:
            continue

        # Handle special cases
        if field == "TRTP":
            result["transaction_type"] = value
        elif field == "IBAN":
            result["iban"] = value
        elif field == "BIC":
            result["bic"] = value
        elif field == "NAME":
            result["name"] = value
        elif field == "REMI":
            result["remittance_info"] = value
        elif field == "EREF":
            result["end_to_end_reference"] = value
        elif field == "MREF":
            result["mandate_reference"] = value
        elif field == "PREF":
            result["payment_reference"] = value
        elif field == "CRED":
            result["creditor_reference"] = value
        elif field == "DEBT":
            result["debtor_reference"] = value
        elif field == "COAM":
            result["commission_amount"] = value
        elif field == "OAMT":
            result["original_amount"] = value
        else:
            # Store unknown fields with their original tag
            if "other_fields" not in result:
                result["other_fields"] = {}
            result["other_fields"][field] = value

    if result:
        result["format"] = "mt940"

        # Check if this is a Tikkie transaction and parse Tikkie-specific fields
        parse_tikkie_fields(result)

        return result

    return None


def parse_tikkie_fields(result: dict[str, Any]) -> None:
    """Parse Tikkie-specific fields from MT940 transaction data.

    Detects Tikkie transactions and extracts:
    - Tikkie ID
    - Payer information (name, IBAN)
    - Payment description

    Args:
        result: The parsed MT940 result dictionary (modified in place)
    """
    name = result.get("name", "").upper()
    remi = result.get("remittance_info", "")
    transaction_type = result.get("transaction_type", "")

    # Check if this is a Tikkie transaction
    is_tikkie = False
    if "TIKKIE" in name or "TIKKIE" in remi.upper():
        is_tikkie = True
        result["is_tikkie"] = True
        result["payment_service"] = "Tikkie"

    if not is_tikkie:
        return

    # Parse Tikkie SEPA OVERBOEKING format
    # REMI format: "TIKKIE ID 001123453991, PICS, VAN G VAN AMSTERDAM, NL83ABNA0105946443"
    if transaction_type == "SEPA OVERBOEKING" and "TIKKIE ID" in remi.upper():
        # Extract Tikkie ID
        tikkie_id_match = re.search(r"TIKKIE ID\s+(\d+)", remi, re.IGNORECASE)
        if tikkie_id_match:
            result["tikkie_id"] = tikkie_id_match.group(1)

        # Parse REMI: "TIKKIE ID 001123453991, PICS, VAN G VAN AMSTERDAM, NL83ABNA0105946443"
        # Split by comma and extract components
        parts = [p.strip() for p in remi.split(",")]

        # Find payer name (usually after Tikkie ID and a code like "PICS" or "PLS")
        payer_name = None
        payer_iban = None

        for i, part in enumerate(parts):
            # Look for IBAN pattern (starts with country code, 2 letters + 2 digits)
            iban_match = re.search(r"([A-Z]{2}\d{2}[A-Z0-9]{4,30})", part)
            if iban_match:
                payer_iban = iban_match.group(1)
                # Payer name is usually the part before the IBAN
                if i > 0:
                    # Check previous parts for payer name
                    for j in range(i - 1, -1, -1):
                        prev_part = parts[j].strip()
                        # Skip if it's a code like "PICS", "PLS", or contains "TIKKIE ID"
                        if (
                            not re.match(r"^[A-Z]{2,4}$", prev_part)
                            and "TIKKIE ID" not in prev_part.upper()
                        ):
                            payer_name = prev_part
                            break
                break

        if payer_name:
            result["payer_name"] = payer_name
        if payer_iban:
            result["payer_iban"] = payer_iban

    # Parse Tikkie IDEAL format
    # REMI format: "001112686692 0031855697994810 FOR THE COIN NL21A BNA0869690930"
    elif transaction_type == "IDEAL" and "VIA TIKKIE" in name.upper():
        # Extract Tikkie ID (first number sequence in REMI, 12 digits)
        tikkie_id_match = re.search(r"^(\d{12})", remi)
        if tikkie_id_match:
            result["tikkie_id"] = tikkie_id_match.group(1)

        # Extract payment reference (second number sequence after Tikkie ID)
        payment_ref_match = re.search(r"^\d{12}\s+(\d+)", remi)
        if payment_ref_match:
            result["payment_reference"] = payment_ref_match.group(1)

        # Extract payer IBAN (at the end, full IBAN pattern)
        # Look for IBAN pattern at the end: 2 letters, 2 digits, then alphanumeric (may contain spaces)
        # Pattern: NL21ABNA0869690930 or NL21A BNA0869690930
        iban_match = re.search(r"([A-Z]{2}\d{2}[A-Z0-9\s]{12,30})$", remi)
        if iban_match:
            # Remove spaces from IBAN
            payer_iban = iban_match.group(1).replace(" ", "")
            result["payer_iban"] = payer_iban

        # Extract payment description (text between payment reference and IBAN)
        if result.get("tikkie_id") and result.get("payment_reference"):
            # Remove Tikkie ID and payment reference from start
            desc_part = remi
            desc_part = re.sub(
                r"^" + re.escape(result["tikkie_id"]) + r"\s+", "", desc_part
            )
            desc_part = re.sub(
                r"^" + re.escape(result["payment_reference"]) + r"\s+",
                "",
                desc_part,
            )

            # Remove IBAN from end if found
            if result.get("payer_iban"):
                # Find IBAN pattern in original (may have spaces)
                # Build pattern that matches IBAN with optional spaces
                iban_pattern = result["payer_iban"]
                # Insert optional spaces between characters for matching
                iban_pattern_with_spaces = r"\s*".join(iban_pattern)
                desc_part = re.sub(
                    r"\s*" + iban_pattern_with_spaces + r"\s*$",
                    "",
                    desc_part,
                )

            # Clean up any remaining trailing numbers
            desc_part = re.sub(r"\s+\d+\s*$", "", desc_part).strip()
            if desc_part:
                result["payment_description"] = desc_part

        # Extract payer name from NAME field (before "VIA TIKKIE")
        original_name = result.get("name", "")
        name_match = re.search(r"^(.+?)\s+VIA\s+TIKKIE", original_name, re.IGNORECASE)
        if name_match:
            result["payer_name"] = name_match.group(1).strip()

        # Extract timestamp from EREF if present
        eref = result.get("end_to_end_reference", "")
        eref_ts = re.search(r"(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2})", eref)
        if eref_ts:
            result["tikkie_timestamp"] = eref_ts.group(1)

        # Extract timestamp from KENMERK field if present
        # Format: "15-07-2025 18:46 003151 4239726178"
        if result.get("reference"):
            kenmerk = result["reference"]
            timestamp_match = re.search(
                r"(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2})", kenmerk
            )
            if timestamp_match:
                result["tikkie_timestamp"] = timestamp_match.group(1)


def parse_pos_description(description: str) -> dict[str, Any] | None:
    """Parse POS terminal description into structured JSON format.

    Parses formats like:
    - "BEA, BETAALPAS BCK*PLUS BECKERS,PAS422 NR:BS172538, 11.11.24/16:26 MAASTRICHT"
    - "BEA, APPLE PAY PATISSERIE LEMMENS,PAS422 NR:95ZFJ5, 30.08.23/11:05 MARGRATEN"
    - "ECOM, APPLE PAY PRAGUE CLASS. CONCERTS NR:MIPS1354, 14.12.24/11:47 PRAHA - NOVE, LAND: CZE CZK 1.100,00 1EUR=24,5316 CZK ECB KOERS=25,092969 OPSLAG=2,29%"

    Args:
        description: The raw POS description string

    Returns:
        Dictionary with parsed fields, or None if no structured data found
    """
    if not description:
        return None

    result = {}

    # Check if it looks like a POS transaction
    pos_indicators = ["BEA", "ECOM", "BETAALPAS", "APPLE PAY", "PAS", "NR:", "/"]

    if not any(indicator in description.upper() for indicator in pos_indicators):
        return None

    # Extract transaction type
    if "BEA" in description.upper():
        result["transaction_type"] = "POS"
        result["payment_method"] = "Betaalautomaat"

    if "ECOM" in description.upper():
        result["transaction_type"] = "ECOM"
        result["payment_method"] = "E-commerce"

    if "BETAALPAS" in description.upper():
        result["payment_method"] = "Betaalpas"

    # Extract Apple Pay payment method
    if "APPLE PAY" in description.upper():
        result["payment_method"] = "Apple Pay"

    # Extract merchant name (usually between payment method and PAS/NR)
    # First try the format with merchant code: CODE*MERCHANT
    merchant_match = re.search(r"([A-Z0-9]+\*[^,]+)", description)
    if merchant_match:
        merchant_part = merchant_match.group(1)
        if "*" in merchant_part:
            parts = merchant_part.split("*", 1)
            if len(parts) == 2:
                result["merchant_code"] = parts[0]
                result["merchant_name"] = parts[1].strip()

    # For Apple Pay, merchant name comes directly after "APPLE PAY" without code prefix
    if "APPLE PAY" in description.upper() and "merchant_name" not in result:
        # Extract text after "APPLE PAY" until ",PAS", ",NR:", or "NR:" (with or without comma)
        # Pattern matches everything until comma followed by PAS/NR: or just NR: directly
        apple_pay_match = re.search(
            r"APPLE PAY\s+(.+?)(?=,PAS|,NR:|NR:)", description, re.IGNORECASE
        )
        if apple_pay_match:
            merchant_name = apple_pay_match.group(1).strip()
            # Remove any trailing spaces or special characters
            merchant_name = merchant_name.rstrip(" ,")
            if merchant_name:
                result["merchant_name"] = merchant_name

    # For BETAALPAS, merchant name may come directly after "BETAALPAS" without code prefix
    if "BETAALPAS" in description.upper() and "merchant_name" not in result:
        # Extract text after "BETAALPAS" until ",PAS", ",NR:", "NR:" (with or without comma), or date pattern
        # Pattern: BETAALPAS MERCHANT_NAME,PAS or BETAALPAS MERCHANT_NAME,NR: or BETAALPAS MERCHANT_NAME NR:
        betaalpas_match = re.search(
            r"BETAALPAS\s+(.+?)(?=,PAS|,NR:|NR:|\d{1,2}\.\d{1,2}\.\d{2,4})",
            description,
            re.IGNORECASE,
        )
        if betaalpas_match:
            merchant_name = betaalpas_match.group(1).strip()
            # Remove any trailing spaces or special characters
            merchant_name = merchant_name.rstrip(" ,")
            if merchant_name:
                result["merchant_name"] = merchant_name

    # Extract card/terminal identifier (PAS followed by numbers)
    pas_match = re.search(r"PAS\s*(\d+)", description, re.IGNORECASE)
    if pas_match:
        result["card_terminal_id"] = pas_match.group(1)

    # Extract transaction reference (NR: followed by alphanumeric)
    nr_match = re.search(r"NR:\s*([A-Z0-9]+)", description, re.IGNORECASE)
    if nr_match:
        result["transaction_reference"] = nr_match.group(1)

    # Extract date and time (format: DD.MM.YY/HH:MM or DD.MM.YY/HH.MM)
    # Try HH:MM format first (standard)
    datetime_match = re.search(
        r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s*/\s*(\d{1,2}):(\d{2})", description
    )
    if not datetime_match:
        # Try HH.MM format (alternative with dots)
        datetime_match = re.search(
            r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s*/\s*(\d{1,2})\.(\d{2})", description
        )
    if datetime_match:
        day, month, year, hour, minute = datetime_match.groups()
        if len(year) == 2:
            year = "20" + year
        result["transaction_date"] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        result["transaction_time"] = f"{hour.zfill(2)}:{minute}"

    # Extract location (usually before currency conversion info)
    # Look for location pattern after date/time and before "LAND:" or currency info
    # Pattern: text after date/time pattern (supports both HH:MM and HH.MM formats), before "LAND:" or currency codes
    location_pattern = r"(\d{1,2}\.\d{1,2}\.\d{2,4}\s*/\s*\d{1,2}[.:]\d{2})\s+([A-Z][A-Z\s\-]+?)(?=,\s*LAND:|,\s*[A-Z]{3}\s+\d|$)"
    location_match = re.search(location_pattern, description)
    if location_match:
        location = location_match.group(2).strip()
        # Clean up location - remove trailing dashes, spaces, and common separators
        location = location.rstrip(" ,-")
        if location and len(location) > 2 and not location.isdigit():
            if (
                "NR:" not in location
                and "PAS" not in location
                and "LAND:" not in location
            ):
                result["location"] = location

    # Extract currency conversion info if present (for foreign transactions)
    land_match = re.search(r"LAND:\s*([A-Z]{3})", description, re.IGNORECASE)
    if land_match:
        result["country_code"] = land_match.group(1).upper()

    # Extract foreign currency amount if present
    foreign_currency_match = re.search(r"([A-Z]{3})\s+([\d.,]+)", description)
    if foreign_currency_match:
        currency_code = foreign_currency_match.group(1)
        amount_str = foreign_currency_match.group(2).replace(".", "").replace(",", ".")
        try:
            result["foreign_currency"] = currency_code
            result["foreign_amount"] = float(amount_str)
        except ValueError:
            pass

    # Extract exchange rate if present
    eur_rate_match = re.search(r"1EUR=([\d.,]+)", description, re.IGNORECASE)
    if eur_rate_match:
        rate_str = eur_rate_match.group(1).replace(",", ".")
        try:
            result["exchange_rate"] = float(rate_str)
        except ValueError:
            pass

    if result:
        result["format"] = "pos"
        return result

    return None


def parse_sepa_description(description: str) -> dict[str, Any] | None:
    """Parse SEPA transaction description into structured JSON format.

    Parses formats like:
    - "SEPA OVERBOEKING IBAN: NL86INGB0675939674 BIC: INGBNL2A NAAM: CHELSEA BALMER ARTIST OMSCHRIJVING: ALEX VAN MAHAJAN"
    - "SEPA IDEAL IBAN: DE17202208000000020234 BIC: SXPYDEHH NAAM: AMAZON PAYMENTS EUROPE SCA VIA STRIPE TECHNOLOGY EUROPE LT D OMSCHRIJVING: ..."
    - "SEPA INCASSO ALGEMEEN DOORLOPEND INCASSANT: NL37ZZZ801111060000 NAAM: XPLOR-ANYTIME FITNESS MACHTIGING: ANYTIME-NL-4799217 IBAN: NL77RABO0362406480 KENMERK: 42215366-68650"

    Args:
        description: The raw SEPA description string

    Returns:
        Dictionary with parsed fields, or None if no structured data found
    """
    if not description:
        return None

    # Check if it's a SEPA transaction
    if not description.upper().startswith("SEPA"):
        return None

    result = {}

    # Extract SEPA transaction type
    sepa_type_match = re.match(r"SEPA\s+(\w+)", description, re.IGNORECASE)
    if sepa_type_match:
        sepa_type = sepa_type_match.group(1).upper()
        result["sepa_type"] = sepa_type

        if sepa_type == "OVERBOEKING":
            result["transaction_type"] = "SEPA Transfer"
        elif sepa_type == "IDEAL":
            result["transaction_type"] = "SEPA iDEAL"
        elif sepa_type == "INCASSO":
            result["transaction_type"] = "SEPA Direct Debit"
            # Check for additional modifiers
            if "ALGEMEEN" in description.upper():
                result["direct_debit_type"] = "General"
            if "DOORLOPEND" in description.upper():
                result["recurring"] = True

    # Extract IBAN (format: IBAN: followed by alphanumeric, typically 15-34 chars)
    iban_match = re.search(
        r"IBAN:\s*([A-Z]{2}\d{2}[A-Z0-9]{4,30})", description, re.IGNORECASE
    )
    if iban_match:
        result["iban"] = iban_match.group(1).upper()

    # Extract BIC (format: BIC: followed by 8-11 alphanumeric)
    bic_match = re.search(
        r"BIC:\s*([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?)",
        description,
        re.IGNORECASE,
    )
    if bic_match:
        result["bic"] = bic_match.group(1).upper()

    # Extract NAAM (name) - everything after "NAAM:" until next field or end
    # Look for NAAM: followed by text until next field (IBAN:, BIC:, OMSCHRIJVING:, BETALINGSKENM.:, etc.) or end
    # Note: BETALINGSKENM. has a period before the colon
    naam_match = re.search(
        r"NAAM:\s*([^:]+?)(?=\s+(?:IBAN|BIC|OMSCHRIJVING|INCASSANT|MACHTIGING|KENMERK|BETALINGSKENM\.?):|$)",
        description,
        re.IGNORECASE,
    )
    if naam_match:
        result["name"] = naam_match.group(1).strip()

    # Extract OMSCHRIJVING (description) - everything after "OMSCHRIJVING:" until next field or end
    omschrijving_match = re.search(
        r"OMSCHRIJVING:\s*(.+?)(?=\s+(?:IBAN|BIC|NAAM|INCASSANT|MACHTIGING|KENMERK|BETALINGSKENM\.?):|$)",
        description,
        re.IGNORECASE,
    )
    if omschrijving_match:
        result["description"] = omschrijving_match.group(1).strip()

    # Extract BETALINGSKENM. (payment reference) - everything after "BETALINGSKENM.:" until next field or end
    betalingskenm_match = re.search(
        r"BETALINGSKENM\.?:\s*(.+?)(?=\s+(?:IBAN|BIC|NAAM|OMSCHRIJVING|INCASSANT|MACHTIGING|KENMERK):|$)",
        description,
        re.IGNORECASE,
    )
    if betalingskenm_match:
        result["payment_reference"] = betalingskenm_match.group(1).strip()

    # Extract INCASSANT (creditor identifier for direct debits)
    incassant_match = re.search(r"INCASSANT:\s*([A-Z0-9]+)", description, re.IGNORECASE)
    if incassant_match:
        result["creditor_identifier"] = incassant_match.group(1).upper()

    # Extract MACHTIGING (mandate reference for direct debits)
    machtiging_match = re.search(
        r"MACHTIGING:\s*([A-Z0-9\-]+)", description, re.IGNORECASE
    )
    if machtiging_match:
        result["mandate_reference"] = machtiging_match.group(1)

    # Extract KENMERK (reference/identifier) - everything after "KENMERK:" until next field or end
    kenmerk_match = re.search(
        r"KENMERK:\s*(.+?)(?=\s+(?:IBAN|BIC|NAAM|OMSCHRIJVING|INCASSANT|MACHTIGING|BETALINGSKENM\.?):|$)",
        description,
        re.IGNORECASE,
    )
    if kenmerk_match:
        result["reference"] = kenmerk_match.group(1).strip()

    # Check if this is a Tikkie transaction and parse Tikkie-specific fields
    # For SEPA IDEAL with "VIA TIKKIE" in NAAM field
    if result.get("sepa_type") == "IDEAL" and result.get("name"):
        name_upper = result["name"].upper()
        if "VIA TIKKIE" in name_upper or "TIKKIE" in name_upper:
            result["is_tikkie"] = True
            result["payment_service"] = "Tikkie"

            # Extract payer name from NAAM field (before "VIA TIKKIE")
            name_match = re.search(
                r"^(.+?)\s+VIA\s+TIKKIE", result["name"], re.IGNORECASE
            )
            if name_match:
                result["payer_name"] = name_match.group(1).strip()

            # Parse OMSCHRIJVING field for Tikkie IDEAL format
            # Format: "001059714643 00315 14239726178 YEAH NL58INGB0631694 404"
            # Or: "001059700584 00314 14536784156 MASKS NL31ABNA088098 4945"
            # Pattern: Tikkie ID (12 digits), payment ref (variable digits), description, IBAN (may have spaces), optional number
            if result.get("description"):
                omschrijving = result["description"]

                # Extract Tikkie ID (first 12-digit number)
                tikkie_id_match = re.search(r"^(\d{12})", omschrijving)
                if tikkie_id_match:
                    result["tikkie_id"] = tikkie_id_match.group(1)

                # Extract payment reference (second number sequence, variable length)
                # After Tikkie ID, there's a space, then the payment reference
                payment_ref_match = re.search(r"^\d{12}\s+(\d+)", omschrijving)
                if payment_ref_match:
                    result["payment_reference"] = payment_ref_match.group(1)

                # Extract payer IBAN (look for complete IBAN pattern)
                # Dutch IBAN format: NL + 2 digits + 4 letter bank code + 10 digit account = 18 chars
                # But in descriptions, IBANs may be shorter or have spaces, and may be followed by a separate number
                # Pattern: NL + 2 digits + 4 letters + 6-10 digits, optionally followed by space and number
                # We want to extract just the IBAN, excluding any trailing number after a space
                iban_match = re.search(
                    r"(NL\d{2}[A-Z]{4}\d{6,10})(?:\s+\d+)?", omschrijving
                )
                if iban_match:
                    # Get just the IBAN part (group 1), excluding any trailing space+number
                    payer_iban = iban_match.group(1)
                    # Remove any spaces from the IBAN itself
                    payer_iban = payer_iban.replace(" ", "")
                    # Verify it looks like a valid Dutch IBAN (starts with NL, has reasonable length)
                    if payer_iban.startswith("NL") and len(payer_iban) >= 14:
                        result["payer_iban"] = payer_iban

                # Extract payment description (text between payment reference and IBAN)
                if result.get("tikkie_id") and result.get("payment_reference"):
                    # Remove Tikkie ID and payment reference from start
                    desc_part = omschrijving
                    desc_part = re.sub(
                        r"^" + re.escape(result["tikkie_id"]) + r"\s+", "", desc_part
                    )
                    desc_part = re.sub(
                        r"^" + re.escape(result["payment_reference"]) + r"\s+",
                        "",
                        desc_part,
                    )

                    # Remove IBAN from end if found (handle with or without spaces)
                    if result.get("payer_iban"):
                        # Find IBAN pattern in original (may have spaces)
                        # Build pattern that matches IBAN with optional spaces
                        iban_pattern = result["payer_iban"]
                        # Insert optional spaces between characters for matching
                        iban_pattern_with_spaces = r"\s*".join(iban_pattern)
                        desc_part = re.sub(
                            r"\s*" + iban_pattern_with_spaces + r"\s*\d*\s*$",
                            "",
                            desc_part,
                        )

                    # Clean up any remaining trailing numbers
                    desc_part = re.sub(r"\s+\d+\s*$", "", desc_part).strip()
                    if desc_part:
                        result["payment_description"] = desc_part

            # Extract timestamp from KENMERK field if present
            # Format: "15-07-2025 18:46 003151 4239726178"
            if result.get("reference"):
                kenmerk = result["reference"]
                timestamp_match = re.search(
                    r"(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2})", kenmerk
                )
                if timestamp_match:
                    result["tikkie_timestamp"] = timestamp_match.group(1)

    if result:
        result["format"] = "sepa"
        return result

    return None


def parse_account_balance_description(description: str) -> dict[str, Any] | None:
    """Parse account balance/interest credit descriptions.

    Format: "ACCOUNT BALANCED                 CREDIT INTEREST            0,38C FROM 30.06.2025 TO 30.09.2025    DIRECT SAVINGS FOR INTEREST RATES PLEASE VISIT  WWW.ABNAMRO.NL/RENTE"

    Args:
        description: The raw description string

    Returns:
        Dictionary with parsed fields, or None if no structured data found
    """
    if not description:
        return None

    # Check if this is an account balance description
    if not (
        "ACCOUNT BALANCED" in description.upper()
        or "CREDIT INTEREST" in description.upper()
    ):
        return None

    result = {"format": "account_balance", "transaction_type": "Account Balance"}

    # Extract transaction type (CREDIT INTEREST, DEBIT INTEREST, etc.)
    # Look for interest type
    interest_match = re.search(
        r"(CREDIT INTEREST|DEBIT INTEREST|INTEREST)", description, re.IGNORECASE
    )
    if interest_match:
        result["interest_type"] = interest_match.group(1).upper()
        result["transaction_type"] = interest_match.group(1).title()

    # Extract amount and credit/debit indicator
    # Format: "0,38C" or "1,23D" where C=credit, D=debit
    amount_match = re.search(r"(\d+[,\.]\d+)\s*([CD])", description, re.IGNORECASE)
    if amount_match:
        amount_str = amount_match.group(1).replace(",", ".")
        try:
            amount = float(amount_str)
            indicator = amount_match.group(2).upper()
            result["amount"] = amount
            result["amount_indicator"] = indicator
            result["is_credit"] = indicator == "C"
        except ValueError:
            pass

    # Extract date range (FROM DD.MM.YYYY TO DD.MM.YYYY)
    date_range_match = re.search(
        r"FROM\s+(\d{2}\.\d{2}\.\d{4})\s+TO\s+(\d{2}\.\d{2}\.\d{4})",
        description,
        re.IGNORECASE,
    )
    if date_range_match:
        from_date_str = date_range_match.group(1)
        to_date_str = date_range_match.group(2)

        # Parse dates (DD.MM.YYYY format)
        try:
            from_parts = from_date_str.split(".")
            to_parts = to_date_str.split(".")
            from_date = f"{from_parts[2]}-{from_parts[1]}-{from_parts[0]}"
            to_date = f"{to_parts[2]}-{to_parts[1]}-{to_parts[0]}"
            result["period_from"] = from_date
            result["period_to"] = to_date
        except (IndexError, ValueError):
            pass

    # Extract additional description/info (everything after the date range or amount)
    # Try to find the descriptive text
    desc_match = re.search(
        r"(?:TO\s+\d{2}\.\d{2}\.\d{4}|[CD]\s+)(.+)$", description, re.IGNORECASE
    )
    if desc_match:
        additional_info = desc_match.group(1).strip()
        if additional_info:
            result["additional_info"] = additional_info

    # Extract URL if present
    url_match = re.search(r"(https?://[^\s]+|www\.[^\s]+)", description, re.IGNORECASE)
    if url_match:
        result["url"] = url_match.group(1)

    if len(result) > 2:  # More than just format and transaction_type
        return result

    return None


def parse_transaction_description(description: str) -> dict[str, Any] | None:
    """Parse transaction description into structured JSON format.

    Tries MT940 format first, then account balance format, then SEPA, then POS format.

    Args:
        description: The raw description string

    Returns:
        Dictionary with parsed fields, or None if no structured data found
    """
    if not description:
        return None

    # Try MT940 format first
    mt940_result = parse_mt940_description(description)
    if mt940_result:
        return mt940_result

    # Try account balance format (before SEPA/POS to avoid false matches)
    account_balance_result = parse_account_balance_description(description)
    if account_balance_result:
        return account_balance_result

    # Try SEPA format
    sepa_result = parse_sepa_description(description)
    if sepa_result:
        return sepa_result

    # Try POS format
    pos_result = parse_pos_description(description)
    if pos_result:
        return pos_result

    return None

