from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # API Settings
    API_TITLE: str = "Bulk CC Checker API"
    API_VERSION: str = "2.0.0"
    API_DESCRIPTION: str = "Advanced credit card checking with detailed status"
    
    # Rate Limiting
    MAX_BULK_SIZE: int = 100
    CONCURRENT_REQUESTS: int = 10
    RATE_LIMIT_PER_IP: int = 60  # per minute
    
    # Redis (Optional)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    
    # Security
    API_TOKEN: str = "your-secret-token-here"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"

settings = Settings()