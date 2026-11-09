import pytest

from app.storage import delete_object, get_cdn_url, put_object


@pytest.mark.asyncio
async def test_local_storage():
    url = get_cdn_url("test.png")
    assert url == "/uploads/test.png"

    path = await put_object("test.txt", b"Hello Benchmarking!")
    assert "test.txt" in path

    deleted = await delete_object("test.txt")
    assert deleted is True
