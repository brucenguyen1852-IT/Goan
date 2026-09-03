"""eKYC / face-matching bên thứ 3 (SPEC 7.3, 7.4) — interface chuẩn + mock cho MVP."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class FaceMatchResult:
    match_score: float
    provider: str


@dataclass
class IdVerificationResult:
    verified: bool
    provider: str


class EkycProvider(ABC):
    @abstractmethod
    async def match_face(self, reference_url: str, selfie_url: str) -> FaceMatchResult: ...

    @abstractmethod
    async def verify_national_id(
        self, national_id: str, full_name: str
    ) -> IdVerificationResult: ...


class MockEkycProvider(EkycProvider):
    """Mock deterministic cho dev/test: cùng URL ảnh -> khớp 0.99, khác -> 0.4.

    Quy ước test: selfie_url chứa 'mismatch' luôn trả điểm thấp để test luồng khoá tài khoản.
    """

    async def match_face(self, reference_url: str, selfie_url: str) -> FaceMatchResult:
        if not reference_url or not selfie_url:
            return FaceMatchResult(match_score=0.0, provider="mock")
        if "mismatch" in selfie_url:
            return FaceMatchResult(match_score=0.40, provider="mock")
        return FaceMatchResult(match_score=0.99, provider="mock")

    async def verify_national_id(self, national_id: str, full_name: str) -> IdVerificationResult:
        return IdVerificationResult(verified=bool(national_id and full_name), provider="mock")


class ThirdPartyEkycProvider(EkycProvider):
    """TODO: tích hợp nhà cung cấp eKYC thật (VNPT eKYC / FPT.AI) khi rời MVP."""

    async def match_face(self, reference_url: str, selfie_url: str) -> FaceMatchResult:
        raise NotImplementedError("Chưa tích hợp eKYC provider thật")

    async def verify_national_id(self, national_id: str, full_name: str) -> IdVerificationResult:
        raise NotImplementedError("Chưa tích hợp eKYC provider thật")


_provider: EkycProvider = MockEkycProvider()


def get_ekyc_provider() -> EkycProvider:
    return _provider


def set_ekyc_provider(provider: EkycProvider) -> None:
    global _provider
    _provider = provider
