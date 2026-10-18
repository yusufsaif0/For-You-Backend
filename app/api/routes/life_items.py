from fastapi import APIRouter, Depends, Query, Response, status

from app.core.auth import require_user
from app.schemas.life_item import LifeItemCreate, LifeItemKind, LifeItemRead, LifeItemUpdate
from app.services.life_item_service import life_item_service


router = APIRouter(prefix="/life-items", tags=["Life tracking"])


@router.post("", response_model=LifeItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(item: LifeItemCreate, user: dict = Depends(require_user)) -> LifeItemRead:
    return await life_item_service.create(item, user["uid"])


@router.get("", response_model=list[LifeItemRead])
async def list_items(kind: LifeItemKind = Query(), user: dict = Depends(require_user)) -> list[LifeItemRead]:
    return await life_item_service.list(kind, user["uid"])


@router.patch("/{item_id}", response_model=LifeItemRead)
async def update_item(item_id: str, changes: LifeItemUpdate, user: dict = Depends(require_user)) -> LifeItemRead:
    return await life_item_service.update(item_id, changes, user["uid"])


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: str, user: dict = Depends(require_user)) -> Response:
    await life_item_service.delete(item_id, user["uid"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
