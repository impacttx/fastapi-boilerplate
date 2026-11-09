from datetime import UTC, datetime
import uuid

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlmodel import col, delete

from app.auth.models import AccountInfoRequest, User
from app.auth.security import get_current_user
from app.core.db_service import get_latest_active_terms
from app.core.schemas import ImageUploadedResponse, MessageResponse
from app.database import SessionDep
from app.settings import UPLOAD_DIR_ROOT, settings
from app.storage import put_object

from . import schemas

router = APIRouter(prefix="/user", tags=["User"])

TNC_MUST_BE_ACCEPTED = "You must accept the terms and conditions to proceed."


@router.post("/tnc", status_code=status.HTTP_200_OK)
async def accept_terms_and_conditions(
    payload: schemas.TermAcceptancePayload,
    db_session: SessionDep,
    user: User = Depends(get_current_user),
) -> MessageResponse:
    tnc = await get_latest_active_terms(db_session)

    if not tnc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Terms and conditions not found.")

    if not payload.accepted or not payload.revision:
        raise HTTPException(status.HTTP_403_FORBIDDEN, TNC_MUST_BE_ACCEPTED)

    user.accepted_terms[payload.revision] = datetime.now(tz=UTC)
    user.updated_at = datetime.now(tz=UTC)
    db_session.add(user)
    await db_session.commit()
    return MessageResponse(message="Terms and conditions accepted successfully", status="success")


@router.get("/profile")
async def get_self_profile(
    user: User = Depends(get_current_user),
) -> schemas.UserSchema:
    if not user.accepted_terms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, TNC_MUST_BE_ACCEPTED)
    return schemas.UserSchema(
        id=user.id or uuid.UUID(int=0),
        mobile_number=user.mobile_number,
        profile_picture=user.profile_picture,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        date_of_birth=user.date_of_birth,
    )


@router.put("/profile", response_model=schemas.UserSchema, status_code=status.HTTP_202_ACCEPTED)
async def update_self_profile(
    payload: schemas.ProfileUpdatePayload,
    db_session: SessionDep,
    user: User = Depends(get_current_user),
):
    if not user.accepted_terms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, TNC_MUST_BE_ACCEPTED)
    user.first_name = payload.first_name
    user.last_name = payload.last_name
    if payload.email:
        user.email = payload.email
    user.date_of_birth = payload.date_of_birth
    user.updated_at = datetime.now(tz=UTC)
    user.bio = payload.bio or user.bio
    db_session.add(user)
    await db_session.commit()
    return user


@router.patch("/profile", status_code=status.HTTP_202_ACCEPTED)
async def patch_self_profile(
    payload: schemas.ProfilePatchPayload,
    db_session: SessionDep,
    user: User = Depends(get_current_user),
) -> schemas.UserSchema:
    if not user.accepted_terms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, TNC_MUST_BE_ACCEPTED)
    if payload.first_name is not None:
        user.first_name = payload.first_name
    if payload.last_name is not None:
        user.last_name = payload.last_name
    if payload.email is not None:
        user.email = payload.email
    if payload.date_of_birth is not None:
        user.date_of_birth = payload.date_of_birth
    if payload.bio is not None:
        user.bio = payload.bio

    if any(
        [
            payload.first_name is not None,
            payload.last_name is not None,
            payload.email is not None,
            payload.date_of_birth is not None,
            payload.bio is not None,
        ]
    ):
        # Only update the timestamp if any field is changed
        user.updated_at = datetime.now(tz=UTC)
    db_session.add(user)
    await db_session.commit()

    return schemas.UserSchema(
        id=user.id or uuid.UUID(int=0),
        mobile_number=user.mobile_number,
        profile_picture=user.profile_picture,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        date_of_birth=user.date_of_birth,
    )


@router.put("/profile-picture", status_code=status.HTTP_200_OK)
async def update_profile_picture(
    db_session: SessionDep,
    image: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> ImageUploadedResponse:
    if image.content_type not in ["image/jpg", "image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid image format. Only JPEG and PNG are allowed."
        )
    if not user.accepted_terms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, TNC_MUST_BE_ACCEPTED)

    # Derive extension from content-type; fall back to filename if available
    file_ext = "png" if image.content_type == "image/png" else "jpg"
    if image.filename:
        name_ext = image.filename.rsplit(".", 1)[-1].lower()
        if name_ext in {"jpg", "jpeg", "png", "webp"}:
            file_ext = name_ext
    filename = f"{user.id}.{file_ext}"
    if settings.has_s3_configured():
        file_path = f"images/profile/{filename}"
        # Upload to S3 or other object storage
        await put_object(
            key=file_path,
            data=await image.read(),
            content_type=image.content_type,
        )
        picture_url = f"{settings.DO_SPACES_CDN_ENDPOINT}/{file_path}"
    else:
        async with aiofiles.open(UPLOAD_DIR_ROOT / filename, "wb") as f:
            content = await image.read()
            await f.write(content)
        # Build a server-relative URL for locally stored images
        file_path = f"{settings.STATIC_ASSETS_PATH}/{filename}"
        picture_url = str(file_path)

    user.profile_picture = picture_url
    user.updated_at = datetime.now(tz=UTC)
    db_session.add(user)
    await db_session.commit()
    return ImageUploadedResponse(
        message="Profile picture updated successfully",
        image_url=user.profile_picture,
    )


@router.delete("/profile", status_code=status.HTTP_200_OK)
async def delete_profile(
    db_session: SessionDep,
    user: User = Depends(get_current_user),
) -> MessageResponse:
    # Delete user profile
    await db_session.exec(delete(User).where(col(User.id) == user.id))
    await db_session.commit()
    return MessageResponse(message="Profile deleted successfully", status="success")


@router.post("/account-report", status_code=status.HTTP_202_ACCEPTED)
async def request_account_info(
    db_session: SessionDep,
    user: User = Depends(get_current_user),
) -> MessageResponse:
    """
    Endpoint to request account info report.
    The report will include user details, assets, and data size.
    It will be sent via email and notification.
    """
    if not user.id or not user.accepted_terms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, TNC_MUST_BE_ACCEPTED)

    account_info_request = AccountInfoRequest(user_id=user.id, reason="User requested account info report")
    db_session.add(account_info_request)
    await db_session.commit()

    # From here, a background task or worker would process this request,
    # generate the report, and send it to the user via email/notification.

    return MessageResponse(
        message="Account info report request received. You will be notified once the report is sent.",
        status="info",
    )
