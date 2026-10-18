from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import AwareDatetime

from app.core.auth import require_user
from app.schemas.schedule import ScheduleCreate, ScheduleRead, ScheduleUpdate
from app.services.schedule_service import schedule_service


router = APIRouter(prefix="/schedules", tags=["Schedules"])


@router.post("", response_model=ScheduleRead, status_code=status.HTTP_201_CREATED)
async def create_schedule(schedule: ScheduleCreate, user: dict = Depends(require_user)) -> ScheduleRead:
    return await schedule_service.create(schedule, user["uid"])


@router.get("", response_model=list[ScheduleRead])
async def list_schedules(
    scheduled_for: AwareDatetime | None = Query(default=None),
    user: dict = Depends(require_user),
) -> list[ScheduleRead]:
    return await schedule_service.list(scheduled_for, user["uid"])


@router.patch("/{schedule_id}", response_model=ScheduleRead)
async def update_schedule(schedule_id: str, changes: ScheduleUpdate, user: dict = Depends(require_user)) -> ScheduleRead:
    return await schedule_service.update(schedule_id, changes, user["uid"])


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(schedule_id: str, user: dict = Depends(require_user)) -> Response:
    await schedule_service.delete(schedule_id, user["uid"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
