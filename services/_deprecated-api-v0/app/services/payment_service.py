"""Payment Service — điều phối luồng thanh toán Online/Tiền mặt.

Dùng Adapter Pattern cho cổng thanh toán để dễ thêm/đổi nhà cung cấp
(VNPay/MoMo/ZaloPay) mà không sửa logic nghiệp vụ core (đúng khuyến nghị
trong tài liệu kiến trúc, mục 11 - Rủi ro kỹ thuật #4).
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CaptureResult:
    success: bool
    gateway_txn_ref: str | None
    error_message: str | None = None


class PaymentGatewayAdapter(ABC):
    """Interface chung — mỗi cổng thanh toán thật implement class riêng."""

    @abstractmethod
    def capture(self, amount: int, idempotency_key: str, metadata: dict) -> CaptureResult:
        ...

    @abstractmethod
    def refund(self, gateway_txn_ref: str, amount: int) -> CaptureResult:
        ...

    @abstractmethod
    def verify_webhook_signature(self, payload: dict, signature: str) -> bool:
        ...


class VNPayAdapter(PaymentGatewayAdapter):
    """TODO: implement thật khi có tài khoản đối tác VNPay.
    Xem: https://sandbox.vnpayment.vn/apis/docs/ — dùng HMAC-SHA512 để verify."""

    def capture(self, amount: int, idempotency_key: str, metadata: dict) -> CaptureResult:
        raise NotImplementedError("Cắm API VNPay thật vào đây")

    def refund(self, gateway_txn_ref: str, amount: int) -> CaptureResult:
        raise NotImplementedError

    def verify_webhook_signature(self, payload: dict, signature: str) -> bool:
        raise NotImplementedError


class MockGatewayAdapter(PaymentGatewayAdapter):
    """Dùng cho môi trường dev/test — luôn capture thành công, không gọi mạng thật."""

    def capture(self, amount: int, idempotency_key: str, metadata: dict) -> CaptureResult:
        return CaptureResult(success=True, gateway_txn_ref=f"MOCK-{uuid.uuid4().hex[:12]}")

    def refund(self, gateway_txn_ref: str, amount: int) -> CaptureResult:
        return CaptureResult(success=True, gateway_txn_ref=gateway_txn_ref)

    def verify_webhook_signature(self, payload: dict, signature: str) -> bool:
        return True


def get_gateway_adapter(gateway_name: str) -> PaymentGatewayAdapter:
    adapters = {
        "vnpay": VNPayAdapter,
        "mock": MockGatewayAdapter,
    }
    adapter_cls = adapters.get(gateway_name, MockGatewayAdapter)
    return adapter_cls()
