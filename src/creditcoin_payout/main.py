"""Creditcoin Payout 프로그램 진입점.

1회 실행 후 종료하는 one-shot 방식.
cron에 의해 매일 11:07에 호출된다.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog
import yaml
from dotenv import load_dotenv

from creditcoin_payout import __version__
from creditcoin_payout.balance_checker import BalanceChecker, InsufficientBalanceError
from creditcoin_payout.chain_client import ChainClient
from creditcoin_payout.key_manager import KeyLoadError, KeyManager
from creditcoin_payout.notifier import Notifier
from creditcoin_payout.payout_executor import PayoutExecutor, PayoutFatalError
from creditcoin_payout.validator_checker import ValidatorChecker

logger = structlog.get_logger(__name__)

# 현재 스크립트 위치 기준으로 프로젝트 루트 계산 (src/creditcoin_payout/main.py -> 루트)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Graceful shutdown 플래그
_shutdown_requested = False
_payout_executor: PayoutExecutor | None = None


def load_config(config_path: str = "config/config.yaml") -> dict:
    """YAML 설정 파일을 로드한다."""
    path = Path(config_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if not path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {path}")

    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def setup_logging(cfg: dict) -> None:
    """structlog 및 Python 표준 로깅을 초기화한다."""
    log_level = getattr(logging, cfg.get("level", "INFO").upper(), logging.INFO)
    log_file_str = cfg.get("file", "logs/payout.log")
    
    log_file = Path(log_file_str)
    if not log_file.is_absolute():
        log_file = PROJECT_ROOT / log_file
        
    max_bytes = cfg.get("max_bytes", 10485760)
    backup_count = cfg.get("backup_count", 7)
    log_format = cfg.get("format", "text")

    # 로그 디렉토리 생성
    log_dir = log_file.parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # structlog 프로세서 설정
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        # Terminal 및 로그 파일 가독성을 위해 ConsoleRenderer 사용
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    # 핸들러 설정 (파일 및 표준 출력)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    file_handler = RotatingFileHandler(
        str(log_file), maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handlers.append(file_handler)

    for handler in handlers:
        handler.setFormatter(formatter)
        handler.setLevel(log_level)

    logging.root.handlers = handlers
    logging.root.setLevel(log_level)


def update_heartbeat(heartbeat_path: str, status: str = "completed") -> None:
    """실행 완료 시각을 heartbeat 파일에 기록한다."""
    path = Path(heartbeat_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
        
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "last_run": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "version": __version__,
    }))


def graceful_shutdown(signum, frame) -> None:
    """SIGTERM/SIGINT 핸들러."""
    global _shutdown_requested
    _shutdown_requested = True

    sig_name = signal.Signals(signum).name
    logger.warning("graceful_shutdown", signal=sig_name)

    if _payout_executor:
        _payout_executor.request_shutdown()


def run_payout(config: dict) -> None:
    """Payout 실행 로직."""
    global _payout_executor

    start_time = time.time()
    notifier = Notifier()

    # 1. RPC 연결
    rpc_cfg = config["rpc"]
    chain_client = ChainClient(
        endpoint=rpc_cfg["endpoint"],
        fallback_endpoint=rpc_cfg.get("fallback_endpoint"),
        timeout=rpc_cfg.get("timeout", 30),
    )

    try:
        chain_client.connect()
    except ConnectionError as e:
        notifier.notify_error(str(e))
        raise

    try:
        # 2. Controller 키 로드
        keypair = KeyManager.load_from_env()

        # 3. Validator 상태 확인
        validator_checker = ValidatorChecker(chain_client)
        payout_cfg = config["payout"]
        statuses = validator_checker.check_all(
            config["validators"],
            depth=payout_cfg.get("depth_eras", 84),
        )

        # 총 예상 TX 수 계산
        total_tx = sum(
            len(s.unclaimed_eras) * s.page_count
            for s in statuses
            if s.is_active and s.unclaimed_eras
        )

        # 4. 잔액 확인
        balance_cfg = config["balance"]
        balance_checker = BalanceChecker(
            chain_client, min_balance=balance_cfg["min_balance_ctc"]
        )
        controller_address = config["controller"]["address"]

        try:
            balance_checker.check_sufficient(controller_address, expected_tx_count=total_tx)
        except InsufficientBalanceError as e:
            notifier.notify_error(str(e))
            raise

        # 5. Payout 실행
        _payout_executor = PayoutExecutor(
            chain_client=chain_client,
            keypair=keypair,
            retry_count=payout_cfg.get("retry_count", 3),
            retry_delay=payout_cfg.get("retry_delay_sec", 10),
            tx_interval=payout_cfg.get("tx_interval_sec", 6),
        )

        if _shutdown_requested:
            logger.warning("shutdown_before_payout")
            return

        summary = _payout_executor.execute_all(statuses)

        # 6. 결과 알림
        elapsed = round(time.time() - start_time, 2)
        logger.info(
            "payout_complete",
            success=summary["success"],
            failed=summary["failed"],
            skipped=summary["skipped"],
            elapsed_sec=elapsed,
        )
        notifier.notify_success(summary)

    except PayoutFatalError as e:
        notifier.notify_error(str(e))
        raise
    finally:
        chain_client.disconnect()


def main() -> None:
    """프로그램 진입점."""
    # SIGTERM / SIGINT 핸들러 등록
    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)

    # .env 로드
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(dotenv_path=env_path)

    # 설정 로드
    config = load_config()
    setup_logging(config["logging"])

    logger.info("payout_start", version=__version__)

    heartbeat_file = config["logging"].get("heartbeat_file", "logs/heartbeat")

    try:
        run_payout(config)
        update_heartbeat(heartbeat_file, status="completed")
    except KeyLoadError as e:
        logger.critical("key_load_error", error=str(e))
        update_heartbeat(heartbeat_file, status="key_error")
        sys.exit(1)
    except InsufficientBalanceError as e:
        logger.critical("balance_error", error=str(e))
        update_heartbeat(heartbeat_file, status="balance_error")
        sys.exit(1)
    except ConnectionError as e:
        logger.critical("connection_error", error=str(e))
        update_heartbeat(heartbeat_file, status="connection_error")
        sys.exit(1)
    except PayoutFatalError as e:
        logger.critical("payout_fatal", error=str(e))
        update_heartbeat(heartbeat_file, status="fatal_error")
        sys.exit(1)
    except Exception as e:
        logger.exception("payout_unexpected_error", error=str(e))
        update_heartbeat(heartbeat_file, status="unexpected_error")
        sys.exit(1)


if __name__ == "__main__":
    main()
