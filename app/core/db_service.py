from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import TermsAndConditions


async def get_latest_active_terms(session: AsyncSession) -> TermsAndConditions | None:
    """Retrieve the latest active version of terms and conditions."""
    statement = (
        select(TermsAndConditions)
        .where(
            TermsAndConditions.is_active == True,
        )
        .order_by(col(TermsAndConditions.created_at).desc())
    )
    result = await session.exec(statement)
    return result.first()
