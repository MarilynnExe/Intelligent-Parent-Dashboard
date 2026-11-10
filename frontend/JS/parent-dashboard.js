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
        requestId: 0,
        loading: false,
    };

    // -------------------------------------------------------------------------
    // 3. UI Helpers: Toasts & Tab Navigation
    // -------------------------------------------------------------------------
    
    function escapeHtml(str) {
        if (!str && str !== 0) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function showToast(message, type = "info", duration = 4000) {
        const container = document.getElementById("toast-container");
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;

        const icon = type === "error" ? "❌" : "ℹ️";
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
    const initialPeriod = currentAcademicPeriod();
    document.getElementById("parent-year").value = initialPeriod.academic_year;
    document.getElementById("parent-term").value = initialPeriod.term;
    function selectedPeriod() {
        const yearInput = document.getElementById("parent-year");
        if (!yearInput.reportValidity()) return null;
        return {term: document.getElementById("parent-term").value, academic_year: yearInput.value};
    }
    function refreshChild(quiet = false) {
        if (state.activeChild) loadChildData(state.activeChild, quiet);
        else loadRegisteredChildren();
    }
    document.getElementById("parent-refresh").addEventListener("click", () => refreshChild());
    ["parent-year", "parent-term"].forEach(id => document.getElementById(id).addEventListener("change", () => refreshChild()));
    setInterval(() => {
        if (!document.hidden && !state.loading && state.activeChild) refreshChild(true);
    }, 30000);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden && !state.loading && state.activeChild) refreshChild(true);
    });

    async function loadChildData(child, quiet = false) {
        const period = selectedPeriod();
        if (!period) return;
        const requestId = ++state.requestId;
        state.loading = true;
        const loading = document.getElementById("global-loading");
        const mainContent = document.getElementById("main-content");
        const refreshStatus = document.getElementById("parent-refresh-status");
        refreshStatus.textContent = "Refreshing…";
        if (!quiet) {
            loading.style.display = "block";
            mainContent.style.display = "none";
        }
        document.getElementById("child-full-name").textContent = `${child.first_name} ${child.last_name}`;
        document.getElementById("child-adm").textContent = `ADM: ${child.admission_number}`;
        document.getElementById("child-grade-stream").textContent = `Class: ${child.grade_level} ${child.stream || ''}`;
        document.getElementById("child-relation").textContent = `Relationship: ${child.relationship_type || 'Parent'}`;
        document.getElementById("child-profile-banner").style.display = "flex";
        const query = new URLSearchParams(period);
        try {
            const [analyticsRes, progressRes, assignmentsRes] = await Promise.all([
                apiFetch(`/analytics/student/${child.student_id}?${query}`),
                apiFetch(`/parent/children/${child.student_id}/progress?${query}`),
                apiFetch(`/parent/children/${child.student_id}/assignments?${query}`),
            ]);
            if (requestId !== state.requestId) return;
            if (!progressRes.ok) throw new Error("Unable to load learner progress. Please refresh to retry.");
            if (!analyticsRes.ok && analyticsRes.status !== 404) throw new Error("Unable to load analytics. Please refresh to retry.");
            const progress = await progressRes.json();
            const analytics = analyticsRes.ok ? await analyticsRes.json() : null;
            if (requestId !== state.requestId) return;
            renderEmptyAnalytics();
            const current = analytics && analytics.is_current && progress.freshness === "current"
                && analytics.calculated_at === progress.calculated_at;
            if (current) renderAnalytics(analytics);
            const calculatedAt = progress.calculated_at;
            const timestamp = calculatedAt ? new Date(calculatedAt.endsWith("Z") ? calculatedAt : calculatedAt + "Z").toLocaleString() : "Never";
            document.getElementById("analytics-freshness").textContent =
                `${period.term} ${period.academic_year} · Analytics: ${progress.freshness}. Last calculated: ${timestamp}. ` +
                (progress.freshness === "current" ? "" : (progress.freshness_message || "Ask the teacher to retry calculation."));
            if (!current) {
                document.getElementById("hero-risk-probability").textContent = progress.freshness === "pending" ? "Pending" : "Unavailable";
                document.getElementById("hero-risk-badge").textContent = "Calculation needed";
                document.getElementById("badge-overall-status").textContent = "Calculation needed";
                document.getElementById("parent-recommendations-list").textContent = progress.freshness_message || "Ask the teacher to recalculate for this period.";
            }
            document.getElementById("hero-period").textContent = `— ${period.term} ${period.academic_year}`;
            document.getElementById("stat-average-label").textContent = `${period.term} Academic Average`;
            document.getElementById("stat-academic-average").textContent = progress.overall_average == null ? "—" : `${progress.overall_average.toFixed(1)}%`;
            renderAssessments(progress.assessments);
            renderProgress(progress);
            if (assignmentsRes.ok) {
                const assignments = await assignmentsRes.json();
                if (requestId !== state.requestId) return;
                AssignmentParent.render(assignments);
            } else {AssignmentParent.error();}
            refreshStatus.textContent = `Updated ${new Date().toLocaleTimeString()}. Refreshes every 30 seconds.`;
        } catch (err) {
            if (requestId !== state.requestId) return;
            // Clear cached guidance: a failed refresh must never look like current information.
            renderEmptyAnalytics();
            renderEmptyAssessments();
            AssignmentParent.error();
            document.getElementById("assessment-progress").textContent = "Progress unavailable. Refresh to retry.";
            document.getElementById("attendance-summary").textContent = "Attendance unavailable.";
            document.getElementById("attendance-trend").replaceChildren();
            document.getElementById("analytics-freshness").textContent = "Could not verify freshness. Refresh to retry.";
            refreshStatus.textContent = err.message;
        } finally {
            if (requestId === state.requestId) {
                state.loading = false;
                loading.style.display = "none";
                mainContent.style.display = "block";
            }
        }
    }

    function renderProgress(data) {
        const totals = data.attendance_totals;
        document.getElementById("stat-absences").textContent = `${totals.Absent} Days`;
        document.getElementById("attendance-count-big").textContent = totals.Absent;
        document.getElementById("attendance-summary").textContent = totals.recorded
            ? `${totals.recorded} recorded days: ${totals.Present} present, ${totals.Absent} absent, ${totals.Late} late, ${totals.Excused} excused.`
            : "No attendance records for this period.";
        document.getElementById("attendance-trend").innerHTML = data.attendance_months.length
            ? data.attendance_months.map(row => `<tr><td>${escapeHtml(row.month)}</td><td>${row.present}</td><td>${row.absent}</td><td>${row.late}</td><td>${row.excused}</td><td>${row.recorded}</td></tr>`).join("")
            : '<tr><td colspan="6">No recorded attendance yet.</td></tr>';
        const bySubject = new Map();
        data.assessments.forEach(item => {
            if (!bySubject.has(item.subject_name)) bySubject.set(item.subject_name, []);
            bySubject.get(item.subject_name).push(item);
        });
        const chart = document.getElementById("assessment-progress");
        chart.innerHTML = [...bySubject].map(([subject, items]) => `<div class="progress-subject"><h4>${escapeHtml(subject)}</h4>${items.map(item => `
            <div class="score-observation"><span>${escapeHtml(item.assessment_date)} · ${escapeHtml(item.assessment_type)}</span>
            <meter min="0" max="100" value="${item.percentage}" aria-label="${escapeHtml(subject)} ${escapeHtml(item.assessment_date)}">${item.percentage}%</meter>
            <strong>${item.percentage.toFixed(1)}%</strong></div>`).join("")}</div>`).join("") || "No assessments for this period.";
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
                        No additional intervention recommendations were generated for this period.
                    </p>
                </div>
            `;
            return;
        }

        data.recommendations.forEach(rec => {
            const priorityClass = rec.priority === "High" ? "high" : (rec.priority === "Medium" ? "medium" : "low");
            const lp = rec.learning_path;

            let alignmentBadgeHtml = "";
            let lpDetailsHtml = "";

            if (lp) {
                if (lp.alignment_type === "CURRICULUM_ALIGNED") {
                    alignmentBadgeHtml = `<span class="alignment-pill pill-curriculum" title="${escapeHtml(lp.alignment_source || 'KICD Junior Secondary Curriculum')}">✓ CBC Curriculum Aligned</span>`;
                } else {
                    alignmentBadgeHtml = `<span class="alignment-pill pill-provisional" title="${escapeHtml(lp.alignment_source || 'Provisional Learning Support')}">ℹ️ Provisional Learning Support</span>`;
                }

                lpDetailsHtml = `
                    <div class="lp-detail-container">
                        <div class="lp-topic">🎯 <strong>Learning Area & Skill:</strong> ${escapeHtml(lp.subject_name)} — <em>${escapeHtml(lp.topic_competency)}</em></div>
                        <div class="lp-reason">💡 <strong>Why this was suggested:</strong> ${escapeHtml(lp.reason)}</div>
                        <div class="lp-activity-box">
                            <div class="lp-activity-title">📌 <strong>Learning Activity:</strong> ${escapeHtml(lp.activity_title)}</div>
                            <div class="lp-activity-desc">${escapeHtml(lp.activity_description)}</div>
                            ${lp.suggested_duration ? `<div class="lp-duration">⏱️ <strong>Frequency / Duration:</strong> ${escapeHtml(lp.suggested_duration)}</div>` : ''}
                        </div>
                        <div class="lp-resource-box">
                            <div class="lp-resource-header">
                                <span>📖 <strong>Resource:</strong> ${escapeHtml(lp.resource_title)}</span>
                                ${lp.resource_url ? `<a href="${escapeHtml(lp.resource_url)}" target="_blank" rel="noopener noreferrer" class="btn-resource-link">🔗 Open Resource ↗</a>` : ''}
                            </div>
                            ${lp.resource_description ? `<div class="lp-resource-desc">${escapeHtml(lp.resource_description)}</div>` : ''}
                        </div>
                        ${lp.recommended_next_step ? `<div class="lp-next-step">🚀 <strong>Recommended Next Step:</strong> ${escapeHtml(lp.recommended_next_step)}</div>` : ''}
                    </div>
                `;
            }

            const div = document.createElement("div");
            div.className = "rec-item";
            div.innerHTML = `
                <div class="rec-item-header">
                    <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                        <span class="rec-priority ${priorityClass}">Priority: ${rec.priority}</span>
                        <span class="rec-target-badge">For: ${rec.target_audience}</span>
                    </div>
                    ${alignmentBadgeHtml}
                </div>
                <div class="rec-body">${escapeHtml(rec.recommendation_text)}</div>
                ${lpDetailsHtml}
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
        document.getElementById("stat-absences").textContent = "—";
        document.getElementById("attendance-count-big").textContent = "—";

        const recList = document.getElementById("parent-recommendations-list");
        recList.innerHTML = `
            <div class="rec-item" style="background: #f8fafc;">
                <p style="color: var(--text-muted);">
                    Analytics are not available for this period. Ask the teacher to record assessments and retry calculation.
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
                <td style="font-weight: 700; color: var(--text-heading);">${escapeHtml(item.subject_name)}</td>
                <td><span style="font-size: 0.85rem;">${escapeHtml(item.assessment_type)}</span></td>
                <td><span style="font-size: 0.85rem;">${escapeHtml(item.term)} ${escapeHtml(item.academic_year)}</span></td>
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