"""Controller 잔액 사전 검증 모듈.

Payout 실행 전 Controller 계정의 잔액이 트랜잭션 수수료를
감당할 수 있는지 확인한다.
"""

from __future__ import annotations

import structlog

from creditcoin_payout.chain_client import ChainClient

logger = structlog.get_logger(__name__)

# Creditcoin은 18자리 decimals
CTC_DECIMALS = 18
CTC_UNIT = 10**CTC_DECIMALS


class InsufficientBalanceError(Exception):
    """잔액 부족 시 발생하는 예외."""


class BalanceChecker:
    """Controller 계정 잔액 검증."""

    def __init__(self, chain_client: ChainClient, min_balance: float):
        self.chain_client = chain_client
        self.min_balance = min_balance  # CTC 단위

    def get_free_balance(self, address: str) -> float:
        """주소의 free balance를 CTC 단위로 반환한다."""
        substrate = self.chain_client.connect()
        result = substrate.query("System", "Account", params=[address])

        # AccountInfo 구조에서 free balance 추출
        if result is None:
            return 0.0

        account_data = result.value
        if isinstance(account_data, dict) and "data" in account_data:
            free = account_data["data"].get("free", 0)
        else:
            free = 0

        return free / CTC_UNIT

    def check_sufficient(self, address: str, expected_tx_count: int = 0) -> bool:
        """잔액이 최소 요구량 이상인지 확인한다.

        Args:
            address: Controller 주소
            expected_tx_count: 예상 트랜잭션 수 (로깅용)

        Returns:
            True if 잔액 충분

        Raises:
            InsufficientBalanceError: 잔액 부족 시
        """
        balance = self.get_free_balance(address)

        logger.info(
            "balance_check",
            balance_ctc=round(balance, 4),
            min_required=self.min_balance,
            expected_tx_count=expected_tx_count,
        )

        if balance < self.min_balance:
            msg = (
                f"Controller 잔액 부족: {balance:.4f} CTC < "
                f"최소 {self.min_balance} CTC (예상 TX: {expected_tx_count}건)"
            )
            logger.error(
                "balance_insufficient",
                balance_ctc=round(balance, 4),
                min_required=self.min_balance,
                expected_tx_count=expected_tx_count,
            )
            raise InsufficientBalanceError(msg)

        return True
