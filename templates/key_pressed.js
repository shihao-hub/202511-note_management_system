function test() {
    console.log("test test");
}


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
})

