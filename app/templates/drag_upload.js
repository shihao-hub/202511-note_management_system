function uploadFile(files, on_response_ok) {
    console.log(`[uploadFile] ${files}`)

    // 限制单个文件的上传大小（前端限制）
    const maxMbNum = 10
    const maxFileSize = maxMbNum * 1024 * 1024;
    for (const file of files) {
        if (file.size > maxFileSize) {
            alert(`文件大于 ${maxMbNum}MB，无法上传`)
            return
        }
    }

    const urlParams = new URLSearchParams(window.location.search);
    const temporary_uuid = urlParams.get("temporary_uuid");

    // temporary_uuid 是与后端的约定
    if (temporary_uuid === null) {
        console.log("temporary_uuid === null");
        alert(`上传过程中发生错误：temporary_uuid === null`);
        return;
    }

    // 创建 FormData 用于上传
    const formData = new FormData();
    files.forEach(file => formData.append("files", file));

    let url = "/api/upload" + `?temporary_uuid=${temporary_uuid}`;

    // 发送 POST 请求到后端
    fetch(url, {
        method: "POST",
        body: formData
    }).then(response => {
        if (response.ok) {
            on_response_ok();
        } else {
            alert("文件上传失败，response.ok !== true");
        }
    }).catch(error => {
        console.error("上传错误:", error);
        alert(`上传过程中发生错误，原因：${error}`);
    });
}

/**
 * code grave
 */
function build_ws() {
    const ws = new WebSocket("ws://" + window.location.host + "/ws");

    // 等待连接建立完成后再发送消息
    ws.onopen = function () {
        console.log("WebSocket connected successfully");
        ws.send("hello"); // 现在连接已建立，可以安全发送
    };

    // 处理收到的消息
    ws.onmessage = function (event) {
        console.log("Message from server:", event.data);
    };

    // 处理错误
    ws.onerror = function (error) {
        console.error("WebSocket error:", error);
    };

    // 处理连接关闭
    ws.onclose = function (event) {
        console.log("WebSocket closed", event);
    };
}

document.addEventListener("DOMContentLoaded", function () {
    console.log("{{ container_id }}")
    const container = document.querySelector("#{{container_id}}");
    // 阻止默认行为，允许 drop 事件触发（dragover 也得阻止，否则有问题）
    // 实践发现，不止需要阻止默认行为，python 层面的监听器存在缺陷，这种拖拽文件上传我需要考虑通过 js 层实现了
    container.addEventListener("dragover", function (e) {
        console.log("dragover");
        e.preventDefault();
        e.stopPropagation();
    });

    container.addEventListener("drop", function (e) {
        console.log("drop");
        e.preventDefault();
        e.stopPropagation();

        // 获取拖拽的文件
        const files = Array.from(e.dataTransfer.files);
        if (files.length === 0) return;

        uploadFile(files, function () {
            console.log("上传成功");
            // container.dispatchEvent(new CustomEvent("nms_upload_success"));
            container.dispatchEvent(new Event("nms_upload_success"));

            // build_ws();

            // 重新加载页面或更新UI（根据需求调整）
            // location.reload();
        });
    });
});