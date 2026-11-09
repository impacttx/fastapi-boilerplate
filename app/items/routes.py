import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import col, func, select

from app.database import SessionDep

from .models import Item
from .schemas import ItemCreate, ItemRead, ItemUpdate

router = APIRouter(prefix="/items", tags=["Items CRUD"])


@router.post("/", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(payload: ItemCreate, session: SessionDep) -> Item:
    """Create a new item in the database."""
    item = Item(
        title=payload.title,
        description=payload.description,
        is_completed=payload.is_completed,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/", response_model=list[ItemRead])
async def list_items(
    session: SessionDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> list[Item]:
    """List items with pagination for benchmarking read throughput."""
    stmt = select(Item).order_by(col(Item.created_at).desc()).offset(skip).limit(limit)
    result = await session.exec(stmt)
    return list(result.all())


@router.get("/count")
async def count_items(session: SessionDep) -> dict[str, int]:
    """Count total items in database."""
    stmt = select(func.count(col(Item.id)))
    result = await session.exec(stmt)
    count = result.one() or 0
    return {"total": count}


@router.get("/{item_id}", response_model=ItemRead)
async def get_item(item_id: uuid.UUID, session: SessionDep) -> Item:
    """Fetch an item by its unique ID."""
    item = await session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


@router.put("/{item_id}", response_model=ItemRead)
async def update_item(item_id: uuid.UUID, payload: ItemUpdate, session: SessionDep) -> Item:
    """Update an item by ID."""
    item = await session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    if payload.title is not None:
        item.title = payload.title
    if payload.description is not None:
        item.description = payload.description
    if payload.is_completed is not None:
        item.is_completed = payload.is_completed

    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: uuid.UUID, session: SessionDep):
    """Delete an item by ID."""
    item = await session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    await session.delete(item)
    await session.commit()
