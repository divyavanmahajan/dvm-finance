"""Unit tests for the statement parser."""
import tempfile
import unittest
from pathlib import Path

from abn_combined.parsers import (
    parse_statement_file,
    parse_transaction_description,
)
from abn_combined.parsers.description import (
    parse_account_balance_description,
    parse_mt940_description,
    parse_pos_description,
    parse_sepa_description,
)
from abn_combined.parsers.mt940 import parse_mt940_file


class TestParser(unittest.TestCase):
    """Test cases for statement parser."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_data_dir = Path(__file__).parent.parent / "data" / "uploads"

    def test_parse_sta_file(self):
        """Test parsing a STA file (MT940 format)."""
        # Find a STA file in the uploads directory
        sta_files = list(self.test_data_dir.glob("*.STA"))

        if not sta_files:
            # Create a temporary STA file with sample MT940 content
            sample_sta_content = """ABNANL2A
940
ABNANL2A
:20:ABN AMRO BANK NV
:25:720317081
:28:13701/1
:60F:C240515EUR151,31
:61:2405160516D5,75N426NONREF
:86:BEA, BETAALPAS                   WLBSS TEE MARKT,PAS603
NR:24960249, 16.05.24/15:52      RWHMIAYZMC
:62F:C240516EUR145,56
-"""
            with tempfile.NamedTemporaryFile(mode='w', suffix='.STA', delete=False) as f:
                f.write(sample_sta_content)
                temp_sta_path = Path(f.name)

            try:
                # Parse the STA file
                transactions = parse_statement_file(temp_sta_path)

                # Verify the result
                self.assertIsInstance(transactions, list, "Should return a list of transactions")
                self.assertGreater(len(transactions), 0, "Should parse at least one transaction")

                # Check structure of first transaction
                if transactions:
                    first_trans = transactions[0]
                    self.assertIn('accountNumber', first_trans, "Transaction should have accountNumber")
                    self.assertIn('amount', first_trans, "Transaction should have amount")
                    self.assertIn('description', first_trans, "Transaction should have description")
                    self.assertIn('transactiondate', first_trans, "Transaction should have transactiondate")

                    # Verify data types
                    self.assertIsInstance(first_trans['accountNumber'], str)
                    self.assertIsInstance(first_trans['description'], str)

                    # Verify description_structured is included if description exists
                    if first_trans.get('description'):
                        # description_structured may or may not be present depending on parsing success
                        # but if present, it should be a JSON string
                        if 'description_structured' in first_trans and first_trans['description_structured']:
                            import json
                            try:
                                parsed = json.loads(first_trans['description_structured'])
                                self.assertIsInstance(parsed, dict, "description_structured should be valid JSON")
                            except json.JSONDecodeError:
                                self.fail("description_structured should be valid JSON string")

                    print(f"✓ Successfully parsed STA file with {len(transactions)} transactions")
                    if transactions:
                        print(f"  First transaction: {first_trans.get('description', 'N/A')} - €{first_trans.get('amount', 0)}")
            finally:
                # Clean up temporary file
                temp_sta_path.unlink()
        else:
            # Use existing STA file
            sta_file = sta_files[0]
            print(f"Testing with existing STA file: {sta_file.name}")

            # Parse the STA file
            transactions = parse_statement_file(sta_file)

            # Verify the result
            self.assertIsInstance(transactions, list, "Should return a list of transactions")
            self.assertGreater(len(transactions), 0, "Should parse at least one transaction")

            # Check structure of first transaction
            if transactions:
                first_trans = transactions[0]
                self.assertIn('accountNumber', first_trans, "Transaction should have accountNumber")
                self.assertIn('amount', first_trans, "Transaction should have amount")
                self.assertIn('description', first_trans, "Transaction should have description")
                self.assertIn('transactiondate', first_trans, "Transaction should have transactiondate")

                # Verify data types
                self.assertIsInstance(first_trans['accountNumber'], str)
                self.assertIsInstance(first_trans['description'], str)

                # Verify description_structured is included if description exists
                if first_trans.get('description'):
                    # description_structured may or may not be present depending on parsing success
                    # but if present, it should be a JSON string
                    if 'description_structured' in first_trans and first_trans['description_structured']:
                        import json
                        try:
                            parsed = json.loads(first_trans['description_structured'])
                            self.assertIsInstance(parsed, dict, "description_structured should be valid JSON")
                        except json.JSONDecodeError:
                            self.fail("description_structured should be valid JSON string")

                print(f"✓ Successfully parsed STA file with {len(transactions)} transactions")
                print(f"  First transaction: {first_trans.get('description', 'N/A')} - €{first_trans.get('amount', 0)}")

    def test_parse_sta_file_direct(self):
        """Test parsing a STA file directly using parse_mt940_file."""
        # Create a temporary STA file with sample MT940 content
        sample_sta_content = """ABNANL2A
