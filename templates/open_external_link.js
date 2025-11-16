
// [使用 JavaScript 拦截所有外部链接](https://lxblog.com/qianwen/share?shareId=0d41b4ad-dd1a-499a-ab7a-6b5ad012bd81)
document.addEventListener("click", function (e) {
    let el = e.target;
    while (el && el.tagName !== "A") {
        el = el.parentElement;
    }
    if (el && el.href) {
        e.preventDefault();
        fetch("/open-external-link?url=" + encodeURIComponent(el.href))
            .catch(err => console.error("Failed to open link:", err));
    }
});