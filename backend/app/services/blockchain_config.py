"""Lazy, isolated configuration. Secrets are never included in repr or responses."""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv
from app.config import BASE_DIR


@dataclass(frozen=True)
class BlockchainConfig:
    enabled: bool = False
    rpc_url: str = field(default="http://127.0.0.1:8545", repr=False)
    chain_id: int = 31337
    contract_address: str = ""
    private_key: str = field(default="", repr=False)
    hmac_key: str = field(default="", repr=False)
    hmac_key_id: str = "local-v1"
    rpc_timeout: float = 3.0
    receipt_timeout: float = 15.0


def get_config() -> BlockchainConfig:
    load_dotenv(BASE_DIR / ".env", override=False)
    return BlockchainConfig(
        enabled=os.getenv("BLOCKCHAIN_ENABLED", "false").lower() == "true",
        rpc_url=os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545"),
        chain_id=int(os.getenv("BLOCKCHAIN_CHAIN_ID", "31337")),
        contract_address=os.getenv("BLOCKCHAIN_CONTRACT_ADDRESS", ""),
        private_key=os.getenv("BLOCKCHAIN_WRITER_PRIVATE_KEY", ""),
        hmac_key=os.getenv("BLOCKCHAIN_AUDIT_HMAC_KEY", ""),
        hmac_key_id=os.getenv("BLOCKCHAIN_AUDIT_HMAC_KEY_ID", "local-v1"),
        rpc_timeout=float(os.getenv("BLOCKCHAIN_RPC_TIMEOUT", "3")),
        receipt_timeout=float(os.getenv("BLOCKCHAIN_RECEIPT_TIMEOUT", "15")),
    )
