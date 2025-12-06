import asyncio
import aiosqlite
from nicegui import ui, app


# （init_db 和 fetch_users 保持不变）
async def init_db():
    async with aiosqlite.connect('example.db') as db:
        await db.execute('''
                         CREATE TABLE IF NOT EXISTS users
                         (
                             id
                             INTEGER
                             PRIMARY
                             KEY,
                             name
                             TEXT
                             NOT
                             NULL
                         )
                         ''')
        cursor = await db.execute('SELECT COUNT(*) FROM users')
        count = await cursor.fetchone()
        if count[0] == 0:
            await db.executemany('INSERT INTO users (name) VALUES (?)',
                                 [('Alice',), ('Bob',), ('Charlie',), ('Diana',), ('Eve',)])
        await db.commit()


async def fetch_users():
    await asyncio.sleep(2)  # 模拟慢查询
    users = []
    async with aiosqlite.connect('example.db') as db:
        async with db.execute('SELECT id, name FROM users') as cursor:
            async for row in cursor:
                users.append({'id': row[0], 'name': row[1]})
    return users


@app.on_startup
async def on_startup():
    await init_db()


@ui.page('/')
def main_page():
    # 预估或固定展示区域高度，避免布局跳跃
    user_cards = []  # 存储卡片引用，用于后续更新

    with ui.column().classes('w-full max-w-2xl mx-auto p-4 gap-3'):
        ui.label('User List').classes('text-2xl font-bold')

        # 方案1：如果你知道大概有多少条数据（比如分页固定10条）
        # 这里假设最多显示5个用户
        status_label = ui.label('Loading users...').classes('text-gray-500')
        print("status_label:", status_label)

        # 预先创建占位卡片（骨架屏）
        skeleton_rows = []
        for i in range(5):  # 假设最多5个用户
            with ui.card().classes('w-full p-4 animate-pulse') as card:
                ui.label('').classes('h-6 bg-gray-200 rounded w-3/4')  # 模拟文本占位
            skeleton_rows.append(card)

        # 数据加载完成后，原地更新这些卡片
        async def load_and_update():
            try:
                users = await fetch_users()
                status_label.classes('text-green-600').set_text(f'Loaded {len(users)} users')

                # 更新已有卡片（复用 DOM）
                for i, user in enumerate(users):
                    if i < len(skeleton_rows):
                        card = skeleton_rows[i]
                        # 清空并重绘内容（保持容器不变）
                        card.clear()
                        with card:
                            ui.label(f"ID: {user['id']}, Name: {user['name']}").classes('text-lg')

                # 如果用户数少于占位数，隐藏多余的
                for j in range(len(users), len(skeleton_rows)):
                    skeleton_rows[j].set_visibility(False)

            except Exception as e:
                status_label.classes('text-red-600').set_text(f'Error: {e}')

        # 启动后台加载
        asyncio.create_task(load_and_update())


if __name__ in {'__main__', '__mp_main__'}:
    ui.run(title="Smooth Async Loading with Skeleton")
