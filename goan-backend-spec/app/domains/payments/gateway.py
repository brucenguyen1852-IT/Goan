"""Cổng thanh toán (SPEC 9): interface chuẩn ngay từ đầu, MVP dùng mock."""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class PaymentResult:
    success: bool
    reference: str
    message: str = ""


class PaymentGateway(ABC):
    @abstractmethod
    async def charge(self, rider_id: str, amount: Decimal, trip_id: str) -> PaymentResult: ...

    @abstractmethod
    async def refund(self, payment_id: str, amount: Decimal) -> PaymentResult: ...


class MockPaymentGateway(PaymentGateway):
    """Luôn thành công — dùng cho dev/test."""

    async def charge(self, rider_id: str, amount: Decimal, trip_id: str) -> PaymentResult:
        return PaymentResult(success=True, reference=f"mock_{uuid.uuid4().hex[:16]}")

    async def refund(self, payment_id: str, amount: Decimal) -> PaymentResult:
        return PaymentResult(success=True, reference=f"mock_refund_{uuid.uuid4().hex[:16]}")


class VNPayGateway(PaymentGateway):
    """TODO: tích hợp VNPay thật (chữ ký HMAC, IPN webhook idempotent)."""

    async def charge(self, rider_id: str, amount: Decimal, trip_id: str) -> PaymentResult:
        raise NotImplementedError("VNPay chưa được tích hợp trong MVP")

    async def refund(self, payment_id: str, amount: Decimal) -> PaymentResult:
        raise NotImplementedError("VNPay chưa được tích hợp trong MVP")


_gateway: PaymentGateway = MockPaymentGateway()


def get_payment_gateway() -> PaymentGateway:
    return _gateway


def set_payment_gateway(gateway: PaymentGateway) -> None:
    global _gateway
    _gateway = gateway
