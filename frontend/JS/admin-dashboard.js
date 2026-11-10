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
            tbody.innerHTML = stateRow(6, "No users registered yet.");
            return;
        }
        tbody.innerHTML = state.users.map(u => `
            <tr>
                <td style="color: var(--text-muted);">${u.user_id}</td>
                <td><strong>${escapeHtml(u.full_name)}</strong></td>
                <td>${escapeHtml(u.email_or_username)}</td>
                <td>${rolePill(u.role)}</td>
                <td>${escapeHtml(u.phone_number || "—")}</td>
                <td>${formatDate(u.created_at)}</td>
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
        const teachers = state.users.filter(u => u.role === "TEACHER");
        const parents = state.users.filter(u => u.role === "PARENT");

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
            tbody.innerHTML = stateRow(6, err.message, true);
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
            tbody.innerHTML = stateRow(7, "No learners enrolled yet.");
            return;
        }
        tbody.innerHTML = state.students.map(s => `
            <tr>
                <td style="color: var(--text-muted);">${s.student_id}</td>
                <td>${escapeHtml(s.admission_number)}</td>
                <td><strong>${escapeHtml(s.first_name)} ${escapeHtml(s.last_name)}</strong></td>
                <td>${escapeHtml(s.grade_level)} ${escapeHtml(s.stream || "")}</td>
                <td>${escapeHtml(s.gender || "—")}</td>
                <td>${escapeHtml(s.date_of_birth)}</td>
                <td>${formatDate(s.created_at)}</td>
            </tr>
        `).join("");
    }

    async function loadStudents() {
        const tbody = document.getElementById("students-tbody");
        try {
            state.students = await apiJson("/admin/students", {}, "Failed to load learners.");
            renderStudents();
            fillSelect("link-student-select", state.students,
                state.students.length ? "Select learner..." : "No learners enrolled yet",
                s => ({
                    value: s.student_id,
                    label: `${s.first_name} ${s.last_name} (${s.admission_number} • ${s.grade_level} ${s.stream || ""})`,
                }));
        } catch (err) {
            console.error("Students Error:", err);
            tbody.innerHTML = stateRow(7, err.message, true);
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
    // 9. Bootstrap Dashboard
    // -------------------------------------------------------------------------
    loadStats();
    loadUsers();
    loadStudents();
    loadAssignments();
    loadParentLinks();

});
