from fastapi import HTTPException, status
from httpx2 import AsyncClient
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import User
from app.rbac import db_service
from app.rbac.dependencies import get_admin_user, get_ops_user, get_sales_user, get_staff_user, require_roles
from app.rbac.schemas import UserRole
from app.settings import settings


@pytest.fixture
async def admin_user(session: AsyncSession, test_user: User) -> User:
    test_user.is_admin = True
    session.add(test_user)
    await session.commit()
    await session.refresh(test_user)
    return test_user


# ──────────────────────────────────────────────────────────────────────────
# 1. DB Service CRUD Tests
# ──────────────────────────────────────────────────────────────────────────


async def test_rbac_db_service(session: AsyncSession, test_user: User):
    # Get or create role
    role = await db_service.get_or_create_role(session, UserRole.ADMIN)
    assert role.name == UserRole.ADMIN

    # Assign role
    assign = await db_service.assign_role(session, test_user.id, UserRole.ADMIN)
    await session.commit()
    assert assign.user_id == test_user.id

    # Re-assign same role (idempotent)
    assign2 = await db_service.assign_role(session, test_user.id, UserRole.ADMIN)
    assert assign2.id == assign.id

    # Check role
    assert await db_service.user_has_role(session, test_user.id, UserRole.ADMIN) is True
    assert await db_service.user_has_role(session, test_user.id, UserRole.SALES) is False

    assert await db_service.user_has_any_role(session, test_user.id, [UserRole.ADMIN, UserRole.SALES]) is True
    assert await db_service.user_has_any_role(session, test_user.id, [UserRole.SALES]) is False

    # List user roles
    roles = await db_service.get_user_roles(session, test_user.id)
    assert UserRole.ADMIN in roles

    # Remove role
    removed = await db_service.remove_role(session, test_user.id, UserRole.ADMIN)
    await session.commit()
    assert removed is True
    assert await db_service.user_has_role(session, test_user.id, UserRole.ADMIN) is False

    # Remove non-assigned role
    removed_no = await db_service.remove_role(session, test_user.id, UserRole.ADMIN)
    assert removed_no is False

    # Get all roles
    all_roles = await db_service.get_all_roles(session)
    assert len(all_roles) >= 1

    # Get users with roles
    users_with_roles, total = await db_service.get_users_with_roles(session, search=test_user.email)
    assert total >= 1
    assert any(u.id == test_user.id for u in users_with_roles)


# ──────────────────────────────────────────────────────────────────────────
# 2. Dependencies Tests
# ──────────────────────────────────────────────────────────────────────────


async def test_rbac_dependencies(session: AsyncSession, test_user: User):
    # Non-admin user raises exception
    with pytest.raises(HTTPException) as exc:
        await get_admin_user(test_user, session)
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    # Assigning role lets them pass
    await db_service.assign_role(session, test_user.id, UserRole.ADMIN)
    await session.commit()
    res = await get_admin_user(test_user, session)
    assert res.id == test_user.id

    # Test is_admin flag bypass
    test_user.is_admin = True
    res_bypass = await get_admin_user(test_user, session)
    assert res_bypass.id == test_user.id

    # Test sales, ops, staff dependencies with is_admin
    assert (await get_sales_user(test_user, session)).id == test_user.id
    assert (await get_ops_user(test_user, session)).id == test_user.id
    assert (await get_staff_user(test_user, session)).id == test_user.id

    # Test sales/ops/staff dependencies with roles (non-admin)
    test_user.is_admin = False
    session.add(test_user)
    await db_service.remove_role(session, test_user.id, UserRole.ADMIN)
    await session.commit()

    with pytest.raises(HTTPException):
        await get_sales_user(test_user, session)
    with pytest.raises(HTTPException):
        await get_ops_user(test_user, session)
    with pytest.raises(HTTPException):
        await get_staff_user(test_user, session)

    # Assign sales
    await db_service.assign_role(session, test_user.id, UserRole.SALES)
    await session.commit()
    assert (await get_sales_user(test_user, session)).id == test_user.id
    assert (await get_staff_user(test_user, session)).id == test_user.id

    # Assign ops
    await db_service.remove_role(session, test_user.id, UserRole.SALES)
    await db_service.assign_role(session, test_user.id, UserRole.OPERATIONS)
    await session.commit()
    assert (await get_ops_user(test_user, session)).id == test_user.id
    assert (await get_staff_user(test_user, session)).id == test_user.id

    # Test custom require_roles factory dependency
    check_factory = require_roles(UserRole.SALES)
    with pytest.raises(HTTPException):
        await check_factory(test_user, session)

    await db_service.assign_role(session, test_user.id, UserRole.SALES)
    await session.commit()
    res_factory = await check_factory(test_user, session)
    assert res_factory.id == test_user.id


# ──────────────────────────────────────────────────────────────────────────
# 3. Router Endpoint Tests
# ──────────────────────────────────────────────────────────────────────────


async def test_rbac_admin_routes(
    async_auth_client: AsyncClient, admin_user: User, test_user: User, session: AsyncSession
):
    # List roles
    response = await async_auth_client.get("/admin/rbac/roles/")
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)

    # List users with roles
    response = await async_auth_client.get("/admin/rbac/users/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1

    # List users with search parameter (by UUID or email)
    test_user.email = "testuser@example.com"
    session.add(test_user)
    await session.commit()

    response = await async_auth_client.get(f"/admin/rbac/users/?search={test_user.id}")
    assert response.status_code == status.HTTP_200_OK
    assert any(u["id"] == str(test_user.id) for u in response.json()["items"])

    # Get my roles
    response = await async_auth_client.get("/admin/rbac/me/roles/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["user_id"] == str(admin_user.id)

    # Get roles of test_user
    response = await async_auth_client.get(f"/admin/rbac/users/{test_user.id}/roles/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["user_id"] == str(test_user.id)

    # Update user status (deactivate / activate)
    response = await async_auth_client.post(
        "/admin/rbac/users/status", json={"user_id": str(test_user.id), "is_active": False}
    )
    assert response.status_code == status.HTTP_200_OK

    response = await async_auth_client.post(
        "/admin/rbac/users/status", json={"user_id": str(test_user.id), "is_active": True}
    )
    assert response.status_code == status.HTTP_200_OK

    # Set test_user email to unauthorized domain for staff promotion test
    test_user.email = "unauthorized@externalgmail.com"
    session.add(test_user)
    await session.commit()

    # Assign staff role with unauthorized domain -> 400
    response = await async_auth_client.post(
        "/admin/rbac/assign", json={"user_id": str(test_user.id), "role": UserRole.SALES.value}
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # Set test_user email to allowed domain -> 200
    allowed_domain = settings.ALLOWED_STAFF_EMAIL_DOMAINS[0]
    test_user.email = f"user@{allowed_domain}"
    session.add(test_user)
    await session.commit()

    # Assign role
    response = await async_auth_client.post(
        "/admin/rbac/assign", json={"user_id": str(test_user.id), "role": UserRole.SALES.value}
    )
    assert response.status_code == status.HTTP_200_OK, response.json()

    # Remove role
    response = await async_auth_client.post(
        "/admin/rbac/remove", json={"user_id": str(test_user.id), "role": UserRole.SALES.value}
    )
    assert response.status_code == status.HTTP_200_OK

    # Remove non-existent assignment -> 404
    response = await async_auth_client.post(
        "/admin/rbac/remove", json={"user_id": str(test_user.id), "role": UserRole.SALES.value}
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
