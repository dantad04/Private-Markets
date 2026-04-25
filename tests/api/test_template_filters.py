from __future__ import annotations

from decimal import Decimal
import unittest

from app.api.app import _format_aud_compact, _format_pct_compact


class TestTemplateFilters(unittest.TestCase):
    def test_aud_compact_formats_core_magnitudes(self) -> None:
        self.assertEqual("$0", _format_aud_compact(0))
        self.assertEqual("—", _format_aud_compact(None))
        self.assertEqual("$999", _format_aud_compact(Decimal("999")))
        self.assertEqual("$12.3k", _format_aud_compact(Decimal("12345")))
        self.assertEqual("$59.5m", _format_aud_compact(Decimal("59460189")))
        self.assertEqual("$3.34b", _format_aud_compact(Decimal("3344802313")))
        self.assertEqual("$23.4m", _format_aud_compact(Decimal("23389252")))

    def test_pct_compact_formats_decimal_fractions_and_impossible_values(self) -> None:
        self.assertEqual("—", _format_pct_compact(None))
        self.assertEqual("0.18%", _format_pct_compact(Decimal("0.0018")))
        self.assertEqual("16.90%", _format_pct_compact(Decimal("0.169")))
        self.assertEqual("100.00%", _format_pct_compact(Decimal("1")))
        self.assertEqual("1.2", _format_pct_compact(Decimal("1.2")))

