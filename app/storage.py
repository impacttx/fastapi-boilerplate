from pathlib import Path

import aiofiles

from app.settings import UPLOAD_DIR_ROOT


def get_cdn_url(key: str) -> str:
    return f"/uploads/{key}"


async def put_object(key: str, data: bytes, content_type: str | None = None) -> str:
    path = Path(UPLOAD_DIR_ROOT) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "wb") as f:
        await f.write(data)
    return str(path)


async def delete_object(key: str) -> bool:
    path = Path(UPLOAD_DIR_ROOT) / key
    if path.exists():
        path.unlink()
        return True
    return False


async def list_objects(prefix: str = "uploads/") -> list[str]:
    root = Path(UPLOAD_DIR_ROOT)
    if not root.exists():
        return []
    return [str(p.relative_to(root)) for p in root.glob("**/*") if p.is_file()]
