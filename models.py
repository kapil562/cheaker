from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

class CardStatus(str, Enum):
    CHARGED = "charged"
    LIVE = "live"
    DEAD = "dead"
    CCN = "ccn"
    ERROR = "error"
    UNKNOWN = "unknown"
    PENDING = "pending"
    REQUIRES_ACTION = "requires_action"

class ProcessorType(str, Enum):
    STRIPE = "stripe"
    RAZORPAY = "razorpay"
    PAYPAL = "paypal"
    BRAINTREE = "braintree"
    ADYEN = "adyen"

class CardCheckRequest(BaseModel):
    card_number: str
    exp_month: int = Field(..., ge=1, le=12)
    exp_year: int = Field(..., ge=2024)
    cvv: str = Field(..., min_length=3, max_length=4)
    processor: str = "stripe"
    amount: float = 1.0
    currency: str = "USD"

    @validator('card_number')
    def validate_card_number(cls, v):
        v = v.replace(" ", "").replace("-", "")
        if not v.isdigit():
            raise ValueError("Card number must contain only digits")
        if len(v) < 13 or len(v) > 19:
            raise ValueError("Card number must be between 13-19 digits")
        return v

class BulkCheckRequest(BaseModel):
    cards: List[str] = Field(..., min_items=1, max_items=100)
    processor: str = "stripe"
    amount: float = 1.0
    currency: str = "USD"

class CheckResult(BaseModel):
    success: bool
    status: CardStatus
    message: str
    card_number: str
    card_type: str
    card_brand: str
    processor: str
    payment_id: Optional[str] = None
    error_code: Optional[str] = None
    time_taken: float
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: Optional[Dict[str, Any]] = {}