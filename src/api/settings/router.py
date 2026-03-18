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
    restaurant_timezone: str
    force_store_open: bool | None
    prompt_instructions: str | None
    locked_prompt_tail: str = retell_service.LOCKED_PROMPT_TAIL
    updated_at: datetime
    retell_live: dict | None = None

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
    restaurant_timezone: str | None = None
    prompt_instructions: str | None = None


@router.get("", response_model=AgentSettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    import logging
    logger = logging.getLogger(__name__)
    settings = await get_agent_settings(db)
    retell_live = None
    try:
        retell_live = await retell_service.get_agent()
        if retell_live is not None:
            settings = await update_agent_settings(
                db,
                voice_id=retell_live.get("voice_id", settings.voice_id),
                voice_speed=retell_live.get("voice_speed", settings.voice_speed),
                interruption_sensitivity=retell_live.get("interruption_sensitivity", settings.interruption_sensitivity),
                responsiveness=retell_live.get("responsiveness", settings.responsiveness),
            )
    except Exception as e:
        logger.error("Failed to fetch live settings from Retell: %s", e)

    response = AgentSettingsResponse.model_validate(settings)
    response.retell_live = retell_live
    return response


@router.get("/retell")
async def get_retell_live(_: User = Depends(get_current_user)):
    return await retell_service.get_agent()


@router.patch("", response_model=AgentSettingsResponse)
async def patch_settings(
    body: UpdateAgentSettingsRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    import logging
    logger = logging.getLogger(__name__)
    updates = body.model_dump(exclude_none=True)
    voice_fields = {"voice_id", "voice_speed", "interruption_sensitivity", "responsiveness"}
    voice_updates = {k: v for k, v in updates.items() if k in voice_fields}
    
    if "voice_id" in voice_updates:
        valid_prefixes = ("11labs-", "cartesia-", "retell-", "openai-", "deepgram-", "minimax-")
        if not voice_updates["voice_id"].startswith(valid_prefixes):
            logger.error("Invalid voice_id format: %s", voice_updates["voice_id"])
            voice_updates.pop("voice_id")
            
    is_active = updates.get("is_active")
    prompt_instructions = updates.get("prompt_instructions")
    settings = await update_agent_settings(db, **updates)
    if voice_updates:
        try:
            logger.warning("Sending to Retell update-agent: %s", voice_updates)
            result = await retell_service.update_agent_voice_settings(**voice_updates)
            logger.warning("Retell update-agent response: %s", result)
        except Exception as e:
            logger.error("Failed to sync voice settings to Retell: %s", e)
    if is_active is not None:
        try:
            await retell_service.toggle_agent_active(is_active)
        except Exception as e:
            logger.error("Failed to sync active status to Retell: %s", e)
    if prompt_instructions is not None:
        try:
            full_prompt = retell_service.assemble_global_prompt(prompt_instructions)
            await retell_service.update_conversation_flow({"global_prompt": full_prompt})
        except Exception as e:
            logger.error("Failed to sync prompt to Retell: %s", e)
    return AgentSettingsResponse.model_validate(settings)


class StoreStatusRequest(BaseModel):
    open: bool | None = None


class StoreStatusResponse(BaseModel):
    force_store_open: bool | None
    message: str


@router.post("/store-status", response_model=StoreStatusResponse)
async def set_store_status(
    body: StoreStatusRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    settings = await update_agent_settings(db, force_store_open=body.open)
    if body.open is True:
        msg = "Store forced OPEN. Time-based hours are bypassed."
    elif body.open is False:
        msg = "Store forced CLOSED. Time-based hours are bypassed."
    else:
        msg = "Store set to AUTO. Time-based hours are active."
    return StoreStatusResponse(force_store_open=settings.force_store_open, message=msg)
