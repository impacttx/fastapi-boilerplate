"""RBAC management routes (admin only)."""

from fastapi import APIRouter, HTTPException, status

from app.core.schemas import MessageResponse
from app.database import SessionDep
from app.settings import settings

from . import db_service
from .dependencies import AdminUser, CurrentUser
from .schemas import (
    AssignRoleRequest,
    RemoveRoleRequest,
    RoleResponse,
    UpdateUserStatusRequest,
    UserListWithRolesResponse,
    UserRole,
    UserRolesResponse,
)

router = APIRouter(prefix="/admin/rbac", tags=["Admin & Reporting -- RBAC"])


@router.get("/roles/", response_model=list[RoleResponse])
async def list_roles(current_user: AdminUser, session: SessionDep):
    """List all defined roles (admin only)."""
    return await db_service.get_all_roles(session)


@router.get("/users/", response_model=UserListWithRolesResponse)
async def list_users_with_roles(
    current_user: AdminUser,
    session: SessionDep,
    search: str | None = None,
    role: UserRole | None = None,
    skip: int = 0,
    limit: int = 100,
):
    """List all users with their assigned roles (admin only)."""
    items, total = await db_service.get_users_with_roles(
        session, search=search, role_filter=role, skip=skip, limit=limit
    )
    return UserListWithRolesResponse(items=items, total=total)


@router.get("/users/{user_id}/roles/", response_model=UserRolesResponse)
async def get_user_roles(user_id: str, current_user: AdminUser, session: SessionDep):
    """Get roles for a specific user (admin only)."""
    from uuid import UUID

    uid = UUID(user_id)
    roles = await db_service.get_user_roles(session, uid)
    return UserRolesResponse(user_id=uid, roles=roles)


@router.get("/me/roles/", response_model=UserRolesResponse)
async def get_my_roles(current_user: CurrentUser, session: SessionDep):
    """Get the current user's roles."""
    roles = await db_service.get_user_roles(session, current_user.id)  # pyright: ignore[reportArgumentType]
    return UserRolesResponse(user_id=current_user.id, roles=roles)  # pyright: ignore[reportArgumentType]


@router.post("/assign", response_model=MessageResponse)
async def assign_role(payload: AssignRoleRequest, current_user: AdminUser, session: SessionDep):
    """Assign a role to a user (admin only). Restricts staff roles to authorized email domains."""
    from sqlmodel import select

    from app.auth.models import User

    # Validate staff email domain restriction for staff/admin roles
    if payload.role != UserRole.CUSTOMER:
        result = await session.exec(select(User).where(User.id == payload.user_id))
        target_user = result.first()
        if not target_user or not target_user.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User must have a registered email address to be assigned a staff/admin role.",
            )

        email_domain = target_user.email.split("@")[-1].lower() if "@" in target_user.email else ""
        allowed_domains = [d.lower() for d in settings.ALLOWED_STAFF_EMAIL_DOMAINS]

        if email_domain not in allowed_domains:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Email domain '@{email_domain}' is not authorized for staff/admin roles. "
                    f"Allowed staff domains: {', '.join(settings.ALLOWED_STAFF_EMAIL_DOMAINS)}"
                ),
            )

    await db_service.assign_role(session, payload.user_id, payload.role, assigned_by=current_user.id)
    await session.commit()
    return MessageResponse(message=f"Role '{payload.role.value}' assigned successfully", status="success")


@router.post("/remove", response_model=MessageResponse)
async def remove_role(payload: RemoveRoleRequest, current_user: AdminUser, session: SessionDep):
    """Remove a role from a user (admin only)."""
    removed = await db_service.remove_role(session, payload.user_id, payload.role)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role assignment not found")
    await session.commit()
    return MessageResponse(message=f"Role '{payload.role.value}' removed successfully", status="success")


@router.post("/users/status", response_model=MessageResponse)
async def update_user_status(payload: UpdateUserStatusRequest, current_user: AdminUser, session: SessionDep):
    """Activate or deactivate a user account (admin only)."""
    updated = await db_service.update_user_status(session, payload.user_id, payload.is_active)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await session.commit()
    status_str = "activated" if payload.is_active else "deactivated"
    return MessageResponse(message=f"User account {status_str} successfully", status="success")
