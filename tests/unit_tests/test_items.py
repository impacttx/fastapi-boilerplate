from httpx2 import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_items_crud_lifecycle(async_client: AsyncClient):
    # 1. Create item
    payload = {
        "title": "Benchmark Test Item",
        "description": "Evaluating FastAPI throughput and latency",
        "is_completed": False,
    }
    create_res = await async_client.post("/items/", json=payload)
    assert create_res.status_code == 201
    item = create_res.json()
    item_id = item["id"]
    assert item["title"] == payload["title"]
    assert item["description"] == payload["description"]
    assert item["is_completed"] is False

    # 2. Get item by ID
    get_res = await async_client.get(f"/items/{item_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == item_id

    # 3. List items
    list_res = await async_client.get("/items/?skip=0&limit=10")
    assert list_res.status_code == 200
    items = list_res.json()
    assert isinstance(items, list)
    assert any(i["id"] == item_id for i in items)

    # 4. Update item
    update_res = await async_client.put(
        f"/items/{item_id}",
        json={"title": "Updated Benchmark Item", "is_completed": True},
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["title"] == "Updated Benchmark Item"
    assert updated["is_completed"] is True

    # 5. Delete item
    del_res = await async_client.delete(f"/items/{item_id}")
    assert del_res.status_code == 204

    # 6. Verify 404
    missing_res = await async_client.get(f"/items/{item_id}")
    assert missing_res.status_code == 404
