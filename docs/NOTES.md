# 笔记管理系统（小桌面应用）

## git 版本管理

> 有什么 git 命令需求问 ai 即可，如：
> 
> git 忽略形如：notes.db.bak.1、笔记管理系统v1.1.2.spec 的文件如何做？
> 
> `notes.db.bak.*、*.spec`

1. 在 Git 中移除一个已经提交（committed）的文件，但又不想删除本地文件（仅从版本控制中移除）
   
   `git rm --cached <文件名>`

2. 






## 开发笔记

2025-11-10 晚，基本上已完成（消耗的时间依旧是前端，但是不得不说，多练习项目确实很有用，加油）

2025-11-14 晚，又完善了几天，几乎快完成了，就剩下附件图片渲染了，有些感想（个人感想）：
1. python nicegui 似乎更适合常规 web 应用即浏览器打开而非桌面 web 应用（主要是启动速度方面）
2. python pyinstaller 单应用启动太慢了（应该是因为需要解压文件到临时目录）
3. 实践发现，确实不能打包成单应用，打包成文件夹的话启动速度没那么慢（但是也没有快多少，快了 1/3 ~ 1/2 左右）
4. `v1.1.1` 版本差不多已经可用了，我也没有多少耐心了，几乎到此为止吧。其实还缺少导入导出功能，因为用 sqlite 作为文件系统的。

> 到此为止，前去学 golang 吧，未来需要做的事情如下：
> 1. 整理整个项目的 todo、note、question、step 等注释，并记成笔记
> 2. 在下面记录还需要优化的方向
> 3. ...

优化项：
1. 

#### 数据库存储时区

使用 SQLAlchemy-Utc 库：`from sqlalchemy_utc import UtcDateTime, utcnow`

#### nicegui-pack 打包

dev lib: pyinstaller pillow pywebview

```bash
nicegui-pack --onefile --windowed --icon "icon.png" --name "笔记管理系统v1.0.0" main.py

nicegui-pack --windowed --icon "icon.png" --name "笔记管理系统v1.1.2" main.py
```

#### nicegui 实现拖拽上传

最初就是问通义，它告诉我 dragover、dragleave、drop 事件，
但是 python 层面的监听器回调没办法执行 preventDefault 和 stopPropagation。

为此选择添加 js 代码，以阻止默认行为，允许 drop 事件触发。

可是与此同时，还需要通过 ui.timer 延迟注册 python 层面的回调，保证 js 层的回调在 python 层之前执行。

到此，由于拖拽上传文件通过 js 层获取到，还需要添加 js 层代码以调用后端定义的上传文件接口。

最后，文件上传得以实现，但是由于上传是通过 http，python 层修改元素以响应用户存在难点。

起初，考虑 python 层监听自定义事件，但是可能代码有问题，以为不生效。后面研究了 fastapi 的 websocket 技术，
可是这也类似 http，可行性不太好，最终发现，监听自定义事件是可行的！（实在不行我就通过触发原有事件并获取 e.args 的 isTrusted 来模拟了）

## 项目开发流程简述

作为后端程序员，在前端设计与开发方面较为薄弱，故而对于小桌面应用，我选择 nicegui 框架来进行开发前端部分，后端选择 fastapi 框架（nicegui 框架本就基于 fastapi、vue、websocket 等技术）。

关于前端设计方面，我选择将我的初版设计文档交予[扣子](https://space.coze.cn)的设计技能，由其进行设计。主要生成了 html 页面，我将其转换为 nicegui 框架的页面以锻炼自己的前端开发能力。

关于后端开发，我选择边开发边学习，主要是 fastapi、sqlalchemy 和原始 sql 语句，测试阶段使用 sqlite 数据库，正式部署时切换到 postgresql 数据库（链接失败则切换到 sqlite 数据库）。

该项目起源于个人的小需求，但是也是想多做项目锻炼自己，包括但不限于下列能力：
- 前后端开发能力、数据库设计与管理能力、项目部署与维护能力
- ai 工具的使用能力，如将设计工作交给 ai 工作，ai 辅助开发等

## 目录结构

``txt

.gitignore
.python-version
pyproject.toml
README.md

migrations
alembic.ini
models.py
schemas.py
services.py
filters.py

apps
api.py
dependencies.py
middlewares.py

settings.py
utils.py

main.py

``