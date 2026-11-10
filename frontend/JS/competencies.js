/* Teacher-recorded evidence, separate from academic predictions. */
(() => {
    const levels = {BELOW_EXPECTATIONS:"Below expectations", APPROACHING_EXPECTATIONS:"Approaching expectations", MEETING_EXPECTATIONS:"Meeting expectations", EXCEEDING_EXPECTATIONS:"Exceeding expectations", NOT_ASSESSED:"Not assessed"};
    const label = value => levels[value] || value;
    const esc = value => escapeHtml(String(value ?? ""));
    const evidence = rows => rows.map(row => `<li>${esc(row.observed_on)} · <strong>${esc(label(row.level))}</strong><p class="work-instructions">${esc(row.evidence)}</p></li>`).join("");
    window.CompetencyParent = {
        error(message = "Competencies unavailable. Use Refresh progress to retry.") {document.getElementById("parent-competencies").textContent = message;},
        render(data) {
            document.getElementById("parent-competencies").innerHTML = `<p>${esc(data.term)} ${esc(data.academic_year)} · As of ${esc(data.as_of)}</p><p>${esc(data.rubric_source)}</p>
                <div class="work-counts">${Object.entries(data.counts).map(([key,n]) => `<div class="work-count">${esc(label(key))}<strong>${n}</strong></div>`).join("")}</div>
                ${data.guidance.map(g => `<p class="work-guidance">${esc(g.text)}</p>`).join("")}
                ${data.competencies.length ? data.competencies.map(item => `<article class="work-card"><h3>${esc(item.name)}</h3><p>${esc(item.subject_name)} · ${esc(item.strand)}</p>
                <p>${esc(item.description)}</p><p><strong>${esc(label(item.latest?.level || "NOT_ASSESSED"))}</strong>${item.change ? ` · ${esc(item.change)} since previous observation` : ""}${item.current_class ? "" : " · Previous class history"}</p>
                ${item.latest ? `<p>Latest observation: ${esc(item.latest.observed_on)}</p><p class="work-instructions">${esc(item.latest.evidence)}</p><details><summary>Evidence history (${item.history.length})</summary><ol>${evidence(item.history)}</ol></details>` : "<p>No evidence recorded for this skill in the selected period.</p>"}</article>`).join("") : "<p>No competencies recorded for this learner and period.</p>"}`;
        }
    };
    document.addEventListener("DOMContentLoaded", () => {
        const form = document.getElementById("competency-form");
        if (!form) return;
        let context = null, catalog = [], register = null, generation = 0;
        const list = document.getElementById("competency-list"), panel = document.getElementById("competency-register"), status = document.getElementById("competency-status");
        const request = (path, method="GET", body) => RecordEditor.request(path, method, body);
        const path = id => `/teacher/competencies/${id}`;
        const detailsFields = [{name:"name", label:"Competency / skill",maxLength:150}, {name:"strand",label:"Strand / topic",maxLength:150,required:false}, {name:"description",label:"What demonstrating this skill looks like",type:"textarea",maxLength:4000,required:false}];
        const periodQuery = ctx => new URLSearchParams({term:ctx.term,academic_year:ctx.academic_year});
        function message(result, text) {status.textContent = text + (result?.notification_delivery?.status === "retry_needed" ? " Records saved, but alerts need retry. Use Retry follow-up alerts." : "");}
        async function load() {
            if (!context) return;
            const ticket = ++generation;
            register = null; panel.hidden = true; list.textContent = "Loading competencies…";
            try {
                const data = await request(`/teacher/competencies?${new URLSearchParams({grade_level:context.grade_level,stream:context.stream,subject_name:context.subject_name,include_archived:document.getElementById("competency-include-archived").checked})}`);
                if (ticket !== generation) return;
                catalog = data;
                list.innerHTML = data.length ? data.map(c => `<article class="work-card"><h3>${esc(c.name)}${c.is_archived ? " (Archived)" : ""}</h3><p>${esc(c.strand)}</p><p>${esc(c.description)}</p><div class="record-actions">
                    <button data-action="register" data-id="${c.competency_id}">Evidence register</button>${c.is_archived ? "" : `<button data-action="edit" data-id="${c.competency_id}">Edit competency</button>`}
                    <button data-action="archive" data-id="${c.competency_id}">${c.is_archived ? "Restore" : "Archive"}</button><button data-action="notify" data-id="${c.competency_id}">Retry follow-up alerts</button></div></article>`).join("") : "No competencies defined for this class and subject. Add one above.";
            } catch(err) {if (ticket === generation) list.textContent = err.message;}
        }
        async function openRegister(id) {
            const ticket = ++generation, ctx = {...context};
            panel.hidden = false; panel.textContent = "Loading evidence…";
            try {
                const data = await request(`${path(id)}/register?${periodQuery(ctx)}`);
                if (ticket !== generation) return;
                register = data;
                panel.innerHTML = `<h3>${esc(data.competency.name)} · ${esc(ctx.term)} ${esc(ctx.academic_year)}</h3><p>Not assessed means no evidence has been recorded. Add another dated observation to track progress; edit to correct an existing one.</p>
                    ${data.learners.map(s => `<article class="work-card"><h4>${esc(s.name)}</h4>${!data.competency.is_archived ? `<button data-action="observe" data-student="${s.student_id}">Record evidence</button>` : ""}
                    ${s.observations.length ? `<ol>${s.observations.map(r => `<li>${esc(r.observed_on)} · <strong>${esc(label(r.level))}</strong><p class="work-instructions">${esc(r.evidence)}</p>${data.competency.is_archived ? "" : `<div class="record-actions"><button data-action="correct" data-id="${r.observation_id}">Correct evidence</button><button data-action="delete" data-id="${r.observation_id}">Delete evidence</button></div>`}</li>`).join("")}</ol>` : "<p>Not assessed in this period</p>"}</article>`).join("") || "<p>No active learners in this class.</p>"}`;
            } catch(err) {if (ticket === generation) panel.textContent = err.message;}
        }
        document.addEventListener("teacher-context-change", event => {
            context = {...event.detail};
            document.getElementById("competency-context").textContent = `${context.grade_level} / ${context.stream} · ${context.subject_name} · ${context.term} ${context.academic_year}`;
            form.querySelector("button").disabled = false; load();
        });
        document.getElementById("competency-refresh").onclick = load;
        document.getElementById("competency-include-archived").onchange = load;
        form.onsubmit = async event => {
            event.preventDefault(); if (!context) return;
            const ctx = {...context}, ticket = generation, button = form.querySelector("button"); button.disabled = true;
            try {
                await request("/teacher/competencies","POST",{grade_level:ctx.grade_level,stream:ctx.stream,subject_name:ctx.subject_name,name:document.getElementById("competency-name").value,strand:document.getElementById("competency-strand").value,description:document.getElementById("competency-description").value});
                if (ticket === generation) {form.reset(); message(null,"Competency created."); await load();}
            } catch(err) {status.textContent = err.message;}
            finally {button.disabled = !context;}
        };
        list.onclick = async event => {
            const button = event.target.closest("button[data-action]"); if (!button) return;
            const id = Number(button.dataset.id), skill = catalog.find(c => c.competency_id === id), ctx = {...context}, ticket = generation;
            try {
                if (button.dataset.action === "register") return await openRegister(id);
                if (button.dataset.action === "edit") return RecordEditor.open({title:"Edit competency",fields:detailsFields,values:skill,onSave:async values => {await request(path(id),"PUT",values); if (ticket === generation) await load();}});
                button.disabled = true;
                if (button.dataset.action === "archive") {
                    if (!confirm(`${skill.is_archived ? "Restore" : "Archive"} this competency? Evidence history is retained.`)) return;
                    const result = skill.is_archived ? await request(`${path(id)}/status`,"PATCH",{is_archived:false}) : await request(path(id),"DELETE");
                    if (ticket === generation) {message(result,skill.is_archived ? "Competency restored." : "Competency archived."); await load();}
                } else {
                    const result = await request(`${path(id)}/notify?${periodQuery(ctx)}`,"POST");
                    if (ticket === generation) status.textContent = result.status === "complete" ? "Follow-up alerts checked." : "Alert delivery still unavailable. Retry later.";
                }
            } catch(err) {status.textContent = err.message;} finally {button.disabled = false;}
        };
        panel.onclick = async event => {
            const button = event.target.closest("button[data-action]"); if (!button || !register) return;
            const ctx = {...context}, skillId = register.competency.competency_id, ticket = generation;
            const row = register.learners.flatMap(s => s.observations).find(r => r.observation_id === Number(button.dataset.id));
            if (button.dataset.action === "delete") {
                if (!confirm("Delete this evidence? Correction history is retained for administrators.")) return;
                button.disabled = true;
                try {const result = await request(`/teacher/competency-observations/${row.observation_id}`,"DELETE"); if (ticket === generation) {message(result,"Evidence deleted."); await openRegister(skillId);}} catch(err) {status.textContent = err.message;} finally {button.disabled = false;}
                return;
            }
            const now = new Intl.DateTimeFormat("en-CA",{timeZone:"Africa/Nairobi",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
            const start = `${ctx.academic_year}-${{"Term 1":"01-01","Term 2":"05-01","Term 3":"09-01"}[ctx.term]}`;
            const end = `${ctx.academic_year}-${{"Term 1":"04-30","Term 2":"08-31","Term 3":"12-31"}[ctx.term]}`;
            const values = row || {observed_on:now >= start && now <= end ? now : start,level:"APPROACHING_EXPECTATIONS",evidence:""};
            RecordEditor.open({title:row ? "Correct competency evidence" : "Record competency evidence",values,fields:[
                {name:"observed_on",label:"Observation date",type:"date",max:now},
                {name:"level",label:"Demonstrated level",options:Object.entries(levels).filter(([key]) => key !== "NOT_ASSESSED").map(([value,label]) => ({value,label}))},
                {name:"evidence",label:"Observed work / evidence and support needed",type:"textarea",maxLength:2000}],
                onSave:async fields => {
                    const payload = {...fields,term:ctx.term,academic_year:ctx.academic_year};
                    const result = row ? await request(`/teacher/competency-observations/${row.observation_id}`,"PUT",payload) : await request(`${path(skillId)}/observations`,"POST",{...payload,student_id:Number(button.dataset.student)});
                    if (ticket === generation) {message(result,"Competency evidence saved."); await openRegister(skillId);}
                }});
        };
    });
})();
