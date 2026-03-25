"""Payout 트랜잭션 실행 모듈.

payoutStakers / payoutStakersByPage 트랜잭션을 서명하고 제출한다.
에러 유형별 분류 처리 및 재시도 로직을 포함한다.
"""

from __future__ import annotations

import time

import structlog
from substrateinterface import Keypair

from creditcoin_payout.chain_client import ChainClient
from creditcoin_payout.validator_checker import ValidatorStatus

logger = structlog.get_logger(__name__)

# 재시도 불가 에러 키워드
NON_RETRYABLE_ERRORS = [
    "AlreadyClaimed",
    "InvalidEraToReward",
    "InsufficientFunds",
    "InsufficientBond",
]

# 즉시 전체 중단이 필요한 에러
FATAL_ERRORS = [
    "InsufficientFunds",
    "InsufficientBond",
]


class PayoutFatalError(Exception):
    """Payout 즉시 중단이 필요한 에러."""


class PayoutExecutor:
    """Payout 트랜잭션 실행기."""

    def __init__(
        self,
        chain_client: ChainClient,
        keypair: Keypair,
        retry_count: int = 3,
        retry_delay: int = 10,
        tx_interval: int = 6,
    ):
        self.chain_client = chain_client
        self.keypair = keypair
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.tx_interval = tx_interval
        self._shutdown_requested = False

    def request_shutdown(self) -> None:
        """Graceful shutdown 요청."""
        self._shutdown_requested = True

    def payout_single_era(
        self, validator_stash: str, era: int, page: int = 0, use_paged: bool = False
    ) -> dict:
        """단일 Era/Page에 대한 payout 트랜잭션을 실행한다.

        Returns:
            {"status": "success"|"skipped"|"failed", "tx_hash": str|None, "error": str|None}
        """
        substrate = self.chain_client.connect()

        # 트랜잭션 구성
        if use_paged:
            call = substrate.compose_call(
                call_module="Staking",
                call_function="payout_stakers_by_page",
                call_params={
                    "validator_stash": validator_stash,
                    "era": era,
                    "page": page,
                },
            )
        else:
            call = substrate.compose_call(
                call_module="Staking",
                call_function="payout_stakers",
                call_params={
                    "validator_stash": validator_stash,
                    "era": era,
                },
            )

        # 서명
        extrinsic = substrate.create_signed_extrinsic(
            call=call,
            keypair=self.keypair,
        )

        # 제출 (inclusion 대기)
        try:
            receipt = substrate.submit_extrinsic(
                extrinsic, wait_for_inclusion=True
            )

            if receipt.is_success:
                tx_hash = receipt.extrinsic_hash
                logger.info(
                    "payout_success",
                    validator=validator_stash[:12],
                    era=era,
                    page=page,
                    tx_hash=tx_hash,
                )
                return {"status": "success", "tx_hash": tx_hash, "error": None}
            else:
                error_msg = str(receipt.error_message) if receipt.error_message else "unknown"
                return self._handle_tx_error(error_msg, validator_stash, era, page)

        except Exception as e:
            error_msg = str(e)
            return self._handle_tx_error(error_msg, validator_stash, era, page)

    def _handle_tx_error(
        self, error_msg: str, validator_stash: str, era: int, page: int
    ) -> dict:
        """트랜잭션 에러를 분류하고 적절한 결과를 반환한다."""
        # AlreadyClaimed → 건너뛰기
        if "AlreadyClaimed" in error_msg:
            logger.warning(
                "payout_skipped",
                validator=validator_stash[:12],
                era=era,
                page=page,
                reason="AlreadyClaimed",
            )
            return {"status": "skipped", "tx_hash": None, "error": "AlreadyClaimed"}

        # InvalidEraToReward → 건너뛰기
        if "InvalidEraToReward" in error_msg:
            logger.warning(
                "payout_skipped",
                validator=validator_stash[:12],
                era=era,
                page=page,
                reason="InvalidEraToReward",
            )
            return {"status": "skipped", "tx_hash": None, "error": "InvalidEraToReward"}

        # InsufficientFunds → 즉시 전체 중단
        for fatal_keyword in FATAL_ERRORS:
            if fatal_keyword in error_msg:
                logger.critical(
                    "payout_fatal_error",
                    validator=validator_stash[:12],
                    era=era,
                    page=page,
                    error=error_msg,
                )
                raise PayoutFatalError(f"치명적 에러로 전체 중단: {error_msg}")

        # 기타 에러 → 실패 반환 (상위에서 재시도 처리)
        logger.error(
            "payout_failed",
            validator=validator_stash[:12],
            era=era,
            page=page,
            error=error_msg,
        )
        return {"status": "failed", "tx_hash": None, "error": error_msg}

    def payout_with_retry(
        self, validator_stash: str, era: int, page: int = 0, use_paged: bool = False
    ) -> dict:
        """재시도 로직을 포함한 payout 실행."""
        last_result = None

        for attempt in range(1, self.retry_count + 1):
            if self._shutdown_requested:
                logger.warning("shutdown_requested", action="payout_cancelled")
                return {"status": "failed", "tx_hash": None, "error": "shutdown_requested"}

            try:
                result = self.payout_single_era(validator_stash, era, page, use_paged)

                if result["status"] in ("success", "skipped"):
                    return result

                last_result = result

                # 재시도 불가 에러인지 확인
                error_msg = result.get("error", "")
                if any(keyword in error_msg for keyword in NON_RETRYABLE_ERRORS):
                    return result

            except PayoutFatalError:
                raise
            except Exception as e:
                last_result = {"status": "failed", "tx_hash": None, "error": str(e)}

            # 재시도 대기
            if attempt < self.retry_count:
                delay = self.retry_delay * attempt  # exponential backoff
                logger.warning(
                    "payout_retry",
                    validator=validator_stash[:12],
                    era=era,
                    page=page,
                    attempt=attempt,
                    max_attempts=self.retry_count,
                    delay_sec=delay,
                )
                time.sleep(delay)

        return last_result or {"status": "failed", "tx_hash": None, "error": "max_retries_exceeded"}

    def payout_all_pages(
        self, validator_stash: str, era: int, page_count: int
    ) -> list[dict]:
        """Era의 모든 페이지에 대해 payout을 실행한다."""
        results = []
        use_paged = page_count > 1

        for page in range(page_count):
            if self._shutdown_requested:
                break

            result = self.payout_with_retry(
                validator_stash, era, page, use_paged=use_paged
            )
            result["page"] = page
            results.append(result)

            # 성공한 TX 후 interval 대기
            if result["status"] == "success" and page < page_count - 1:
                time.sleep(self.tx_interval)

        return results

    def execute_all(self, statuses: list[ValidatorStatus]) -> dict:
        """모든 Validator의 미수령 Era에 대해 payout을 실행한다.

        Returns:
            {"success": int, "failed": int, "skipped": int, "details": [...]}
        """
        summary = {"success": 0, "failed": 0, "skipped": 0, "details": []}

        for status in statuses:
            if self._shutdown_requested:
                break

            if not status.is_active:
                summary["skipped"] += 1
                summary["details"].append({
                    "validator": status.name,
                    "era": None,
                    "page": None,
                    "status": "skipped",
                    "tx_hash": None,
                    "error": "Waiting 상태",
                })
                continue

            if not status.unclaimed_eras:
                logger.info(
                    "no_unclaimed_eras",
                    validator=status.name,
                )
                continue

            for era in status.unclaimed_eras:
                if self._shutdown_requested:
                    break

                page_count = status.page_count

                logger.info(
                    "payout_attempt",
                    validator=status.name,
                    era=era,
                    page_count=page_count,
                )

                try:
                    page_results = self.payout_all_pages(
                        status.stash, era, page_count
                    )

                    for pr in page_results:
                        detail = {
                            "validator": status.name,
                            "era": era,
                            "page": pr.get("page", 0),
                            "status": pr["status"],
                            "tx_hash": pr.get("tx_hash"),
                            "error": pr.get("error"),
                        }
                        summary["details"].append(detail)

                        if pr["status"] == "success":
                            summary["success"] += 1
                        elif pr["status"] == "skipped":
                            summary["skipped"] += 1
                        else:
                            summary["failed"] += 1

                except PayoutFatalError as e:
                    summary["details"].append({
                        "validator": status.name,
                        "era": era,
                        "page": 0,
                        "status": "fatal",
                        "tx_hash": None,
                        "error": str(e),
                    })
                    summary["failed"] += 1
                    logger.critical("payout_fatal_abort", error=str(e))
                    return summary

                # Era 간 대기
                if self.tx_interval > 0:
                    time.sleep(self.tx_interval)

        return summary
