from datetime import datetime
from fastapi import APIRouter, Depends
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.db import get_db, User
from src.utils.dependencies import get_current_user
from src.utils.db_functions import get_agent_settings, update_agent_settings
from src.services import retell_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


class AgentSettingsResponse(BaseModel):
    id: str
    voice_id: str
    voice_speed: float
    voice_temperature: float
    interruption_sensitivity: float
    responsiveness: float
    is_active: bool
    kitchen_open_time: str
    kitchen_close_time: str
    store_open_time: str
    store_close_time: str
    closed_greeting: str
    open_greeting: str | None
    updated_at: datetime

    class Config:
        from_attributes = True


class UpdateAgentSettingsRequest(BaseModel):
    voice_id: str | None = None
    voice_speed: float | None = Field(default=None, ge=0.5, le=2.0)
    voice_temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    interruption_sensitivity: float | None = Field(default=None, ge=0.0, le=1.0)
    responsiveness: float | None = Field(default=None, ge=0.0, le=1.0)
    is_active: bool | None = None
    kitchen_open_time: str | None = None
    kitchen_close_time: str | None = None
    store_open_time: str | None = None
    store_close_time: str | None = None
    closed_greeting: str | None = None
    open_greeting: str | None = None


@router.get("", response_model=AgentSettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    settings = await get_agent_settings(db)
    return AgentSettingsResponse.model_validate(settings)


@router.patch("", response_model=AgentSettingsResponse)
async def patch_settings(
    body: UpdateAgentSettingsRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    updates = body.model_dump(exclude_none=True)
    voice_fields = {"voice_id", "voice_speed", "voice_temperature", "interruption_sensitivity", "responsiveness"}
    voice_updates = {k: v for k, v in updates.items() if k in voice_fields}
    is_active = updates.get("is_active")
    settings = await update_agent_settings(db, **updates)
    if voice_updates:
        await retell_service.update_agent_voice_settings(**voice_updates)
    if is_active is not None:
        await retell_service.toggle_agent_active(is_active)
    return AgentSettingsResponse.model_validate(settings)
