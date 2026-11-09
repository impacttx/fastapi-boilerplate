from httpx2 import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    response = await async_client.get("http://testserver/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["framework"] == "FastAPI"


@pytest.mark.asyncio
async def test_root_check(async_client: AsyncClient):
    response = await async_client.get("http://testserver/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "fastapi-performance-containerization"
