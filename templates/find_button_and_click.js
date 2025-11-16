document.addEventListener("keydown", function (event) {
    if (event.key === "{{pressed_key}}") {
        event.preventDefault();
        const targetButton = document.querySelector("#c{{button_id}}");
        console.log("targetButton: ", targetButton)
        if (targetButton) {
            targetButton.click();
        }
    }
});