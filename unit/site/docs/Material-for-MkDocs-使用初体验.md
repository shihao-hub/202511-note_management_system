[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/getting-started/)


1. pip install mkdocs-material
2. 在 python 项目的命令行中执行 `mkdocs new .`，预期结果：创建 `.\mkdocs.yml` 和 `.\docs\index.md` 文件
3. 完善 mkdocs.yml 文件，推荐内容：

		```yml
		site_name: 心悦卿兮的笔记
		theme: material  # 使用 Material 主题（需先安装）
		
		nav:
		  - 首页: index.md
		  - 安装指南: installation.md
		  - 快速开始: quickstart.md
		```

	其中，site_name 是站点名，theme 是主题需要安装，nav 是左侧导航，内容来自 docs 中的 md 文件

4. mkdocs serve 即可本地运行，默认 8000 端口（mkdocs serve -a localhost:8080 可指定端口号，mkdocs serve -a 0.0.0.0:8080 直接允许外部访问）

题外话：

1. mkdocs build 可以构建一个 site 目录，存放了前端代码，所以这个 mkdocs 实际就是将 markdown 文件转为 html 并配套前端 js 代码实现搜索等功能
2. **关于 site 目录**，其中存放的是生成静态网站，可直接部署到任何 Web 服务器，推荐使用 GitHub Pages 部署
	
	官方插件（无敌了，傻瓜式布局，有必要阅读一下[源代码](https://github.com/mkdocs/mkdocs)了）：

	1. 安装部署插件：pip install mkdocs-git-repository-plugin
	2. 在 mkdocs.yml 中添加：remote_branch: gh-pages
	3. 构建并推送：mkdocs gh-deploy
	
	> 自动将 site/ 内容推送到 GitHub 仓库的 gh-pages 分支，并启用 GitHub Pages
	>
	> 访问地址：https://<用户名>.github.io/<仓库名>/



