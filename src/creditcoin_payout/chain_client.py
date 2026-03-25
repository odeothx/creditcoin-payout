"""Substrate RPC 연결 관리 모듈.

WebSocket 연결 생성, 재연결 처리, fallback 엔드포인트 지원.
"""

from __future__ import annotations

import structlog
from substrateinterface import SubstrateInterface

logger = structlog.get_logger(__name__)


class ChainClient:
    """Substrate 체인 RPC 클라이언트.

    로컬 RPC 연결 실패 시 공식 RPC 엔드포인트로 자동 fallback.
    """

    def __init__(self, endpoint: str, fallback_endpoint: str | None = None, timeout: int = 30):
        self.endpoint = endpoint
        self.fallback_endpoint = fallback_endpoint
        self.timeout = timeout
        self._substrate: SubstrateInterface | None = None
        self._connected_endpoint: str | None = None

    def connect(self) -> SubstrateInterface:
        """RPC 연결을 반환한다. 끊겼으면 자동 재연결."""
        if self._substrate is not None:
            try:
                # 연결 상태 확인 (간단한 쿼리)
                self._substrate.get_chain_head()
                return self._substrate
            except Exception:
                logger.warning("rpc_connection_lost", endpoint=self._connected_endpoint)
                self._substrate = None

        # 1차 시도: primary endpoint
        try:
            logger.info("rpc_connecting", endpoint=self.endpoint)
            self._substrate = SubstrateInterface(
                url=self.endpoint,
                auto_reconnect=True,
            )
            self._connected_endpoint = self.endpoint
            logger.info(
                "rpc_connected",
                endpoint=self.endpoint,
                chain=self._substrate.chain,
                chain_version=self._substrate.version,
            )
            return self._substrate
        except Exception as e:
            logger.warning(
                "rpc_primary_failed",
                endpoint=self.endpoint,
                error=str(e),
            )

        # 2차 시도: fallback endpoint
        if self.fallback_endpoint:
            try:
                logger.info("rpc_fallback_connecting", endpoint=self.fallback_endpoint)
                self._substrate = SubstrateInterface(
                    url=self.fallback_endpoint,
                    auto_reconnect=True,
                )
                self._connected_endpoint = self.fallback_endpoint
                logger.info(
                    "rpc_connected",
                    endpoint=self.fallback_endpoint,
                    chain=self._substrate.chain,
                    chain_version=self._substrate.version,
                )
                return self._substrate
            except Exception as e:
                logger.error(
                    "rpc_fallback_failed",
                    endpoint=self.fallback_endpoint,
                    error=str(e),
                )

        raise ConnectionError(
            f"RPC 연결 실패: primary={self.endpoint}, fallback={self.fallback_endpoint}"
        )

    def disconnect(self) -> None:
        """WebSocket 연결을 종료한다."""
        if self._substrate is not None:
            try:
                self._substrate.close()
            except Exception:
                pass
            self._substrate = None
            logger.info("rpc_disconnected", endpoint=self._connected_endpoint)
            self._connected_endpoint = None

    def get_metadata_info(self) -> dict:
        """체인 메타데이터 정보를 반환한다 (디버깅용)."""
        substrate = self.connect()
        staking_storage = []
        try:
            for fn in substrate.get_metadata_storage_functions("Staking"):
                staking_storage.append(fn)
        except Exception:
            pass

        staking_calls = []
        try:
            calls = substrate.get_metadata_call_functions("Staking")
            staking_calls = [c for c in calls if "payout" in str(c).lower()]
        except Exception:
            pass

        return {
            "ss58_format": substrate.ss58_format,
            "chain": substrate.chain,
            "version": substrate.version,
            "staking_storage_functions": staking_storage,
            "payout_calls": staking_calls,
        }
