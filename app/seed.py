from datetime import UTC, datetime

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.hashing import hash_content
from app.auth.models import User
from app.core.models import Revision, TermsAndConditions
from app.rbac.models import Role, UserRoleAssignment
from app.settings import settings

ROLES = ["admin", "staff", "user"]


async def seed_roles(session: AsyncSession) -> None:
    for role_name in ROLES:
        statement = select(Role).where(Role.name == role_name)
        existing = (await session.exec(statement)).first()
        if not existing:
            role = Role(name=role_name, description=f"Default {role_name} role")
            session.add(role)
            logger.info(f"Seeded role: {role_name}")
    await session.commit()


async def seed_terms_and_conditions(session: AsyncSession) -> TermsAndConditions:
    statement = select(TermsAndConditions).where(TermsAndConditions.revision == Revision.V1_0.value)
    existing = (await session.exec(statement)).first()
    if existing:
        return existing

    tnc = TermsAndConditions(
        revision=Revision.V1_0.value,
        content="Standard Terms and Conditions for Performance Benchmark API.",
        is_active=True,
    )
    session.add(tnc)
    await session.commit()
    await session.refresh(tnc)
    logger.info("Seeded terms and conditions")
    return tnc


async def seed_super_admin(session: AsyncSession, tnc_revision: str) -> None:
    statement = select(User).where(User.email == settings.ADMIN_EMAIL)
    existing = (await session.exec(statement)).first()
    if existing:
        return

    admin_user = User(
        email=settings.ADMIN_EMAIL,
        mobile_number=settings.ADMIN_MOBILE,
        hashed_password=hash_content(settings.ADMIN_PASSWORD.get_secret_value()),
        first_name="Admin",
        last_name="User",
        is_active=True,
        is_admin=True,
        accepted_terms={tnc_revision: datetime.now(tz=UTC)},
    )
    session.add(admin_user)
    await session.commit()
    await session.refresh(admin_user)

    admin_role = (await session.exec(select(Role).where(Role.name == "admin"))).first()
    if admin_role:
        assignment = UserRoleAssignment(user_id=admin_user.id, role_id=admin_role.id)
        session.add(assignment)
        await session.commit()

    logger.info(f"Seeded admin user: {settings.ADMIN_EMAIL}")
