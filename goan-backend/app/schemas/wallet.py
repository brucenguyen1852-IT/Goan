from pydantic import BaseModel


class WalletSummaryOut(BaseModel):
    earning_balance: int
    escrow_balance: int
    escrow_target: int
    escrow_status: str
    open_debt: int
