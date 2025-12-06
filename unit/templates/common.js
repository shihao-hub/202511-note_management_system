// templates js 能否不局限于 template？能不能视为原生 js？
// 之所以有 template js，是因为需要从 python 层传递 id 过来，但是 js 层本就可以直接找到那个元素呀？
// todo: js 如何定位到指定元素

// template js 就为了传递 id 进来，真的应该放在 templates 目录下吗？
// 以及如何从文件组织中看出来某个 template js 是给哪个页面用的啊？毕竟 ide 跳转失效了。
// 关于文件组织，是否可以参看 django 的 templates 呢？root templates 和 app templates
// jinji2 的 env 也需要思考一下，多次定义是否存在问题

// 总而言之，
// nicegui ui.x 基础组件搭建骨架
// tailwind css 初步美化页面
// quasar 进一步美化页面
// nicegui 其他功能，如 on_click、on、Event 等将满足 80% 的场景
// templates js 实现更复杂的逻辑，且要考虑和 python 层解构，做到 js 变化，整个项目不需要重新打包即可使用
// templates html 单文件本就可以做到 ui.page 的功能，它自然也能派上用场，如语音录入、语音上传等
// 按照上述操作，我认为能实现日常 95% 的场景（对我而言而已）
