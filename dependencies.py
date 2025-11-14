from typing import AsyncGenerator, Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from models import AsyncSessionLocal

# region - template

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """依赖项：提供异步数据库会话

    使用方式：
    - 在路由函数中：db: AsyncSession = Depends(get_db)

    """
    db = AsyncSessionLocal()
    try:
        yield db
    finally:
        await db.close()


DBSession = Annotated[AsyncSession, Depends(get_db)]
"""类型别名（提高可读性）

示例路由：
@app.post("/users/", response_model=User)
async def create_user(user: User, db: DBSession):
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

"""

# endregion