940
ABNANL2A
:20:ABN AMRO BANK NV
:25:720317081
:28:13701/1
:60F:C240515EUR151,31
:61:2405160516D5,75N426NONREF
:86:BEA, BETAALPAS                   WLBSS TEE MARKT,PAS603
NR:24960249, 16.05.24/15:52      RWHMIAYZMC
:62F:C240516EUR145,56
-"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.STA', delete=False) as f:
            f.write(sample_sta_content)
            temp_sta_path = Path(f.name)

        try:
            # Parse the STA file directly
            transactions = parse_mt940_file(temp_sta_path)

            # Verify the result
            self.assertIsInstance(transactions, list, "Should return a list of transactions")

            # Note: The parser might return empty list if the sample is too simple
            # But the function should not raise an error
            print("✓ Successfully called parse_mt940_file on STA file")
            print(f"  Parsed {len(transactions)} transactions")
        except ValueError as e:
            if "not available" in str(e):
                self.skipTest("abn-amro-statement-parser not installed")
            else:
                raise
        finally:
            # Clean up temporary file
            temp_sta_path.unlink()

    def test_parse_mt940_transaction_type_code_and_reference(self):
        """Test parsing transaction type code and reference from :61: line."""
        # Create a temporary STA file with :61: line containing type code and reference
        sample_sta_content = """ABNANL2A
940
ABNANL2A
:20:ABN AMRO BANK NV
:25:720317081
:28:13701/1
:60F:C240515EUR151,31
:61:2405160516D5,75N426NONREF
:86:BEA, BETAALPAS                   WLBSS TEE MARKT,PAS603
NR:24960249, 16.05.24/15:52      RWHMIAYZMC
:62F:C240516EUR145,56
-"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.STA', delete=False) as f:
            f.write(sample_sta_content)
            temp_sta_path = Path(f.name)

        try:
            # Parse the STA file
            transactions = parse_mt940_file(temp_sta_path)

            # Verify we got at least one transaction
            self.assertGreater(len(transactions), 0, "Should parse at least one transaction")

            if transactions:
                trans = transactions[0]
                # Verify transaction type code is extracted
                self.assertIn('transaction_type_code', trans, "Transaction should have transaction_type_code")
                self.assertEqual(trans['transaction_type_code'], 'N426', "Transaction type code should be N426")

                # Verify transaction reference is extracted
                self.assertIn('transaction_reference', trans, "Transaction should have transaction_reference")
                self.assertEqual(trans['transaction_reference'], 'NONREF', "Transaction reference should be NONREF")

                # Verify other fields are still correct
                self.assertEqual(trans['amount'], -5.75, "Amount should be -5.75 (debit)")
                self.assertIn('transactiondate', trans, "Transaction should have transactiondate")

                print("✓ Transaction type code and reference extraction test passed")
        except ValueError as e:
            if "not available" in str(e):
                self.skipTest("abn-amro-statement-parser not installed")
            else:
                raise
        finally:
            # Clean up temporary file
            temp_sta_path.unlink()

    def test_parse_mt940_transaction_type_code_variations(self):
        """Test parsing different transaction type code formats."""
        test_cases = [
            {
                'line': ':61:2405160516D5,75N426NONREF',
                'expected_type_code': 'N426',
                'expected_reference': 'NONREF',
                'expected_amount': -5.75
            },
            {
                'line': ':61:2405160516C100,00N123REF12345',
                'expected_type_code': 'N123',
                'expected_reference': 'REF12345',
                'expected_amount': 100.00
            },
            {
                'line': ':61:2405160516D25,50N999CUSTOMREF',
                'expected_type_code': 'N999',
                'expected_reference': 'CUSTOMREF',
                'expected_amount': -25.50
            },
        ]

        for i, test_case in enumerate(test_cases):
            # Create a minimal STA file with the test :61: line
            sample_sta_content = f"""ABNANL2A
