from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AccountLogEntryRead(BaseModel):
    index: int
    account_id: str
    timestamp: datetime
    level: str
    message: str
