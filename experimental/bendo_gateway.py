from __future__ import annotations

"""Bendo integration scaffold.

IMPORTANT:
- This module is intentionally NOT imported by the production app yet.
- No Bendo endpoint is guessed or hardcoded here.
- It becomes active only after Bendo provides the official API/SDK contract.
- Never store PAN, CVV, PIN, expiration date, track or EMV sensitive data.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional
import hashlib
import hmac
import json
import os
import uuid


class PaymentStatus(str, Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    CANCELLED = "CANCELLED"
    REVERSED = "REVERSED"
    REFUNDED = "REFUNDED"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"


class CardType(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    PREPAID = "PREPAID"
    UNKNOWN = "UNKNOWN"


SRI_PAYMENT_CODE = {
    CardType.DEBIT: "16",
    CardType.PREPAID: "18",
    CardType.CREDIT: "19",
}


@dataclass(frozen=True)
class BendoConfig:
    enabled: bool = False
    api_base_url: str = ""
    api_token: str = ""
    merchant_id: str = ""
    terminal_id: str = ""
    webhook_secret: str = ""

    @classmethod
    def from_env(cls) -> "BendoConfig":
        return cls(
            enabled=(os.getenv("BENDO_ENABLED") or "0").strip() == "1",
            api_base_url=(os.getenv("BENDO_API_BASE_URL") or "").strip().rstrip("/"),
            api_token=(os.getenv("BENDO_API_TOKEN") or "").strip(),
            merchant_id=(os.getenv("BENDO_MERCHANT_ID") or "").strip(),
            terminal_id=(os.getenv("BENDO_TERMINAL_ID") or "").strip(),
            webhook_secret=(os.getenv("BENDO_WEBHOOK_SECRET") or "").strip(),
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.enabled
            and self.api_base_url
            and self.api_token
            and self.merchant_id
        )


@dataclass(frozen=True)
class PaymentRequest:
    amount: float
    visit_ids: tuple[int, ...]
    patient_id: int
    currency: str = "USD"
    payment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""

    @property
    def idempotency_key(self) -> str:
        """Stable key for one intended charge.

        The exact header/field name must be mapped to Bendo's official contract.
        """
        raw = f"BENDO|{self.payment_id}|{self.patient_id}|{self.amount:.2f}|{','.join(map(str, self.visit_ids))}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class PaymentResult:
    payment_id: str
    status: PaymentStatus
    amount: float
    provider_transaction_id: Optional[str] = None
    approval_code: Optional[str] = None
    card_brand: Optional[str] = None
    card_type: CardType = CardType.UNKNOWN
    masked_pan: Optional[str] = None
    installments: Optional[int] = None
    provider_message: Optional[str] = None
    safe_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def sri_payment_code(self) -> Optional[str]:
        return SRI_PAYMENT_CODE.get(self.card_type)


class BendoContractUnavailable(RuntimeError):
    pass


class BendoGateway:
    """Provider boundary for the future production integration.

    Endpoint paths, request fields and response parsing are intentionally absent
    until Bendo provides the official merchant API/SDK documentation.
    """

    def __init__(self, config: Optional[BendoConfig] = None):
        self.config = config or BendoConfig.from_env()

    def assert_ready(self) -> None:
        if not self.config.enabled:
            raise BendoContractUnavailable("Bendo integration is disabled")
        if not self.config.configured:
            raise BendoContractUnavailable(
                "Bendo integration is enabled but official API configuration is incomplete"
            )

    def initiate_payment(self, request: PaymentRequest) -> PaymentResult:
        self.assert_ready()
        raise BendoContractUnavailable(
            "Official Bendo endpoint/SDK contract is still required before initiating payments"
        )

    def get_payment_status(self, provider_transaction_id: str) -> PaymentResult:
        self.assert_ready()
        raise BendoContractUnavailable(
            "Official Bendo status endpoint contract is still required"
        )

    def reverse_or_refund(self, provider_transaction_id: str, amount: Optional[float] = None) -> PaymentResult:
        self.assert_ready()
        raise BendoContractUnavailable(
            "Official Bendo reversal/refund endpoint contract is still required"
        )

    def verify_webhook(self, raw_body: bytes, signature: str) -> bool:
        """Generic HMAC helper only if Bendo documents HMAC-SHA256.

        Do NOT call this in production until the official signing scheme,
        canonicalization rules and header name are confirmed by Bendo.
        """
        secret = self.config.webhook_secret
        if not secret:
            return False
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, str(signature or "").strip())


def sanitize_provider_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only non-sensitive fields useful for reconciliation/audit.

    The exact allow-list should be tightened once Bendo publishes its schema.
    """
    allowed = {
        "id",
        "transaction_id",
        "status",
        "amount",
        "currency",
        "approval_code",
        "authorization_code",
        "card_brand",
        "card_type",
        "masked_pan",
        "last4",
        "installments",
        "created_at",
        "updated_at",
        "message",
    }
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if str(key).lower() in allowed:
            clean[str(key).lower()] = value
    return clean


def safe_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(sanitize_provider_payload(payload), ensure_ascii=False, separators=(",", ":"))
