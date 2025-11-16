function test() {
    console.log("test test");
}

// todo:
//      1. 将一个 page 中的 js 代码卸载一个 js 文件中
//      2. 优化报错弹出，不要只用 alert，太丑了
//      3. 了解如何不通过 npm 使用 vue（目的就是在 html 中嵌入式使用），如果可以做到，需要搞个 vue 插件进行语法分析
//      4. 削弱对 js 的抵触心理


document.addEventListener("keydown", function (e) {
    if (!(e.ctrlKey || e.metaKey)) {
        return;
    }


    if (e.key === "s") {
        // 阻止浏览器默认保存行为
        e.preventDefault();

        // document.body 触发的事件不知道为什么 ui.on 监听不到...
        // document.body.dispatchEvent(new CustomEvent("nms_ctrl_s_pressed"));

        const save_btn = document.getElementById("c{{save_btn_id}}");
        if (save_btn !== null) {
            save_btn.click();
        }
    } else if (e.key === "v") {
        // [2025-11-14] 绷不住，这个阻止了默认事件，导致 paste 事件也就不存在了...
        // e.preventDefault();
        // todo: 捕获到剪切板复制的文件，然后上传
    }
});


document.addEventListener("DOMContentLoaded", function () {
    const container = document.getElementById("c{{content_id}}");
    container.addEventListener('paste', async (e) => {
        console.log("paste!");
        const items = e.clipboardData?.items;

        if (!items) return;

        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            if (item.kind === 'file') {
                const file = item.getAsFile();
                console.log('粘贴的文件:', file.name, file.type, file.size);
                // 你可以在这里上传、预览等
                uploadFile([file], function () {
                    container.dispatchEvent(new Event("nms_upload_success"));
                })
            }
        }
    });

    document.addEventListener('keydown', function (e) {

        if (e.key === 'Tab' && e.target.tagName === 'TEXTAREA') {

            e.preventDefault();

            const start = e.target.selectionStart;

            const end = e.target.selectionEnd;

            const value = e.target.value;

            // todo: templates 相关 js 要标识清楚在哪里被引用吧，不然找不到


            // todo: 这么暴力吗？直接字符串拼接
            // [参考优化方案](https://lxblog.com/qianwen/share?shareId=5d0b27c3-e599-48df-9663-09659f8488b6)
            e.target.value = value.substring(0, start) + '\t' + value.substring(end);

            e.target.selectionStart = e.target.selectionEnd = start + 1;

        }

    });
})

