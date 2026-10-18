/**
 * Parent Dashboard Controller
 * Connects the Parent Dashboard UI to the live FastAPI backend:
 *   - GET /api/parent/my-children
 *   - GET /api/parent/children/{student_id}/assessments
 *   - GET /api/analytics/student/{student_id}
 */

document.addEventListener("DOMContentLoaded", () => {

    // -------------------------------------------------------------------------
    // 1. Authentication & Role Guard
    // -------------------------------------------------------------------------
    if (!Auth.requireRole("PARENT")) {
        return;
    }

    const currentUser = Auth.getUser();
    if (currentUser && currentUser.full_name) {
        document.getElementById("user-display-name").textContent = currentUser.full_name;
    }

    // Logout
    document.getElementById("logout-btn").addEventListener("click", () => {
        Auth.logout();
    });

    // -------------------------------------------------------------------------
    // 2. State Management
    // -------------------------------------------------------------------------
    let state = {
        children: [],
        activeChild: null,
    };

    // -------------------------------------------------------------------------
    // 3. UI Helpers: Toasts & Tab Navigation
    // -------------------------------------------------------------------------
    function showToast(message, type = "info", duration = 4000) {
        const container = document.getElementById("toast-container");
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;

        const icon = type === "error" ? "❌" : "ℹ️";
        toast.innerHTML = `
            <span style="font-size: 1.1rem;">${icon}</span>
            <div style="flex: 1;">
                <div style="font-size: 0.88rem; font-weight: 600;">${message}</div>
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

    // Tab Navigation
    const tabs = document.querySelectorAll(".sub-nav-btn");
    const sections = document.querySelectorAll(".content-section");

    function switchTab(targetSectionId) {
        tabs.forEach(btn => {
            btn.classList.toggle("active", btn.getAttribute("data-target") === targetSectionId);
        });
        sections.forEach(sec => {
            sec.classList.toggle("active", sec.id === targetSectionId);
        });
    }

    tabs.forEach(btn => {
        btn.addEventListener("click", () => {
            const target = btn.getAttribute("data-target");
            switchTab(target);
        });
    });

    // -------------------------------------------------------------------------
    // 4. Load Parent's Verified Children
    // -------------------------------------------------------------------------
    async function loadRegisteredChildren() {
        const loading = document.getElementById("global-loading");
        const emptyState = document.getElementById("global-empty");
        const mainContent = document.getElementById("main-content");
        const childSelector = document.getElementById("child-selector");
        const childCountEl = document.getElementById("child-selector-count");

        loading.style.display = "block";
        emptyState.style.display = "none";
        mainContent.style.display = "none";

        try {
            const res = await apiFetch("/parent/my-children");
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Unable to fetch linked learners.");
            }

            const children = await res.json();
            state.children = children;

            if (!children || children.length === 0) {
                loading.style.display = "none";
                emptyState.style.display = "block";
                childSelector.innerHTML = `<option value="" disabled selected>No registered children found</option>`;
                childCountEl.textContent = "0 Learners";
                return;
            }

            // Populate Dropdown
            childSelector.innerHTML = "";
            children.forEach((child, index) => {
                const opt = document.createElement("option");
                opt.value = index;
                opt.textContent = `${child.first_name} ${child.last_name} (${child.grade_level} ${child.stream || ''} • ${child.admission_number})`;
                childSelector.appendChild(opt);
            });

            childCountEl.textContent = `${children.length} Registered Learner${children.length > 1 ? 's' : ''}`;

            // Select first child by default
            state.activeChild = children[0];
            childSelector.value = 0;

            await loadChildData(children[0]);

        } catch (err) {
            console.error("Parent Children Error:", err);
            loading.style.display = "none";
            showToast(err.message, "error");
        }
    }

    // Change Child Selection
    document.getElementById("child-selector").addEventListener("change", (e) => {
        const index = parseInt(e.target.value);
        if (!isNaN(index) && state.children[index]) {
            state.activeChild = state.children[index];
            loadChildData(state.children[index]);
        }
    });

    // -------------------------------------------------------------------------
    // 5. Load Active Child's Analytics & Assessments
    // -------------------------------------------------------------------------
    async function loadChildData(child) {
        const loading = document.getElementById("global-loading");
        const mainContent = document.getElementById("main-content");
        const banner = document.getElementById("child-profile-banner");

        loading.style.display = "block";
        mainContent.style.display = "none";

        // Update Child Profile Banner
        document.getElementById("child-full-name").textContent = `${child.first_name} ${child.last_name}`;
        document.getElementById("child-adm").textContent = `ADM: ${child.admission_number}`;
        document.getElementById("child-grade-stream").textContent = `Class: ${child.grade_level} ${child.stream || ''}`;
        document.getElementById("child-relation").textContent = `Relationship: ${child.relationship_type || 'Parent'}`;
        banner.style.display = "flex";

        try {
            // Parallel fetch: Analytics and Assessments
            const [analyticsRes, assessmentsRes] = await Promise.all([
                apiFetch(`/analytics/student/${child.student_id}`),
                apiFetch(`/parent/children/${child.student_id}/assessments`)
            ]);

            // Handle Analytics
            if (analyticsRes.ok) {
                const analytics = await analyticsRes.json();
                renderAnalytics(analytics);
            } else {
                renderEmptyAnalytics();
            }

            // Handle Assessments
            if (assessmentsRes.ok) {
                const assessments = await assessmentsRes.json();
                renderAssessments(assessments);
            } else {
                renderEmptyAssessments();
            }

            loading.style.display = "none";
            mainContent.style.display = "block";

        } catch (err) {
            console.error("Child Data Error:", err);
            loading.style.display = "none";
            mainContent.style.display = "block";
            showToast("Failed to load some learner metrics.", "error");
        }
    }

    // -------------------------------------------------------------------------
    // 6. Render Analytics & Expert Recommendations
    // -------------------------------------------------------------------------
    function renderAnalytics(data) {
        const prob = data.support_probability;
        const probPct = (prob !== null && prob !== undefined) ? (prob * 100).toFixed(1) + "%" : "—";
        const status = data.support_status || "Not Analyzed";

        // Hero Card
        document.getElementById("hero-risk-probability").textContent = probPct;
        const heroBadge = document.getElementById("hero-risk-badge");
        const heroFill = document.getElementById("hero-risk-fill");
        const headerBadge = document.getElementById("badge-overall-status");

        heroBadge.className = "status-pill";
        headerBadge.className = "status-pill";
        heroFill.className = "parent-risk-fill";
        heroFill.style.width = prob !== null ? probPct : "0%";

        if (status === "On Track") {
            heroBadge.classList.add("status-on-track");
            heroBadge.textContent = "● On Track";
            headerBadge.classList.add("status-on-track");
            headerBadge.textContent = "● On Track";
            heroFill.classList.add("fill-on-track");
        } else if (status === "Monitoring Suggested") {
            heroBadge.classList.add("status-monitoring");
            heroBadge.textContent = "● Monitoring Suggested";
            headerBadge.classList.add("status-monitoring");
            headerBadge.textContent = "● Monitoring Suggested";
            heroFill.classList.add("fill-monitoring");
        } else if (status === "Targeted Support Recommended") {
            heroBadge.classList.add("status-targeted");
            heroBadge.textContent = "● Targeted Support Recommended";
            headerBadge.classList.add("status-targeted");
            headerBadge.textContent = "● Targeted Support Recommended";
            heroFill.classList.add("fill-targeted");
        } else {
            heroBadge.classList.add("status-none");
            heroBadge.textContent = "● In Progress";
            headerBadge.classList.add("status-none");
            headerBadge.textContent = "● In Progress";
        }

        // Analytics are for the latest term the teacher calculated
        document.getElementById("hero-period").textContent = `— ${data.term} ${data.academic_year}`;
        document.getElementById("stat-average-label").textContent = `${data.term} Academic Average`;

        // Indicators
        document.getElementById("stat-academic-average").textContent =
            data.overall_average !== null ? `${data.overall_average.toFixed(1)}%` : "—";

        const pct = data.cohort_percentile;
        if (pct !== null && pct !== undefined) {
            document.getElementById("stat-cohort-percentile").textContent = `${pct.toFixed(1)}th`;
            document.getElementById("stat-cohort-desc").textContent =
                `Performing higher than ~${Math.round(pct)}% of class peers`;
        } else {
            document.getElementById("stat-cohort-percentile").textContent = "—";
            document.getElementById("stat-cohort-desc").textContent = "Peer comparison pending";
        }

        const absences = data.absences_count || 0;
        document.getElementById("stat-absences").textContent = `${absences} Days`;
        document.getElementById("attendance-count-big").textContent = absences;

        // Recommendations
        const recList = document.getElementById("parent-recommendations-list");
        recList.innerHTML = "";

        if (!data.recommendations || data.recommendations.length === 0) {
            recList.innerHTML = `
                <div class="rec-item" style="background: var(--pastel-green-bg); border-color: var(--pastel-green-border);">
                    <p style="color: var(--pastel-green-text); font-weight: 600;">
                        🌟 Your child is performing commendably on track. Continue positive reinforcement and encourage daily curiosity!
                    </p>
                </div>
            `;
            return;
        }

        data.recommendations.forEach(rec => {
            const priorityClass = rec.priority === "High" ? "high" : (rec.priority === "Medium" ? "medium" : "low");
            const div = document.createElement("div");
            div.className = "rec-item";
            div.innerHTML = `
                <div class="rec-item-header">
                    <span class="rec-priority ${priorityClass}">Priority: ${rec.priority}</span>
                    <span class="rec-target-badge">For: ${rec.target_audience}</span>
                </div>
                <div class="rec-body">${rec.recommendation_text}</div>
            `;
            recList.appendChild(div);
        });
    }

    function renderEmptyAnalytics() {
        document.getElementById("hero-risk-probability").textContent = "Pending";
        document.getElementById("hero-period").textContent = "";
        document.getElementById("hero-risk-badge").className = "status-pill status-none";
        document.getElementById("hero-risk-badge").textContent = "In Progress";
        document.getElementById("badge-overall-status").className = "status-pill status-none";
        document.getElementById("badge-overall-status").textContent = "In Progress";
        document.getElementById("hero-risk-fill").style.width = "0%";

        document.getElementById("stat-academic-average").textContent = "—";
        document.getElementById("stat-cohort-percentile").textContent = "—";
        document.getElementById("stat-cohort-desc").textContent = "Calculated after first term CATs";
        document.getElementById("stat-absences").textContent = "0 Days";
        document.getElementById("attendance-count-big").textContent = "0";

        const recList = document.getElementById("parent-recommendations-list");
        recList.innerHTML = `
            <div class="rec-item" style="background: #f8fafc;">
                <p style="color: var(--text-muted);">
                    Formative academic assessments are currently being collected by teachers. Early intervention analytics and recommendations will appear once Period 1 evaluations are finalized.
                </p>
            </div>
        `;
    }

    // -------------------------------------------------------------------------
    // 7. Render Assessments Table
    // -------------------------------------------------------------------------
    function renderAssessments(assessments) {
        const tbody = document.getElementById("assessments-tbody");
        if (!assessments || assessments.length === 0) {
            renderEmptyAssessments();
            return;
        }

        tbody.innerHTML = "";
        assessments.forEach(item => {
            const tr = document.createElement("tr");
            const isDeficient = item.percentage < 50;

            tr.innerHTML = `
                <td style="font-weight: 700; color: var(--text-heading);">${item.subject_name}</td>
                <td><span style="font-size: 0.85rem;">${item.assessment_type}</span></td>
                <td><span style="font-size: 0.85rem;">${item.term} ${item.academic_year}</span></td>
                <td>${item.score} / ${item.max_score}</td>
                <td>
                    <strong style="color: ${isDeficient ? 'var(--pastel-pink-text)' : 'var(--pastel-purple-text)'};">
                        ${item.percentage.toFixed(1)}%
                    </strong>
                </td>
                <td style="font-size: 0.85rem; color: var(--text-muted);">${item.assessment_date || '—'}</td>
            `;
            tbody.appendChild(tr);
        });
    }

    function renderEmptyAssessments() {
        const tbody = document.getElementById("assessments-tbody");
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="state-box">
                    <p>No assessment records entered yet for this learner.</p>
                </td>
            </tr>
        `;
    }

    // -------------------------------------------------------------------------
    // 8. Bootstrap Dashboard
    // -------------------------------------------------------------------------
    loadRegisteredChildren();

});