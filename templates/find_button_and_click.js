document.addEventListener("keydown", function (event) {
    let condition = event.key === "{{pressed_key}}";
    {% if is_ctrl %}
    condition = condition && event.ctrlKey;
    {% elif is_alt %}
    condition = condition && event.altKey;
    {% elif is_ctrl_alt %}
    condition = condition && event.ctrlKey && event.altKey;
    {% endif %}
    if (condition) {
        event.preventDefault();
        const targetButton = document.querySelector("#c{{button_id}}");
        console.log("targetButton: ", targetButton)
        if (targetButton) {
            targetButton.click();
        }
    }
});