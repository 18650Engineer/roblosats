"""
Roblosats rl12: follow-ups from the external review of the order-lock / payout hardening.

- BTCB2 price oracle: the last stored USD price is really read (it was always None, so
  BTCB2_MAX_STEP never applied); fewer than BTCB2_MIN_VENUES distinct venues (or two that disagree)
  keep the last stored price; the legacy Neoxa-only path uses the book midpoint.
- LND hold-invoice amount check: an under-paid invoice is never reported LOCKED, even
  if cancelling it fails.
- order_lock refuses to run without PostgreSQL.
"""

import hashlib
from decimal import Decimal
from unittest.mock import MagicMock, patch

from decouple import config as real_config
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from api.models import Currency, LNPayment
from api.utils import neoxa_rates, nonkyc_rates

NONKYC = "https://api.nonkyc.io/api/v2/ticker/BTCB2_USDT"
NONKYC_BTC = "https://api.nonkyc.io/api/v2/ticker/BTCB2_BTC"
NEOXA = "https://neoxa.exchange/api/exchange/ticker/BTCB2_USDC"
NEOXA_BTC = "https://neoxa.exchange/api/exchange/ticker/BTCB2_BTC"
YADIO = "https://api.yadio.io/exrates/USD"


def fake_config(overrides):
    def _config(name, *args, **kwargs):
        if name in overrides:
            return overrides[name]
        if "default" in kwargs:
            return kwargs["default"]
        return real_config(name, *args, **kwargs)

    return _config


class FakeSession:
    """session.get(url).json() from a dict; a missing URL raises like a dead venue."""

    def __init__(self, answers):
        self.answers = answers

    def get(self, url, *args, **kwargs):
        if url not in self.answers:
            raise ConnectionError(f"{url} unreachable")
        r = MagicMock()
        r.json.return_value = self.answers[url]
        return r


def nonkyc_book(bid, ask):
    return {"bid": str(bid), "ask": str(ask)}


def neoxa_book(bid, ask):
    return {"ticker": {"bestBid": str(bid), "bestAsk": str(ask), "lastPrice": "1"}}


YADIO_ANSWER = {"USD": {"EUR": 0.9}, "BTC": 100000.0}


class NonkycRatesTest(TestCase):
    def setUp(self):
        self.usd = next(int(k) for k, v in Currency.currency_dict.items() if v == "USD")

    def store_last(self, price):
        Currency.objects.update_or_create(
            currency=self.usd, defaults={"exchange_rate": Decimal(price)}
        )

    def rates(self, answers, **overrides):
        cfg = {"NEOXA_TICKER_URL": NEOXA, **overrides}
        with patch("api.utils.config", side_effect=fake_config(cfg)):
            return nonkyc_rates(FakeSession(answers), NONKYC, ["USD", "EUR"])

    def test_two_agreeing_venues_mean(self):
        self.store_last(1000)
        usd, eur = self.rates(
            {
                YADIO: YADIO_ANSWER,
                NONKYC: nonkyc_book(995, 1005),  # 1000
                NONKYC_BTC: nonkyc_book(0.0099, 0.0101),  # 0.01 x 100000 = 1000
                NEOXA: neoxa_book(1015, 1025),  # 1020
            }
        )
        self.assertAlmostEqual(usd, 1010, places=6)
        self.assertAlmostEqual(eur, 1010 * 0.9, places=6)

    def test_one_venue_keeps_last_price(self):
        # Neoxa down: NonKYC alone (both of its books) must not move the price.
        self.store_last(1000)
        usd, _ = self.rates(
            {
                YADIO: YADIO_ANSWER,
                NONKYC: nonkyc_book(1040, 1050),
                NONKYC_BTC: nonkyc_book(0.0104, 0.0105),
            }
        )
        self.assertEqual(usd, 1000)

    def test_one_venue_allowed_when_min_venues_is_one(self):
        self.store_last(1000)
        usd, _ = self.rates(
            {YADIO: YADIO_ANSWER, NEOXA: neoxa_book(1019, 1021)},
            BTCB2_MIN_VENUES=1,
        )
        self.assertAlmostEqual(usd, 1020, places=6)

    def test_one_venue_on_first_start(self):
        # No stored price yet: one venue is enough to start.
        Currency.objects.filter(currency=self.usd).delete()
        usd, _ = self.rates({YADIO: YADIO_ANSWER, NEOXA: neoxa_book(1019, 1021)})
        self.assertAlmostEqual(usd, 1020, places=6)

    def test_disagreeing_venues_keep_last_price(self):
        self.store_last(1000)
        usd, _ = self.rates(
            {
                YADIO: YADIO_ANSWER,
                NONKYC: nonkyc_book(1000, 1002),
                NEOXA: neoxa_book(1300, 1302),  # 30 % off
            }
        )
        self.assertEqual(usd, 1000)

    def test_step_cap_still_applies(self):
        self.store_last(1000)
        usd, _ = self.rates(
            {
                YADIO: YADIO_ANSWER,
                NONKYC: nonkyc_book(1199, 1201),
                NEOXA: neoxa_book(1199, 1201),
            }
        )
        self.assertAlmostEqual(usd, 1050, places=6)

    def test_wide_spread_is_not_a_quote(self):
        self.store_last(1000)
        usd, _ = self.rates(
            {
                YADIO: YADIO_ANSWER,
                NONKYC: nonkyc_book(500, 1500),  # spread 100 %
                NEOXA: neoxa_book(1019, 1021),
            }
        )
        self.assertEqual(usd, 1000)  # only Neoxa counts: one venue


