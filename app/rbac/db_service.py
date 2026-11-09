"""RBAC database operations."""

from collections.abc import Sequence
import uuid

from sqlalchemy import String, cast, func, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import Role, UserRoleAssignment
from .schemas import UserRole, UserWithRolesResponse


async def get_or_create_role(session: AsyncSession, role_name: UserRole) -> Role:
    result = await session.exec(select(Role).where(Role.name == role_name))
    if role := result.first():
        return role
    role = Role(name=role_name, description=f"{role_name.value} role")
    session.add(role)
    await session.flush()
    return role


async def assign_role(
    session: AsyncSession,
    user_id: uuid.UUID,
    role_name: UserRole,
    assigned_by: uuid.UUID | None = None,
) -> UserRoleAssignment:
    role = await get_or_create_role(session, role_name)
    # Check if already assigned
    result = await session.exec(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user_id,
            UserRoleAssignment.role_id == role.id,
        )
    )
    if existing := result.first():
        return existing
    assignment = UserRoleAssignment(user_id=user_id, role_id=role.id, assigned_by=assigned_by)
    session.add(assignment)
    await session.flush()
    return assignment


async def remove_role(session: AsyncSession, user_id: uuid.UUID, role_name: UserRole) -> bool:
    role = await get_or_create_role(session, role_name)
    result = await session.exec(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user_id,
            UserRoleAssignment.role_id == role.id,
        )
    )
    if assignment := result.first():
        await session.delete(assignment)
        await session.flush()
        return True
    return False


async def get_user_roles(session: AsyncSession, user_id: uuid.UUID) -> list[UserRole]:
    result = await session.exec(
        select(Role.name)
        .join(UserRoleAssignment, col(UserRoleAssignment.role_id) == Role.id)
        .where(UserRoleAssignment.user_id == user_id)
    )
    return [UserRole(r) for r in result.all()]


async def user_has_role(session: AsyncSession, user_id: uuid.UUID, role_name: UserRole) -> bool:
    roles = await get_user_roles(session, user_id)
    return role_name in roles


async def user_has_any_role(session: AsyncSession, user_id: uuid.UUID, role_names: list[UserRole]) -> bool:
    roles = await get_user_roles(session, user_id)
    return any(r in role_names for r in roles)


async def get_all_roles(session: AsyncSession) -> Sequence[Role]:
    result = await session.exec(select(Role).order_by(Role.name))
    return result.all()


async def get_users_with_roles(
    session: AsyncSession,
    search: str | None = None,
    role_filter: UserRole | None = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[UserWithRolesResponse], int]:

    from app.auth.models import User

    stmt = select(User)

    if role_filter:
        stmt = (
            stmt.join(UserRoleAssignment, col(UserRoleAssignment.user_id) == User.id)
            .join(Role, col(UserRoleAssignment.role_id) == Role.id)
            .where(Role.name == role_filter)
        )

    if search:
        search_pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                col(User.first_name).ilike(search_pattern),
                col(User.last_name).ilike(search_pattern),
                col(User.email).ilike(search_pattern),
                col(User.mobile_number).ilike(search_pattern),
                cast(col(User.id), String).ilike(search_pattern),
            )
        )

    # Get total count
    subq = stmt.subquery()
    count_stmt = select(func.count()).select_from(subq)
    total_res = await session.exec(count_stmt)
    total = total_res.first() or 0

    # Get paginated users
    stmt = stmt.distinct().order_by(col(User.created_at).desc()).offset(skip).limit(limit)
    res = await session.exec(stmt)
    users = res.all()

    # Build response items with roles
    items: list[UserWithRolesResponse] = []
    for u in users:
        roles = await get_user_roles(session, u.id)
        items.append(
            UserWithRolesResponse(
                id=u.id,
                email=u.email,
                mobile_number=u.mobile_number,
                first_name=u.first_name,
                last_name=u.last_name,
                profile_picture=u.profile_picture,
                is_active=u.is_active,
                is_admin=u.is_admin,
                created_at=u.created_at,
                roles=roles,
            )
        )

    return items, total


async def update_user_status(session: AsyncSession, user_id: uuid.UUID, is_active: bool) -> bool:
    from app.auth.models import User

    result = await session.exec(select(User).where(User.id == user_id))
    if user := result.first():
        user.is_active = is_active
        session.add(user)
        await session.flush()
        return True
    return False
