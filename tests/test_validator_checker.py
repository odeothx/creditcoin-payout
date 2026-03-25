"""ValidatorChecker 유닛 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from creditcoin_payout.validator_checker import ValidatorChecker, ValidatorStatus


@pytest.fixture
def mock_chain_client():
    """Mock ChainClient를 생성한다."""
    client = MagicMock()
    substrate = MagicMock()
    client.connect.return_value = substrate
    return client, substrate


class TestGetCurrentEra:
    """get_current_era 테스트."""

    def test_returns_current_era(self, mock_chain_client):
        client, substrate = mock_chain_client
        result_mock = MagicMock()
        result_mock.value = 1523
        substrate.query.return_value = result_mock

        checker = ValidatorChecker(client)
        era = checker.get_current_era()

        assert era == 1523
        substrate.query.assert_called_once_with("Staking", "CurrentEra")

    def test_returns_zero_when_none(self, mock_chain_client):
        client, substrate = mock_chain_client
        substrate.query.return_value = None

        checker = ValidatorChecker(client)
        era = checker.get_current_era()

        assert era == 0


class TestIsValidatorActive:
    """is_validator_active 테스트."""

    def test_active_via_overview(self, mock_chain_client):
        client, substrate = mock_chain_client
        result_mock = MagicMock()
        result_mock.value = {"total": 1000000, "own": 500000, "page_count": 1}
        substrate.query.return_value = result_mock

        checker = ValidatorChecker(client)
        assert checker.is_validator_active("5Gtest...", 1523) is True

    def test_inactive_via_overview(self, mock_chain_client):
        client, substrate = mock_chain_client
        result_mock = MagicMock()
        result_mock.value = {"total": 0}
        substrate.query.return_value = result_mock

        checker = ValidatorChecker(client)
        assert checker.is_validator_active("5Gtest...", 1523) is False

    def test_fallback_to_eras_stakers(self, mock_chain_client):
        """ErasStakersOverview 실패 시 ErasStakers로 fallback."""
        client, substrate = mock_chain_client

        # 첫 query (ErasStakersOverview) 실패, 두 번째 (ErasStakers) 성공
        era_stakers = MagicMock()
        era_stakers.value = {"total": 500000, "own": 250000, "others": []}
        substrate.query.side_effect = [
            Exception("Storage not found"),
            era_stakers,
        ]

        checker = ValidatorChecker(client)
        assert checker.is_validator_active("5Gtest...", 1523) is True


class TestGetUnclaimedEras:
    """get_unclaimed_eras 테스트."""

    def test_returns_unclaimed_eras(self, mock_chain_client):
        client, substrate = mock_chain_client
        checker = ValidatorChecker(client)

        stash = "5G9TuCM8NtpxXw7mYXvmsbRKdQmoYTs1GEJsSg5tNUuFTpdf"

        # _has_reward_points와 _is_claimed를 모킹
        with patch.object(checker, "_has_reward_points") as mock_reward, \
             patch.object(checker, "_is_claimed") as mock_claimed:
            # Era 1520: 보상 있음, 미수령
            # Era 1521: 보상 있음, 이미 수령
            # Era 1522: 보상 없음
            mock_reward.side_effect = lambda s, era, stash: era in (1520, 1521)
            mock_claimed.side_effect = lambda s, era, stash: era == 1521

            result = checker.get_unclaimed_eras(stash, current_era=1523, depth=5)

        assert result == [1520]

    def test_empty_when_all_claimed(self, mock_chain_client):
        client, substrate = mock_chain_client
        checker = ValidatorChecker(client)

        with patch.object(checker, "_has_reward_points") as mock_reward, \
             patch.object(checker, "_is_claimed") as mock_claimed:
            mock_reward.return_value = True
            mock_claimed.return_value = True

            result = checker.get_unclaimed_eras("5Gtest...", current_era=1523, depth=3)

        assert result == []


class TestGetPageCount:
    """get_page_count 테스트."""

    def test_returns_page_count(self, mock_chain_client):
        client, substrate = mock_chain_client
        result_mock = MagicMock()
        result_mock.value = {"page_count": 3, "total": 1000}
        substrate.query.return_value = result_mock

        checker = ValidatorChecker(client)
        assert checker.get_page_count("5Gtest...", 1523) == 3

    def test_returns_one_when_no_overview(self, mock_chain_client):
        client, substrate = mock_chain_client
        substrate.query.side_effect = Exception("Not found")

        checker = ValidatorChecker(client)
        assert checker.get_page_count("5Gtest...", 1523) == 1


class TestCheckAll:
    """check_all 통합 테스트."""

    def test_check_all_mixed_validators(self, mock_chain_client):
        client, substrate = mock_chain_client
        checker = ValidatorChecker(client)

        validators = [
            {"stash": "5Gactive...", "name": "Validator-1"},
            {"stash": "5Gwaiting...", "name": "Validator-2"},
        ]

        with patch.object(checker, "get_current_era", return_value=1523), \
             patch.object(checker, "is_validator_active") as mock_active, \
             patch.object(checker, "get_unclaimed_eras") as mock_unclaimed, \
             patch.object(checker, "get_page_count", return_value=1):

            mock_active.side_effect = lambda stash, era: stash == "5Gactive..."
            mock_unclaimed.return_value = [1521, 1522]

            results = checker.check_all(validators, depth=84)

        assert len(results) == 2

        # Validator-1: Active
        assert results[0].is_active is True
        assert results[0].unclaimed_eras == [1521, 1522]

        # Validator-2: Waiting
        assert results[1].is_active is False
        assert results[1].unclaimed_eras == []