class NeoxaRatesTest(TestCase):
    def test_midpoint_not_last_trade(self):
        with patch("api.utils.config", side_effect=fake_config({})):
            usd, btc = neoxa_rates(
                FakeSession(
                    {
                        YADIO: YADIO_ANSWER,
                        NEOXA: neoxa_book(990, 1010),
                        NEOXA_BTC: neoxa_book(0.0099, 0.0101),
                    }
                ),
                NEOXA,
                ["USD", "BTC"],
            )
        self.assertAlmostEqual(usd, 1000, places=6)
        self.assertAlmostEqual(btc, 0.01, places=9)

    def test_wide_spread_uses_fallback(self):
        with patch(
            "api.utils.config", side_effect=fake_config({"BTCB2_FALLBACK_USD": 800.0})
        ):
            (usd,) = neoxa_rates(
                FakeSession({YADIO: YADIO_ANSWER, NEOXA: neoxa_book(500, 1500)}),
                NEOXA,
                ["USD"],
            )
        self.assertEqual(usd, 800.0)


class LockedAmountCheckTest(TestCase):
    """lookup_invoice_status: an ACCEPTED invoice with less locked than its value."""

    def lookup(self, cancel_side_effect=None):
        from api.lightning.lnd import LNDNode

        htlc = MagicMock(amt_msat=500_000, expiry_height=100)
        response = MagicMock(state=3, htlcs=[htlc])  # ACCEPTED
        stub = MagicMock()
        stub.LookupInvoiceV2.return_value = response
        lnpayment = MagicMock(
            payment_hash=hashlib.sha256(b"x").hexdigest(),
            num_satoshis=1000,  # 1,000,000 msat expected
            status=LNPayment.Status.INVGEN,
        )
        with patch(
            "api.lightning.lnd.invoices_pb2_grpc.InvoicesStub", return_value=stub
        ), patch.object(
            LNDNode, "cancel_return_hold_invoice", side_effect=cancel_side_effect
        ) as cancel:
            status, _ = LNDNode.lookup_invoice_status(lnpayment)
        return status, cancel

    def test_underpaid_is_cancelled(self):
        status, cancel = self.lookup()
        self.assertEqual(status, LNPayment.Status.CANCEL)
        cancel.assert_called_once()

    def test_underpaid_not_locked_even_if_cancel_fails(self):
        status, cancel = self.lookup(cancel_side_effect=RuntimeError("LND down"))
        self.assertEqual(status, LNPayment.Status.CANCEL)
        cancel.assert_called_once()


class OrderLockTest(TestCase):
    def test_works_on_postgresql(self):
        from api.logics import order_lock

        with order_lock(123456):
            pass

    def test_refuses_other_databases(self):
        from api import logics

        with patch.object(logics.connection, "vendor", "sqlite"):
            with self.assertRaises(ImproperlyConfigured):
                with logics.order_lock(123456):
                    pass
