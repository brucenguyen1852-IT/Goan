"""Import tập trung mọi ORM model để Alembic autogenerate và create_all thấy đủ metadata."""

from app.database import Base
from app.domains.approvals.models import ApprovalRequest
from app.domains.audit.models import AuditLog
from app.domains.escrow.models import EscrowTransaction
from app.domains.fraud.models import DriverOnlineSession, FraudIncident, FraudReviewQueue
from app.domains.iam.models import Permission, Role, RolePermission, StaffRole, StaffUser
from app.domains.partners.models import (
    MarketingSubsidy,
    Partner,
    PartnerCommission,
    SatelliteZone,
)
from app.domains.payments.models import (
    DriverWallet,
    Payment,
    ReconciliationReport,
    WalletTransaction,
)
from app.domains.pricing.models import PeakPeriod, PricingRule
from app.domains.trips.models import Trip, TripEvent, TripGpsLog, TripRating
from app.domains.users.models import DriverProfile, User

__all__ = [
    "Base",
    "AuditLog",
    "ApprovalRequest",
    "StaffUser",
    "Role",
    "Permission",
    "RolePermission",
    "StaffRole",
    "User",
    "DriverProfile",
    "Trip",
    "TripGpsLog",
    "TripEvent",
    "TripRating",
    "PricingRule",
    "PeakPeriod",
    "EscrowTransaction",
    "FraudIncident",
    "FraudReviewQueue",
    "DriverOnlineSession",
    "Partner",
    "PartnerCommission",
    "SatelliteZone",
    "MarketingSubsidy",
    "Payment",
    "DriverWallet",
    "WalletTransaction",
    "ReconciliationReport",
]
