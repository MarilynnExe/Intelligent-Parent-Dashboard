/**
 * Admin Dashboard Controller
 * Connects the Administration Console UI to the live FastAPI backend:
 *   - GET    /api/admin/stats
 *   - GET    /api/admin/users              POST /api/admin/users
 *   - GET    /api/admin/students           POST /api/admin/students
 *   - GET    /api/admin/teacher-assignments
 *   - POST   /api/admin/teacher-assignments
 *   - DELETE /api/admin/teacher-assignments/{id}
 *   - GET    /api/admin/parent-links
 *   - POST   /api/admin/parent-links
 *   - DELETE /api/admin/parent-links/{id}
 */

document.addEventListener("DOMContentLoaded", () => {

    // -------------------------------------------------------------------------
    // 1. Authentication & Role Guard
    // -------------------------------------------------------------------------
    if (!Auth.requireRole("ADMIN")) {
        return;
    }

    const user = Auth.getUser();
    document.getElementById("user-display-name").textContent = user.full_name;

    document.getElementById("logout-btn").addEventListener("click", () => {
        Auth.logout();
    });

    // -------------------------------------------------------------------------
    // 2. State
    // -------------------------------------------------------------------------
    const state = {
        users: [],
        students: [],
    };

    // -------------------------------------------------------------------------
    // 3. UI Helpers: Toasts, Tabs, API errors
    // -------------------------------------------------------------------------
    function showToast(message, type = "info", duration = 4000) {
        const container = document.getElementById("toast-container");
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;

        const icon = type === "success" ? "✅" : (type === "error" ? "❌" : "ℹ️");
        toast.innerHTML = `
            <span style="font-size: 1.1rem;">${icon}</span>
            <div style="flex: 1;">
                <div style="font-size: 0.88rem; font-weight: 600;">${escapeHtml(message)}</div>
            </div>
        `;

        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(100%)";
            toast.style.transition = "all 0.3s ease";
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    const tabs = document.querySelectorAll(".sub-nav-btn");
    const sections = document.querySelectorAll(".content-section");

    tabs.forEach(btn => {
        btn.addEventListener("click", () => {
            const target = btn.getAttribute("data-target");
            tabs.forEach(b => b.classList.toggle("active", b === btn));
            sections.forEach(sec => sec.classList.toggle("active", sec.id === target));
        });
    });

    // Turn a FastAPI error body (string detail or validation list) into a message
    function errorMessage(data, fallback) {
        if (!data || !data.detail) return fallback;
        if (Array.isArray(data.detail)) {
            return data.detail
                .map(d => `${d.loc[d.loc.length - 1]}: ${d.msg}`)
                .join("; ");
        }
        return data.detail;
    }

    async function apiJson(endpoint, options = {}, fallbackError = "Request failed.") {
        const res = await apiFetch(endpoint, options);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(errorMessage(data, fallbackError));
        }
        return data;
    }

    function stateRow(colspan, message, isError = false) {
        const style = isError ? ' style="color: var(--pastel-pink-text);"' : "";
        return `<tr><td colspan="${colspan}" class="state-box"><p${style}>${escapeHtml(message)}</p></td></tr>`;
    }

    function formatDate(value) {
        if (!value) return "—";
        const d = new Date(value);
        return isNaN(d) ? escapeHtml(value) : d.toLocaleDateString();
    }

    // Disable a submit button while its request runs
    async function withBusyButton(button, busyLabel, task) {
        const label = button.textContent;
        button.disabled = true;
        button.textContent = busyLabel;
        try {
            await task();
        } finally {
            button.disabled = false;
            button.textContent = label;
        }
    }

    // -------------------------------------------------------------------------
    // 4. System Statistics
    // -------------------------------------------------------------------------
    async function loadStats() {
        try {
            const stats = await apiJson("/admin/stats", {}, "Failed to load statistics.");
            document.getElementById("stat-total-users").textContent = stats.total_users;
            document.getElementById("stat-users-sub").textContent =
                `${stats.total_admins} admin · ${stats.total_teachers} teachers · ${stats.total_parents} parents`;
            document.getElementById("stat-total-students").textContent = stats.total_students;
            document.getElementById("stat-total-assessments").textContent = stats.total_assessments;
            document.getElementById("stat-total-attendance").textContent = stats.total_attendance_records;
        } catch (err) {
            console.error("Stats Error:", err);
            showToast(err.message, "error");
        }
    }

    document.getElementById("btn-refresh-stats").addEventListener("click", () => {
        loadStats();
        showToast("Refreshing statistics...", "info", 1500);
    });

    // -------------------------------------------------------------------------
    // 5. User Management
    // -------------------------------------------------------------------------
    function rolePill(role) {
        const cls = { ADMIN: "role-admin", TEACHER: "role-teacher", PARENT: "role-parent" }[role] || "";
        return `<span class="role-pill ${cls}">${escapeHtml(role)}</span>`;
    }

    function renderUsers() {
        const tbody = document.getElementById("users-tbody");
        if (state.users.length === 0) {
            tbody.innerHTML = stateRow(7, "No users registered yet.");
            return;
        }
        tbody.innerHTML = state.users.map(u => `
            <tr>
                <td style="color: var(--text-muted);">${u.user_id}</td>
                <td><strong>${escapeHtml(u.full_name)}</strong><span class="record-status">${u.is_active ? "Active" : "Deactivated"}</span></td>
                <td>${escapeHtml(u.email_or_username)}</td>
                <td>${rolePill(u.role)}</td>
                <td>${escapeHtml(u.phone_number || "—")}</td>
                <td>${formatDate(u.created_at)}</td>
                <td class="record-actions"><button data-crud="edit-user" data-id="${u.user_id}">Edit</button><button data-crud="toggle-user" data-id="${u.user_id}">${u.is_active ? "Deactivate" : "Restore"}</button></td>
            </tr>
        `).join("");
    }

    function fillSelect(selectId, items, placeholder, toOption) {
        const select = document.getElementById(selectId);
        const previous = select.value;
        select.innerHTML = `<option value="" disabled selected>${escapeHtml(placeholder)}</option>`;
        items.forEach(item => {
            const { value, label } = toOption(item);
            const opt = document.createElement("option");
            opt.value = value;
            opt.textContent = label;
            select.appendChild(opt);
        });
        // Keep the admin's current choice across reloads
        if (previous && items.some(i => String(toOption(i).value) === previous)) {
            select.value = previous;
        }
    }

    function refreshUserSelects() {
        const teachers = state.users.filter(u => u.role === "TEACHER" && u.is_active !== false);
        const parents = state.users.filter(u => u.role === "PARENT" && u.is_active !== false);

        fillSelect("assign-teacher-select", teachers,
            teachers.length ? "Select teacher..." : "No teacher accounts yet",
            u => ({ value: u.user_id, label: `${u.full_name} (${u.email_or_username})` }));

        fillSelect("link-parent-select", parents,
            parents.length ? "Select parent..." : "No parent accounts yet",
            u => ({ value: u.user_id, label: `${u.full_name} (${u.email_or_username})` }));
    }

    async function loadUsers() {
        const tbody = document.getElementById("users-tbody");
        try {
            state.users = await apiJson("/admin/users", {}, "Failed to load users.");
            renderUsers();
            refreshUserSelects();
        } catch (err) {
            console.error("Users Error:", err);
            tbody.innerHTML = stateRow(7, err.message, true);
        }
    }

    const createUserForm = document.getElementById("create-user-form");
    createUserForm.addEventListener("submit", (e) => {
        e.preventDefault();

        const payload = {
            full_name: document.getElementById("user-full-name").value.trim(),
            email_or_username: document.getElementById("user-email-username").value.trim(),
            password: document.getElementById("user-password").value,
            role: document.getElementById("user-role").value,
            phone_number: document.getElementById("user-phone").value.trim() || null,
        };

        withBusyButton(document.getElementById("btn-save-user"), "Creating account...", async () => {
            try {
                const created = await apiJson("/admin/users", {
                    method: "POST",
                    body: JSON.stringify(payload),
                }, "Failed to create user.");
                showToast(`Created ${created.role.toLowerCase()} account for ${created.full_name}.`, "success");
                createUserForm.reset();
                await Promise.all([loadUsers(), loadStats()]);
            } catch (err) {
                showToast(err.message, "error");
            }
        });
    });

    // -------------------------------------------------------------------------
    // 6. Student Records
    // -------------------------------------------------------------------------
    function renderStudents() {
        const tbody = document.getElementById("students-tbody");
        if (state.students.length === 0) {
            tbody.innerHTML = stateRow(8, "No learners enrolled yet.");
            return;
        }
        tbody.innerHTML = state.students.map(s => `
            <tr>
                <td style="color: var(--text-muted);">${s.student_id}</td>
                <td>${escapeHtml(s.admission_number)}</td>
                <td><strong>${escapeHtml(s.first_name)} ${escapeHtml(s.last_name)}</strong><span class="record-status">${s.is_archived ? "Archived" : "Active"}</span></td>
                <td>${escapeHtml(s.grade_level)} ${escapeHtml(s.stream || "")}</td>
                <td>${escapeHtml(s.gender || "—")}</td>
                <td>${escapeHtml(s.date_of_birth)}</td>
                <td>${formatDate(s.created_at)}</td>
                <td class="record-actions"><button data-crud="edit-student" data-id="${s.student_id}">Edit</button><button data-crud="toggle-student" data-id="${s.student_id}">${s.is_archived ? "Restore" : "Archive"}</button></td>
            </tr>
        `).join("");
    }

    async function loadStudents() {
        const tbody = document.getElementById("students-tbody");
        try {
            state.students = await apiJson("/admin/students", {}, "Failed to load learners.");
            renderStudents();
            fillSelect("link-student-select", state.students.filter(s => !s.is_archived),
                state.students.length ? "Select learner..." : "No learners enrolled yet",
                s => ({
                    value: s.student_id,
                    label: `${s.first_name} ${s.last_name} (${s.admission_number} • ${s.grade_level} ${s.stream || ""})`,
                }));
        } catch (err) {
            console.error("Students Error:", err);
            tbody.innerHTML = stateRow(8, err.message, true);
        }
    }

    const enrollForm = document.getElementById("enroll-student-form");
    enrollForm.addEventListener("submit", (e) => {
        e.preventDefault();

        const payload = {
            admission_number: document.getElementById("student-adm-no").value.trim(),
            first_name: document.getElementById("student-first-name").value.trim(),
            last_name: document.getElementById("student-last-name").value.trim(),
            date_of_birth: document.getElementById("student-dob").value,
            gender: document.getElementById("student-gender").value || null,
            grade_level: document.getElementById("student-grade").value.trim(),
            stream: document.getElementById("student-stream").value.trim() || null,
        };

        withBusyButton(document.getElementById("btn-save-student"), "Enrolling...", async () => {
            try {
                const created = await apiJson("/admin/students", {
                    method: "POST",
                    body: JSON.stringify(payload),
                }, "Failed to enroll learner.");
                showToast(`Enrolled ${created.first_name} ${created.last_name} (${created.admission_number}).`, "success");
                enrollForm.reset();
                await Promise.all([loadStudents(), loadStats()]);
            } catch (err) {
                showToast(err.message, "error");
            }
        });
    });

    // -------------------------------------------------------------------------
    // 7. Teacher Class Assignments
    // -------------------------------------------------------------------------
    async function loadAssignments() {
        const tbody = document.getElementById("assignments-tbody");
        try {
            const rows = await apiJson("/admin/teacher-assignments", {}, "Failed to load assignments.");
            state.assignmentRows = rows;
            if (rows.length === 0) {
                tbody.innerHTML = stateRow(5, "No teacher assignments yet.");
                return;
            }
            tbody.innerHTML = rows.map(a => `
                <tr>
                    <td><strong>${escapeHtml(a.teacher_name)}</strong></td>
                    <td>${escapeHtml(a.grade_level)}</td>
                    <td>${escapeHtml(a.stream)}</td>
                    <td>${escapeHtml(a.subject_name)}</td>
                    <td style="text-align: right;">
                        <button class="btn btn-sm" data-crud="edit-assignment" data-id="${a.assignment_id}">Edit</button>
                        <button class="btn-outline-danger-sm btn-delete-assignment" data-id="${a.assignment_id}"
                                data-label="${escapeHtml(`${a.teacher_name} — ${a.subject_name}, ${a.grade_level} ${a.stream}`)}">
                            Remove
                        </button>
                    </td>
                </tr>
            `).join("");

            tbody.querySelectorAll(".btn-delete-assignment").forEach(btn => {
                btn.addEventListener("click", () => deleteAssignment(btn.dataset.id, btn.dataset.label));
            });
        } catch (err) {
            console.error("Assignments Error:", err);
            tbody.innerHTML = stateRow(5, err.message, true);
        }
    }

    async function deleteAssignment(id, label) {
        if (!confirm(`Remove this teacher assignment?\n\n${label}`)) return;
        try {
            await apiJson(`/admin/teacher-assignments/${id}`, { method: "DELETE" }, "Failed to remove assignment.");
            showToast("Teacher assignment removed.", "success");
            loadAssignments();
        } catch (err) {
            showToast(err.message, "error");
        }
    }

    document.getElementById("assign-teacher-form").addEventListener("submit", (e) => {
        e.preventDefault();

        const teacherId = parseInt(document.getElementById("assign-teacher-select").value);
        if (!teacherId) {
            showToast("Please select a teacher.", "error");
            return;
        }

        const payload = {
            teacher_user_id: teacherId,
            grade_level: document.getElementById("assign-grade").value.trim(),
            stream: document.getElementById("assign-stream").value.trim(),
            subject_name: document.getElementById("assign-subject").value.trim(),
        };

        withBusyButton(document.getElementById("btn-save-assignment"), "Saving...", async () => {
            try {
                const created = await apiJson("/admin/teacher-assignments", {
                    method: "POST",
                    body: JSON.stringify(payload),
                }, "Failed to save assignment.");
                showToast(`${created.teacher_name} assigned to ${created.subject_name}, ${created.grade_level} ${created.stream}.`, "success");
                loadAssignments();
            } catch (err) {
                showToast(err.message, "error");
            }
        });
    });

    // -------------------------------------------------------------------------
    // 8. Parent-Learner Links
    // -------------------------------------------------------------------------
    async function loadParentLinks() {
        const tbody = document.getElementById("parent-links-tbody");
        try {
            const rows = await apiJson("/admin/parent-links", {}, "Failed to load parent links.");
            state.linkRows = rows;
            if (rows.length === 0) {
                tbody.innerHTML = stateRow(5, "No parent-learner links yet.");
                return;
            }
            tbody.innerHTML = rows.map(l => `
                <tr>
                    <td><strong>${escapeHtml(l.parent_name)}</strong></td>
                    <td>${escapeHtml(l.student_name)}</td>
                    <td>${escapeHtml(l.admission_number)}</td>
                    <td>${escapeHtml(l.relationship_type || "—")}</td>
                    <td style="text-align: right;">
                        <button class="btn btn-sm" data-crud="edit-link" data-id="${l.id}">Edit</button>
                        <button class="btn-outline-danger-sm btn-delete-link" data-id="${l.id}"
                                data-label="${escapeHtml(`${l.parent_name} → ${l.student_name}`)}">
                            Unlink
                        </button>
                    </td>
                </tr>
            `).join("");

            tbody.querySelectorAll(".btn-delete-link").forEach(btn => {
                btn.addEventListener("click", () => deleteParentLink(btn.dataset.id, btn.dataset.label));
            });
        } catch (err) {
            console.error("Parent Links Error:", err);
            tbody.innerHTML = stateRow(5, err.message, true);
        }
    }

    async function deleteParentLink(id, label) {
        if (!confirm(`Unlink this parent from the learner? They will lose access to the learner's records.\n\n${label}`)) return;
        try {
            await apiJson(`/admin/parent-links/${id}`, { method: "DELETE" }, "Failed to remove link.");
            showToast("Parent-learner link removed.", "success");
            loadParentLinks();
        } catch (err) {
            showToast(err.message, "error");
        }
    }

    document.getElementById("link-parent-form").addEventListener("submit", (e) => {
        e.preventDefault();

        const parentId = parseInt(document.getElementById("link-parent-select").value);
        const studentId = parseInt(document.getElementById("link-student-select").value);
        if (!parentId || !studentId) {
            showToast("Please select both a parent and a learner.", "error");
            return;
        }

        const payload = {
            parent_user_id: parentId,
            student_id: studentId,
            relationship_type: document.getElementById("link-relationship").value,
        };

        withBusyButton(document.getElementById("btn-save-link"), "Saving...", async () => {
            try {
                const created = await apiJson("/admin/parent-links", {
                    method: "POST",
                    body: JSON.stringify(payload),
                }, "Failed to link parent.");
                showToast(`${created.parent_name} linked to ${created.student_name}.`, "success");
                loadParentLinks();
            } catch (err) {
                showToast(err.message, "error");
            }
        });
    });


    // -------------------------------------------------------------------------
    // 8. Teacher Workload Monitoring & Balancing
    // -------------------------------------------------------------------------
    let workloadCache = null;

    async function loadWorkload() {
        const tbody = document.getElementById("teacher-workload-tbody");
        const recsContainer = document.getElementById("workload-recommendations-list");
        if (!tbody || !recsContainer) return;

        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="state-box">
                    <div class="state-spinner"></div>
                    <p>Loading teacher workload records...</p>
                </td>
            </tr>
        `;
        recsContainer.innerHTML = `
            <div class="state-box">
                <div class="state-spinner"></div>
                <p>Evaluating teacher workload distribution...</p>
            </div>
        `;

        try {
            const report = await apiJson("/admin/teacher-workload", {}, "Failed to load teacher workload report.");
            workloadCache = report;

            // Update Summary Stats
            const s = report.summary;
            const statusEl = document.getElementById("stat-wl-status");
            if (statusEl) {
                statusEl.textContent = s.capacity_status;
                if (s.high_workload_count > 0 && (s.low_workload_count > 0 || s.unassigned_teachers_count > 0)) {
                    statusEl.style.color = "var(--pastel-pink-text, #be185d)";
                } else if (s.high_workload_count > 0) {
                    statusEl.style.color = "var(--pastel-amber-text, #b45309)";
                } else {
                    statusEl.style.color = "var(--pastel-green-text, #15803d)";
                }
            }

            const activeSubEl = document.getElementById("stat-wl-active-sub");
            if (activeSubEl) {
                activeSubEl.textContent = `${s.active_teachers_count} active / ${s.unassigned_teachers_count} unassigned of ${s.total_teachers} teachers`;
            }

            const highEl = document.getElementById("stat-wl-high");
            if (highEl) {
                highEl.textContent = s.high_workload_count;
                highEl.style.color = s.high_workload_count > 0 ? "var(--pastel-pink-text, #be185d)" : "var(--text-heading)";
            }

            const avgEl = document.getElementById("stat-wl-avg-learners");
            if (avgEl) {
                avgEl.textContent = s.average_learners_per_teacher;
            }

            const targetedEl = document.getElementById("stat-wl-targeted");
            if (targetedEl) {
                targetedEl.textContent = s.total_targeted_support_learners;
            }

            const methEl = document.getElementById("workload-methodology-note");
            if (methEl && report.scoring_methodology) {
                methEl.textContent = report.scoring_methodology;
            }

            // Render Balancing Recommendations
            renderWorkloadRecommendations(report.balancing_recommendations);

            // Render Teacher Table (with current filter)
            renderWorkloadTable(report.teachers);

        } catch (err) {
            console.error("Workload Error:", err);
            tbody.innerHTML = stateRow(7, err.message, true);
            recsContainer.innerHTML = `<div class="state-box"><p style="color: var(--pastel-pink-text);">${escapeHtml(err.message)}</p></div>`;
        }
    }

    function renderWorkloadRecommendations(recommendations) {
        const container = document.getElementById("workload-recommendations-list");
        if (!container) return;

        if (!recommendations || recommendations.length === 0) {
            container.innerHTML = `
                <div class="state-box" style="padding: 1rem;">
                    <p>No balancing recommendations available at this time.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = recommendations.map(rec => {
            const prioClass = rec.priority === "High" ? "prio-high" : (rec.priority === "Medium" ? "prio-medium" : "prio-low");
            const icon = rec.priority === "High" ? "⚠️" : (rec.recommendation_type === "BALANCED" ? "✅" : "💡");
            const prioBadgeColor = rec.priority === "High" ? "background: #fee2e2; color: #991b1b;" : (rec.priority === "Medium" ? "background: #fef3c7; color: #92400e;" : "background: #dcfce7; color: #166534;");

            return `
                <div class="balancing-card ${prioClass}">
                    <span style="font-size: 1.25rem; line-height: 1;">${icon}</span>
                    <div style="flex: 1;">
                        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
                            <span style="font-size: 0.75rem; font-weight: 700; padding: 0.15rem 0.5rem; border-radius: 4px; ${prioBadgeColor}">
                                ${escapeHtml(rec.priority)} Priority
                            </span>
                            <span style="font-size: 0.78rem; color: var(--text-muted); font-weight: 600;">
                                ${escapeHtml(rec.recommendation_type.replace(/_/g, " "))}
                            </span>
                        </div>
                        <div style="font-size: 0.88rem; color: var(--text-body); line-height: 1.45;">
                            ${escapeHtml(rec.message)}
                        </div>
                    </div>
                </div>
            `;
        }).join("");
    }

    function renderWorkloadTable(teachers) {
        const tbody = document.getElementById("teacher-workload-tbody");
        if (!tbody) return;

        const filterVal = document.getElementById("workload-filter-status")?.value || "ALL";
        const filtered = filterVal === "ALL" ? teachers : teachers.filter(t => t.workload_status === filterVal);

        if (filtered.length === 0) {
            tbody.innerHTML = stateRow(7, "No teachers match the selected workload filter.");
            return;
        }

        tbody.innerHTML = filtered.map(t => {
            // Status badge
            let badgeClass = "badge-low";
            let statusIcon = "🟢";
            if (t.workload_status === "HIGH") {
                badgeClass = "badge-high";
                statusIcon = "🔴";
            } else if (t.workload_status === "MODERATE") {
                badgeClass = "badge-moderate";
                statusIcon = "🟡";
            } else if (t.workload_status === "UNASSIGNED") {
                badgeClass = "badge-unassigned";
                statusIcon = "⚪";
            }

            // Classes & subjects markup
            const classesMarkup = t.assigned_classes.length > 0
                ? `<div style="font-weight: 600; color: var(--text-heading);">${t.assigned_classes.map(c => escapeHtml(c)).join(", ")}</div>
                   <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem;">${t.assigned_subjects.map(s => escapeHtml(s)).join(", ") || "No subjects listed"}</div>`
                : `<span style="color: var(--text-muted); font-style: italic;">No active classes</span>`;

            // Support breakdown chips
            const supportChips = t.assigned_learners_count > 0
                ? `
                    <div style="display: flex; flex-wrap: wrap; gap: 0.2rem;">
                        ${t.targeted_support_count > 0 ? `<span class="support-chip chip-targeted" title="Requires targeted intervention">${t.targeted_support_count} Targeted</span>` : ""}
                        ${t.monitoring_count > 0 ? `<span class="support-chip chip-monitoring" title="Requires monitoring">${t.monitoring_count} Monitoring</span>` : ""}
                        ${t.on_track_count > 0 ? `<span class="support-chip chip-ontrack" title="On track">${t.on_track_count} On Track</span>` : ""}
                        ${t.unassessed_learners_count > 0 ? `<span class="support-chip chip-unassessed" title="Pending initial evaluation">${t.unassessed_learners_count} Unassessed</span>` : ""}
                    </div>
                  `
                : `<span style="color: var(--text-muted); font-size: 0.8rem;">—</span>`;

            // Notifications
            const notifMarkup = t.unread_notifications_count > 0
                ? `<span style="font-weight: 600; color: ${t.high_priority_notifications_count > 0 ? 'var(--pastel-pink-text)' : 'var(--text-body)'};">
                        ${t.unread_notifications_count} unread ${t.high_priority_notifications_count > 0 ? `<small style="display: block; font-size: 0.75rem; color: #b91c1c;">(${t.high_priority_notifications_count} High)</small>` : ""}
                   </span>`
                : `<span style="color: var(--text-muted); font-size: 0.82rem;">0 unread</span>`;

            return `
                <tr>
                    <td>
                        <div style="font-weight: 700; color: var(--text-heading);">${escapeHtml(t.teacher_name)}</div>
                        <div style="font-size: 0.8rem; color: var(--text-muted);">${escapeHtml(t.email_or_username)}</div>
                    </td>
                    <td>${classesMarkup}</td>
                    <td style="text-align: center;">
                        <span style="font-size: 1.05rem; font-weight: 800; color: var(--text-heading);">${t.assigned_learners_count}</span>
                    </td>
                    <td>${supportChips}</td>
                    <td style="text-align: center;">${notifMarkup}</td>
                    <td>
                        <div class="badge-workload ${badgeClass}">
                            <span>${statusIcon}</span>
                            <span>${escapeHtml(t.workload_label)}</span>
                        </div>
                        <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 0.25rem;">
                            Score: <strong>${t.workload_score.toFixed(1)}</strong>
                        </div>
                    </td>
                    <td style="max-width: 320px;">
                        <div style="font-size: 0.82rem; color: var(--text-body); line-height: 1.4;">
                            ${escapeHtml(t.explanation)}
                        </div>
                    </td>
                </tr>
            `;
        }).join("");
    }

    // Event listeners for Workload tab
    document.getElementById("btn-refresh-workload")?.addEventListener("click", () => {
        loadWorkload();
    });

    document.getElementById("workload-filter-status")?.addEventListener("change", () => {
        if (workloadCache) {
            renderWorkloadTable(workloadCache.teachers);
        }
    });

    // -------------------------------------------------------------------------
    // 9. Bootstrap Dashboard
    // -------------------------------------------------------------------------
    loadStats();
    loadUsers();
    loadStudents();
    loadAssignments();
    loadParentLinks();
    loadWorkload();

    const field = (name, label, extra = {}) => ({name, label, ...extra});
    const userFields = [field("full_name", "Full name", {maxLength:150}), field("email_or_username", "Username or email", {maxLength:150}),
        field("role", "Role", {options:["ADMIN", "TEACHER", "PARENT"]}), field("phone_number", "Phone", {required:false,maxLength:30}),
        field("password", "New password (leave blank to keep)", {type:"password",required:false})];
    const studentFields = [field("admission_number", "Admission number", {maxLength:50}), field("first_name", "First name", {maxLength:100}),
        field("last_name", "Last name", {maxLength:100}), field("date_of_birth", "Date of birth", {type:"date"}),
        field("gender", "Gender", {required:false}), field("grade_level", "Grade", {maxLength:50}), field("stream", "Stream", {required:false,maxLength:50})];
    async function refreshCrudTables() {await Promise.all([loadUsers(), loadStudents(), loadAssignments(), loadParentLinks(), loadStats()]);}
    document.addEventListener("click", async event => {
        const button = event.target.closest("[data-crud]");
        if (!button) return;
        const id = Number(button.dataset.id);
        const action = button.dataset.crud;
        try {
            if (action === "toggle-user") {
                const user = state.users.find(u => u.user_id === id);
                if (!confirm(user.is_active ? "Deactivate this account? Existing sessions will be signed out; history is preserved." : "Restore this account?")) return;
                await RecordEditor.request(`/admin/users/${id}${user.is_active ? "" : "/status"}`, user.is_active ? "DELETE" : "PATCH", user.is_active ? undefined : {is_active:true});
                await refreshCrudTables(); return;
            }
            if (action === "toggle-student") {
                const student = state.students.find(s => s.student_id === id);
                if (!confirm(student.is_archived ? "Restore this learner?" : "Archive this learner? Classroom and parent access will be hidden; history is preserved.")) return;
                await RecordEditor.request(`/admin/students/${id}${student.is_archived ? "/status" : ""}`, student.is_archived ? "PATCH" : "DELETE", student.is_archived ? {is_archived:false} : undefined);
                await refreshCrudTables(); return;
            }
            let values, fields, path, title;
            if (action === "edit-user") {values = state.users.find(u => u.user_id === id); fields = userFields; path = `/admin/users/${id}`; title = "Edit account";}
            if (action === "edit-student") {values = state.students.find(s => s.student_id === id); fields = studentFields; path = `/admin/students/${id}`; title = "Edit learner";}
            if (action === "edit-assignment") {
                values = state.assignmentRows.find(a => a.assignment_id === id); path = `/admin/teacher-assignments/${id}`; title = "Edit teaching assignment";
                fields = [field("teacher_user_id", "Teacher", {options:state.users.filter(u => u.role === "TEACHER" && u.is_active).map(u => ({value:u.user_id,label:u.full_name}))}),
                    field("grade_level", "Grade"), field("stream", "Stream"), field("subject_name", "Subject")];
            }
            if (action === "edit-link") {
                values = state.linkRows.find(l => l.id === id); path = `/admin/parent-links/${id}`; title = "Edit parent link";
                fields = [field("parent_user_id", "Parent", {options:state.users.filter(u => u.role === "PARENT" && u.is_active).map(u => ({value:u.user_id,label:u.full_name}))}),
                    field("student_id", "Learner", {options:state.students.filter(s => !s.is_archived).map(s => ({value:s.student_id,label:`${s.first_name} ${s.last_name} (${s.admission_number})`}))}),
                    field("relationship_type", "Relationship", {options:["Mother", "Father", "Guardian", "Other"]})];
            }
            if (!values) return;
            RecordEditor.open({title, fields, values, onSave:async payload => {
                if (action === "edit-user") payload.password = payload.password || null;
                if (action === "edit-student") {payload.stream ||= null; payload.gender ||= null;}
                await RecordEditor.request(path, "PUT", payload);
                if (action === "edit-user" && id === Auth.getUser().user_id && (payload.password || payload.role !== Auth.getUser().role)) {Auth.logout(); return;}
                await refreshCrudTables(); showToast("Changes saved.", "success");
            }});
        } catch (error) {showToast(error.message, "error");}
    });

});
