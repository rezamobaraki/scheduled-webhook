import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_async_session
from src.schemas import TimerCreateRequest, TimerCreateResponse, TimerRetrieveResponse
from src.services import TimerService

router = APIRouter(prefix="/timer", tags=["timers"])

AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]


@router.post(
    "",
    response_model=TimerCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Set a new timer",
)
async def create_timer(
    body: TimerCreateRequest,
    session: AsyncSessionDep,
) -> TimerCreateResponse:
    service = TimerService(session)
    return await service.create_timer(body)


@router.get(
    "/{timer_id}",
    response_model=TimerRetrieveResponse,
    summary="Get timer status",
)
async def retrieve_timer(
    timer_id: Annotated[uuid.UUID, Path(title="Timer ID", description="UUID of the timer")],
    session: AsyncSessionDep,
) -> TimerRetrieveResponse:
    service = TimerService(session)
    return await service.retrieve_timer(timer_id)
