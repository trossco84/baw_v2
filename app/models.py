from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class AgentCreate(AgentBase):
    pass


class AgentUpdate(AgentBase):
    pass


class Agent(AgentBase):
    id: int

    class Config:
        from_attributes = True


class PlayerBase(BaseModel):
    player_id: str = Field(..., pattern=r'^pyr\d+$')
    display_name: Optional[str] = None
    agent_id: int

    @field_validator('player_id')
    @classmethod
    def lowercase_player_id(cls, v: str) -> str:
        return v.lower()


class PlayerCreate(PlayerBase):
    pass


class PlayerUpdate(BaseModel):
    player_id: Optional[str] = Field(None, pattern=r'^pyr\d+$')
    display_name: Optional[str] = None
    agent_id: Optional[int] = None

    @field_validator('player_id')
    @classmethod
    def lowercase_player_id(cls, v: Optional[str]) -> Optional[str]:
        return v.lower() if v else v


class Player(PlayerBase):
    id: int

    class Config:
        from_attributes = True


class Week(BaseModel):
    week_id: date

    class Config:
        from_attributes = True


class WeeklyRawBase(BaseModel):
    week_id: date
    player_id: str
    week_amount: Decimal
    pending: Decimal


class WeeklyRawCreate(WeeklyRawBase):
    pass


class WeeklyRaw(WeeklyRawBase):
    scraped_at: datetime

    class Config:
        from_attributes = True


class ManualSlipBase(BaseModel):
    week_id: date
    player_id: str
    amount: Decimal
    note: Optional[str] = None


class ManualSlipCreate(ManualSlipBase):
    pass


class ManualSlip(ManualSlipBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class WeeklyPlayerStatusBase(BaseModel):
    week_id: date
    player_id: str
    engaged: bool = False
    paid: bool = False


class WeeklyPlayerStatusCreate(WeeklyPlayerStatusBase):
    pass


class WeeklyPlayerStatusUpdate(BaseModel):
    engaged: Optional[bool] = None
    paid: Optional[bool] = None


class WeeklyPlayerStatus(WeeklyPlayerStatusBase):
    updated_at: datetime

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    success: bool
    message: str
    week_id: Optional[date] = None
    players_imported: int = 0


class ErrorResponse(BaseModel):
    success: bool = False
    error: str