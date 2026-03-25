# Creditcoin Payout 자동화 프로그램

Creditcoin 네트워크 Validator들을 위한 `payoutStakers` (Paged Exposure 포함) 트랜잭션 자동행 도구입니다.

[English README](README.md)

## 주요 기능

- **자동 Payout**: 여러 Validator의 스테이킹 보상을 자동으로 수령합니다.
- **Paged Exposure 지원**: 일반 `payoutStakers`와 `payoutStakersByPage` 호출을 모두 처리합니다.
- **RPC Fallback**: 로컬 RPC(`ws://localhost:9944`) 연결 실패 시 공식 RPC(`wss://mainnet3.creditcoin.network`)로 자동 전환됩니다.
- **잔액 검증**: 실행 전 Controller 계정의 수수료 잔액을 사전에 확인합니다.
- **안정성**: 지수 백오프(Exponential Backoff)를 포함한 재시도 로직 및 에러 분류 처리가 적용되어 있습니다.
- **구조화된 로깅**: `structlog`를 사용하여 모니터링이 용이한 JSON/Text 로그를 제공합니다.

## 사전 요구 사항

- **Python**: 3.12 버전 이상
- **패키지 매니저**: [uv](https://docs.astral.sh/uv/) (권장) 또는 `pip`

## 설치 방법

1. **저장소 클론**:
   ```bash
   git clone https://github.com/odeothx/creditcoin-payout.git
   cd creditcoin-payout
   ```

2. **의존성 설치**:
   ```bash
   uv sync
   ```

## 설정 방법

### 1. 환경변수 설정 (`.env`)
템플릿 파일을 복사하여 Controller의 니모닉을 입력합니다.
```bash
cp .env.example .env
chmod 600 .env
vi .env
```
```dotenv
CONTROLLER_MNEMONIC="12단어 또는 24단어 니모닉 입력"
CONTROLLER_ADDRESS="5H5wrwyNM4bs..." # 선택 사항 (검증용 주소)
```

### 2. config/config.yaml
Validator 목록 및 RPC 설정을 수정합니다.
```yaml
rpc:
  endpoint: "ws://localhost:9944"
  fallback_endpoint: "wss://mainnet3.creditcoin.network"

validators:
  - stash: "5G..."
    name: "Validator-1"
  # ... 추가 Validator 등록
```

## 사용법

### 수동 실행
프로그램을 1회 실행하고 종료합니다:
```bash
uv run creditcoin-payout
```

### 정기 실행 등록 (Cron)
매일 정해진 시각(예: 오전 11:10)에 실행되도록 cron에 등록합니다:
```bash
crontab -l | cat - deploy/crontab.example | crontab -
```

## 테스트
Mock을 사용하여 실제 RPC 연결 없이 로직을 검증합니다:
```bash
uv run pytest tests/ -v
```

## 로깅
`logs/` 디렉토리에 로그가 저장됩니다:
- `logs/payout.log`: 상세 실행 로그 (JSON/Text 형식).
- `logs/heartbeat`: 마지막 정상 실행 시각 기록 (상태 모니터링용).

## 보안
- **권한 관리**: `.env` 파일 권한을 `600`으로 유지하십시오.
- **비밀 정보 보호**: 로그에는 주소의 앞 12자리만 기록되며, 니모닉은 절대 노출되지 않습니다.
- **암호화 통신**: 공식 RPC Fallback 시 SSL(`wss://`)을 사용합니다.

## 라이선스
MIT
