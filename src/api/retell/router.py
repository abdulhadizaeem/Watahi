import os
from datetime import datetime, date, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.db import get_db, User, Caller
from src.utils.dependencies import get_current_user
from src.utils.db_functions import (
    list_call_logs,
    get_call_log_by_call_id,
    get_combined_stats,
    get_caller_by_phone,
    upsert_caller,
    update_caller_last_called,
    create_call_log,
    update_call_log,
    create_reservation,
    get_reservation_by_id,
    list_reservations,
    update_reservation,
    get_reservation_stats,
    link_reservation_to_call,
    get_agent_settings,
    build_menu_text,
    create_order,
    list_orders,
    get_order_by_id,
    update_order,
    get_order_stats,
    get_recent_order_for_caller,
)
from src.services import retell_service

RETELL_API_KEY = os.getenv("RETELL_API_KEY", "")

router = APIRouter(prefix="/api/retell", tags=["retell"])

ALLOWED_RESERVATION_STATUSES = {"confirmed", "cancelled", "completed", "no_show"}
ALLOWED_ORDER_STATUSES = {"received", "preparing", "ready", "completed", "cancelled"}
ALLOWED_ORDER_TYPES = {"pickup", "delivery", "dine_in"}


def _check_business_hours(current_hhmm: str, open_hhmm: str, close_hhmm: str) -> bool:
    def to_minutes(t: str) -> int:
        h, m = map(int, t.split(":"))
        return h * 60 + m
    now = to_minutes(current_hhmm)
    return to_minutes(open_hhmm) <= now <= to_minutes(close_hhmm)


def _format_reservation_message(res_date: date, time_str: str, party_size: int) -> str:
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    month = months[res_date.month - 1]
    day = res_date.day
    hour, minute = map(int, time_str.split(":"))
    period = "am" if hour < 12 else "pm"
    display_hour = hour % 12 or 12
    time_display = f"{display_hour}:{minute:02d}{period}" if minute else f"{display_hour}{period}"
    return f"Your reservation has been confirmed for {month} {day} at {time_display} for {party_size} {'person' if party_size == 1 else 'people'}."


class CallLogResponse(BaseModel):
    id: str
    call_id: str
    caller_phone: str
    customer_name: str | None
    call_status: str
    direction: str
    recording_url: str | None
    transcript: str | None
    call_summary: str | None
    order_booked: bool
    call_successful: bool | None
    user_sentiment: str | None
    duration_ms: int | None
    start_timestamp: int | None
    end_timestamp: int | None
    order_items: str | None
    order_type: str | None
    special_notes: str | None
    call_reason: str | None
    customer_name_extracted: str | None
    reservation_date: str | None
    party_size: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class CombinedStatsResponse(BaseModel):
    calls: dict
    reservations: dict
    orders: dict


class CallerResponse(BaseModel):
    id: str
    phone_number: str
    customer_name: str | None
    notes: str | None
    created_at: datetime
    last_called_at: datetime | None

    class Config:
        from_attributes = True


class UpdateCallerRequest(BaseModel):
    customer_name: str | None = None
    notes: str | None = None


class FlowNodeInstruction(BaseModel):
    type: str = "prompt"
    text: str


class FlowNodeUpdate(BaseModel):
    id: str
    type: str
    instruction: FlowNodeInstruction


class UpdateFlowRequest(BaseModel):
    global_prompt: str | None = None
    nodes: list[FlowNodeUpdate] | None = None
    default_dynamic_variables: dict | None = None
    model_choice: dict | None = None
    model_temperature: float | None = Field(default=None, ge=0, le=1)


class AddKnowledgeBaseRequest(BaseModel):
    kb_id: str


class InboundDynamicVariables(BaseModel):
    customer_name: str
    is_returning_customer: str
    customer_phone: str
    kitchen_is_open: str
    store_is_open: str
    menu: str


class InboundCallInnerResponse(BaseModel):
    dynamic_variables: InboundDynamicVariables


class InboundWebhookResponse(BaseModel):
    call_inbound: InboundCallInnerResponse


class WebhookResponse(BaseModel):
    received: bool


class ReservationResponse(BaseModel):
    reservation_id: str
    customer_name: str
    caller_phone: str
    reservation_date: date
    reservation_time: str
    party_size: int
    special_requests: str | None
    status: str
    call_id: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReservationListResponse(BaseModel):
    reservations: list[ReservationResponse]
    total: int
    skip: int
    limit: int


class ReservationStatsResponse(BaseModel):
    total: int
    confirmed: int
    completed: int
    cancelled: int
    no_show: int
    today: int


