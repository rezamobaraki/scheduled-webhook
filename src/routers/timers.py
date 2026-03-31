"""Timer REST endpoints.

* ``POST /timer``          — create a new timer
* ``GET  /timer/{id}``     — query remaining time
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.schemas import TimerCreateRequest, TimerCreateResponse, TimerGetResponse
from app.services.timer_service import TimerService

router = APIRouter(prefix="/timer", tags=["timers"])


@router.post(
    "",
    response_model=TimerCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Set a new timer",
)
async def create_timer(
    body: TimerCreateRequest,
    session: AsyncSession = Depends(get_async_session),
) -> TimerCreateResponse:
    """Schedule a webhook to fire after the specified delay."""
    service = TimerService(session)
    return await service.create_timer(body)


@router.get(
    "/{timer_id}",
    response_model=TimerGetResponse,
    summary="Get timer status",
)
async def get_timer(
    timer_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> TimerGetResponse:
    """Return seconds remaining until the timer fires (``0`` if expired)."""
    service = TimerService(session)
    result = await service.get_timer(timer_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Timer {timer_id} not found.",
        )
    return result
