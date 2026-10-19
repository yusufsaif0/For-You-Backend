from fastapi import APIRouter, Depends, Response, status

from app.core.auth import require_user
from app.schemas.family import (
    FamilyDocumentAccessApprove,
    FamilyDocumentCreate,
    FamilyInviteCreate,
    FamilyPublicKeyUpdate,
    FamilyTaskCreate,
    FamilyTaskUpdate,
    FamilyWishContributionCreate,
    FamilyWishCreate,
    FamilyWishUpdate,
)
from app.services import family_service


router = APIRouter(prefix="/family", tags=["Family"])


@router.get("")
async def get_family(user: dict = Depends(require_user)):
    return await family_service.get_overview(user)


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(request: FamilyInviteCreate, user: dict = Depends(require_user)):
    return await family_service.create_invitation(request, user)


@router.post("/invitations/{invitation_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
async def accept_invitation(invitation_id: str, user: dict = Depends(require_user)) -> Response:
    await family_service.respond_invitation(invitation_id, True, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/invitations/{invitation_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline_invitation(invitation_id: str, user: dict = Depends(require_user)) -> Response:
    await family_service.respond_invitation(invitation_id, False, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/members/{member_uid}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(member_uid: str, user: dict = Depends(require_user)) -> Response:
    await family_service.remove_member(member_uid, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/public-key")
async def get_own_public_key(user: dict = Depends(require_user)):
    return await family_service.get_own_public_key(user)


@router.put("/public-key", status_code=status.HTTP_204_NO_CONTENT)
async def register_public_key(request: FamilyPublicKeyUpdate, user: dict = Depends(require_user)) -> Response:
    await family_service.register_public_key(request, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tasks")
async def list_tasks(user: dict = Depends(require_user)):
    return await family_service.list_tasks(user)


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(request: FamilyTaskCreate, user: dict = Depends(require_user)):
    return await family_service.create_task(request, user)


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, changes: FamilyTaskUpdate, user: dict = Depends(require_user)):
    return await family_service.update_task(task_id, changes, user)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: str, user: dict = Depends(require_user)) -> Response:
    await family_service.delete_task(task_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/wishes")
async def list_wishes(user: dict = Depends(require_user)):
    return await family_service.list_wishes(user)


@router.post("/wishes", status_code=status.HTTP_201_CREATED)
async def create_wish(request: FamilyWishCreate, user: dict = Depends(require_user)):
    return await family_service.create_wish(request, user)


@router.patch("/wishes/{wish_id}")
async def update_wish(wish_id: str, changes: FamilyWishUpdate, user: dict = Depends(require_user)):
    return await family_service.update_wish(wish_id, changes, user)


@router.delete("/wishes/{wish_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wish(wish_id: str, user: dict = Depends(require_user)) -> Response:
    await family_service.delete_wish(wish_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/wishes/{wish_id}/contributions")
async def add_wish_contribution(
    wish_id: str,
    request: FamilyWishContributionCreate,
    user: dict = Depends(require_user),
):
    return await family_service.add_wish_contribution(wish_id, request, user)


@router.get("/documents")
async def list_documents(user: dict = Depends(require_user)):
    return await family_service.list_documents(user)


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def publish_document(request: FamilyDocumentCreate, user: dict = Depends(require_user)):
    return await family_service.publish_document(request, user)


@router.post("/documents/{document_id}/requests", status_code=status.HTTP_201_CREATED)
async def create_document_request(document_id: str, user: dict = Depends(require_user)):
    return await family_service.create_document_request(document_id, user)


@router.get("/document-requests")
async def list_document_requests(user: dict = Depends(require_user)):
    return await family_service.list_document_requests(user)


@router.post("/document-requests/{request_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
async def approve_document_request(
    request_id: str,
    request: FamilyDocumentAccessApprove,
    user: dict = Depends(require_user),
) -> Response:
    await family_service.respond_document_request(request_id, True, request, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/document-requests/{request_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline_document_request(request_id: str, user: dict = Depends(require_user)) -> Response:
    await family_service.respond_document_request(request_id, False, None, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/documents/{document_id}/content")
async def get_document_content(document_id: str, user: dict = Depends(require_user)):
    return await family_service.get_document_content(document_id, user)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, user: dict = Depends(require_user)) -> Response:
    await family_service.delete_document(document_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
