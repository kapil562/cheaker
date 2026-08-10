from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import httpx
import json
import time


class PaymentProcessor(ABC):
    """Base payment processor"""
    
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.name = "base"
    
    @abstractmethod
    async def process_card(
        self,
        card_number: str,
        exp_month: int,
        exp_year: int,
        cvv: str,
        amount: float = 1.0,
        currency: str = "USD"
    ) -> Dict[str, Any]:
        pass


class ProcessorFactory:
    """Factory for creating processors"""
    
    _processors = {}
    
    @classmethod
    def initialize(cls, client: httpx.AsyncClient):
        cls._processors = {}
    
    @classmethod
    def get_processor(cls, name: str) -> Optional[PaymentProcessor]:
        return cls._processors.get(name)
    
    @classmethod
    def get_available_processors(cls) -> Dict[str, PaymentProcessor]:
        return cls._processors
