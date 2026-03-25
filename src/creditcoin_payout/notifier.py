"""실행 결과 알림 모듈 (로그 기반 초기 구현).

초기 구현에서는 structlog를 활용한 로그 기록으로 대체한다.
추후 Telegram, Slack, Email 등으로 확장 가능.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class Notifier:
    """Payout 실행 결과 알림."""

    def notify_success(self, summary: dict) -> None:
        """Payout 성공 결과를 알린다."""
        logger.info(
            "payout_complete",
            success=summary["success"],
            failed=summary["failed"],
            skipped=summary["skipped"],
        )

    def notify_error(self, error: str) -> None:
        """에러 발생을 알린다."""
        logger.error("payout_error_notification", error=error)

    def notify_balance_insufficient(self, balance: float, min_required: float) -> None:
        """잔액 부족을 알린다."""
        logger.error(
            "balance_insufficient_notification",
            balance_ctc=round(balance, 4),
            min_required=min_required,
        )
