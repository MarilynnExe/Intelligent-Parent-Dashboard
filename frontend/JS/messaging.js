/* Private messaging is independent of active monitoring/period selection. */
document.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("message-start") || !["PARENT","TEACHER"].includes(Auth.getUser()?.role)) return;
    const el = id => document.getElementById(id), esc = value => escapeHtml(String(value ?? ""));
    let active = null, rows = [], generation = 0, conversations = [], listGeneration = 0, contactsGeneration = 0, learnersGeneration = 0, hasOlder = false, refreshing = false, sending = false;
    const drafts = new Map();
    const visible = () => !document.hidden && el("section-messages").classList.contains("active");
    const status = text => {el("messages-status").textContent = text;};
    async function request(path,method="GET",body) {
        const response = await apiFetch(`/messaging${path}`,{method,...(body===undefined ? {} : {body:JSON.stringify(body)})});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {const error = new Error(Array.isArray(data.detail) ? data.detail.map(e=>e.msg).join("; ") : data.detail || "Messaging unavailable. Refresh to retry.");error.status=response.status;throw error;}
        return data;
    }
    function saveDraft() {
        if (!active) return;
        const draft = drafts.get(active.conversation_id) || {};
        if (!draft.attempt) draft.text = el("message-body").value;
        drafts.set(active.conversation_id,draft);
    }
    function renderComposer() {
        const draft = active && drafts.get(active.conversation_id);
        el("message-body").disabled = !active?.can_reply || sending || Boolean(draft?.attempt);
        el("message-send").disabled = !active?.can_reply || sending;
        el("message-send").textContent = draft?.attempt ? "Retry send" : "Send message";
        el("message-reply-state").textContent = active ? active.read_only_reason || "Only you and this contact can read this conversation." : "";
    }
    function renderHistory() {
        const cursor = active?.peer_read_through_id || 0;
        el("message-history").innerHTML = rows.map(row=>`<li data-message-id="${row.message_id}" class="${row.is_mine ? "message-mine" : ""}"><strong>${row.is_mine ? "You" : esc(active.contact_name)}</strong><p>${esc(row.body)}</p><small>${esc(new Date(row.sent_at.endsWith("Z") ? row.sent_at : row.sent_at+"Z").toLocaleString())}${row.is_mine ? row.message_id <= cursor ? " · Read" : " · Sent" : ""}</small></li>`).join("") || "<li>No messages yet. Start the conversation below.</li>";
        el("messages-older").hidden = !hasOlder;
    }
    async function loadList(more=false) {
        const ticket = ++listGeneration;
        const data = await request(`/conversations?limit=30&offset=${more ? conversations.length : 0}`);
        if (ticket !== listGeneration) return;
        conversations = more ? [...conversations,...data.items].filter((item,index,all)=>all.findIndex(x=>x.conversation_id===item.conversation_id)===index) : data.items;
        el("messages-unread").textContent = data.unread_total;
        el("messages-more-conversations").hidden = !data.has_more;
        el("message-conversations").innerHTML = conversations.length ? conversations.map(c=>`<button type="button" data-conversation="${c.conversation_id}" aria-current="${active?.conversation_id===c.conversation_id}"><strong>${esc(c.student_name)}</strong><br>${esc(c.contact_name)}${c.unread_count ? `<br>${c.unread_count} unread` : ""}${c.can_reply ? "" : "<br>Read-only history"}</button>`).join("") : "No conversations yet. Choose a learner and contact above.";
    }
    async function readDisplayed(ticket) {
        if (!active || !visible() || !rows.length || ticket !== generation) return;
        const id=active.conversation_id;
        const data=await request(`/conversations/${id}/read`,"POST",{through_message_id:rows.at(-1).message_id});
        if (ticket !== generation || !visible()) return;
        active=data;renderComposer();await loadList();
    }
    function reconcileDraft() {
        const draft=drafts.get(active.conversation_id);
        if (draft?.attempt && rows.some(row=>row.is_mine && row.client_message_id===draft.attempt.client_message_id)) {
            drafts.delete(active.conversation_id);el("message-body").value="";status("Message delivered.");
        }
    }
    async function openConversation(id) {
        saveDraft();const ticket=++generation;active=null;rows=[];hasOlder=false;renderComposer();el("message-history").textContent="Loading messages…";
        try {
            const data=await request(`/conversations/${id}/messages`);
            if (ticket!==generation) return;
            active=data.conversation;rows=data.items;hasOlder=data.has_older;
            el("message-thread-title").textContent=`${active.student_name} · ${active.contact_name}`;
            el("message-body").value=drafts.get(id)?.text || "";
            reconcileDraft();renderHistory();renderComposer();await readDisplayed(ticket);await loadList();
        } catch(error) {if(ticket===generation){status(error.message);el("message-history").textContent="Messages could not be loaded. Select the conversation to retry.";}}
    }
    async function refresh() {
        if(refreshing)return;refreshing=true;
        const ticket=generation;
        try {
            await loadList();
            if(active && visible()) {
                const id=active.conversation_id;
                // Drain newer pages before marking displayed messages read.
                let more=true;
                while(more && ticket===generation && visible()) {
                    const query=rows.length ? `?after_id=${rows.at(-1).message_id}` : "";
                    const data=await request(`/conversations/${id}/messages${query}`);
                    if(ticket!==generation)return;
                    active=data.conversation;
                    rows=[...rows,...data.items].filter((row,index,all)=>all.findIndex(x=>x.message_id===row.message_id)===index);
                    if(!query)hasOlder=data.has_older;
                    more=Boolean(query && data.has_more);
                }
                reconcileDraft();renderHistory();renderComposer();await readDisplayed(ticket);
            }
        } catch(error) {status(error.message);if(ticket===generation && active){active.can_reply=false;active.read_only_reason="Could not verify reply access. Refresh messages to retry.";renderComposer();}}
        finally {refreshing=false;}
    }
    async function loadLearners() {
        const ticket=++learnersGeneration, selected=el("message-learner").value;
        try {
            const data=await request("/learners");
            if(ticket!==learnersGeneration)return;
            el("message-learner").innerHTML='<option value="">Choose a learner</option>'+data.map(s=>`<option value="${s.student_id}">${esc(s.name)} · ${esc(s.grade_level)} ${esc(s.stream)}</option>`).join("");
            if(!data.length)el("message-learner").innerHTML='<option value="">No currently linked learners</option>';
            if(data.some(s=>String(s.student_id)===selected))el("message-learner").value=selected;
            el("message-learner").onchange();
        } catch(error){status(error.message);el("message-learner").innerHTML='<option value="">Learners unavailable</option>';}
    }
    el("message-learner").onchange=async()=> {
        const ticket=++contactsGeneration;el("message-start-button").disabled=true;el("message-contact").innerHTML='<option value="">Loading contacts…</option>';
        if(!el("message-learner").value){el("message-contact").innerHTML='<option value="">Select a learner first</option>';return;}
        try {
            const data=await request(`/contacts?student_id=${el("message-learner").value}`);
            if(ticket!==contactsGeneration)return;
            el("message-contact").innerHTML=data.length ? data.map(c=>`<option value="${c.user_id}">${esc(c.full_name)}</option>`).join("") : '<option value="">No eligible contacts</option>';
            el("message-start-button").disabled=!data.length;
        }catch(error){if(ticket===contactsGeneration){status(error.message);el("message-contact").innerHTML='<option value="">Contacts unavailable</option>';}}
    };
    el("message-start").onsubmit=async event=> {
        event.preventDefault();el("message-start-button").disabled=true;
        try {const data=await request("/conversations","POST",{student_id:Number(el("message-learner").value),contact_user_id:Number(el("message-contact").value)});await openConversation(data.conversation_id);}
        catch(error){status(error.message);}finally{el("message-start-button").disabled=!el("message-contact").value;}
    };
    el("message-conversations").onclick=event=> {const button=event.target.closest("[data-conversation]");if(button)openConversation(Number(button.dataset.conversation));};
    el("messages-more-conversations").onclick=()=>loadList(true).catch(error=>status(error.message));
    el("messages-older").onclick=async()=> {
        if(!active || !rows.length)return;
        const ticket=generation,id=active.conversation_id;el("messages-older").disabled=true;
        try {const data=await request(`/conversations/${id}/messages?before_id=${rows[0].message_id}`);if(ticket!==generation)return;rows=[...data.items,...rows];hasOlder=data.has_older;renderHistory();}
        catch(error){status(error.message);}finally{el("messages-older").disabled=false;}
    };
    el("message-body").oninput=saveDraft;
    el("message-compose").onsubmit=async event=> {
        event.preventDefault();if(!active?.can_reply || sending)return;
        const id=active.conversation_id,ticket=generation;
        saveDraft();const draft=drafts.get(id) || {};
        if(!draft.attempt){
            const body=el("message-body").value.trim();
            if(!body){status("Enter a message before sending.");return;}
            draft.attempt={body,client_message_id:crypto.randomUUID()};
        }
        draft.text=draft.attempt.body;drafts.set(id,draft);sending=true;renderComposer();
        try {
            const result=await request(`/conversations/${id}/messages`,"POST",draft.attempt);
            drafts.delete(id);
            if(ticket===generation){rows=[...rows.filter(row=>row.message_id!==result.message_id),result].sort((a,b)=>a.message_id-b.message_id);renderHistory();el("message-body").value="";status(result.notification_delivery.status==="retry_needed" ? "Message sent. Its notification is temporarily unavailable; the message remains in the conversation." : "Message sent.");await refresh();}
        } catch(error) {
            if(error.status && error.status<500){draft.attempt=null;drafts.set(id,draft);}
            if(ticket===generation)status(draft.attempt ? "Delivery could not be confirmed. Your draft is saved here. Retry send safely, or refresh to check delivery." : error.message);
        } finally {sending=false;renderComposer();}
    };
    el("messages-refresh").onclick=()=>{loadLearners();refresh();};
    document.querySelectorAll(".sub-nav-btn").forEach(button=>button.addEventListener("click",()=> {
        const selected=button.dataset.target==="section-messages";document.body.classList.toggle("messaging-view",selected);
        if(selected)refresh();
    }));
    document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
    setInterval(()=>{if(!document.hidden)refresh();},30000);
    loadLearners();refresh();
});
