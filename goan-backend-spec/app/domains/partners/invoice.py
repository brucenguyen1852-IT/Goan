"""Hoá đơn điện tử VAT cho chuyến từ khách sạn đối tác (SPEC 10.2) — interface + mock."""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.logging import log_event

logger = logging.getLogger("goan.invoice")


@dataclass
class InvoiceResult:
    invoice_no: str
    provider: str


class InvoiceService(ABC):
    @abstractmethod
    async def issue_vat_invoice(self, trip_id: uuid.UUID) -> InvoiceResult: ...


class MockInvoiceService(InvoiceService):
    async def issue_vat_invoice(self, trip_id: uuid.UUID) -> InvoiceResult:
        result = InvoiceResult(invoice_no=f"MOCK-{str(trip_id)[:8].upper()}", provider="mock")
        log_event(logger, "vat_invoice_issued", trip_id=str(trip_id), invoice_no=result.invoice_no)
        return result


class VnEInvoiceService(InvoiceService):
    """TODO: tích hợp nhà cung cấp hoá đơn điện tử VN (Viettel/VNPT Invoice) sau MVP."""

    async def issue_vat_invoice(self, trip_id: uuid.UUID) -> InvoiceResult:
        raise NotImplementedError("Chưa tích hợp hoá đơn điện tử thật")


_service: InvoiceService = MockInvoiceService()


def get_invoice_service() -> InvoiceService:
    return _service


def set_invoice_service(service: InvoiceService) -> None:
    global _service
    _service = service
