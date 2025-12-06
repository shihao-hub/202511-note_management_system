function test() {
    console.log("test test");
}

// todo:
//      1. 将一个 page 中的 js 代码卸载一个 js 文件中
//      2. 优化报错弹出，不要只用 alert，太丑了
//      3. 了解如何不通过 npm 使用 vue（目的就是在 html 中嵌入式使用），如果可以做到，需要搞个 vue 插件进行语法分析
//      4. 削弱对 js 的抵触心理

// todo: 我认为，templates 只传 id 进来是毫无意义的，不如 js 层自己找呢...


// [question] 这个 document 添加的事件是全局的吗？
(function () {
    const saveBtnId = "{{save_btn_id}}"

    document.addEventListener("keydown", function (e) {
        console.log(e)
        // ctrl+s 搜索保存按钮并点击
        if ((e.ctrlKey || e.metaKey) && e.key === "s") {
            console.log("ctrl+s pressed")
            e.preventDefault();

            // document.body 触发的事件不知道为什么 ui.on 监听不到...
            // document.body.dispatchEvent(new CustomEvent("nms_ctrl_s_pressed"));

            const saveBtn = document.getElementById(saveBtnId);
            if (saveBtn !== null) {
                saveBtn.click();
            }
        }



    });

})()


document.addEventListener("DOMContentLoaded", function () {
    const contentId = "{{content_id}}";
    const content = document.getElementById(contentId);

    content.addEventListener("paste", async (e) => {
        console.log(`${contentId}: paste event`);
        const items = e.clipboardData?.items;

        if (!items) {
            return;
        }

        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            if (item.kind === "file") {
                const file = item.getAsFile();
                console.log("粘贴的文件：", file.name, file.type, file.size);
                uploadFile([file], function () {
                    content.dispatchEvent(new Event("nms_upload_success"));
                })
            }
        }
    });


    document.addEventListener("keydown", function (e) {
        // tab 自动缩进
        if (e.key === "Tab" && e.target.tagName === "TEXTAREA") {
            e.preventDefault();
            // 获得选中文本的起始位置/索引（包含）和结束位置/索引（不包含）
            const start = e.target.selectionStart;
            const end = e.target.selectionEnd;
            // 直接字符串拼接可能存在问题，可参考的优化方案：https://lxblog.com/qianwen/share?shareId=5d0b27c3-e599-48df-9663-09659f8488b6
            const value = e.target.value;
            // e.target.value = value.substring(0, start) + "\t" + value.substring(end);
            // e.target.selectionStart = e.target.selectionEnd = start + 1;
            // 切割 [start, end] 之间的文本，并按照 \n 切割，新行开头加 \t
            const selectedText = value.substring(start, end);
            const lines = selectedText.split("\n");
            // todo: 快速学习一下 javascript 的基础语法和 api 如何？看样子还是应该学学 javascript...
            const indentedText = lines.map(line => "\t" + line).join("\n");
            e.target.value = value.substring(0, start) + indentedText + value.substring(end);

            // 移动光标到缩进后的位置
            e.target.selectionStart = e.target.selectionEnd = start + indentedText.length;

            // todo: 希望这边的修改能够通知 textarea 的 ctrl+z 撤回实践？还是说 quasar 实现的呢？
        }

        // ctrl+end 滚动到 textarea 末尾
        // generate by ai: https://lxblog.com/qianwen/share?shareId=1f1ee862-4ed8-410b-9122-636c462c35a8
        if (e.ctrlKey && e.key === "End" && e.target.tagName === "TEXTAREA") {
            e.preventDefault();
            // 将光标移到整个文本末尾
            const el = e.target;
            const len = el.value.length;
            el.setSelectionRange(len, len);
            // 滚动到底部
            setTimeout(() => {
                el.scrollTop = el.scrollHeight;
            }, 0);
        }

        // end 滚动到当前行末尾
        // generate by ai: https://lxblog.com/qianwen/share?shareId=1da264dc-c797-4c27-8d17-6159dc4bb0c4
        if (e.key === "End" && e.target.tagName === "TEXTAREA") {
            e.preventDefault();
            const el = e.target;
            const value = el.value;
            // 获得当前光标位置
            const cursorPos = el.selectionStart;
            // 找到当前行的结束位置（从 cursorPos 向后找第一个 \n）
            const lineEnd = value.indexOf("\n", cursorPos);
            // 没找到 \n 则直达末尾
            const endPos = lineEnd === -1 ? value.length : lineEnd;
            // 设置光标到当前行末尾
            el.setSelectionRange(endPos, endPos);
        }

    });
})

