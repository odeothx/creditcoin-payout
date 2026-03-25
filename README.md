# Creditcoin Payout Automation

Automation tool for executing `payoutStakers` (including Paged Exposure) transactions for Creditcoin network validators.

[한국어 문서 (Korean README)](README_KO.md)

## Features

- **Automated Payouts**: Automatically claims staking rewards for multiple validators.
- **Paged Exposure Support**: Handles both standard `payoutStakers` and `payoutStakersByPage` extrinsics.
- **RPC Fallback**: Connects to local RPC (`ws://localhost:9944`) by default, with automatic fallback to official RPC (`wss://mainnet3.creditcoin.network`).
- **Safety Checks**: Pre-execution balance validation for the controller account.
- **Robustness**: Automatic retries with exponential backoff and error classification.
- **Structured Logging**: JSON/Text logging using `structlog` for easy monitoring.

## Prerequisites

- **Python**: 3.12 or higher
- **Manager**: [uv](https://docs.astral.sh/uv/) (Recommended) or `pip`

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/odeothx/creditcoin-payout.git
   cd creditcoin-payout
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

## Configuration

### 1. Environment Variables (`.env`)
Create a `.env` file from the template and enter your controller's mnemonic.
```bash
cp .env.example .env
chmod 600 .env
vi .env
```
```dotenv
CONTROLLER_MNEMONIC="your twelve or twenty-four word mnemonic"
CONTROLLER_ADDRESS="5H5wrwyNM4bs..." # Optional address for verification
```

### 2. config/config.yaml
Modify the validator list and RPC settings as needed.
```yaml
rpc:
  endpoint: "ws://localhost:9944"
  fallback_endpoint: "wss://mainnet3.creditcoin.network"

validators:
  - stash: "5G..."
    name: "Validator-1"
  # ... Add more
```

## Usage

### Manual Execution
Run the program once and exit:
```bash
uv run creditcoin-payout
```

### Scheduled Execution (Cron)
Add a cron job to run daily (e.g., at 11:10 AM):
```bash
crontab -l | cat - deploy/crontab.example | crontab -
```

## Testing
Run unit tests with mocks (no RPC connection required):
```bash
uv run pytest tests/ -v
```

## Logging
Logs are stored in the `logs/` directory:
- `logs/payout.log`: Detailed execution logs (JSON/Text).
- `logs/heartbeat`: Contains the timestamp of the last successful run (for health checks).

## Security
- **Strict Permissions**: Keep `.env` permissions at `600`.
- **No Private Keys in Logs**: Only the first 12 characters of addresses are logged.
- **Fallback Security**: Uses SSL (`wss://`) for the official RPC fallback.

## License
MIT
