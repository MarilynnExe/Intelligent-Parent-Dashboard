/* Shared accessible editor for administrative changes and teacher corrections. */
window.RecordEditor = {
    open({title, fields, values, onSave}) {
        document.getElementById("record-editor")?.remove();
        const previousFocus = document.activeElement;
        const backdrop = document.createElement("div");
        backdrop.id = "record-editor";
        backdrop.className = "record-editor-backdrop";
        backdrop.innerHTML = `<section class="record-editor-card" role="dialog" aria-modal="true" aria-labelledby="record-editor-title">
            <h2 id="record-editor-title">${escapeHtml(title)}</h2><form id="record-editor-form">
            <div id="record-editor-fields"></div><p id="record-editor-error" role="alert"></p>
            <div class="record-editor-actions"><button type="button" id="record-editor-cancel" class="btn">Cancel</button>
            <button type="submit" id="record-editor-save" class="btn btn-primary">Save changes</button></div></form></section>`;
        const close = () => {document.removeEventListener("keydown", onKey); backdrop.remove(); previousFocus?.focus();};
        const onKey = event => {
            if (event.key === "Escape" && !backdrop.querySelector("#record-editor-save").disabled) close();
            if (event.key === "Tab") {
                const controls = [...backdrop.querySelectorAll("input, select, textarea, button")].filter(el => !el.disabled);
                if (event.shiftKey && document.activeElement === controls[0]) {event.preventDefault(); controls.at(-1).focus();}
                else if (!event.shiftKey && document.activeElement === controls.at(-1)) {event.preventDefault(); controls[0].focus();}
            }
        };
        document.addEventListener("keydown", onKey);
        document.body.appendChild(backdrop);
        const container = backdrop.querySelector("#record-editor-fields");
        fields.forEach(field => {
            const label = document.createElement("label");
            label.textContent = field.label;
            const input = document.createElement(field.options ? "select" : field.type === "textarea" ? "textarea" : "input");
            input.name = field.name;
            input.id = `edit-${field.name}`;
            if (input.tagName === "INPUT") input.type = field.type || "text";
            input.required = field.required !== false;
            if (field.maxLength) input.maxLength = field.maxLength;
            if (field.min !== undefined) input.min = field.min;
            if (field.max !== undefined) input.max = field.max;
            if (field.type === "number") input.step = "any";
            if (field.options) field.options.forEach(option => {
                const node = document.createElement("option");
                node.value = typeof option === "object" ? option.value : option;
                node.textContent = typeof option === "object" ? option.label : option;
                input.appendChild(node);
            });
            input.value = values[field.name] ?? "";
            label.appendChild(input);
            container.appendChild(label);
        });
        backdrop.querySelector("#record-editor-cancel").onclick = close;
        backdrop.querySelector("form").onsubmit = async event => {
            event.preventDefault();
            const button = backdrop.querySelector("#record-editor-save");
            const cancel = backdrop.querySelector("#record-editor-cancel");
            button.disabled = cancel.disabled = true;
            const result = Object.fromEntries(new FormData(event.target));
            fields.filter(f => f.type === "number").forEach(f => {result[f.name] = Number(result[f.name]);});
            try {await onSave(result); close();}
            catch (error) {backdrop.querySelector("#record-editor-error").textContent = error.message;}
            finally {button.disabled = cancel.disabled = false;}
        };
        backdrop.querySelector("input, select, textarea")?.focus();
    },
    async request(path, method, payload) {
        const response = await apiFetch(path, {method, ...(payload === undefined ? {} : {body: JSON.stringify(payload)})});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(Array.isArray(data.detail) ? data.detail.map(e => e.msg).join("; ") : data.detail || "Could not save changes.");
        return data;
    }
};