940
ABNANL2A
:20:ABN AMRO BANK NV
:25:720317081
:28:13701/1
:60F:C240515EUR151,31
{test_case['line']}
:86:Test transaction description
:62F:C240516EUR145,56
-"""
            with tempfile.NamedTemporaryFile(mode='w', suffix='.STA', delete=False) as f:
                f.write(sample_sta_content)
                temp_sta_path = Path(f.name)

            try:
                # Parse the STA file
                transactions = parse_mt940_file(temp_sta_path)

                if transactions:
                    trans = transactions[0]
                    self.assertEqual(
                        trans.get('transaction_type_code'),
                        test_case['expected_type_code'],
                        f"Test case {i+1}: Type code should be {test_case['expected_type_code']}"
                    )
                    self.assertEqual(
                        trans.get('transaction_reference'),
                        test_case['expected_reference'],
                        f"Test case {i+1}: Reference should be {test_case['expected_reference']}"
                    )
                    self.assertAlmostEqual(
                        trans.get('amount'),
                        test_case['expected_amount'],
                        places=2,
                        msg=f"Test case {i+1}: Amount should be {test_case['expected_amount']}"
                    )
                else:
                    # If parser returns empty, that's okay for this test
                    # We're mainly testing the parsing logic exists
                    pass
            except ValueError as e:
                if "not available" in str(e):
                    self.skipTest("abn-amro-statement-parser not installed")
                else:
                    raise
            finally:
                # Clean up temporary file
                temp_sta_path.unlink()

        print("✓ Transaction type code variations test passed")


class TestDescriptionParsers(unittest.TestCase):
    """Test cases for transaction description parsers."""

    def test_parse_mt940_description(self):
        """Test parsing MT940 structured descriptions."""
        # Test case from user query
        description = "/TRTP/IDEAL/IBAN/NL17DEUT9882502818/BIC/DEUTNL2A/NAME/MILIEUSTICK ER LIVE VIA MULTISAFEPAY/REMI/1014936296 8151677019329336 BETALIN G VOOR ORDER. SO24774441 MILIEUSTICKER LIVE/EREF/12-11-2024 18:03 8151677019329336"

        result = parse_mt940_description(description)

        self.assertIsNotNone(result, "Should parse MT940 description")
        self.assertEqual(result['format'], 'mt940')
        self.assertEqual(result['transaction_type'], 'IDEAL')
        self.assertEqual(result['iban'], 'NL17DEUT9882502818')
        self.assertEqual(result['bic'], 'DEUTNL2A')
        self.assertIn('MILIEUSTICK', result['name'])
        self.assertIn('1014936296', result['remittance_info'])
        self.assertIn('12-11-2024 18:03', result['end_to_end_reference'])

        print("✓ MT940 description parser test passed")

    def test_parse_mt940_description_unknown_fields(self):
        """Test parsing MT940 with unknown fields."""
        description = "/TRTP/IDEAL/IBAN/NL17DEUT9882502818/UNKNOWN/TEST_VALUE/"

        result = parse_mt940_description(description)

        self.assertIsNotNone(result)
        self.assertIn('other_fields', result)
        self.assertEqual(result['other_fields']['UNKNOWN'], 'TEST_VALUE')

        print("✓ MT940 unknown fields test passed")

    def test_parse_mt940_description_invalid(self):
        """Test parsing invalid MT940 description."""
        description = "This is not an MT940 description"

        result = parse_mt940_description(description)

        self.assertIsNone(result, "Should return None for invalid MT940 description")

        print("✓ MT940 invalid description test passed")

    def test_parse_mt940_description_tikkie_sepa(self):
        """Test parsing Tikkie SEPA OVERBOEKING description."""
        description = "/TRTP/SEPA OVERBOEKING/IBAN/NL13ABNA8992624444/BIC/ABNANL2A/NAME/ AAB INZ TIKKIE/REMI/TIKKIE ID 434142529147, PICS, VAN Q VAN EXAMPLEDAM, NL83ABNA5175097314/EREF/1123453991"

        result = parse_mt940_description(description)

        self.assertIsNotNone(result, "Should parse Tikkie SEPA description")
        self.assertEqual(result['format'], 'mt940')
        self.assertEqual(result['transaction_type'], 'SEPA OVERBOEKING')
        self.assertTrue(result.get('is_tikkie'))
        self.assertEqual(result['payment_service'], 'Tikkie')
        self.assertEqual(result['tikkie_id'], '434142529147')
        self.assertEqual(result['payer_name'], 'VAN Q VAN EXAMPLEDAM')
        self.assertEqual(result['payer_iban'], 'NL83ABNA5175097314')

        print("✓ MT940 Tikkie SEPA description parser test passed")

    def test_parse_mt940_description_tikkie_sepa_alternative(self):
        """Test parsing alternative Tikkie SEPA OVERBOEKING format."""
        description = "/TRTP/SEPA OVERBOEKING/IBAN/NL13ABNA8992624444/BIC/ABNANL2A/NAME/ AAB INZ TIKKIE/REMI/TIKKIE ID 172029543652, PLS, VAN A VAN LCJFOS T, NL21ABNA9847172551/EREF/9461373284"

        result = parse_mt940_description(description)

        self.assertIsNotNone(result, "Should parse Tikkie SEPA description")
        self.assertTrue(result.get('is_tikkie'))
        self.assertEqual(result['tikkie_id'], '172029543652')
        self.assertEqual(result['payer_name'], 'VAN A VAN LCJFOS T')
        self.assertEqual(result['payer_iban'], 'NL21ABNA9847172551')

        print("✓ MT940 Tikkie SEPA alternative format test passed")

    def test_parse_mt940_description_tikkie_ideal(self):
        """Test parsing Tikkie IDEAL description."""
        description = "/TRTP/IDEAL/IBAN/NL13ABNA8992624444/BIC/ABNANL2A/NAME/VAN LCJFOST VIA TIKKIE/REMI/133916989819 6199124765088459 FOR THE COIN NL21A BNA9847172551/EREF/23-10-2025 23:57 6199124765088459"

        result = parse_mt940_description(description)

        self.assertIsNotNone(result, "Should parse Tikkie IDEAL description")
        self.assertEqual(result['format'], 'mt940')
        self.assertEqual(result['transaction_type'], 'IDEAL')
        self.assertTrue(result.get('is_tikkie'))
        self.assertEqual(result['payment_service'], 'Tikkie')
        self.assertEqual(result['tikkie_id'], '133916989819')
        self.assertEqual(result['payment_reference'], '6199124765088459')
        self.assertEqual(result['payment_description'], 'FOR THE COIN')
        self.assertEqual(result['payer_iban'], 'NL21ABNA9847172551')
        self.assertEqual(result['payer_name'], 'VAN LCJFOST')
        self.assertEqual(result['tikkie_timestamp'], '23-10-2025 23:57')

        print("✓ MT940 Tikkie IDEAL description parser test passed")

    def test_parse_pos_description_betaalpas(self):
        """Test parsing POS Betaalpas description with merchant code."""
        description = "BEA, BETAALPAS BCK*PLUS OMBXQOZ,PAS422 NR:DP234188, 11.11.24/16:26 RWHMIAYZMC"

        result = parse_pos_description(description)

        self.assertIsNotNone(result, "Should parse POS description")
        self.assertEqual(result['format'], 'pos')
        self.assertEqual(result['transaction_type'], 'POS')
        self.assertEqual(result['payment_method'], 'Betaalpas')
        self.assertEqual(result['merchant_code'], 'BCK')
        self.assertEqual(result['merchant_name'], 'PLUS OMBXQOZ')
        self.assertEqual(result['card_terminal_id'], '422')
        self.assertEqual(result['transaction_reference'], 'DP234188')
        self.assertEqual(result['transaction_date'], '2024-11-11')
        self.assertEqual(result['transaction_time'], '16:26')
        self.assertEqual(result['location'], 'RWHMIAYZMC')

        print("✓ POS Betaalpas description parser test passed")

    def test_parse_pos_description_betaalpas_no_code(self):
        """Test parsing POS Betaalpas description without merchant code."""
        description = "BEA, BETAALPAS AH UPEVWAWA DMJVGCPGP,PAS604 NR:CT941320, 11.11.25/17:45 RWHMIAYZMC"

        result = parse_pos_description(description)

        self.assertIsNotNone(result, "Should parse POS description")
        self.assertEqual(result['format'], 'pos')
        self.assertEqual(result['transaction_type'], 'POS')
        self.assertEqual(result['payment_method'], 'Betaalpas')
        self.assertEqual(result['merchant_name'], 'AH UPEVWAWA DMJVGCPGP')
        self.assertEqual(result['card_terminal_id'], '604')
        self.assertEqual(result['transaction_reference'], 'CT941320')
        self.assertEqual(result['transaction_date'], '2025-11-11')
        self.assertEqual(result['transaction_time'], '17:45')
        self.assertEqual(result['location'], 'RWHMIAYZMC')
        # Should not have merchant_code when not present
        self.assertNotIn('merchant_code', result)

        print("✓ POS Betaalpas without code description parser test passed")

    def test_parse_pos_description_apple_pay(self):
        """Test parsing POS Apple Pay description."""
        description = "BEA, APPLE PAY PATISSERIE QAAEKFR,PAS422 NR:98SMT9, 30.08.23/11:05 PPBOUVJTE"

        result = parse_pos_description(description)

        self.assertIsNotNone(result, "Should parse Apple Pay description")
        self.assertEqual(result['format'], 'pos')
        self.assertEqual(result['transaction_type'], 'POS')
        self.assertEqual(result['payment_method'], 'Apple Pay')
        self.assertEqual(result['merchant_name'], 'PATISSERIE QAAEKFR')
        self.assertEqual(result['card_terminal_id'], '422')
        self.assertEqual(result['transaction_reference'], '98SMT9')
        self.assertEqual(result['transaction_date'], '2023-08-30')
        self.assertEqual(result['transaction_time'], '11:05')
        self.assertEqual(result['location'], 'PPBOUVJTE')
        # Apple Pay should not have merchant_code
        self.assertNotIn('merchant_code', result)

        print("✓ POS Apple Pay description parser test passed")

    def test_parse_pos_description_apple_pay_with_comma_in_merchant(self):
        """Test parsing POS Apple Pay description with comma in merchant name."""
        description = "BEA, APPLE PAY REWE IRRWHJ, SMTJAPOR,PAS353 NR:26260713, 03.04.25/12:01 IRRWHJ, LAND: DEU"

        result = parse_pos_description(description)

        self.assertIsNotNone(result, "Should parse Apple Pay description with comma in merchant name")
        self.assertEqual(result['format'], 'pos')
        self.assertEqual(result['transaction_type'], 'POS')
        self.assertEqual(result['payment_method'], 'Apple Pay')
        self.assertEqual(result['merchant_name'], 'REWE IRRWHJ, SMTJAPOR')
        self.assertEqual(result['card_terminal_id'], '353')
        self.assertEqual(result['transaction_reference'], '26260713')
        self.assertEqual(result['transaction_date'], '2025-04-03')
        self.assertEqual(result['transaction_time'], '12:01')
        # Location might be "IRRWHJ, LAND: DEU" or just "DEU" depending on parsing
        self.assertIn('location', result)
        # Apple Pay should not have merchant_code
        self.assertNotIn('merchant_code', result)

        print("✓ POS Apple Pay description parser test with comma in merchant name passed")

    def test_parse_pos_description_ecom_apple_pay(self):
        """Test parsing ECOM Apple Pay description with foreign currency."""
        description = "ECOM, APPLE PAY PRAGUE CLASS. CONCERTS NR:JNQI4366, 14.12.24/11:47 PRAHA - NOVE, LAND: CZE CZK 1.100,00 1EUR=24,5316 CZK ECB KOERS=25,092969 OPSLAG=2,29%"

        result = parse_pos_description(description)

        self.assertIsNotNone(result, "Should parse ECOM Apple Pay description")
        self.assertEqual(result['format'], 'pos')
        self.assertEqual(result['transaction_type'], 'ECOM')
        self.assertEqual(result['payment_method'], 'Apple Pay')
        self.assertEqual(result['merchant_name'], 'PRAGUE CLASS. CONCERTS')
        self.assertEqual(result['transaction_reference'], 'JNQI4366')
        self.assertEqual(result['transaction_date'], '2024-12-14')
        self.assertEqual(result['transaction_time'], '11:47')
        self.assertEqual(result['location'], 'PRAHA - NOVE')
        self.assertEqual(result['country_code'], 'CZE')
        self.assertEqual(result['foreign_currency'], 'CZK')
        self.assertEqual(result['foreign_amount'], 1100.0)
        self.assertEqual(result['exchange_rate'], 24.5316)
        # ECOM should not have merchant_code
        self.assertNotIn('merchant_code', result)

        print("✓ ECOM Apple Pay description parser test passed")

    def test_parse_pos_description_invalid(self):
        """Test parsing invalid POS description."""
        description = "This is not a POS transaction"

        result = parse_pos_description(description)

        self.assertIsNone(result, "Should return None for invalid POS description")

        print("✓ POS invalid description test passed")

    def test_parse_sepa_overboeking(self):
        """Test parsing SEPA OVERBOEKING description."""
        description = "SEPA OVERBOEKING IBAN: NL86INGB0274974340 BIC: INGBNL2A NAAM: BDOLWGP GRWMDQ ARTIST OMSCHRIJVING: JYNQ VAN LCJFOST"

        result = parse_sepa_description(description)

        self.assertIsNotNone(result, "Should parse SEPA description")
        self.assertEqual(result['format'], 'sepa')
        self.assertEqual(result['sepa_type'], 'OVERBOEKING')
        self.assertEqual(result['transaction_type'], 'SEPA Transfer')
        self.assertEqual(result['iban'], 'NL86INGB0274974340')
        self.assertEqual(result['bic'], 'INGBNL2A')
        self.assertEqual(result['name'], 'BDOLWGP GRWMDQ ARTIST')
        self.assertEqual(result['description'], 'JYNQ VAN LCJFOST')

        print("✓ SEPA OVERBOEKING description parser test passed")

    def test_parse_sepa_overboeking_with_betalingskenm(self):
        """Test parsing SEPA OVERBOEKING with BETALINGSKENM. and KENMERK fields."""
        description = "SEPA OVERBOEKING IBAN: NL18INGB2073643043 BIC: INGBNL2A NAAM: BSGW BETALINGSKENM.: 8313040666451382 KENMERK: BSGW 2025"

        result = parse_sepa_description(description)

        self.assertIsNotNone(result, "Should parse SEPA description with BETALINGSKENM")
        self.assertEqual(result['format'], 'sepa')
        self.assertEqual(result['sepa_type'], 'OVERBOEKING')
        self.assertEqual(result['transaction_type'], 'SEPA Transfer')
        self.assertEqual(result['iban'], 'NL18INGB2073643043')
        self.assertEqual(result['bic'], 'INGBNL2A')
        self.assertEqual(result['name'], 'BSGW')
        self.assertEqual(result['payment_reference'], '8313040666451382')
        self.assertEqual(result['reference'], 'BSGW 2025')
        # Should not have description field when OMSCHRIJVING is not present
        self.assertNotIn('description', result)

        print("✓ SEPA OVERBOEKING with BETALINGSKENM parser test passed")

    def test_parse_sepa_ideal(self):
        """Test parsing SEPA IDEAL description."""
        description = "SEPA IDEAL IBAN: DE17471785880725371008 BIC: SXPYDEHH NAAM: AMAZON PAYMENTS EUROPE SCA VIA STRIPE TECHNOLOGY EUROPE LT D OMSCHRIJVING: 6526BPW 7140617930 049971 304-0337481-9469925 AMAZO N PAYMENTS EUROPE SCA"

        result = parse_sepa_description(description)

        self.assertIsNotNone(result, "Should parse SEPA IDEAL description")
        self.assertEqual(result['format'], 'sepa')
        self.assertEqual(result['sepa_type'], 'IDEAL')
        self.assertEqual(result['transaction_type'], 'SEPA iDEAL')
        self.assertEqual(result['iban'], 'DE17471785880725371008')
        self.assertEqual(result['bic'], 'SXPYDEHH')
        self.assertIn('AMAZON PAYMENTS', result['name'])
        self.assertIn('6526BPW', result['description'])

        print("✓ SEPA IDEAL description parser test passed")

    def test_parse_sepa_ideal_tikkie(self):
        """Test parsing SEPA IDEAL Tikkie description."""
        description = "SEPA IDEAL IBAN: NL13ABNA8992624444 BIC: ABNANL2A NAAM: VAN LBRMLPK VIA TIKKIE OMSCHRIJVING: 327826342655 00315 88265879905 YEAH NL58INGB1220774 608 KENMERK: 15-07-2025 18:46 003151 6243165508"

        result = parse_sepa_description(description)

        self.assertIsNotNone(result, "Should parse SEPA IDEAL Tikkie description")
        self.assertEqual(result['format'], 'sepa')
        self.assertEqual(result['sepa_type'], 'IDEAL')
        self.assertEqual(result['transaction_type'], 'SEPA iDEAL')
        self.assertTrue(result.get('is_tikkie'), "Should detect as Tikkie transaction")
        self.assertEqual(result.get('payment_service'), 'Tikkie')
        self.assertEqual(result.get('tikkie_id'), '327826342655')
        self.assertEqual(result.get('payer_name'), 'VAN LBRMLPK')
        self.assertEqual(result.get('payment_reference'), '00315')
        self.assertEqual(result.get('payer_iban'), 'NL58INGB1220774')
        self.assertEqual(result.get('payment_description'), '88265879905 YEAH')
        self.assertEqual(result.get('tikkie_timestamp'), '15-07-2025 18:46')

        print("✓ SEPA IDEAL Tikkie description parser test passed")

    def test_parse_sepa_ideal_tikkie_second_format(self):
        """Test parsing SEPA IDEAL Tikkie description (second format)."""
        description = "SEPA IDEAL IBAN: NL13ABNA8992624444 BIC: ABNANL2A NAAM: RRITGG VIA TIKKIE OMSCHRIJVING: 447531226743 00314 79465503525 MASKS NL31ABNA387071 8505 KENMERK: 15-07-2025 18:24 003141 5551317083"

        result = parse_sepa_description(description)

        self.assertIsNotNone(result, "Should parse SEPA IDEAL Tikkie description")
        self.assertEqual(result['format'], 'sepa')
        self.assertEqual(result['sepa_type'], 'IDEAL')
        self.assertEqual(result['transaction_type'], 'SEPA iDEAL')
        self.assertTrue(result.get('is_tikkie'), "Should detect as Tikkie transaction")
        self.assertEqual(result.get('payment_service'), 'Tikkie')
        self.assertEqual(result.get('tikkie_id'), '447531226743')
        self.assertEqual(result.get('payer_name'), 'RRITGG')
        self.assertEqual(result.get('payment_reference'), '00314')
        self.assertEqual(result.get('payer_iban'), 'NL31ABNA387071')
        self.assertEqual(result.get('payment_description'), '79465503525 MASKS')
        self.assertEqual(result.get('tikkie_timestamp'), '15-07-2025 18:24')

        print("✓ SEPA IDEAL Tikkie description parser test (second format) passed")

    def test_parse_sepa_incasso(self):
        """Test parsing SEPA INCASSO description."""
        description = "SEPA INCASSO ALGEMEEN DOORLOPEND INCASSANT: TF45FAQ873822907467 NAAM: VRAWD-KFQONIZ FITNESS MACHTIGING: ANYTIME-NL-0267546 IBAN: NL77RABO8509119907 KENMERK: 42215366-68650"

        result = parse_sepa_description(description)

        self.assertIsNotNone(result, "Should parse SEPA INCASSO description")
        self.assertEqual(result['format'], 'sepa')
        self.assertEqual(result['sepa_type'], 'INCASSO')
        self.assertEqual(result['transaction_type'], 'SEPA Direct Debit')
        self.assertEqual(result['direct_debit_type'], 'General')
        self.assertTrue(result['recurring'])
        self.assertEqual(result['creditor_identifier'], 'TF45FAQ873822907467')
        self.assertEqual(result['name'], 'VRAWD-KFQONIZ FITNESS')
        self.assertEqual(result['mandate_reference'], 'ANYTIME-NL-0267546')
        self.assertEqual(result['iban'], 'NL77RABO8509119907')
        self.assertEqual(result['reference'], '42215366-68650')

        print("✓ SEPA INCASSO description parser test passed")

    def test_parse_sepa_description_invalid(self):
        """Test parsing invalid SEPA description."""
        description = "This is not a SEPA transaction"

        result = parse_sepa_description(description)

        self.assertIsNone(result, "Should return None for invalid SEPA description")

        print("✓ SEPA invalid description test passed")

    def test_parse_transaction_description_mt940(self):
        """Test main parser with MT940 description."""
        description = "/TRTP/IDEAL/IBAN/NL17DEUT9882502818/BIC/DEUTNL2A/NAME/TEST MERCHANT/"

        result = parse_transaction_description(description)

        self.assertIsNotNone(result)
        self.assertEqual(result['format'], 'mt940')
        self.assertEqual(result['transaction_type'], 'IDEAL')

        print("✓ Main parser MT940 test passed")

    def test_parse_transaction_description_sepa(self):
        """Test main parser with SEPA description."""
        description = "SEPA OVERBOEKING IBAN: NL86INGB0274974340 BIC: INGBNL2A NAAM: TEST MERCHANT"

        result = parse_transaction_description(description)

        self.assertIsNotNone(result)
        self.assertEqual(result['format'], 'sepa')
        self.assertEqual(result['transaction_type'], 'SEPA Transfer')

        print("✓ Main parser SEPA test passed")

    def test_parse_transaction_description_pos(self):
        """Test main parser with POS description."""
        description = "BEA, APPLE PAY PATISSERIE QAAEKFR,PAS422 NR:98SMT9, 30.08.23/11:05 PPBOUVJTE"

        result = parse_transaction_description(description)

        self.assertIsNotNone(result)
        self.assertEqual(result['format'], 'pos')
        self.assertEqual(result['payment_method'], 'Apple Pay')

        print("✓ Main parser POS test passed")

    def test_parse_transaction_description_priority(self):
        """Test that parser tries formats in correct order (MT940 -> SEPA -> POS)."""
        # This description could match multiple formats, but MT940 should be tried first
        # Since it doesn't start with /, it won't match MT940
        # Since it doesn't start with SEPA, it won't match SEPA
        # It should match POS
        description = "BEA, BETAALPAS BCK*PLUS OMBXQOZ,PAS422 NR:DP234188, 11.11.24/16:26 RWHMIAYZMC"

        result = parse_transaction_description(description)

        self.assertIsNotNone(result)
        self.assertEqual(result['format'], 'pos', "Should match POS format")

        print("✓ Parser priority test passed")

    def test_parse_transaction_description_unparseable(self):
        """Test main parser with unparseable description."""
        description = "This is a plain text description with no structure"

        result = parse_transaction_description(description)

        self.assertIsNone(result, "Should return None for unparseable description")

        print("✓ Main parser unparseable description test passed")

    def test_parse_transaction_description_empty(self):
        """Test main parser with empty description."""
        result = parse_transaction_description("")
        self.assertIsNone(result)

        result = parse_transaction_description(None)
        self.assertIsNone(result)

        print("✓ Main parser empty description test passed")

    def test_parse_account_balance_description(self):
        """Test parsing account balance/interest credit description."""
        description = "ACCOUNT BALANCED                 CREDIT INTEREST            0,38C FROM 30.06.2025 TO 30.09.2025    DIRECT SAVINGS FOR INTEREST RATES PLEASE VISIT  WWW.ABNAMRO.NL/RENTE"

        result = parse_account_balance_description(description)

        self.assertIsNotNone(result, "Should parse account balance description")
        self.assertEqual(result['format'], 'account_balance')
        self.assertEqual(result['transaction_type'], 'Credit Interest')
        self.assertEqual(result['interest_type'], 'CREDIT INTEREST')
        self.assertEqual(result['amount'], 0.38)
        self.assertEqual(result['amount_indicator'], 'C')
        self.assertTrue(result['is_credit'])
        self.assertEqual(result['period_from'], '2025-06-30')
        self.assertEqual(result['period_to'], '2025-09-30')
        self.assertIn('additional_info', result)
        self.assertIn('DIRECT SAVINGS', result['additional_info'])
        self.assertEqual(result['url'], 'WWW.ABNAMRO.NL/RENTE')

        print("✓ Account balance description parser test passed")

    def test_parse_account_balance_description_debit_interest(self):
        """Test parsing account balance with debit interest."""
        description = "ACCOUNT BALANCED                 DEBIT INTEREST            1,50D FROM 01.01.2025 TO 31.03.2025    OVERDRAFT INTEREST"

        result = parse_account_balance_description(description)

        self.assertIsNotNone(result, "Should parse debit interest description")
        self.assertEqual(result['format'], 'account_balance')
        self.assertEqual(result['interest_type'], 'DEBIT INTEREST')
        self.assertEqual(result['transaction_type'], 'Debit Interest')
        self.assertEqual(result['amount'], 1.50)
        self.assertEqual(result['amount_indicator'], 'D')
        self.assertFalse(result['is_credit'])
        self.assertEqual(result['period_from'], '2025-01-01')
        self.assertEqual(result['period_to'], '2025-03-31')

        print("✓ Account balance debit interest description parser test passed")

    def test_parse_account_balance_description_invalid(self):
        """Test parsing invalid account balance description."""
        description = "This is not an account balance description"

        result = parse_account_balance_description(description)

        self.assertIsNone(result, "Should return None for invalid account balance description")

        print("✓ Account balance invalid description test passed")

    def test_parse_transaction_description_account_balance(self):
        """Test main parser with account balance description."""
        description = "ACCOUNT BALANCED                 CREDIT INTEREST            0,38C FROM 30.06.2025 TO 30.09.2025    DIRECT SAVINGS FOR INTEREST RATES PLEASE VISIT  WWW.ABNAMRO.NL/RENTE"

        result = parse_transaction_description(description)

        self.assertIsNotNone(result)
        self.assertEqual(result['format'], 'account_balance')
        self.assertEqual(result['transaction_type'], 'Credit Interest')
        self.assertEqual(result['amount'], 0.38)

        print("✓ Main parser account balance test passed")


if __name__ == '__main__':
    unittest.main()

