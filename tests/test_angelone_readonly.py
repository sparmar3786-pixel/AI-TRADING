import os
import unittest
from unittest.mock import patch

from integrations.angelone_readonly import AngelOneConfigError, AngelOneReadOnly


class AngelOneReadOnlyTests(unittest.TestCase):
    def test_missing_credentials_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AngelOneConfigError):
                AngelOneReadOnly().profile()

    def test_invalid_exchange_rejected_before_login(self):
        with self.assertRaises(ValueError):
            AngelOneReadOnly().ltp("CRYPTO", "X", "1")

    def test_empty_contract_rejected_before_login(self):
        with self.assertRaises(ValueError):
            AngelOneReadOnly().ltp("NSE", "", "1")


if __name__ == "__main__":
    unittest.main()
