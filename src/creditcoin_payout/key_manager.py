"""Controller 키 보안 로딩 모듈.

환경변수에서 니모닉을 로드하여 Keypair를 생성하고,
선택적으로 주소 일치 여부를 검증한다.
"""

from __future__ import annotations

import os

import structlog
from substrateinterface import Keypair

logger = structlog.get_logger(__name__)


class KeyLoadError(Exception):
    """키 로딩 실패 시 발생하는 예외."""


class KeyManager:
    """Controller 계정 키페어 관리."""

    @staticmethod
    def load_from_env() -> Keypair:
        """환경변수에서 Controller 키페어를 로드한다.

        환경변수:
            CONTROLLER_MNEMONIC: 니모닉 (12 또는 24 단어, 필수)
            CONTROLLER_ADDRESS: 주소 검증용 (선택)

        Returns:
            Keypair: Controller 키페어

        Raises:
            KeyLoadError: 니모닉이 없거나 주소 불일치 시
        """
        mnemonic = os.environ.get("CONTROLLER_MNEMONIC")
        if not mnemonic:
            raise KeyLoadError("CONTROLLER_MNEMONIC 환경변수가 설정되지 않았습니다")

        mnemonic = mnemonic.strip()
        if not mnemonic or mnemonic.startswith("word"):
            raise KeyLoadError(
                "CONTROLLER_MNEMONIC이 템플릿 값입니다. 실제 니모닉을 입력하세요"
            )

        try:
            keypair = Keypair.create_from_mnemonic(mnemonic)
        except Exception as e:
            raise KeyLoadError(f"니모닉으로 키페어 생성 실패: {e}") from e

        # 주소 앞 12자리만 로그 출력 (보안)
        address_prefix = keypair.ss58_address[:12]
        logger.info("key_loaded", address_prefix=f"{address_prefix}...")

        # 선택적 주소 검증
        expected_address = os.environ.get("CONTROLLER_ADDRESS")
        if expected_address:
            expected_address = expected_address.strip()
            if keypair.ss58_address != expected_address:
                raise KeyLoadError(
                    f"Controller 주소 불일치: "
                    f"생성={keypair.ss58_address[:12]}..., "
                    f"기대={expected_address[:12]}..."
                )
            logger.info("key_address_verified", address_prefix=f"{address_prefix}...")

        return keypair
