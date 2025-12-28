"""
Pydantic models for BAW v2 API with player instance tracking.

This version uses player_instances instead of a simple players table,
allowing the same player_id to be reused over time for different people.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


# ============================================================================
# Agents (unchanged)
# ============================================================================

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


# ============================================================================
# Player Instances (replaces Player models)
# ============================================================================

class PlayerInstanceBase(BaseModel):
    player_id: str = Field(..., pattern=r'^pyr\d+$')
    display_name: Optional[str] = None
    agent_id: int

    @field_validator('player_id')
    @classmethod
    def lowercase_player_id(cls, v: str) -> str:
        return v.lower()


class PlayerInstanceCreate(PlayerInstanceBase):
    """Create a new player instance (used when adding a player)"""
    pass


class PlayerInstanceUpdate(BaseModel):
    """Update an existing player instance (change name or agent)"""
    display_name: Optional[str] = None
    agent_id: Optional[int] = None


class PlayerInstance(PlayerInstanceBase):
    """Full player instance with metadata"""
    id: int
    first_seen: date
    last_seen: Optional[date] = None
    is_current: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


class PlayerInstanceWithAgent(PlayerInstance):
    """Player instance with agent name included"""
    agent_name: str


# For backwards compatibility with existing API consumers
# These models work with player_id but internally use player instances
class PlayerBase(BaseModel):
    """Legacy player model for API compatibility"""
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
    display_name: Optional[str] = None
    agent_id: Optional[int] = None


class Player(PlayerBase):
    """
    Represents a current player (is_current=true player instance).
    Includes the instance ID for internal use.
    """
    id: int  # This is the player_instance_id
    agent_name: Optional[str] = None

    class Config:
        from_attributes = True


# ============================================================================
# Weeks (unchanged)
# ============================================================================

class Week(BaseModel):
    week_id: date

    class Config:
        from_attributes = True


# ============================================================================
# Weekly Raw Data (updated to use player_instance_id)
# ============================================================================

class WeeklyRawBase(BaseModel):
    week_id: date
    player_instance_id: int
    week_amount: Decimal
    pending: Decimal


class WeeklyRawCreate(WeeklyRawBase):
    pass


class WeeklyRaw(WeeklyRawBase):
    scraped_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Manual Slips (updated to use player_instance_id)
# ============================================================================

class ManualSlipBase(BaseModel):
    """
    Base model for manual slips.
    API accepts player_id for convenience, but internally converts to player_instance_id
    """
    week_id: date
    player_id: str  # Convenience field - will be converted to player_instance_id
    amount: Decimal
    note: Optional[str] = None

    @field_validator('player_id')
    @classmethod
    def lowercase_player_id(cls, v: str) -> str:
        return v.lower()


class ManualSlipCreate(ManualSlipBase):
    """Create manual slip using player_id (converted to instance internally)"""
    pass


class ManualSlipInternal(BaseModel):
    """Internal model that uses player_instance_id directly"""
    week_id: date
    player_instance_id: int
    amount: Decimal
    note: Optional[str] = None


class ManualSlip(BaseModel):
    """
    Manual slip response model.
    Includes both instance_id (internal) and player_id (convenience)
    """
    id: int
    week_id: date
    player_instance_id: int
    amount: Decimal
    note: Optional[str] = None
    created_at: datetime

    # Convenience fields populated from joins
    player_id: Optional[str] = None
    display_name: Optional[str] = None
    agent_name: Optional[str] = None

    class Config:
        from_attributes = True


# ============================================================================
# Weekly Player Status (updated to use player_instance_id)
# ============================================================================

class WeeklyPlayerStatusBase(BaseModel):
    week_id: date
    player_instance_id: int
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


# ============================================================================
# Upload & Responses (unchanged)
# ============================================================================

class UploadResponse(BaseModel):
    success: bool
    message: str
    week_id: Optional[date] = None
    players_imported: int = 0


class ErrorResponse(BaseModel):
    success: bool = False
    error: str


# ============================================================================
# Dashboard/Display Models
# ============================================================================

class PlayerRow(BaseModel):
    """
    Player data for dashboard display.
    Combines data from player_instances, weekly_raw, and status.
    """
    week_id: date
    player_id: str
    display_name: Optional[str]
    agent_name: str
    week_amount: Decimal
    action: str  # "Pay" or "Request"
    abs_amount: Decimal
    engaged: bool = False
    paid: bool = False


class AgentSummary(BaseModel):
    """Summary statistics for an agent"""
    agent_name: str
    num_players: int
    net: Decimal
    final_balance: Decimal
    players: list[PlayerRow] = []


class Transfer(BaseModel):
    """Settlement transfer between agents"""
    from_agent: str = Field(alias="from")
    to_agent: str = Field(alias="to")
    amount: Decimal

    class Config:
        populate_by_name = True
