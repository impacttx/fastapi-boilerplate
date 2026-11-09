"""RBAC dependencies for route protection."""

from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.auth.models import User
from app.auth.security import get_current_user, get_optional_current_user
from app.database import SessionDep

from . import db_service
from .schemas import UserRole


def require_roles(*roles: UserRole):
    """Factory: returns a dependency that checks the current user has at least one of the given roles."""

    async def _check(
        current_user: Annotated[User, Depends(get_current_user)],
        session: SessionDep,
    ) -> User:
        # Admins always pass
        if current_user.is_admin:
            return current_user
        if not await db_service.user_has_any_role(session, current_user.id, list(roles)):  # pyright: ignore[reportArgumentType]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _check


# Pre-built role dependencies for common use
async def get_admin_user(
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
) -> User:
    if current_user.is_admin:
        return current_user
    if await db_service.user_has_role(session, current_user.id, UserRole.ADMIN):  # pyright: ignore[reportArgumentType]
        return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


async def get_sales_user(
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
) -> User:
    if current_user.is_admin:
        return current_user
    if await db_service.user_has_any_role(session, current_user.id, [UserRole.SALES, UserRole.ADMIN]):  # pyright: ignore[reportArgumentType]
        return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sales access required")


async def get_ops_user(
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
) -> User:
    if current_user.is_admin:
        return current_user
    if await db_service.user_has_any_role(session, current_user.id, [UserRole.OPERATIONS, UserRole.ADMIN]):  # pyright: ignore[reportArgumentType]
        return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operations access required")


async def get_staff_user(
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
) -> User:
    """Any internal staff: sales, ops, marketing, or admin."""
    if current_user.is_admin:
        return current_user
    if await db_service.user_has_any_role(
        session,
        current_user.id,  # pyright: ignore[reportArgumentType]
        [UserRole.SALES, UserRole.OPERATIONS, UserRole.MARKETING, UserRole.ADMIN],
    ):
        return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff access required")


# Type aliases for use in route signatures
AdminUser = Annotated[User, Depends(get_admin_user)]
SalesUser = Annotated[User, Depends(get_sales_user)]
OpsUser = Annotated[User, Depends(get_ops_user)]
StaffUser = Annotated[User, Depends(get_staff_user)]
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalCurrentUser = Annotated[User | None, Depends(get_optional_current_user)]
