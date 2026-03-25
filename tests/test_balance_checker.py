"""BalanceChecker 유닛 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from creditcoin_payout.balance_checker import (
    BalanceChecker,
    CTC_UNIT,
    InsufficientBalanceError,
)


@pytest.fixture
def mock_chain_client():
    """Mock ChainClient를 생성한다."""
    client = MagicMock()
    substrate = MagicMock()
    client.connect.return_value = substrate
    return client, substrate


class TestGetFreeBalance:
    """get_free_balance 테스트."""

    def test_returns_balance_in_ctc(self, mock_chain_client):
        client, substrate = mock_chain_client

        result_mock = MagicMock()
        result_mock.value = {
            "data": {
                "free": 5 * CTC_UNIT,  # 5 CTC
                "reserved": 0,
                "misc_frozen": 0,
                "fee_frozen": 0,
            },
            "nonce": 42,
        }
        substrate.query.return_value = result_mock

        checker = BalanceChecker(client, min_balance=1.0)
        balance = checker.get_free_balance("5Htest...")

        assert balance == 5.0
        substrate.query.assert_called_once_with("System", "Account", params=["5Htest..."])

    def test_returns_zero_when_none(self, mock_chain_client):
        client, substrate = mock_chain_client
        substrate.query.return_value = None

        checker = BalanceChecker(client, min_balance=1.0)
        balance = checker.get_free_balance("5Htest...")

        assert balance == 0.0

    def test_returns_fractional_balance(self, mock_chain_client):
        client, substrate = mock_chain_client

        result_mock = MagicMock()
        # 5.23 CTC
        result_mock.value = {
            "data": {"free": int(5.23 * CTC_UNIT)},
        }
        substrate.query.return_value = result_mock

        checker = BalanceChecker(client, min_balance=1.0)
        balance = checker.get_free_balance("5Htest...")

        assert abs(balance - 5.23) < 0.001


class TestCheckSufficient:
    """check_sufficient 테스트."""

    def test_sufficient_balance_returns_true(self, mock_chain_client):
        client, substrate = mock_chain_client

        result_mock = MagicMock()
        result_mock.value = {"data": {"free": 5 * CTC_UNIT}}
        substrate.query.return_value = result_mock

        checker = BalanceChecker(client, min_balance=1.0)
        assert checker.check_sufficient("5Htest...", expected_tx_count=10) is True

    def test_insufficient_balance_raises_error(self, mock_chain_client):
        client, substrate = mock_chain_client

        result_mock = MagicMock()
        result_mock.value = {"data": {"free": int(0.5 * CTC_UNIT)}}  # 0.5 CTC
        substrate.query.return_value = result_mock

        checker = BalanceChecker(client, min_balance=1.0)

        with pytest.raises(InsufficientBalanceError) as exc_info:
            checker.check_sufficient("5Htest...", expected_tx_count=5)

        assert "잔액 부족" in str(exc_info.value)

    def test_exact_minimum_balance_passes(self, mock_chain_client):
        client, substrate = mock_chain_client

        result_mock = MagicMock()
        result_mock.value = {"data": {"free": 1 * CTC_UNIT}}  # 정확히 1 CTC
        substrate.query.return_value = result_mock

        checker = BalanceChecker(client, min_balance=1.0)
        assert checker.check_sufficient("5Htest...") is True

    def test_zero_balance_raises_error(self, mock_chain_client):
        client, substrate = mock_chain_client
        substrate.query.return_value = None  # 계정 없음

        checker = BalanceChecker(client, min_balance=1.0)

        with pytest.raises(InsufficientBalanceError):
            checker.check_sufficient("5Htest...")
