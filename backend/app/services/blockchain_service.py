"""Optional, fail-safe EVM audit transport and immutable local reservations."""
import hmac
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.database import SessionLocal
from app.audit_models import BlockchainAudit
from app.models import VerificationCase
from app.config import SESSIONS_DIR
from app.services.audit_canonicalizer import FORMAT, RECORD_TYPES, snapshot, canonical_json, audit_digest, case_key
from app.services.blockchain_config import get_config

_reserve_lock = threading.RLock()
_writer_lock = threading.Lock()  # One backend worker: nonce allocation + duplicate reconciliation.


class ChainUnavailable(Exception):
    pass


def utcnow():
    return datetime.now(timezone.utc)


def load_saved(case_id: str, db) -> tuple[dict, dict]:
    # Never trust session cache for integrity verification, nor accept file paths.
    if not re.fullmatch(r"CASE-[A-Za-z0-9-]{1,58}", case_id):
        raise ValueError("Invalid case identifier")
    try:
        case = json.loads((SESSIONS_DIR / f"{case_id}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise LookupError("Saved case not found") from None
    row = db.query(VerificationCase).filter_by(case_id=case_id).first()
    if row is None or case.get("case_id") != case_id:
        raise LookupError("Case is not persisted in both stores")
    stored = {column.name: getattr(row, column.name) for column in VerificationCase.__table__.columns}
    return case, stored


def metadata(row: BlockchainAudit) -> dict:
    def iso(value):
        return value.replace(tzinfo=timezone.utc).isoformat() if value else None
    return {"id": row.id, "record_type": row.record_type, "version": row.version,
            "status": row.status, "transaction_hash": row.transaction_hash, "block_number": row.block_number,
            "chain_id": row.chain_id, "contract_address": row.contract_address,
            "anchored_at": iso(row.anchored_at), "last_verified_at": iso(row.last_verified_at),
            "error_message": row.error_message, "format_version": row.format_version}


class EVMClient:
    def __init__(self, config):
        from web3 import Web3, HTTPProvider
        from web3.middleware import ExtraDataToPOAMiddleware
        self.config = config
        self.w3 = Web3(HTTPProvider(config.rpc_url, request_kwargs={"timeout": config.rpc_timeout}))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        if not self.w3.is_connected():
            raise ChainUnavailable()
        if self.w3.eth.chain_id != config.chain_id:
            raise ValueError("Configured chain ID does not match RPC")
        address = Web3.to_checksum_address(config.contract_address)
        if not self.w3.eth.get_code(address):
            raise ValueError("No deployed audit contract at configured address")
        abi = json.loads(Path(__file__).with_name("sentinel_audit_abi.json").read_text(encoding="utf-8"))
        self.contract = self.w3.eth.contract(address=address, abi=abi)
        # Validate the expected interface even if an unrelated contract has code.
        self.contract.functions.owner().call()

    def read(self, key, record_type, version):
        record = self.contract.functions.getRecord(key, record_type, version).call()
        return {"digest": "0x" + bytes(record[0]).hex(), "timestamp": record[1], "exists": record[3]}

    def send(self, key, record_type, version, digest):
        account = self.w3.eth.account.from_key(self.config.private_key)
        if not self.contract.functions.writers(account.address).call():
            raise ValueError("Writer is not authorized")
        tx = self.contract.functions.anchorRecord(key, record_type, version, digest).build_transaction({
            "from": account.address, "nonce": self.w3.eth.get_transaction_count(account.address, "pending"),
            "chainId": self.config.chain_id,
        })
        signed = account.sign_transaction(tx)
        return "0x" + bytes(self.w3.eth.send_raw_transaction(signed.raw_transaction)).hex()

    def receipt(self, tx_hash):
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=self.config.receipt_timeout, poll_latency=.2)
        if receipt.status != 1:
            raise ValueError("Audit transaction reverted")
        return {"transaction_hash": "0x" + bytes(receipt.transactionHash).hex(), "block_number": receipt.blockNumber}

    def locate(self, key, record_type, version):
        logs = self.contract.events.AuditAnchored().get_logs(from_block=0, to_block="latest",
            argument_filters={"caseKey": key, "recordType": record_type, "version": version})
        if not logs:
            raise ValueError("Audit event not found")
        event = logs[0]
        return {"transaction_hash": "0x" + bytes(event.transactionHash).hex(), "block_number": event.blockNumber}


def _failure(exc):
    # Never serialize exceptions: provider errors can contain RPC credentials,
    # signed transaction bodies, private keys or internal paths.
    if isinstance(exc, ChainUnavailable) or type(exc).__name__ in {"ConnectionError", "ConnectTimeout", "ReadTimeout", "TimeoutError", "ProviderConnectionError"}:
        return "CHAIN_UNAVAILABLE", "Audit chain unavailable. Screening remains saved locally."
    if type(exc).__name__ == "TimeExhausted":
        return "PENDING", "Transaction confirmation pending. Retry to reconcile the same transaction."
    return "FAILED", "Audit operation failed. Check contract, chain, writer and HMAC configuration."


def prepare(case_id: str, record_type="SCREENING_RESULT", *, new_decision=False) -> dict:
    """Freeze a saved snapshot BEFORE any network I/O. Existing versions never rebase."""
    config = get_config()
    if not config.enabled:
        return {"status": "NOT_ANCHORED", "enabled": False}
    if record_type not in RECORD_TYPES:
        raise ValueError("Unsupported record type")
    with _reserve_lock, SessionLocal() as db:
        rows = db.query(BlockchainAudit).filter_by(case_id=case_id, record_type=record_type).order_by(BlockchainAudit.version.desc()).all()
        if rows and not new_decision:
            return metadata(rows[0])
        case, persisted = load_saved(case_id, db)
        # A duplicate request for the same persisted decision reuses its version.
        if rows and new_decision:
            old = json.loads(rows[0].canonical_payload)
            current = snapshot(case, persisted, record_type, rows[0].version)
            if canonical_json(current) == canonical_json(old):
                return metadata(rows[0])
        version = rows[0].version + 1 if rows else 1
        payload = snapshot(case, persisted, record_type, version)
        row = BlockchainAudit(case_id=case_id, record_type=record_type, version=version,
            hmac_key_id=config.hmac_key_id, case_key=case_key(case_id),
            digest=audit_digest(payload, config.hmac_key), canonical_payload=canonical_json(payload),
            chain_id=config.chain_id, contract_address=config.contract_address, status="PENDING")
        db.add(row)
        db.commit()
        return metadata(row)


def prepare_safely(case_id, record_type="SCREENING_RESULT", *, new_decision=False):
    try:
        return prepare(case_id, record_type, new_decision=new_decision)
    except Exception as exc:
        state, message = _failure(exc)
        return {"status": state, "error_message": message}


def _current_payload(row, db):
    case, persisted = load_saved(row.case_id, db)
    latest = db.query(BlockchainAudit).filter_by(case_id=row.case_id, record_type=row.record_type).order_by(BlockchainAudit.version.desc()).first()
    if row.record_type == "OFFICER_DECISION" and latest.id != row.id:
        # Historical decisions have their own retained off-chain payload; compare
        # that history against chain, while latest decisions compare the live stores.
        return json.loads(row.canonical_payload)
    return snapshot(case, persisted, row.record_type, row.version)


def _assert_binding(row, config):
    if row.chain_id != config.chain_id or row.contract_address.lower() != config.contract_address.lower() or row.hmac_key_id != config.hmac_key_id or row.format_version != FORMAT:
        raise ValueError("Audit binding/key version differs from configured deployment")


def operate(audit_id: int, *, verify=False) -> dict:
    """Read on-chain data for verification; retry preserves the initial digest."""
    with _writer_lock, SessionLocal() as db:
        row = db.get(BlockchainAudit, audit_id)
        if row is None:
            raise LookupError("Audit not found")
        try:
            config = get_config()
            if not config.enabled:
                return {**metadata(row), "status": "NOT_ANCHORED", "enabled": False, "digest_match": None}
            _assert_binding(row, config)
            local_digest = audit_digest(_current_payload(row, db), config.hmac_key)
            frozen_digest = audit_digest(json.loads(row.canonical_payload), config.hmac_key)
            key = case_key(row.case_id)
            # Also protect the retained snapshot and local binding metadata.
            local_intact = (hmac.compare_digest(local_digest, row.digest) and hmac.compare_digest(frozen_digest, row.digest)
                            and row.case_key == key)
            client = EVMClient(config)
            chain_record = client.read(key, RECORD_TYPES[row.record_type], row.version)
            if not chain_record["exists"]:
                if verify:
                    row.status = "NOT_ANCHORED"
                    row.error_message = "No audit record exists on this chain."
                    db.commit()
                    return {**metadata(row), "digest_match": None}
                if not local_intact:
                    row.status = "TAMPER_DETECTED"
                    row.error_message = "Saved data differs from the reserved audit snapshot; retry refused."
                    db.commit()
                    return {**metadata(row), "digest_match": False}
                if not row.transaction_hash:
                    row.transaction_hash = client.send(key, RECORD_TYPES[row.record_type], row.version, row.digest)
                    row.status = "PENDING"
                    db.commit()  # Preserve tx hash before waiting, including timeout/crash recovery.
                receipt = client.receipt(row.transaction_hash)
                row.block_number = receipt["block_number"]
                chain_record = client.read(key, RECORD_TYPES[row.record_type], row.version)
                if not chain_record["exists"]:
                    raise ValueError("Mined transaction has no audit record")
            located = client.locate(key, RECORD_TYPES[row.record_type], row.version)
            row.transaction_hash = located["transaction_hash"]
            row.block_number = located["block_number"]
            row.anchored_at = datetime.fromtimestamp(chain_record["timestamp"], timezone.utc)
            matches = local_intact and hmac.compare_digest(local_digest, chain_record["digest"])
            # ANCHORED is distinct from explicit fresh integrity verification.
            row.status = ("VERIFIED" if verify else "ANCHORED") if matches else "TAMPER_DETECTED"
            row.last_verified_at = utcnow() if verify else row.last_verified_at
            row.error_message = None if matches else "Saved case differs from immutable audit proof."
            db.commit()
            return {**metadata(row), "digest_match": matches}
        except Exception as exc:
            state, message = _failure(exc)
            row.status, row.error_message = state, message
            db.commit()
            return {**metadata(row), "digest_match": None}


def anchor_safely(audit_id):
    try:
        return operate(audit_id)
    except Exception:
        return {"status": "FAILED", "error_message": "Audit persistence unavailable; case remains locally saved."}


def list_audits(case_id):
    with SessionLocal() as db:
        load_saved(case_id, db)
        return [metadata(row) for row in db.query(BlockchainAudit).filter_by(case_id=case_id).order_by(BlockchainAudit.record_type, BlockchainAudit.version).all()]


def network_status():
    result = {"enabled": False, "rpc_reachable": False, "contract_reachable": False, "chain_id": None, "contract_address": None}
    try:
        config = get_config()
        result.update(enabled=config.enabled, chain_id=config.chain_id, contract_address=config.contract_address or None)
        if not config.enabled:
            return result
        from web3 import Web3, HTTPProvider
        rpc = Web3(HTTPProvider(config.rpc_url, request_kwargs={"timeout": config.rpc_timeout}))
        result["rpc_reachable"] = rpc.is_connected()
        EVMClient(config)
        result["contract_reachable"] = True
    except Exception:
        result["error_message"] = "Audit network or contract unavailable; screening remains available."
    return result