class ReservationUpdateRequest(BaseModel):
    status: str | None = None
    reservation_date: date | None = None
    reservation_time: str | None = None
    party_size: int | None = None
    special_requests: str | None = None
    customer_name: str | None = None


class OrderResponse(BaseModel):
    order_id: str
    call_id: str | None
    caller_phone: str
    customer_name: str
    order_items: list[dict]
    order_type: str
    delivery_address: str | None
    total_amount: float | None
    status: str
    special_notes: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    skip: int
    limit: int


class OrderStatsResponse(BaseModel):
    total: int
    received: int
    preparing: int
    ready: int
    completed: int
    cancelled: int
    today: int


class OrderUpdateRequest(BaseModel):
    status: str | None = None
    special_notes: str | None = None
    delivery_address: str | None = None


class OrderConfirmRequest(BaseModel):
    customer_name: str
    customer_phone: str
    order_items: list[dict]
    order_type: str
    delivery_address: str = ""
    total_amount: float | None = None


@router.get("/calls", response_model=list[CallLogResponse])
async def get_calls(
    skip: int = 0,
    limit: int = 20,
    call_status: str | None = None,
    order_booked: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    logs = await list_call_logs(db, skip, limit, call_status, order_booked)
    return [CallLogResponse.model_validate(log) for log in logs]


@router.get("/calls/{call_id}", response_model=CallLogResponse)
async def get_call(
    call_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    log = await get_call_log_by_call_id(db, call_id)
    if not log:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Call log not found")
    return CallLogResponse.model_validate(log)


@router.get("/calls/{call_id}/live")
async def get_live_call(call_id: str, _: User = Depends(get_current_user)) -> dict:
    return await retell_service.get_call(call_id)


@router.get("/stats", response_model=CombinedStatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stats = await get_combined_stats(db)
    return CombinedStatsResponse(**stats)


@router.get("/flow")
async def get_flow(_: User = Depends(get_current_user)) -> dict:
    return await retell_service.get_conversation_flow()


@router.patch("/flow")
async def update_flow(
    body: UpdateFlowRequest,
    _: User = Depends(get_current_user),
) -> dict:
    payload = body.model_dump(exclude_none=True)
    return await retell_service.update_conversation_flow(payload)


@router.get("/knowledge-bases")
async def get_knowledge_bases(_: User = Depends(get_current_user)) -> dict:
    return await retell_service.list_knowledge_bases()


@router.post("/flow/knowledge-base")
async def add_knowledge_base(
    body: AddKnowledgeBaseRequest,
    _: User = Depends(get_current_user),
) -> dict:
    return await retell_service.add_knowledge_base_to_flow(body.kb_id)


@router.delete("/flow/knowledge-base/{kb_id}")
async def remove_knowledge_base(
    kb_id: str,
    _: User = Depends(get_current_user),
) -> dict:
    return await retell_service.remove_knowledge_base_from_flow(kb_id)


@router.get("/callers", response_model=list[CallerResponse])
async def get_callers(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Caller).offset(skip).limit(limit))
    callers = result.scalars().all()
    return [CallerResponse.model_validate(c) for c in callers]


@router.get("/callers/{phone_number}", response_model=CallerResponse)
async def get_caller(
    phone_number: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    caller = await get_caller_by_phone(db, phone_number)
    if not caller:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Caller not found")
    return CallerResponse.model_validate(caller)


@router.patch("/callers/{phone_number}", response_model=CallerResponse)
async def update_caller(
    phone_number: str,
    body: UpdateCallerRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    caller = await get_caller_by_phone(db, phone_number)
    if not caller:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Caller not found")
    updates = body.model_dump(exclude_none=True)
    if updates:
        await db.execute(
            sa_update(Caller).where(Caller.phone_number == phone_number).values(**updates)
        )
        await db.commit()
        await db.refresh(caller)
    return CallerResponse.model_validate(caller)


@router.get("/reservations/stats", response_model=ReservationStatsResponse)
async def get_reservations_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stats = await get_reservation_stats(db)
    return ReservationStatsResponse(**stats)


@router.get("/reservations", response_model=ReservationListResponse)
async def get_reservations(
    skip: int = 0,
    limit: int = 20,
    date: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from sqlalchemy import func as sa_func, select as sa_select
    from src.utils.db import Reservation
    count_query = sa_select(sa_func.count()).select_from(Reservation)
    if date:
        count_query = count_query.where(Reservation.reservation_date == date)
    if status:
        count_query = count_query.where(Reservation.status == status)
    total = await db.scalar(count_query) or 0
    rows = await list_reservations(db, skip, limit, date, status)
    return ReservationListResponse(
        reservations=[ReservationResponse.model_validate(r) for r in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/reservations/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(
    reservation_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    reservation = await get_reservation_by_id(db, reservation_id)
    if not reservation:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    return ReservationResponse.model_validate(reservation)


@router.patch("/reservations/{reservation_id}", response_model=ReservationResponse)
async def patch_reservation(
    reservation_id: str,
    body: ReservationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    reservation = await get_reservation_by_id(db, reservation_id)
    if not reservation:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    updates = body.model_dump(exclude_none=True)
    if "status" in updates and updates["status"] not in ALLOWED_RESERVATION_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of: {', '.join(ALLOWED_RESERVATION_STATUSES)}",
        )
    updated = await update_reservation(db, reservation_id, **updates)
    return ReservationResponse.model_validate(updated)


@router.delete("/reservations/{reservation_id}")
async def cancel_reservation(
    reservation_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    reservation = await get_reservation_by_id(db, reservation_id)
    if not reservation:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    await update_reservation(db, reservation_id, status="cancelled")
    return {"message": "Reservation cancelled"}


@router.get("/orders/stats", response_model=OrderStatsResponse)
async def get_orders_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stats = await get_order_stats(db)
    return OrderStatsResponse(**stats)


@router.get("/orders", response_model=OrderListResponse)
async def get_orders(
    skip: int = 0,
    limit: int = 20,
    status: str | None = None,
    date: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from sqlalchemy import func as sa_func, select as sa_select
    from src.utils.db import Order
    count_query = sa_select(sa_func.count()).select_from(Order)
    if status:
        count_query = count_query.where(Order.status == status)
    if date:
        from datetime import date as date_type
        count_query = count_query.where(sa_func.date(Order.created_at) == date_type.fromisoformat(date))
    total = await db.scalar(count_query) or 0
    rows = await list_orders(db, skip, limit, status, date)
    return OrderListResponse(
        orders=[OrderResponse.model_validate(r) for r in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    order = await get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Order not found")
    return OrderResponse.model_validate(order)


@router.patch("/orders/{order_id}", response_model=OrderResponse)
async def patch_order(
    order_id: str,
    body: OrderUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    updates = body.model_dump(exclude_none=True)
    if "status" in updates and updates["status"] not in ALLOWED_ORDER_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of: {', '.join(ALLOWED_ORDER_STATUSES)}",
        )
    updated = await update_order(db, order_id, **updates)
    return OrderResponse.model_validate(updated)


@router.post("/order-confirm")
async def order_confirm(request: Request, db: AsyncSession = Depends(get_db)):
    payload_bytes = await request.body()
    signature = request.headers.get("x-retell-signature", "")
    if not retell_service.verify_webhook_signature(payload_bytes, signature, secret=RETELL_API_KEY):
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
    try:
        raw = await request.json()
    except Exception:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")
    try:
        body = OrderConfirmRequest(**raw)
    except Exception as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    if body.order_type not in ALLOWED_ORDER_TYPES:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"order_type must be one of: {', '.join(ALLOWED_ORDER_TYPES)}",
        )
    if body.order_type == "delivery" and not body.delivery_address.strip():
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Delivery address is required for delivery orders.",
        )
    order = await create_order(
        db,
        caller_phone=body.customer_phone,
        customer_name=body.customer_name,
        order_items=body.order_items,
        order_type=body.order_type,
        delivery_address=body.delivery_address.strip() or None,
        total_amount=body.total_amount,
        special_notes=None,
        call_id=None,
    )
    await upsert_caller(db, body.customer_phone, body.customer_name)
    messages = {
        "pickup": "Your order has been confirmed. It will be ready for pickup in about 15 minutes.",
        "delivery": "Your order has been confirmed and will be delivered to you in about 30 minutes.",
        "dine_in": "Your order has been confirmed and will be brought to your table shortly.",
    }
    return {"order_id": order.order_id, "message": messages[body.order_type]}


@router.post("/reservation-confirm")
async def reservation_confirm(request: Request, db: AsyncSession = Depends(get_db)):
    payload_bytes = await request.body()
    signature = request.headers.get("x-retell-signature", "")
    if not retell_service.verify_webhook_signature(payload_bytes, signature, secret=RETELL_API_KEY):
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")
    customer_name = (body.get("customer_name") or "").strip()
    customer_phone = (body.get("customer_phone") or "").strip()
    date_str = (body.get("reservation_date") or "").strip()
    time_str = (body.get("reservation_time") or "").strip()
    party_size = body.get("party_size")
    special_requests = (body.get("special_requests") or "").strip() or None
    if not all([customer_name, customer_phone, date_str, time_str, party_size is not None]):
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Missing required fields")
    try:
        res_date = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid date format. Use YYYY-MM-DD")
    reservation = await create_reservation(
        db,
        caller_phone=customer_phone,
        customer_name=customer_name,
        reservation_date=res_date,
        reservation_time=time_str,
        party_size=int(party_size),
        special_requests=special_requests,
        call_id=None,
    )
    await upsert_caller(db, customer_phone, customer_name)
    message = _format_reservation_message(res_date, time_str, int(party_size))
    return {"reservation_id": reservation.reservation_id, "message": message}


@router.post("/inbound-webhook", response_model=InboundWebhookResponse)
async def inbound_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload_bytes = await request.body()
    signature = request.headers.get("x-retell-signature", "")
    if not retell_service.verify_webhook_signature(payload_bytes, signature, secret=RETELL_API_KEY):
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")
    call_inbound = event.get("call_inbound", {})
    from_number = call_inbound.get("from_number", "")
    existing_caller = await get_caller_by_phone(db, from_number)
    dynamic_vars = retell_service.build_caller_dynamic_variables(existing_caller, from_number)
    await upsert_caller(db, from_number, existing_caller.customer_name if existing_caller else None)
    await update_caller_last_called(db, from_number)
    settings = await get_agent_settings(db)
    now_hhmm = datetime.now(timezone.utc).strftime("%H:%M")
    dynamic_vars["kitchen_is_open"] = "true" if _check_business_hours(now_hhmm, settings.kitchen_open_time, settings.kitchen_close_time) else "false"
    dynamic_vars["store_is_open"] = "true" if _check_business_hours(now_hhmm, settings.store_open_time, settings.store_close_time) else "false"
    dynamic_vars["menu"] = await build_menu_text(db)
    return InboundWebhookResponse(
        call_inbound=InboundCallInnerResponse(
            dynamic_variables=InboundDynamicVariables(**dynamic_vars)
        )
    )


@router.post("/webhook", response_model=WebhookResponse)
async def webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload_bytes = await request.body()
    signature = request.headers.get("x-retell-signature", "")
    if not retell_service.verify_webhook_signature(payload_bytes, signature):
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")
    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")
    event_type = event.get("event")
    call_data = event.get("call", {})
    call_id = call_data.get("call_id", "")
    if event_type == "call_ended":
        from_number = call_data.get("from_number", "")
        direction = call_data.get("direction", "inbound")
        collected = call_data.get("collected_dynamic_variables", {})
        customer_name_extracted = (collected.get("customer_name") or "").strip()
        order_items = (collected.get("order_items_summary") or "").strip() or None
        order_type = (collected.get("order_type") or "").strip() or None
        special_notes = (collected.get("special_notes") or "").strip() or None
        reservation_date = (collected.get("reservation_date") or "").strip() or None
        party_size = (collected.get("party_size") or "").strip() or None
        existing_log = await get_call_log_by_call_id(db, call_id)
        if not existing_log:
            caller = await get_caller_by_phone(db, from_number)
            await create_call_log(
                db,
                call_id=call_id,
                caller_phone=from_number,
                customer_name=caller.customer_name if caller else None,
                direction=direction,
                call_status="ended",
            )
        await update_call_log(
            db,
            call_id,
            call_status="ended",
            duration_ms=call_data.get("duration_ms"),
            end_timestamp=call_data.get("end_timestamp"),
            start_timestamp=call_data.get("start_timestamp"),
            transcript=call_data.get("transcript"),
            recording_url=call_data.get("recording_url"),
            raw_payload=event,
            order_items=order_items,
            order_type=order_type,
            special_notes=special_notes,
            customer_name_extracted=customer_name_extracted or None,
            reservation_date=reservation_date,
            party_size=party_size,
        )
        if customer_name_extracted:
            await upsert_caller(db, from_number, customer_name_extracted)
        if from_number:
            recent_order = await get_recent_order_for_caller(db, from_number, minutes=60)
            if recent_order:
                await update_order(db, recent_order.order_id, call_id=call_id)
                await update_call_log(db, call_id, order_booked=True)
    elif event_type == "call_analyzed":
        analysis = call_data.get("call_analysis", {})
        custom = analysis.get("custom_analysis_data", {})
        call_reason = (custom.get("call_reason") or "").strip() or None
        await update_call_log(
            db,
            call_id,
            call_summary=analysis.get("call_summary"),
            user_sentiment=analysis.get("user_sentiment"),
            order_booked=bool(custom.get("order_booked", False)),
            call_successful=custom.get("call_successful"),
            call_reason=call_reason,
        )
        if call_reason == "reservation":
            log = await get_call_log_by_call_id(db, call_id)
            if log and log.caller_phone:
                await link_reservation_to_call(db, log.caller_phone, call_id)
    return WebhookResponse(received=True)
