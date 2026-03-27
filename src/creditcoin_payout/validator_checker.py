"""Validator 상태 및 미수령 Era 조회 모듈.

Validator 활성 여부 확인, 미수령 Era 목록 반환, 페이지 수 확인.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from creditcoin_payout.chain_client import ChainClient

logger = structlog.get_logger(__name__)


@dataclass
class ValidatorStatus:
    """Validator 상태 정보."""

    stash: str
    name: str
    is_active: bool = False
    unclaimed_eras: list[int] = field(default_factory=list)
    page_count: int = 1


class ValidatorChecker:
    """Validator 상태 확인 및 미수령 Era 조회."""

    def __init__(self, chain_client: ChainClient):
        self.chain_client = chain_client

    def get_current_era(self) -> int:
        """현재 Era 번호를 반환한다."""
        substrate = self.chain_client.connect()
        result = substrate.query("Staking", "CurrentEra")
        era = result.value if result else 0
        logger.info("current_era", era=era)
        return era

    def is_validator_active(self, stash: str, era: int) -> bool:
        """Validator가 해당 Era에서 Active set에 있는지 확인한다."""
        substrate = self.chain_client.connect()

        # ErasStakersOverview 시도 (Paged Exposure)
        try:
            overview = substrate.query(
                "Staking", "ErasStakersOverview", params=[era, stash]
            )
            if overview and overview.value:
                total = overview.value.get("total", 0)
                return total > 0
        except Exception:
            pass

        # Fallback: ErasStakers
        try:
            stakers = substrate.query(
                "Staking", "ErasStakers", params=[era, stash]
            )
            if stakers and stakers.value:
                total = stakers.value.get("total", 0)
                return total > 0
        except Exception:
            pass

        return False

    def get_unclaimed_eras(self, stash: str, current_era: int, depth: int) -> list[int]:
        """미수령 Era 목록을 반환한다.

        현재 Era에서 depth만큼 과거까지 조회하여,
        보상 포인트가 있으나 ClaimedRewards에 없는 Era를 반환한다.
        """
        substrate = self.chain_client.connect()
        unclaimed = []

        start_era = max(0, current_era - depth)

        for era in range(start_era, current_era):
            # 1. 해당 Era에서 보상 포인트가 있는지 확인
            if not self._has_reward_points(substrate, era, stash):
                continue

            # 2. 이미 수령했는지 확인
            if self._is_claimed(substrate, era, stash):
                continue

            unclaimed.append(era)

        return unclaimed

    def _has_reward_points(self, substrate, era: int, stash: str) -> bool:
        """해당 Era에서 Validator가 보상 포인트를 받았는지 확인."""
        try:
            result = substrate.query(
                "Staking", "ErasRewardPoints", params=[era]
            )
            if result and result.value:
                individual = result.value.get("individual", [])
                # individual은 [(account, points), ...] 형태
                if isinstance(individual, list):
                    for item in individual:
                        if isinstance(item, (list, tuple)) and len(item) >= 2:
                            if item[0] == stash and item[1] > 0:
                                return True
                elif isinstance(individual, dict):
                    points = individual.get(stash, 0)
                    return points > 0
        except Exception as e:
            logger.debug("reward_points_query_error", era=era, stash=stash[:12], error=str(e))

        return False

    def _is_claimed(self, substrate, era: int, stash: str) -> bool:
        """해당 Era의 보상이 이미 수령되었는지 확인."""
        # 방법 1: ClaimedRewards storage (standalone)
        try:
            result = substrate.query(
                "Staking", "ClaimedRewards", params=[era, stash]
            )
            if result and result.value:
                # ClaimedRewards가 존재하면 해당 page가 수령됨
                return True
        except Exception:
            pass

        # 방법 2: Ledger의 legacy_claimed_rewards 필드
        try:
            result = substrate.query(
                "Staking", "Ledger", params=[stash]
            )
            if result and result.value:
                legacy = result.value.get("legacy_claimed_rewards", [])
                if not legacy:
                    legacy = result.value.get("claimed_rewards", [])
                if era in legacy:
                    return True
        except Exception:
            pass

        return False

    def get_page_count(self, stash: str, era: int) -> int:
        """Era별 페이지 수를 반환한다 (Paged Exposure)."""
        substrate = self.chain_client.connect()

        try:
            overview = substrate.query(
                "Staking", "ErasStakersOverview", params=[era, stash]
            )
            if overview and overview.value:
                page_count = overview.value.get("page_count", 1)
                return max(1, page_count)
        except Exception:
            pass

        return 1  # Paged Exposure 미지원 시 기본 1페이지

    def check_all(self, validators: list[dict], depth: int) -> list[ValidatorStatus]:
        """모든 Validator의 상태를 확인하고 결과를 반환한다."""
        current_era = self.get_current_era()
        results = []

        for v in validators:
            stash = v["stash"]
            name = v["name"]

            is_active = self.is_validator_active(stash, current_era)
            unclaimed = self.get_unclaimed_eras(stash, current_era, depth)

            if not is_active and not unclaimed:
                logger.warning(
                    "validator_status",
                    validator=name,
                    active=False,
                    message="Waiting 상태이며 미수령 보상 없음 - 건너뜀",
                )
                results.append(ValidatorStatus(
                    stash=stash, name=name, is_active=False,
                ))
                continue

            # 미수령 Era가 있으면 각 Era의 page_count도 확인
            page_count = 1
            if unclaimed:
                # 첫 번째 미수령 Era의 page_count를 대표값으로 사용
                page_count = self.get_page_count(stash, unclaimed[0])

            logger.info(
                "validator_status",
                validator=name,
                active=is_active,
                unclaimed_eras=unclaimed,
                page_count=page_count,
                message="Waiting 상태이나 미수령 보상 존재" if not is_active else None,
            )

            results.append(ValidatorStatus(
                stash=stash,
                name=name,
                is_active=is_active,
                unclaimed_eras=unclaimed,
                page_count=page_count,
            ))

        return results
