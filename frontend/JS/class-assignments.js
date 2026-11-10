/* Class work completion; scored assessments and predictive inputs stay separate. */
(() => {
    const labels = {PENDING:"Pending", MISSING:"Missing", SUBMITTED:"Submitted on time", LATE:"Submitted late", EXCUSED:"Excused", WITHDRAWN:"Withdrawn"};
    const badge = status => `<span class="work-status work-${status.toLowerCase()}">${labels[status] || escapeHtml(status)}</span>`;
    window.AssignmentParent = {
        error(message = "Assignments could not be loaded. Use Refresh progress to retry.") {
            document.getElementById("parent-assignment-list").textContent = message;
            document.getElementById("assignment-guidance").replaceChildren();
            document.getElementById("assignment-completion-rate").textContent = "—";
            document.getElementById("assignment-counts").replaceChildren();
            document.getElementById("assignment-asof").textContent = "";
        },
        render(data) {
            document.getElementById("assignment-asof").textContent = `${data.term} ${data.academic_year} · As of ${data.as_of} (Africa/Nairobi)`;
            document.getElementById("assignment-completion-rate").textContent = data.completion_rate === null
                ? "No assignments due" : `${data.completion_rate.toFixed(1)}% · ${data.completed_due_count}/${data.due_count} completed`;
            document.getElementById("assignment-counts").innerHTML = Object.entries(data.counts).map(([key, value]) => `<div class="work-count">${badge(key)}<strong>${value}</strong></div>`).join("");
            document.getElementById("assignment-guidance").innerHTML = data.guidance.map(rule => `<p class="work-guidance">${escapeHtml(rule.text)}</p>`).join("");
            document.getElementById("parent-assignment-list").innerHTML = data.assignments.length ? data.assignments.map(item => {
                const assignment = item.assignment;
                return `<article class="work-card"><header><h3>${escapeHtml(assignment.title)}</h3>${badge(item.display_status)}</header>
                    <p>${escapeHtml(assignment.subject_name)} · Assigned ${assignment.assigned_date} · Due ${assignment.due_date}</p>
                    <p class="work-instructions">${escapeHtml(assignment.instructions)}</p>
                    ${item.submitted_on ? `<p>Submitted: ${item.submitted_on}</p>` : ""}
                    ${item.reason ? `<p><strong>${item.display_status === "LATE" ? "Late reason" : "Teacher note"}:</strong> ${escapeHtml(item.reason)}</p>` : ""}</article>`;
            }).join("") : '<p class="state-box">No assignments recorded for this learner and period.</p>';
        }
    };

    document.addEventListener("DOMContentLoaded", () => {
        const form = document.getElementById("class-assignment-form");
        if (!form) return;
        let context = null, assignments = [], register = null, listRequest = 0, registerRequest = 0;
        const status = document.getElementById("work-teacher-status");
        const list = document.getElementById("teacher-assignment-list");
        const request = (path, method = "GET", body) => RecordEditor.request(path, method, body);
        const endpoint = id => `/teacher/class-assignments/${id}`;
        const field = (name, label, extra = {}) => ({name, label, ...extra});
        const detailsFields = [field("title", "Title", {maxLength:150}), field("instructions", "Instructions", {type:"textarea",required:false,maxLength:4000}),
            field("assigned_date", "Assigned date", {type:"date"}), field("due_date", "Due date", {type:"date"})];
        function busyForm(busy) {form.querySelector("button[type=submit]").disabled = busy || !context;}
        function closeRegister() {
            ++registerRequest;
            register = null;
            document.getElementById("assignment-register-panel").hidden = true;
        }
        function setStatus(message) {status.textContent = message;}
        async function loadList() {
            if (!context) return;
            const ticket = ++listRequest;
            closeRegister();
            list.textContent = "Loading assignments…";
            try {
                const query = new URLSearchParams({...context, include_withdrawn:document.getElementById("work-include-withdrawn").checked});
                const data = await request(`/teacher/class-assignments?${query}`);
                if (ticket !== listRequest) return;
                assignments = data;
                list.innerHTML = data.length ? data.map(a => `<article class="work-card" data-work-id="${a.assignment_id}">
                    <header><h3>${escapeHtml(a.title)}</h3>${a.is_withdrawn ? badge("WITHDRAWN") : ""}</header>
                    <p>${escapeHtml(a.subject_name)} · Assigned ${a.assigned_date} · Due ${a.due_date}</p>
                    <p class="work-instructions">${escapeHtml(a.instructions)}</p><div class="record-actions">
                    <button data-work-action="register" data-id="${a.assignment_id}">Completion register</button>
                    ${a.is_withdrawn ? "" : `<button data-work-action="edit" data-id="${a.assignment_id}">Edit</button>`}
                    <button data-work-action="status" data-id="${a.assignment_id}">${a.is_withdrawn ? "Restore" : "Withdraw"}</button>
                    <button data-work-action="notify" data-id="${a.assignment_id}">Retry follow-up alerts</button></div></article>`).join("")
                    : '<p class="state-box">No assignments for this class, subject and period. Create one above.</p>';
            } catch (error) {if (ticket === listRequest) {list.textContent = error.message; setStatus("Could not load assignments. Use Refresh assignments to retry.");}}
        }
        document.addEventListener("teacher-context-change", event => {
            context = {...event.detail};
            ++listRequest;
            document.getElementById("work-class-context").textContent = `${context.grade_level} / ${context.stream} · ${context.subject_name} · ${context.term} ${context.academic_year}`;
            const now = new Intl.DateTimeFormat("en-CA", {timeZone:"Africa/Nairobi",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
            const starts = {"Term 1":"01-01", "Term 2":"05-01", "Term 3":"09-01"};
            const month = Number(now.slice(5,7));
            const nowTerm = month <= 4 ? "Term 1" : month <= 8 ? "Term 2" : "Term 3";
            const date = now.slice(0,4) === context.academic_year && nowTerm === context.term ? now : `${context.academic_year}-${starts[context.term]}`;
            document.getElementById("work-assigned-date").value = date;
            document.getElementById("work-due-date").value = date;
            busyForm(false);
            loadList();
        });
        document.getElementById("work-refresh").onclick = loadList;
        document.getElementById("work-include-withdrawn").onchange = loadList;
        form.onsubmit = async event => {
            event.preventDefault();
            if (!context) return;
            const captured = {...context};
            busyForm(true); setStatus("Creating assignment…");
            try {
                const result = await request("/teacher/class-assignments", "POST", {...captured,
                    title:document.getElementById("work-title").value, instructions:document.getElementById("work-instructions").value,
                    assigned_date:document.getElementById("work-assigned-date").value, due_date:document.getElementById("work-due-date").value});
                document.getElementById("work-title").value = "";
                document.getElementById("work-instructions").value = "";
                setStatus(result.notification_delivery?.status === "retry_needed" ? "Assignment saved. Some alerts failed; use Retry follow-up alerts." : "Assignment created for the current class.");
                await loadList();
            } catch (error) {setStatus(error.message);}
            finally {busyForm(false);}
        };
        async function loadRegister(id) {
            const ticket = ++registerRequest;
            const panel = document.getElementById("assignment-register-panel");
            const body = document.getElementById("completion-register-body");
            panel.hidden = false; register = null;
            body.innerHTML = '<tr><td colspan="5">Loading completion records…</td></tr>';
            document.getElementById("work-save-register").disabled = true;
            try {
                const data = await request(endpoint(id) + "/register");
                if (ticket !== registerRequest) return;
                register = data;
                document.getElementById("completion-register-title").textContent = data.assignment.title;
                document.getElementById("completion-register-context").textContent = `Due ${data.assignment.due_date} · As of ${data.as_of} (Africa/Nairobi). Late submissions require a reason. Transferred or archived recipients are read-only.`;
                body.innerHTML = data.recipients.length ? data.recipients.map(row => `<tr data-completion-student="${row.student_id}" data-editable="${row.editable}">
                    <td><strong>${escapeHtml(row.student_name)}</strong><br>${escapeHtml(row.admission_number)}${row.editable ? "" : '<br><span class="record-status">Read-only</span>'}</td>
                    <td>${badge(row.display_status)}</td><td><select aria-label="Completion for ${escapeHtml(row.student_name)}" class="work-completion-status" ${row.editable ? "" : "disabled"}>
                    ${[["NOT_SUBMITTED","Not submitted"],["SUBMITTED","Submitted"],["EXCUSED","Excused"]].map(([value,label]) => `<option value="${value}" ${row.status === value ? "selected" : ""}>${label}</option>`).join("")}</select></td>
                    <td><input aria-label="Submission date for ${escapeHtml(row.student_name)}" class="work-submitted-on" type="date" value="${row.submitted_on || ""}" max="${data.as_of}" min="${data.assignment.assigned_date}" ${row.editable ? "" : "disabled"}></td>
                    <td><textarea aria-label="Reason for ${escapeHtml(row.student_name)}" class="work-late-reason" maxlength="1000" ${row.editable ? "" : "disabled"}>${escapeHtml(row.reason || "")}</textarea></td></tr>`).join("")
                    : '<tr><td colspan="5">No learners were recipients of this assignment.</td></tr>';
                body.querySelectorAll("tr[data-completion-student]").forEach(row => {
                    const update = () => {
                        const submitted = row.querySelector(".work-completion-status").value === "SUBMITTED";
                        const date = row.querySelector(".work-submitted-on");
                        const editable = row.dataset.editable === "true";
                        date.disabled = !editable || !submitted;
                        date.required = editable && submitted;
                        if (submitted && editable && !date.value) date.value = data.as_of;
                        row.querySelector(".work-late-reason").required = editable && submitted && date.value > data.assignment.due_date;
                    };
                    row.querySelector("select").onchange = update;
                    row.querySelector(".work-submitted-on").onchange = update;
                    update();
                });
                document.getElementById("work-save-register").disabled = !data.recipients.some(r => r.editable);
                panel.scrollIntoView({block:"start",behavior:"smooth"});
            } catch (error) {if (ticket === registerRequest) {body.innerHTML = `<tr><td colspan="5">${escapeHtml(error.message)} Reopen the register to retry.</td></tr>`;}}
        }
        document.getElementById("completion-register-form").onsubmit = async event => {
            event.preventDefault();
            if (!register) return;
            const data = register;
            const entries = [...document.querySelectorAll('#completion-register-body tr[data-editable="true"]')].map(row => {
                const status = row.querySelector("select").value;
                return {student_id:Number(row.dataset.completionStudent), status,
                    submitted_on:status === "SUBMITTED" ? row.querySelector(".work-submitted-on").value : null,
                    reason:row.querySelector(".work-late-reason").value.trim() || null};
            });
            if (!entries.length) return;
            const button = document.getElementById("work-save-register");
            button.disabled = true; setStatus("Saving completion register…");
            try {
                const result = await request(endpoint(data.assignment.assignment_id) + "/completions", "PUT", {entries});
                setStatus(result.notification_delivery.status === "retry_needed" ? "Completion saved. Some alerts failed; use Retry follow-up alerts." : "Completion saved. Parent summaries and follow-up guidance are updated.");
                if (register === data) await loadRegister(data.assignment.assignment_id);
            } catch (error) {setStatus(error.message);}
            finally {if (register === data) button.disabled = false;}
        };
        document.getElementById("work-close-register").onclick = closeRegister;
        list.onclick = async event => {
            const button = event.target.closest("[data-work-action]");
            if (!button) return;
            const id = Number(button.dataset.id), row = assignments.find(a => a.assignment_id === id);
            try {
                if (button.dataset.workAction === "register") {await loadRegister(id); return;}
                if (button.dataset.workAction === "edit") {
                    RecordEditor.open({title:"Edit assignment",fields:detailsFields,values:row,onSave:async values => {
                        const result = await request(endpoint(id),"PUT",values); await loadList();
                        setStatus(result.notification_delivery?.status === "retry_needed" ? "Assignment updated. Some alerts failed; use Retry follow-up alerts." : "Assignment updated.");
                    }}); return;
                }
                if (button.dataset.workAction === "status") {
                    if (!confirm(row.is_withdrawn ? "Restore this assignment?" : "Withdraw this assignment? It will be excluded from normal summaries; history is preserved.")) return;
                    await request(endpoint(id)+(row.is_withdrawn ? "/status" : ""), row.is_withdrawn ? "PATCH" : "DELETE", row.is_withdrawn ? {is_withdrawn:false} : undefined);
                    await loadList(); setStatus(row.is_withdrawn ? "Assignment restored." : "Assignment withdrawn."); return;
                }
                const result = await request(endpoint(id)+"/notify","POST");
                setStatus(result.status === "complete" ? "Follow-up alerts checked. Repeated alerts are suppressed." : "Some alerts could not be sent. Retry later.");
            } catch (error) {setStatus(error.message);}
        };
    });
})();
