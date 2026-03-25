"""PayoutExecutor 유닛 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from creditcoin_payout.payout_executor import PayoutExecutor, PayoutFatalError
from creditcoin_payout.validator_checker import ValidatorStatus


@pytest.fixture
def mock_setup():
    """Mock ChainClient, Keypair, SubstrateInterface를 생성한다."""
    client = MagicMock()
    substrate = MagicMock()
    client.connect.return_value = substrate
    keypair = MagicMock()
    return client, substrate, keypair


class TestPayoutSingleEra:
    """payout_single_era 테스트."""

    def test_successful_payout(self, mock_setup):
        client, substrate, keypair = mock_setup

        receipt = MagicMock()
        receipt.is_success = True
        receipt.extrinsic_hash = "0xabc123"
        substrate.submit_extrinsic.return_value = receipt

        executor = PayoutExecutor(client, keypair, retry_count=1, retry_delay=0, tx_interval=0)
        result = executor.payout_single_era("5Gtest...", era=1521, page=0)

        assert result["status"] == "success"
        assert result["tx_hash"] == "0xabc123"

        # compose_call이 payout_stakers로 호출되었는지 확인
        substrate.compose_call.assert_called_once_with(
            call_module="Staking",
            call_function="payout_stakers",
            call_params={"validator_stash": "5Gtest...", "era": 1521},
        )

    def test_payout_by_page(self, mock_setup):
        client, substrate, keypair = mock_setup

        receipt = MagicMock()
        receipt.is_success = True
        receipt.extrinsic_hash = "0xdef456"
        substrate.submit_extrinsic.return_value = receipt

        executor = PayoutExecutor(client, keypair, retry_count=1, retry_delay=0, tx_interval=0)
        result = executor.payout_single_era("5Gtest...", era=1521, page=1, use_paged=True)

        assert result["status"] == "success"

        # compose_call이 payout_stakers_by_page로 호출
        substrate.compose_call.assert_called_once_with(
            call_module="Staking",
            call_function="payout_stakers_by_page",
            call_params={"validator_stash": "5Gtest...", "era": 1521, "page": 1},
        )

    def test_already_claimed_skipped(self, mock_setup):
        client, substrate, keypair = mock_setup

        receipt = MagicMock()
        receipt.is_success = False
        receipt.error_message = {"type": "Module", "name": "AlreadyClaimed"}
        substrate.submit_extrinsic.return_value = receipt

        executor = PayoutExecutor(client, keypair, retry_count=1, retry_delay=0, tx_interval=0)
        result = executor.payout_single_era("5Gtest...", era=1521, page=0)

        assert result["status"] == "skipped"
        assert result["error"] == "AlreadyClaimed"

    def test_insufficient_funds_raises_fatal(self, mock_setup):
        client, substrate, keypair = mock_setup

        receipt = MagicMock()
        receipt.is_success = False
        receipt.error_message = {"type": "Module", "name": "InsufficientFunds"}
        substrate.submit_extrinsic.return_value = receipt

        executor = PayoutExecutor(client, keypair, retry_count=1, retry_delay=0, tx_interval=0)

        with pytest.raises(PayoutFatalError):
            executor.payout_single_era("5Gtest...", era=1521, page=0)


class TestPayoutWithRetry:
    """payout_with_retry 테스트."""

    def test_succeeds_on_first_try(self, mock_setup):
        client, substrate, keypair = mock_setup
        executor = PayoutExecutor(client, keypair, retry_count=3, retry_delay=0, tx_interval=0)

        with patch.object(executor, "payout_single_era") as mock_payout:
            mock_payout.return_value = {"status": "success", "tx_hash": "0x123", "error": None}
            result = executor.payout_with_retry("5Gtest...", 1521)

        assert result["status"] == "success"
        assert mock_payout.call_count == 1

    def test_retries_on_failure_then_succeeds(self, mock_setup):
        client, substrate, keypair = mock_setup
        executor = PayoutExecutor(client, keypair, retry_count=3, retry_delay=0, tx_interval=0)

        with patch.object(executor, "payout_single_era") as mock_payout:
            mock_payout.side_effect = [
                {"status": "failed", "tx_hash": None, "error": "Timeout"},
                {"status": "success", "tx_hash": "0x456", "error": None},
            ]
            result = executor.payout_with_retry("5Gtest...", 1521)

        assert result["status"] == "success"
        assert mock_payout.call_count == 2

    def test_returns_failed_after_max_retries(self, mock_setup):
        client, substrate, keypair = mock_setup
        executor = PayoutExecutor(client, keypair, retry_count=2, retry_delay=0, tx_interval=0)

        with patch.object(executor, "payout_single_era") as mock_payout:
            mock_payout.return_value = {"status": "failed", "tx_hash": None, "error": "Timeout"}
            result = executor.payout_with_retry("5Gtest...", 1521)

        assert result["status"] == "failed"
        assert mock_payout.call_count == 2

    def test_no_retry_on_already_claimed(self, mock_setup):
        client, substrate, keypair = mock_setup
        executor = PayoutExecutor(client, keypair, retry_count=3, retry_delay=0, tx_interval=0)

        with patch.object(executor, "payout_single_era") as mock_payout:
            mock_payout.return_value = {"status": "skipped", "tx_hash": None, "error": "AlreadyClaimed"}
            result = executor.payout_with_retry("5Gtest...", 1521)

        assert result["status"] == "skipped"
        assert mock_payout.call_count == 1

    def test_shutdown_cancels_retry(self, mock_setup):
        client, substrate, keypair = mock_setup
        executor = PayoutExecutor(client, keypair, retry_count=3, retry_delay=0, tx_interval=0)
        executor.request_shutdown()

        result = executor.payout_with_retry("5Gtest...", 1521)
        assert result["status"] == "failed"
        assert result["error"] == "shutdown_requested"


class TestExecuteAll:
    """execute_all 통합 테스트."""

    def test_processes_active_and_waiting(self, mock_setup):
        client, substrate, keypair = mock_setup
        executor = PayoutExecutor(client, keypair, retry_count=1, retry_delay=0, tx_interval=0)

        statuses = [
            ValidatorStatus(
                stash="5Gactive...",
                name="Validator-1",
                is_active=True,
                unclaimed_eras=[1521, 1522],
                page_count=1,
            ),
            ValidatorStatus(
                stash="5Gwaiting...",
                name="Validator-2",
                is_active=False,
                unclaimed_eras=[],
                page_count=1,
            ),
        ]

        with patch.object(executor, "payout_all_pages") as mock_pages:
            mock_pages.return_value = [
                {"status": "success", "tx_hash": "0x123", "error": None, "page": 0}
            ]
            summary = executor.execute_all(statuses)

        assert summary["success"] == 2  # 2 Eras × 1 page each
        assert summary["skipped"] == 1  # Validator-2 waiting
        assert summary["failed"] == 0
        assert len(summary["details"]) == 3  # 2 success + 1 skipped

    def test_stops_on_fatal_error(self, mock_setup):
        client, substrate, keypair = mock_setup
        executor = PayoutExecutor(client, keypair, retry_count=1, retry_delay=0, tx_interval=0)

        statuses = [
            ValidatorStatus(
                stash="5Gactive...",
                name="Validator-1",
                is_active=True,
                unclaimed_eras=[1521, 1522],
                page_count=1,
            ),
        ]

        with patch.object(executor, "payout_all_pages") as mock_pages:
            mock_pages.side_effect = PayoutFatalError("InsufficientFunds")
            summary = executor.execute_all(statuses)

        assert summary["failed"] == 1
        assert summary["details"][0]["status"] == "fatal"
