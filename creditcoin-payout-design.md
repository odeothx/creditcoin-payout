# Creditcoin Payout 자동화 프로그램 설계서

> **프로젝트명**: `creditcoin-payout`  
> **작성 목적**: antigravity 개발팀 전달용 설계 문서  
> **패키지 매니저**: [uv](https://docs.astral.sh/uv/)  
> **언어**: Python 3.12+

---

## 1. 개요

### 1.1 목적

Creditcoin 네트워크에서 운영 중인 5개의 Validator 노드에 대해 매일 오전 11:07에 자동으로 `payoutStakers` 트랜잭션을 실행한다.

### 1.2 운영 환경

| 항목 | 내용 |
|------|------|
| 실행 서버 | `js2` (Validator 노드 운영 서버) |
| RPC 엔드포인트 | `ws://localhost:9944` |
| 실행 시각 | 매일 **11:07** (서버 로컬 타임 기준) |
| 스케줄링 | cron |
| 실행 방식 | 1회 실행 후 종료 (one-shot) |

### 1.3 Validator 및 Controller 정보

**Validator Stash 주소 (5개)**

| 이름 | Stash 주소 |
|------|-----------| 
| Validator-1 | `5G9TuCM8NtpxXw7mYXvmsbRKdQmoYTs1GEJsSg5tNUuFTpdf` |
| Validator-2 | `5FRuv3BiBhY87DWPtQqn827Bow5a1VmQQGzUvkheJWXmFwMD` |
| Validator-3 | `5Fuj2qaV39sAZTDCPavjRGxGJxTHThCjCHg2vgymCSF1hZfY` |
| Validator-4 | `5FF5VyM2AAnkUApV6eH7ynsNug8Ng7o8r7vvL6BCBMD4bRdu` |
| Validator-5 | `5FL9Ew83tQNCUpJQFg24q4e57rUdYxWbmzjdQHE1XqQQ5vJv` |

**Controller 계정**

```
5H5wrwyNM4bsnt7ngPsiUCfFi34ho5gRMKjwJ2sHytpbWnRi
```

> Validator 5개 모두 동일한 Controller 계정으로 Payout을 수행한다.

---

## 2. 디렉토리 구조

```
creditcoin-payout/
├── pyproject.toml           # uv 프로젝트 설정 및 의존성
├── uv.lock                  # 의존성 잠금 파일 (git 커밋 포함)
├── .python-version          # Python 버전 고정 (uv 자동 생성)
├── .env.example             # 환경변수 템플릿 (git 커밋 포함)
├── .env                     # 실제 시크릿 (절대 git 커밋 금지)
├── .gitignore
├── config/
│   └── config.yaml          # 공개 설정값
├── deploy/
│   └── crontab.example      # cron 설정 예시
├── src/
│   └── creditcoin_payout/
│       ├── __init__.py
│       ├── main.py              # 진입점, 1회 실행 후 종료
│       ├── chain_client.py      # Substrate RPC 연결 관리
│       ├── validator_checker.py # Validator 상태 및 미수령 Era 조회
│       ├── payout_executor.py   # Payout 트랜잭션 실행 (page 지원)
│       ├── balance_checker.py   # Controller 잔액 사전 검증
│       ├── key_manager.py       # Controller 키 보안 로딩
│       └── notifier.py          # 실행 결과 알림 (선택 구현)
├── tests/
│   ├── test_validator_checker.py
│   ├── test_payout_executor.py
│   └── test_balance_checker.py
└── logs/                    # 로그 파일 디렉토리 (git 제외)
    └── .gitkeep
```

---

## 3. 패키지 관리: uv

### 3.1 초기 설정

```bash
# 저장소 클론 후 의존성 설치
git clone https://github.com/odeothx/creditcoin-payout.git
cd creditcoin-payout
uv sync
```

### 3.2 `pyproject.toml`

```toml
[project]
name = "creditcoin-payout"
version = "1.0.0"
description = "Creditcoin Validator 자동 Payout 프로그램"
requires-python = ">=3.12"
dependencies = [
    "substrate-interface>=1.7.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0",
    "structlog>=24.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]

[project.scripts]
creditcoin-payout = "creditcoin_payout.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### 3.3 개발 및 운영 명령어

```bash
# 의존성 설치
uv sync

# 개발 의존성 포함 설치
uv sync --extra dev

# 프로그램 실행 (1회 실행 후 종료)
uv run creditcoin-payout
# 또는
uv run python -m creditcoin_payout.main

# 테스트 실행
uv run pytest tests/

# 의존성 추가
uv add <패키지명>

# 잠금 파일 갱신
uv lock
```

---

## 4. 설정 파일

### 4.1 `config/config.yaml` (공개 가능, git 커밋)

```yaml
rpc:
  endpoint: "ws://localhost:9944"
  timeout: 30

validators:
  - stash: "5G9TuCM8NtpxXw7mYXvmsbRKdQmoYTs1GEJsSg5tNUuFTpdf"
    name: "Validator-1"
  - stash: "5FRuv3BiBhY87DWPtQqn827Bow5a1VmQQGzUvkheJWXmFwMD"
    name: "Validator-2"
  - stash: "5Fuj2qaV39sAZTDCPavjRGxGJxTHThCjCHg2vgymCSF1hZfY"
    name: "Validator-3"
  - stash: "5FF5VyM2AAnkUApV6eH7ynsNug8Ng7o8r7vvL6BCBMD4bRdu"
    name: "Validator-4"
  - stash: "5FL9Ew83tQNCUpJQFg24q4e57rUdYxWbmzjdQHE1XqQQ5vJv"
    name: "Validator-5"

controller:
  address: "5H5wrwyNM4bsnt7ngPsiUCfFi34ho5gRMKjwJ2sHytpbWnRi"

payout:
  max_eras_per_tx: 1        # Era 1개씩 개별 트랜잭션 (안전 우선)
  retry_count: 3
  retry_delay_sec: 10
  depth_eras: 84            # 조회할 최대 과거 Era 수
  tx_interval_sec: 6        # 트랜잭션 간 대기 시간 (finality 고려)

balance:
  min_balance_ctc: 1.0      # Controller 최소 잔액 (CTC 단위)

logging:
  level: "INFO"
  format: "json"            # "json" 또는 "text"
  file: "logs/payout.log"
  max_bytes: 10485760       # 10MB
  backup_count: 7           # 최근 7개 파일 보관
  heartbeat_file: "logs/heartbeat"   # 실행 완료 시각 기록 파일
```

### 4.2 `.env.example` (git 커밋 포함)

```dotenv
# Controller 계정 니모닉 (12 또는 24 단어)
# 실제 값은 .env 파일에 입력 (절대 git 커밋 금지)
CONTROLLER_MNEMONIC="word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12"

# 주소 검증용 (선택 사항, 입력 시 키 로딩 시 불일치 검증)
CONTROLLER_ADDRESS="5H5wrwyNM4bsnt7ngPsiUCfFi34ho5gRMKjwJ2sHytpbWnRi"
```

### 4.3 `.gitignore`

```gitignore
# 시크릿
.env

# uv 캐시
.venv/
__pycache__/
*.pyc

# 로그
logs/*.log
logs/heartbeat

# 빌드
dist/
*.egg-info/
```

---

## 5. 모듈 상세 설계

### 5.1 `chain_client.py` — RPC 연결 관리

**책임**: Substrate WebSocket 연결 생성 및 재연결 처리

```python
class ChainClient:
    def __init__(self, endpoint: str, timeout: int): ...
    def connect(self) -> SubstrateInterface: ...  # 끊겼으면 자동 재연결
    def disconnect(self): ...
    def get_metadata_info(self) -> dict: ...       # 메타데이터 확인용
```

**핵심 동작**
- 연결 상태 확인 후 재사용 (불필요한 재연결 방지)
- 연결 실패 시 `ConnectionError` 발생 → 상위에서 처리

---

### 5.2 `validator_checker.py` — 상태 및 Era 조회

**책임**: Validator 활성 여부 확인 + 미수령 Era 목록 반환

```python
@dataclass
class ValidatorStatus:
    stash: str
    name: str
    is_active: bool           # True: Active set, False: Waiting
    unclaimed_eras: list[int] # 미수령 Era 번호 목록
    page_count: int           # Era별 페이지 수 (Paged Exposure)

class ValidatorChecker:
    def get_current_era(self) -> int: ...
    def is_validator_active(self, stash: str) -> bool: ...
    def get_unclaimed_eras(self, stash: str, depth: int) -> list[int]: ...
    def get_page_count(self, stash: str, era: int) -> int: ...
    def check_all(self, validators: list[dict], depth: int) -> list[ValidatorStatus]: ...
```

**온체인 조회 항목**

| 조회 대상 | Pallet | Storage | 비고 |
|-----------|--------|---------|------|
| 현재 Era | `Staking` | `CurrentEra` | |
| Validator 활성 여부 | `Staking` | `ErasStakers` 또는 `ErasStakersOverview` | Paged Exposure 도입 시 후자 사용 |
| 수령 완료된 Era | `Staking` | `ClaimedRewards` 또는 `Ledger.legacy_claimed_rewards` | ⚠️ 체인 버전별 차이, 메타데이터 확인 필수 |
| Era별 보상 포인트 | `Staking` | `ErasRewardPoints` | |
| Era별 페이지 수 | `Staking` | `ErasStakersOverview` | Paged Exposure 확인 |

> **⚠️ 구현 필수 사전 작업**: 정확한 Storage 이름은 Creditcoin 체인 메타데이터로 반드시 확인해야 한다.
> 이 작업은 **개발 최우선 착수 항목**이며, 결과에 따라 아래 코드 구조가 변경될 수 있다.
> ```python
> substrate.get_metadata_storage_functions("Staking")
> ```
>
> **확인 필요 항목:**
> 1. `ClaimedRewards`가 별도 storage인지, `Ledger` 내부 필드인지
> 2. `ClaimedRewards`의 파라미터 구조: `[era, stash]` 또는 `[stash]`
> 3. `ErasStakersOverview` storage 존재 여부 (Paged Exposure 지원 확인)
> 4. SS58 prefix 값

**Waiting 상태 처리**
- `ErasStakers` 조회 결과가 없거나 `total == 0`이면 Waiting으로 판단
- Waiting 상태 Validator는 Payout 없이 로그 기록 후 건너뜀

---

### 5.3 `payout_executor.py` — 트랜잭션 실행

**책임**: `payoutStakers` / `payoutStakersByPage` 트랜잭션 서명 및 제출

```python
class PayoutExecutor:
    def __init__(self, chain_client, keypair, retry_count, retry_delay): ...
    def payout_single_era(self, validator_stash: str, era: int, page: int = 0) -> bool: ...
    def payout_all_pages(self, validator_stash: str, era: int, page_count: int) -> dict: ...
    def execute_all(self, statuses: list[ValidatorStatus]) -> dict: ...
```

**트랜잭션 흐름 (Paged Exposure 대응)**

```
Validator별 미수령 Era 순회
    │
    ▼
Era별 page_count 확인
    ├── page_count == 1 (일반)
    │       └── compose_call("Staking", "payout_stakers", {stash, era})
    └── page_count > 1 (Paged Exposure)
            └── for page in range(page_count):
                    compose_call("Staking", "payout_stakers_by_page", {stash, era, page})
    │
    ▼
create_signed_extrinsic(keypair)
    │
    ▼
submit_extrinsic(wait_for_inclusion=True)
    ├── 성공: TxHash 로그
    └── 실패: 에러 유형별 분기 처리
            ├── 재시도 가능 에러 → retry_count 만큼 재시도
            └── 재시도 불가 에러 → 즉시 건너뛰기 또는 중단
```

**Nonce 관리**
- `submit_extrinsic(wait_for_inclusion=True)` 로 트랜잭션 포함 확인 후 다음 TX 제출
- Nonce는 substrate-interface 라이브러리의 자동 조회 기능을 사용 (매 TX 제출 시 최신 Nonce 조회)
- `tx_interval_sec` (기본 6초) 대기 후 다음 트랜잭션 제출

**에러 분류 및 처리 전략**

| 에러 유형 | 재시도 여부 | 조치 |
|-----------|------------|------|
| `AlreadyClaimed` | ❌ | 정상 건너뛰기 (`skipped` 카운트 증가) |
| `InvalidEraToReward` | ❌ | 경고 로그 기록 후 건너뛰기 |
| `InsufficientFunds` | ❌ | **즉시 전체 중단** + 알림 발송 |
| RPC Timeout | ✅ | `retry_count` 만큼 exponential backoff 재시도 |
| Connection Error | ✅ | 재연결 후 재시도 |
| 기타 예외 | ✅ | `retry_count` 만큼 재시도 후 실패 로그 |

**반환 요약 형식**

```python
{
    "success": int,
    "failed": int,
    "skipped": int,
    "details": [
        {"validator": str, "era": int, "page": int, "status": str, "tx_hash": str | None, "error": str | None}
    ]
}
```

---

### 5.4 `balance_checker.py` — Controller 잔액 사전 검증

**책임**: Payout 실행 전 Controller 계정의 잔액이 트랜잭션 수수료를 감당할 수 있는지 확인

```python
class BalanceChecker:
    def __init__(self, chain_client, min_balance: float): ...
    def get_free_balance(self, address: str) -> float: ...
    def check_sufficient(self, address: str, expected_tx_count: int) -> bool: ...
```

**동작**
1. `System.Account` storage에서 Controller 주소의 free balance 조회
2. `min_balance_ctc` 설정값과 비교
3. 잔액 부족 시 `InsufficientBalanceError` 발생 → 알림 발송 후 Payout 중단

---

### 5.5 `key_manager.py` — 키 보안 로딩

**책임**: 환경변수에서 Controller 키페어 로드 및 주소 검증

```python
class KeyManager:
    @staticmethod
    def load_from_env() -> Keypair: ...
```

**동작 순서**
1. `CONTROLLER_MNEMONIC` 환경변수 읽기 (없으면 즉시 예외)
2. `Keypair.create_from_mnemonic()` 으로 키페어 생성
3. `CONTROLLER_ADDRESS` 환경변수가 있으면 주소 불일치 검증
4. 로그에 주소 앞 12자리만 출력 (전체 노출 방지)

---

### 5.6 `main.py` — 진입점 (1회 실행)

**책임**: 설정 로드, 로깅 초기화, Payout 1회 실행 후 종료

```python
import signal
import sys

def load_config() -> dict: ...
def setup_logging(cfg: dict): ...
def run_payout(config: dict): ...   # 실제 Payout 로직 실행
def graceful_shutdown(signum, frame): ...  # SIGTERM 핸들러
def main(): ...
```

**실행 모드**: cron에 의해 매일 1회 호출되며, 모든 Payout 처리 완료 후 정상 종료한다.

```python
def main():
    # SIGTERM 핸들러 등록 (진행 중인 TX 완료 대기)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)

    config = load_config()
    setup_logging(config["logging"])

    try:
        run_payout(config)
    except Exception as e:
        logger.exception("Payout 실행 중 치명적 오류", error=str(e))
        sys.exit(1)
    finally:
        # Heartbeat 파일 갱신
        update_heartbeat(config["logging"]["heartbeat_file"])
```

**Graceful Shutdown**
- `SIGTERM` / `SIGINT` 수신 시 전역 플래그 설정
- 현재 진행 중인 트랜잭션 완료 대기
- WebSocket 연결 정리
- 종료 사유를 로그에 기록

---

### 5.7 `notifier.py` — 결과 알림 (선택 구현)

Payout 완료 후 결과를 외부로 통보하는 선택적 모듈.  
초기 구현에서는 로그 기록으로 대체하고, 필요 시 아래 방식 중 선택 구현.

| 방식 | 구현 복잡도 | 비고 |
|------|------------|------|
| Telegram Bot | 낮음 | 개인/소규모 운영에 적합 |
| Slack Webhook | 낮음 | 팀 운영 시 적합 |
| Email (SMTP) | 중간 | 레거시 환경 호환 |

---

## 6. 실행 흐름

```
cron 스케줄 (매일 11:07) → main.py 실행
        │
        ▼
[로깅 초기화] structlog / JSON 포맷 설정
        │
        ▼
[ChainClient] ws://localhost:9944 연결
        │
        ▼
[KeyManager] .env에서 Controller 니모닉 로드 및 검증
        │
        ▼
[BalanceChecker] Controller 잔액 확인
        ├── 잔액 부족 → 알림 발송, 로그 기록, 프로그램 종료 (exit 1)
        └── 잔액 충분 → 계속
        │
        ▼
[ValidatorChecker] 현재 Era 조회
        │
        ▼
Validator 5개 순회
        ├── Waiting 상태 → 로그 기록 후 건너뜀 (skipped)
        └── Active 상태
                │
                ▼
        ClaimedRewards 조회 → 미수령 Era 목록 추출
                │
                ▼
        Era별 page_count 확인
                │
                ▼
        Era별/Page별 payoutStakers 트랜잭션 서명 & 제출
                ├── 성공 → TxHash 로그 기록
                ├── AlreadyClaimed → 건너뛰기
                ├── InsufficientFunds → 즉시 전체 중단 + 알림
                └── 기타 실패 → 최대 3회 재시도 → 실패 로그
        │
        ▼
완료 요약 로그 출력 (성공 N건 / 실패 N건 / 건너뜀 N건)
        │
        ▼
[Heartbeat] 실행 완료 시각 파일 기록
        │
        ▼
[ChainClient] 연결 해제 → 프로그램 정상 종료
```

---

## 7. 스케줄링: cron 설정

프로그램은 1회 실행 후 종료하는 방식이며, cron이 매일 지정 시각에 실행한다.

### 7.1 cron 설정

```bash
# crontab -e 로 등록
7 11 * * * cd /home/ubuntu/creditcoin-payout && /home/ubuntu/.local/bin/uv run creditcoin-payout >> /home/ubuntu/creditcoin-payout/logs/cron.log 2>&1
```

### 7.2 `deploy/crontab.example`

```crontab
# Creditcoin Payout 자동 실행
# 매일 11:07 서버 로컬 타임 기준
# 설치: crontab -l | cat - deploy/crontab.example | crontab -
7 11 * * * cd /home/ubuntu/creditcoin-payout && /home/ubuntu/.local/bin/uv run creditcoin-payout >> /home/ubuntu/creditcoin-payout/logs/cron.log 2>&1
```

### 7.3 cron vs 다른 스케줄링 방식 비교

| 방식 | 장점 | 단점 |
|------|------|------|
| **cron** (채택) | 가장 단순, 검증된 방식, OS 기본 제공, 설정 1줄 | missed 실행 자동 재실행 없음 |
| systemd timer | `Persistent=true`로 missed 실행 보장 | 설정 파일 2개 필요, cron 대비 복잡 |
| schedule 라이브러리 | Python 코드 내에서 관리 | 상주 프로세스 필요, 리소스 낭비 |

> **참고**: cron의 missed 실행 보완을 위해, 프로그램 시작 시 `depth_eras: 84`로 과거 Era를 충분히 조회하므로 1~2일 누락되더라도 다음 실행 시 자동 보정된다.

---

## 8. 보안 요구사항

### 8.1 파일 권한

```bash
# .env 파일은 소유자만 읽기 가능
chmod 600 .env
chown ubuntu:ubuntu .env

# 로그 디렉토리 접근 제한
chmod 750 logs/
```

### 8.2 방화벽 설정

```bash
# 9944 포트 외부 접근 완전 차단
sudo ufw deny 9944

# localhost에서만 접근 허용 (이미 ws://localhost:9944 사용 중이면 불필요)
sudo ufw allow from 127.0.0.1 to any port 9944
```

### 8.3 보안 체크리스트

| 항목 | 위험도 | 대책 |
|------|--------|------|
| 니모닉 노출 | 🔴 치명적 | `.env` 파일 권한 `600`, `.gitignore` 필수 등록 |
| 로그에 시크릿 출력 | 🔴 치명적 | 니모닉·개인키 로그 출력 코드 금지 (코드 리뷰 필수) |
| 9944 포트 외부 노출 | 🔴 치명적 | ufw로 외부 접근 차단 |
| `.env` git 커밋 | 🔴 치명적 | `.gitignore`에 `.env` 등록 및 pre-commit hook 권장 |
| 중복 Payout 실행 | 🟡 중간 | `ClaimedRewards` 온체인 조회로 이중 실행 방지 |
| Controller 잔액 부족 | 🟡 중간 | Payout 실행 전 `balance_checker.py`로 잔액 검증, 부족 시 중단 |
| cron 미실행 | 🟡 중간 | heartbeat 파일로 모니터링, `depth_eras: 84`로 자동 보정 |
| RPC 연결 끊김 | 🟢 낮음 | 재연결 로직 구현 (`chain_client.py`) |

### 8.4 니모닉 관리 원칙

- 니모닉은 오프라인 매체(종이, 하드웨어 지갑)에 별도 백업
- 서버에는 `.env` 파일 외 다른 경로에 니모닉 저장 금지
- CI/CD 파이프라인, 슬랙, 이메일 등에 니모닉 전달 금지
- 정기적으로 `.env` 파일 접근 로그 점검 (`last`, `auditd`)

---

## 9. 개발 및 배포 절차

### 9.1 로컬 개발 환경 구성

```bash
# 1. 저장소 클론
git clone https://github.com/odeothx/creditcoin-payout.git
cd creditcoin-payout

# 2. 의존성 설치 (개발 의존성 포함)
uv sync --extra dev

# 3. 환경변수 설정
cp .env.example .env
vi .env   # CONTROLLER_MNEMONIC 입력

# 4. 즉시 실행 테스트 (1회 실행)
uv run creditcoin-payout

# 5. 테스트 실행
uv run pytest tests/ -v
```

### 9.2 서버 배포

```bash
# 1. 코드 배포
git clone https://github.com/odeothx/creditcoin-payout.git /home/ubuntu/creditcoin-payout
cd /home/ubuntu/creditcoin-payout

# 2. 의존성 설치
uv sync --no-dev

# 3. .env 파일 생성
cp .env.example .env
chmod 600 .env
vi .env   # 실제 니모닉 입력

# 4. cron 등록
crontab -l | cat - deploy/crontab.example | crontab -

# 5. cron 등록 확인
crontab -l
```

### 9.3 업데이트 절차

```bash
cd /home/ubuntu/creditcoin-payout
git pull
uv sync --no-dev

# cron 설정 변경이 있는 경우에만
crontab -e
```

---

## 10. 로깅 설계

### 10.1 로깅 방식

`structlog` 라이브러리를 사용하여 JSON 형식의 구조화된 로그를 출력한다. 운영 환경에서의 로그 파싱·집계·알림 연동에 유리하다.

### 10.2 로그 출력 대상

| 출력 대상 | 설명 |
|-----------|------|
| 파일 (`logs/payout.log`) | `RotatingFileHandler`로 10MB × 7개 로테이션 |
| 표준출력 (stdout) | cron 실행 시 `logs/cron.log`로 리다이렉트 |
| Heartbeat 파일 | 실행 완료 시각 기록 (모니터링용) |

### 10.3 로그 기록 시점 및 내용

프로그램의 모든 주요 단계에서 로그를 기록한다:

| 시점 | 로그 레벨 | 기록 내용 |
|------|-----------|-----------|
| 프로그램 시작 | INFO | 프로그램 버전, 시작 시각 |
| RPC 연결 | INFO | 연결 성공/실패, 엔드포인트, 체인 이름 |
| Controller 키 로드 | INFO | 주소 앞 12자리 (전체 노출 금지) |
| 잔액 확인 | INFO | Controller 잔액 (CTC), 최소 요구 잔액 |
| 잔액 부족 | ERROR | 현재 잔액, 필요 잔액, 예상 TX 수 |
| 현재 Era 조회 | INFO | Era 번호 |
| Validator 상태 확인 | INFO | Validator 이름, Active/Waiting, 미수령 Era 목록 |
| Payout 시도 | INFO | Validator 이름, Era 번호, Page 번호 |
| Payout 성공 | INFO | Validator 이름, Era, Page, TxHash |
| Payout 실패 | ERROR | Validator 이름, Era, Page, 에러 유형, 에러 메시지, 재시도 횟수 |
| Payout 건너뛰기 | WARNING | 사유 (AlreadyClaimed, InvalidEra, Waiting 등) |
| 재시도 | WARNING | 재시도 횟수, 대기 시간, 에러 원인 |
| 프로그램 종료 | INFO | 완료 요약 (성공/실패/건너뜀 건수), 총 소요 시간 |
| 비정상 종료 | CRITICAL | 예외 메시지, 스택 트레이스 |
| Graceful Shutdown | WARNING | 수신 시그널, 진행 중 TX 대기 여부 |

### 10.4 JSON 로그 형식 예시

```json
{"timestamp": "2025-01-15T11:07:00.123Z", "level": "info", "event": "payout_start", "version": "1.0.0"}
{"timestamp": "2025-01-15T11:07:00.456Z", "level": "info", "event": "rpc_connected", "endpoint": "ws://localhost:9944"}
{"timestamp": "2025-01-15T11:07:00.789Z", "level": "info", "event": "key_loaded", "address_prefix": "5H5wrwyNM4b"}
{"timestamp": "2025-01-15T11:07:01.000Z", "level": "info", "event": "balance_check", "balance_ctc": 5.23, "min_required": 1.0}
{"timestamp": "2025-01-15T11:07:01.012Z", "level": "info", "event": "current_era", "era": 1523}
{"timestamp": "2025-01-15T11:07:01.234Z", "level": "info", "event": "validator_status", "validator": "Validator-1", "active": true, "unclaimed_eras": [1521, 1522]}
{"timestamp": "2025-01-15T11:07:01.456Z", "level": "info", "event": "validator_status", "validator": "Validator-2", "active": false, "unclaimed_eras": []}
{"timestamp": "2025-01-15T11:07:01.678Z", "level": "info", "event": "payout_attempt", "validator": "Validator-1", "era": 1521, "page": 0}
{"timestamp": "2025-01-15T11:07:04.901Z", "level": "info", "event": "payout_success", "validator": "Validator-1", "era": 1521, "page": 0, "tx_hash": "0xabc123..."}
{"timestamp": "2025-01-15T11:07:15.789Z", "level": "info", "event": "payout_complete", "success": 8, "failed": 0, "skipped": 2, "elapsed_sec": 14.67}
```

### 10.5 텍스트 로그 형식 (디버깅용)

`config.yaml`의 `logging.format`을 `"text"`로 설정 시 사람이 읽기 쉬운 형식으로 출력:

```
2025-01-15 11:07:00,123 [INFO] ============================================================
2025-01-15 11:07:00,124 [INFO] Creditcoin 자동 Payout 시작 (v1.0.0)
2025-01-15 11:07:00,456 [INFO] RPC 연결 성공: ws://localhost:9944
2025-01-15 11:07:00,789 [INFO] Controller 키 로드 완료: 5H5wrwyNM4b...
2025-01-15 11:07:01,000 [INFO] Controller 잔액: 5.23 CTC (최소 요구: 1.0 CTC)
2025-01-15 11:07:01,012 [INFO] 현재 Era: 1523
2025-01-15 11:07:01,234 [INFO] [Validator-1] Active - 미수령 Era: [1521, 1522]
2025-01-15 11:07:01,456 [WARNING] [Validator-2] Waiting 상태 - Payout 건너뜀
2025-01-15 11:07:01,678 [INFO] [Validator-1] Era 1521, Page 0 Payout 시도...
2025-01-15 11:07:04,901 [INFO]   ✅ Payout 성공 | Era 1521, Page 0 | TxHash: 0xabc123...
2025-01-15 11:07:07,123 [INFO]   ✅ Payout 성공 | Era 1522, Page 0 | TxHash: 0xdef456...
2025-01-15 11:07:15,789 [INFO] 완료 | 성공: 8, 실패: 0, 건너뜀: 2 | 소요: 14.67초
```

### 10.6 Health Check: Heartbeat 파일

프로그램 실행 완료 시 heartbeat 파일에 실행 결과를 기록한다. 외부 모니터링 도구에서 이 파일의 갱신 시각을 확인하여 정상 실행 여부를 판단할 수 있다.

```python
# 실행 완료 시 heartbeat 파일 갱신
def update_heartbeat(heartbeat_path: str):
    Path(heartbeat_path).write_text(json.dumps({
        "last_run": datetime.now().isoformat(),
        "status": "completed"
    }))
```

**모니터링 예시** (별도 cron 또는 스크립트):
```bash
# heartbeat 파일이 25시간 이상 미갱신이면 알림
find logs/heartbeat -mmin +1500 -exec echo "ALERT: Payout 미실행 감지" \;
```

---

## 11. 구현 시 확인 필요 사항 (개발 최우선 착수)

> **⚠️ 이 항목은 개발 시작 전 반드시 수행해야 한다.**  
> 아래 결과에 따라 5.2절, 5.3절의 Storage 이름과 트랜잭션 호출 방식이 변경될 수 있다.

```python
from substrateinterface import SubstrateInterface

substrate = SubstrateInterface(url="ws://localhost:9944")

# 1. SS58 prefix 확인
print(f"SS58 Format: {substrate.ss58_format}")

# 2. Staking 관련 Storage 함수 목록 확인
print("\n=== Staking Storage Functions ===")
for fn in substrate.get_metadata_storage_functions("Staking"):
    print(fn)

# 3. ClaimedRewards 구조 확인 (별도 storage vs Ledger 내부)
try:
    result = substrate.query("Staking", "ClaimedRewards", params=[<era>, "<stash_address>"])
    print(f"\nClaimedRewards (standalone): {result}")
except:
    print("\nClaimedRewards standalone storage 없음 → Ledger 내부 확인 필요")
    ledger = substrate.query("Staking", "Ledger", params=["<controller_address>"])
    print(f"Ledger: {ledger}")

# 4. ErasStakersOverview 확인 (Paged Exposure 지원 여부)
try:
    overview = substrate.query("Staking", "ErasStakersOverview", params=[<era>, "<stash_address>"])
    print(f"\nErasStakersOverview: {overview}")
    print("→ Paged Exposure 지원됨: payout_stakers_by_page 사용 필요")
except:
    print("\nErasStakersOverview 없음 → 기본 payout_stakers 사용")

# 5. payout_stakers_by_page extrinsic 존재 확인
calls = substrate.get_metadata_call_functions("Staking")
payout_calls = [c for c in calls if "payout" in c.lower()]
print(f"\nPayout 관련 extrinsics: {payout_calls}")
```

**확인 결과 반영 절차:**
1. 위 스크립트 실행 결과를 기록
2. 결과에 따라 5.2절 Storage 이름, 5.3절 extrinsic 이름 확정
3. 확정된 내용으로 설계서 업데이트 후 개발 착수

---

*문서 버전: 2.0 | 최초 작성일: 2025-01 | 최종 수정: 2026-03-25*  
*리뷰 반영 변경사항: payout_stakers_by_page 대응, cron 스케줄링, 잔액 검증, Nonce 관리, 에러 분류, structured logging, health check 추가*
