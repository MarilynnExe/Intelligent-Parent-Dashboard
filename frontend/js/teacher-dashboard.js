/**
 * Teacher Dashboard Controller
 * Connects the Teacher Dashboard UI to the live FastAPI backend:
 *   - GET  /api/teacher/assignments
 *   - GET  /api/teacher/students?grade_level=...&stream=...
 *   - POST /api/teacher/assessments
 *   - GET  /api/teacher/students/{id}/assessments
 *   - POST /api/teacher/attendance/bulk
 *   - POST /api/analytics/calculate/{student_id}
 *   - GET  /api/analytics/student/{student_id}
 */

document.addEventListener("DOMContentLoaded", () => {

    // -------------------------------------------------------------------------
    // 1. Authentication & Role Guard
    // -------------------------------------------------------------------------
    if (!Auth.requireRole("TEACHER")) {
        return;
    }

    const currentUser = Auth.getUser();
    if (currentUser && currentUser.full_name) {
        document.getElementById("user-display-name").textContent = currentUser.full_name;
        document.getElementById("welcome-heading").textContent = `Welcome, ${currentUser.full_name}`;
    }

    // Logout
    document.getElementById("logout-btn").addEventListener("click", () => {
        Auth.logout();
    });

    // -------------------------------------------------------------------------
    // 2. State Management
    // -------------------------------------------------------------------------
    let state = {
        assignments: [],
        activeAssignment: null, // { grade_level, stream, subject_name }
        students: [],
        analyticsCache: {},     // student_id -> analytics data
        attendanceRecords: {},  // student_id -> { status: "Present"|"Absent"|"Late", remarks: "" }
        activeStudentForModal: null,
        period: currentAcademicPeriod(), // { term, academic_year } used for analytics
    };

    // -------------------------------------------------------------------------
    // 3. UI Helpers: Toasts, Modals, Tab Switching
    // -------------------------------------------------------------------------
    function showToast(message, type = "info", duration = 4000) {
        const container = document.getElementById("toast-container");
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;

        const icon = type === "success" ? "✅" : (type === "error" ? "❌" : "ℹ️");
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

    // Default Dates (Today)
    const todayISO = new Date().toISOString().split("T")[0];
    const assessmentDateInput = document.getElementById("assessment-date");
    const attendanceDateInput = document.getElementById("attendance-date");
    if (assessmentDateInput) assessmentDateInput.value = todayISO;
    if (attendanceDateInput) attendanceDateInput.value = todayISO;
    document.getElementById("behaviour-date").value = todayISO;

    // -------------------------------------------------------------------------
    // Analysis Period (term + year) shared by roster, analytics and forms
    // -------------------------------------------------------------------------
    const periodTermSelect = document.getElementById("period-term");
    const periodYearInput = document.getElementById("period-year");

    function applyPeriodToForms() {
        const { term, academic_year } = state.period;
        document.getElementById("assessment-term").value = term;
        document.getElementById("assessment-year").value = academic_year;
        document.getElementById("roster-average-heading").textContent = `${term} Average`;
        document.getElementById("modal-stat-average-sub").textContent = `${term} ${academic_year} assessment mean`;
        document.getElementById("observation-period").textContent = `(${term} ${academic_year})`;
    }

    function onPeriodChange() {
        const year = periodYearInput.value.trim();
        if (!/^\d{4}$/.test(year)) {
            showToast("Enter a four-digit academic year.", "error");
            return;
        }
        state.period = { term: periodTermSelect.value, academic_year: year };
        state.analyticsCache = {};
        applyPeriodToForms();
        if (state.activeAssignment) loadClassStudents();
    }

    periodTermSelect.value = state.period.term;
    periodYearInput.value = state.period.academic_year;
    periodTermSelect.addEventListener("change", onPeriodChange);
    periodYearInput.addEventListener("change", onPeriodChange);
    applyPeriodToForms();

    // -------------------------------------------------------------------------
    // 4. Initial Data Loading: Assignments
    // -------------------------------------------------------------------------
    async function loadAssignments() {
        const classSelect = document.getElementById("class-selector");
        classSelect.innerHTML = `<option value="" disabled selected>Loading teaching assignments...</option>`;

        try {
            const res = await apiFetch("/teacher/assignments");
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to load class assignments.");
            }

            const data = await res.json();
            state.assignments = data;

            if (!data || data.length === 0) {
                classSelect.innerHTML = `<option value="" disabled selected>No assigned classes found</option>`;
                renderEmptyRoster("No teaching assignments found. Please contact administration.");
                return;
            }

            // Populate Class Selector
            classSelect.innerHTML = "";
            data.forEach((item, index) => {
                const opt = document.createElement("option");
                opt.value = index;
                opt.textContent = `${item.grade_level} — Stream ${item.stream} (${item.subject_name})`;
                classSelect.appendChild(opt);
            });

            // Populate Subject Selector in Assessment Form
            populateSubjectDropdown(data);

            // Select first assignment by default
            state.activeAssignment = data[0];
            classSelect.value = 0;

            await loadClassStudents();

        } catch (err) {
            console.error("Assignments Error:", err);
            showToast(`Could not load class assignments: ${err.message}`, "error");
            renderEmptyRoster(`Error loading assignments: ${err.message}`);
        }
    }

    function populateSubjectDropdown(assignments) {
        const subjectSelect = document.getElementById("assessment-subject");
        if (!subjectSelect) return;

        subjectSelect.innerHTML = `<option value="" disabled selected>Select subject...</option>`;
        const uniqueSubjects = Array.from(new Set(assignments.map(a => a.subject_name)));
        uniqueSubjects.forEach(subj => {
            const opt = document.createElement("option");
            opt.value = subj;
            opt.textContent = subj;
            subjectSelect.appendChild(opt);
        });

        if (uniqueSubjects.length === 1) {
            subjectSelect.value = uniqueSubjects[0];
        }
    }

    // Change Class Selection
    document.getElementById("class-selector").addEventListener("change", (e) => {
        const index = parseInt(e.target.value);
        if (!isNaN(index) && state.assignments[index]) {
            state.activeAssignment = state.assignments[index];
            loadClassStudents();
        }
    });

    document.getElementById("btn-refresh-roster").addEventListener("click", () => {
        if (state.activeAssignment) {
            loadClassStudents();
            showToast("Refreshing class roster...", "info", 1500);
        }
    });

    // -------------------------------------------------------------------------
    // 5. Load Class Students & Roster
    // -------------------------------------------------------------------------
    async function loadClassStudents() {
        if (!state.activeAssignment) return;

        const { grade_level, stream } = state.activeAssignment;
        const tbody = document.getElementById("roster-tbody");
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="state-box">
                    <div class="state-spinner"></div>
                    <p>Loading learners for ${grade_level} ${stream}...</p>
                </td>
            </tr>
        `;

        // Update Subheading
        document.getElementById("roster-heading").textContent = `${grade_level} — Stream ${stream}`;
        document.getElementById("roster-subheading").textContent =
            `Subject: ${state.activeAssignment.subject_name} • ${state.period.term} ${state.period.academic_year}`;

        try {
            const url = `/teacher/students?grade_level=${encodeURIComponent(grade_level)}&stream=${encodeURIComponent(stream)}`;
            const res = await apiFetch(url);
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to load student roster.");
            }

            const students = await res.json();
            state.students = students;

            if (!students || students.length === 0) {
                renderEmptyRoster(`No learners enrolled in ${grade_level} ${stream}.`);
                updateStatsStrip([], {});
                populateAssessmentStudentDropdown([]);
                renderAttendanceRegister([]);
                return;
            }

            // Populate Student Dropdown for Assessment Form
            populateAssessmentStudentDropdown(students);

            // Populate Attendance Register
            renderAttendanceRegister(students);

            // Render Roster Rows
            renderRosterRows(students);

            // Fetch any existing analytics for students to display cached risk badges
            await loadExistingAnalyticsForRoster(students);

            // Load recent class assessments
            loadRecentAssessments(students);

        } catch (err) {
            console.error("Students Roster Error:", err);
            renderEmptyRoster(`Failed to load students: ${err.message}`);
            showToast(err.message, "error");
        }
    }

    function renderEmptyRoster(message) {
        const tbody = document.getElementById("roster-tbody");
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="state-box">
                    <p style="font-size: 1rem; color: var(--text-muted);">${message}</p>
                </td>
            </tr>
        `;
        document.getElementById("stat-total-students").textContent = "0";
        document.getElementById("stat-targeted-count").textContent = "0";
        document.getElementById("stat-monitoring-count").textContent = "0";
        document.getElementById("stat-ontrack-count").textContent = "0";
    }

    function renderRosterRows(students) {
        const tbody = document.getElementById("roster-tbody");
        tbody.innerHTML = "";

        students.forEach((student, idx) => {
            const tr = document.createElement("tr");
            tr.id = `roster-row-${student.student_id}`;

            tr.innerHTML = `
                <td style="color: var(--text-muted); font-size: 0.85rem;">${idx + 1}</td>
                <td class="student-adm-cell">${student.admission_number}</td>
                <td class="student-name-cell">${student.first_name} ${student.last_name}</td>
                <td><span style="font-size: 0.85rem;">${student.grade_level} ${student.stream || ""}</span></td>
                <td id="cell-avg-${student.student_id}">
                    <span style="color: var(--text-muted);">—</span>
                </td>
                <td id="cell-status-${student.student_id}">
                    <span class="status-pill status-none">Not Yet Analyzed</span>
                </td>
                <td style="text-align: right;">
                    <div style="display: inline-flex; gap: 0.5rem; justify-content: flex-end;">
                        <button class="btn btn-purple btn-sm btn-analyze"
                                data-student-id="${student.student_id}"
                                data-student-name="${student.first_name} ${student.last_name}"
                                data-student-adm="${student.admission_number}"
                                title="Run CatBoost early-warning model">
                            ⚡ Analyze Risk
                        </button>
                        <button class="btn btn-outline-purple btn-sm btn-quick-grade"
                                data-student-id="${student.student_id}"
                                title="Record assessment for this learner">
                            + Grade
                        </button>
                    </div>
                </td>
            `;

            tbody.appendChild(tr);
        });

        // Attach action handlers
        tbody.querySelectorAll(".btn-analyze").forEach(btn => {
            btn.addEventListener("click", () => {
                const sId = parseInt(btn.getAttribute("data-student-id"));
                const sName = btn.getAttribute("data-student-name");
                const sAdm = btn.getAttribute("data-student-adm");
                openAnalyticsModal(sId, sName, sAdm);
            });
        });

        tbody.querySelectorAll(".btn-quick-grade").forEach(btn => {
            btn.addEventListener("click", () => {
                const sId = btn.getAttribute("data-student-id");
                const select = document.getElementById("assessment-student-id");
                if (select) select.value = sId;
                switchTab("section-assessments");
                showToast("Learner selected in assessment form.", "info", 2000);
            });
        });

        document.getElementById("stat-total-students").textContent = students.length;
    }

    async function loadExistingAnalyticsForRoster(students) {
        let onTrack = 0;
        let monitoring = 0;
        let targeted = 0;

        for (const s of students) {
            try {
                const res = await apiFetch(`/analytics/student/${s.student_id}?${periodQuery()}`);
                if (res.ok) {
                    const data = await res.json();
                    state.analyticsCache[s.student_id] = data;

                    // Update Average Cell
                    const avgCell = document.getElementById(`cell-avg-${s.student_id}`);
                    if (avgCell && data.overall_average !== null && data.overall_average !== undefined) {
                        avgCell.innerHTML = `<strong>${data.overall_average.toFixed(1)}%</strong>`;
                    }

                    // Update Status Cell
                    const statusCell = document.getElementById(`cell-status-${s.student_id}`);
                    if (statusCell && data.support_status) {
                        statusCell.innerHTML = renderStatusPill(data.support_status, data.support_probability);

                        if (data.support_status === "On Track") onTrack++;
                        else if (data.support_status === "Monitoring Suggested") monitoring++;
                        else if (data.support_status === "Targeted Support Recommended") targeted++;
                    }
                }
            } catch (err) {
                // Silently ignore 404s for students not yet analyzed
            }
        }

        updateStatsStrip(students, { onTrack, monitoring, targeted });
    }

    function periodQuery() {
        return new URLSearchParams(state.period).toString();
    }

    function renderStatusPill(status, prob) {
        const probText = (prob !== null && prob !== undefined)
            ? ` (${(prob * 100).toFixed(1)}%)`
            : "";

        if (status === "On Track") {
            return `<span class="status-pill status-on-track">● On Track${probText}</span>`;
        } else if (status === "Monitoring Suggested") {
            return `<span class="status-pill status-monitoring">● Monitoring Suggested${probText}</span>`;
        } else if (status === "Targeted Support Recommended") {
            return `<span class="status-pill status-targeted">● Targeted Support${probText}</span>`;
        }
        return `<span class="status-pill status-none">Not Yet Analyzed</span>`;
    }

    function updateStatsStrip(students, counts = {}) {
        document.getElementById("stat-total-students").textContent = students.length;
        document.getElementById("stat-ontrack-count").textContent = counts.onTrack !== undefined ? counts.onTrack : "—";
        document.getElementById("stat-monitoring-count").textContent = counts.monitoring !== undefined ? counts.monitoring : "—";
        document.getElementById("stat-targeted-count").textContent = counts.targeted !== undefined ? counts.targeted : "—";
    }

    // -------------------------------------------------------------------------
    // 6. Assessment Form Implementation
    // -------------------------------------------------------------------------
    function populateAssessmentStudentDropdown(students) {
        // Learner pickers on the assessment and behaviour tabs share the class roster
        ["assessment-student-id", "notes-student-id"].forEach(id => {
            const select = document.getElementById(id);
            if (!select) return;

            select.innerHTML = `<option value="" disabled selected>Select learner...</option>`;
            students.forEach(s => {
                const opt = document.createElement("option");
                opt.value = s.student_id;
                opt.textContent = `${s.first_name} ${s.last_name} (${s.admission_number})`;
                select.appendChild(opt);
            });
        });
        resetLearnerHistory();
    }

    // Live Percentage Preview
    const scoreInput = document.getElementById("assessment-score");
    const maxScoreInput = document.getElementById("assessment-max-score");
    const pctPreview = document.getElementById("assessment-pct-preview");

    function updateScorePreview() {
        const score = parseFloat(scoreInput.value);
        const maxScore = parseFloat(maxScoreInput.value);
        if (!isNaN(score) && !isNaN(maxScore) && maxScore > 0) {
            const pct = ((score / maxScore) * 100).toFixed(1);
            pctPreview.textContent = `${pct}%`;
            pctPreview.style.color = pct < 50 ? "var(--pastel-pink-text)" : "var(--pastel-purple-text)";
        } else {
            pctPreview.textContent = "—";
        }
    }

    scoreInput.addEventListener("input", updateScorePreview);
    maxScoreInput.addEventListener("input", updateScorePreview);

    // Form Submission
    const assessmentForm = document.getElementById("assessment-form");
    const saveAssessmentBtn = document.getElementById("btn-save-assessment");

    // Reset restores HTML defaults; put the selected period back afterwards
    assessmentForm.addEventListener("reset", () => setTimeout(applyPeriodToForms, 0));

    assessmentForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const studentId = parseInt(document.getElementById("assessment-student-id").value);
        const subject = document.getElementById("assessment-subject").value;
        const term = document.getElementById("assessment-term").value;
        const academicYear = document.getElementById("assessment-year").value.trim();
        const assessmentType = document.getElementById("assessment-type").value;
        const score = parseFloat(scoreInput.value);
        const maxScore = parseFloat(maxScoreInput.value);
        const assessmentDate = document.getElementById("assessment-date").value;

        // Validation
        if (!studentId) {
            showToast("Please select a student.", "error");
            return;
        }
        if (!subject) {
            showToast("Please select an assigned subject.", "error");
            return;
        }
        if (isNaN(score) || score < 0) {
            showToast("Score must be a positive number.", "error");
            return;
        }
        if (isNaN(maxScore) || maxScore <= 0) {
            showToast("Maximum score must be greater than zero.", "error");
            return;
        }
        if (score > maxScore) {
            showToast(`Score (${score}) cannot exceed maximum score (${maxScore}).`, "error");
            return;
        }

        const payload = {
            student_id: studentId,
            subject_name: subject,
            academic_year: academicYear,
            term: term,
            assessment_type: assessmentType,
            score: score,
            max_score: maxScore,
            assessment_date: assessmentDate || null
        };

        saveAssessmentBtn.disabled = true;
        saveAssessmentBtn.textContent = "Saving assessment...";

        try {
            const res = await apiFetch("/teacher/assessments", {
                method: "POST",
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || "Failed to record assessment.");
            }

            showToast(
                `Assessment recorded successfully: ${data.percentage}% in ${data.subject_name}!`,
                "success"
            );

            // Reset score inputs
            scoreInput.value = "";
            pctPreview.textContent = "—";

            // Refresh recent assessments list
            loadRecentAssessments(state.students);

            // Re-fetch analytics for this student to update roster average
            try {
                const aRes = await apiFetch(`/analytics/student/${studentId}?${periodQuery()}`);
                if (aRes.ok) {
                    const aData = await aRes.json();
                    state.analyticsCache[studentId] = aData;
                    const avgCell = document.getElementById(`cell-avg-${studentId}`);
                    if (avgCell && aData.overall_average) {
                        avgCell.innerHTML = `<strong>${aData.overall_average.toFixed(1)}%</strong>`;
                    }
                }
            } catch (_) {}

        } catch (err) {
            console.error("Save Assessment Error:", err);
            showToast(`Error: ${err.message}`, "error");
        } finally {
            saveAssessmentBtn.disabled = false;
            saveAssessmentBtn.textContent = "💾 Save Assessment Record";
        }
    });

    // -------------------------------------------------------------------------
    // 7. Recent Assessments Viewer
    // -------------------------------------------------------------------------
    async function loadRecentAssessments(students) {
        const tbody = document.getElementById("recent-assessments-tbody");
        if (!students || students.length === 0) return;

        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="state-box">
                    <div class="state-spinner" style="width: 24px; height: 24px;"></div>
                    <p>Loading recent class assessments...</p>
                </td>
            </tr>
        `;

        const allAssessments = [];
        const studentMap = {};
        students.forEach(s => { studentMap[s.student_id] = `${s.first_name} ${s.last_name}`; });

        try {
            // Fetch assessments for the students in this class
            for (const s of students) {
                try {
                    const res = await apiFetch(`/teacher/students/${s.student_id}/assessments`);
                    if (res.ok) {
                        const items = await res.json();
                        items.forEach(item => {
                            allAssessments.push({ ...item, student_name: studentMap[s.student_id] });
                        });
                    }
                } catch (_) {}
            }

            if (allAssessments.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" class="state-box">
                            <p>No assessment records entered yet for this class.</p>
                        </td>
                    </tr>
                `;
                return;
            }

            // Sort by date descending
            allAssessments.sort((a, b) => new Date(b.assessment_date) - new Date(a.assessment_date));

            tbody.innerHTML = "";
            allAssessments.slice(0, 15).forEach(item => {
                const tr = document.createElement("tr");
                const isFail = item.percentage < 50;
                tr.innerHTML = `
                    <td style="font-size: 0.85rem; color: var(--text-muted);">${item.assessment_date || "—"}</td>
                    <td class="student-name-cell">${item.student_name}</td>
                    <td>${item.subject_name}</td>
                    <td><span style="font-size: 0.85rem;">${item.assessment_type}</span></td>
                    <td><span style="font-size: 0.85rem;">${item.term}</span></td>
                    <td>${item.score} / ${item.max_score}</td>
                    <td>
                        <strong style="color: ${isFail ? 'var(--pastel-pink-text)' : 'var(--pastel-purple-text)'};">
                            ${item.percentage.toFixed(1)}%
                        </strong>
                    </td>
                `;
                tbody.appendChild(tr);
            });

        } catch (err) {
            console.error("Recent Assessments Error:", err);
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="state-box">
                        <p style="color: var(--pastel-pink-text);">Error loading assessments: ${err.message}</p>
                    </td>
                </tr>
            `;
        }
    }

    // -------------------------------------------------------------------------
    // 8. Daily Attendance Register (Bulk)
    // -------------------------------------------------------------------------
    function renderAttendanceRegister(students) {
        const tbody = document.getElementById("attendance-tbody");
        if (!students || students.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="state-box">
                        <p>No learners enrolled in this class to record attendance.</p>
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = "";
        state.attendanceRecords = {};

        students.forEach((student, idx) => {
            // Default to Present
            state.attendanceRecords[student.student_id] = {
                status: "Present",
                remarks: ""
            };

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td style="color: var(--text-muted); font-size: 0.85rem;">${idx + 1}</td>
                <td class="student-adm-cell">${student.admission_number}</td>
                <td class="student-name-cell">${student.first_name} ${student.last_name}</td>
                <td>
                    <div class="att-status-group" data-student-id="${student.student_id}">
                        <button type="button" class="att-status-btn selected-present" data-status="Present">
                            Present
                        </button>
                        <button type="button" class="att-status-btn" data-status="Absent">
                            Absent
                        </button>
                        <button type="button" class="att-status-btn" data-status="Late">
                            Late
                        </button>
                    </div>
                </td>
                <td>
                    <input type="text"
                           class="form-control att-remarks-input"
                           style="padding: 0.35rem 0.65rem; font-size: 0.85rem;"
                           placeholder="e.g. Illness, Excused"
                           data-student-id="${student.student_id}">
                </td>
            `;

            tbody.appendChild(tr);
        });

        // Attach segmented buttons toggle
        tbody.querySelectorAll(".att-status-group").forEach(group => {
            const sId = parseInt(group.getAttribute("data-student-id"));
            const buttons = group.querySelectorAll(".att-status-btn");

            buttons.forEach(btn => {
                btn.addEventListener("click", () => {
                    const status = btn.getAttribute("data-status");
                    state.attendanceRecords[sId].status = status;

                    buttons.forEach(b => {
                        b.classList.remove("selected-present", "selected-absent", "selected-late");
                    });

                    if (status === "Present") btn.classList.add("selected-present");
                    else if (status === "Absent") btn.classList.add("selected-absent");
                    else if (status === "Late") btn.classList.add("selected-late");
                });
            });
        });

        // Attach remarks input
        tbody.querySelectorAll(".att-remarks-input").forEach(input => {
            const sId = parseInt(input.getAttribute("data-student-id"));
            input.addEventListener("input", () => {
                state.attendanceRecords[sId].remarks = input.value.trim();
            });
        });
    }

    // Mark All Present Shortcut
    document.getElementById("btn-mark-all-present").addEventListener("click", () => {
        Object.keys(state.attendanceRecords).forEach(sId => {
            state.attendanceRecords[sId].status = "Present";
        });

        document.querySelectorAll(".att-status-group").forEach(group => {
            const buttons = group.querySelectorAll(".att-status-btn");
            buttons.forEach(b => {
                b.classList.remove("selected-present", "selected-absent", "selected-late");
                if (b.getAttribute("data-status") === "Present") {
                    b.classList.add("selected-present");
                }
            });
        });

        showToast("All learners marked as Present for today.", "info", 2000);
    });

    // Submit Daily Attendance
    const submitAttendanceBtn = document.getElementById("btn-submit-attendance");
    submitAttendanceBtn.addEventListener("click", async () => {
        const recordDate = document.getElementById("attendance-date").value;
        if (!recordDate) {
            showToast("Please select an attendance date.", "error");
            return;
        }

        if (state.students.length === 0) {
            showToast("No learners available to record attendance.", "error");
            return;
        }

        const entries = state.students.map(s => ({
            student_id: s.student_id,
            status: state.attendanceRecords[s.student_id]?.status || "Present",
            remarks: state.attendanceRecords[s.student_id]?.remarks || null
        }));

        const payload = {
            record_date: recordDate,
            entries: entries
        };

        submitAttendanceBtn.disabled = true;
        submitAttendanceBtn.textContent = "Submitting register...";

        try {
            const res = await apiFetch("/teacher/attendance/bulk", {
                method: "POST",
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || "Failed to record bulk attendance.");
            }

            showToast(
                `Daily attendance successfully saved for ${data.updated} learners!`,
                "success"
            );
            if (data.skipped_student_ids && data.skipped_student_ids.length > 0) {
                showToast(
                    `${data.skipped_student_ids.length} learner(s) were skipped because they are not in your assigned classes.`,
                    "error"
                );
            }

        } catch (err) {
            console.error("Attendance Submit Error:", err);
            showToast(`Attendance Error: ${err.message}`, "error");
        } finally {
            submitAttendanceBtn.disabled = false;
            submitAttendanceBtn.textContent = "📋 Submit Daily Attendance Batch";
        }
    });

    // -------------------------------------------------------------------------
    // 8b. Behaviour Ratings & Classroom Observations
    // -------------------------------------------------------------------------
    const notesStudentSelect = document.getElementById("notes-student-id");

    function selectedNotesStudentId() {
        return parseInt(notesStudentSelect.value) || null;
    }

    function resetLearnerHistory() {
        document.getElementById("notes-history-heading").textContent = "Learner History";
        document.getElementById("behaviour-tbody").innerHTML =
            `<tr><td colspan="4" class="state-box"><p>Select a learner to view behaviour ratings.</p></td></tr>`;
        document.getElementById("observations-tbody").innerHTML =
            `<tr><td colspan="3" class="state-box"><p>Select a learner to view observations.</p></td></tr>`;
    }

    function ratingPill(rating) {
        const cls = rating <= 2 ? "status-targeted" : (rating === 3 ? "status-monitoring" : "status-on-track");
        return `<span class="status-pill ${cls}">${rating} / 5</span>`;
    }

    async function loadLearnerHistory(studentId) {
        const behaviourBody = document.getElementById("behaviour-tbody");
        const observationsBody = document.getElementById("observations-tbody");
        const student = state.students.find(s => s.student_id === studentId);
        if (student) {
            document.getElementById("notes-history-heading").textContent =
                `History — ${student.first_name} ${student.last_name}`;
        }

        behaviourBody.innerHTML = `<tr><td colspan="4" class="state-box"><div class="state-spinner"></div></td></tr>`;
        observationsBody.innerHTML = `<tr><td colspan="3" class="state-box"><div class="state-spinner"></div></td></tr>`;

        try {
            const [bRes, oRes] = await Promise.all([
                apiFetch(`/teacher/students/${studentId}/behaviour`),
                apiFetch(`/teacher/students/${studentId}/observations`)
            ]);
            if (!bRes.ok || !oRes.ok) {
                const errData = await (bRes.ok ? oRes : bRes).json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to load learner history.");
            }
            const behaviour = await bRes.json();
            const observations = await oRes.json();

            behaviourBody.innerHTML = behaviour.length === 0
                ? `<tr><td colspan="4" class="state-box"><p>No behaviour ratings recorded yet.</p></td></tr>`
                : behaviour.map(r => `
                    <tr>
                        <td style="font-size: 0.85rem; color: var(--text-muted);">${escapeHtml(r.record_date)}</td>
                        <td>${escapeHtml(r.category)}</td>
                        <td>${ratingPill(r.rating)}</td>
                        <td>${escapeHtml(r.teacher_note || "—")}</td>
                    </tr>`).join("");

            observationsBody.innerHTML = observations.length === 0
                ? `<tr><td colspan="3" class="state-box"><p>No observations recorded yet.</p></td></tr>`
                : observations.map(o => `
                    <tr>
                        <td style="font-size: 0.85rem; color: var(--text-muted);">${escapeHtml(o.observation_date)}</td>
                        <td><span style="font-size: 0.85rem;">${escapeHtml(o.term)} ${escapeHtml(o.academic_year)}</span></td>
                        <td>${escapeHtml(o.observation_text)}</td>
                    </tr>`).join("");

        } catch (err) {
            console.error("Learner History Error:", err);
            const msg = `<p style="color: var(--pastel-pink-text);">${escapeHtml(err.message)}</p>`;
            behaviourBody.innerHTML = `<tr><td colspan="4" class="state-box">${msg}</td></tr>`;
            observationsBody.innerHTML = `<tr><td colspan="3" class="state-box">${msg}</td></tr>`;
        }
    }

    notesStudentSelect.addEventListener("change", () => {
        const studentId = selectedNotesStudentId();
        if (studentId) loadLearnerHistory(studentId);
    });

    async function submitNote(button, endpoint, payload, successMessage, onSuccess) {
        const label = button.textContent;
        button.disabled = true;
        button.textContent = "Saving...";
        try {
            const res = await apiFetch(endpoint, { method: "POST", body: JSON.stringify(payload) });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                const detail = Array.isArray(data.detail) ? data.detail[0].msg : data.detail;
                throw new Error(detail || "Failed to save record.");
            }
            showToast(successMessage, "success");
            onSuccess();
            loadLearnerHistory(payload.student_id);
        } catch (err) {
            console.error("Save Note Error:", err);
            showToast(`Error: ${err.message}`, "error");
        } finally {
            button.disabled = false;
            button.textContent = label;
        }
    }

    document.getElementById("behaviour-form").addEventListener("submit", (e) => {
        e.preventDefault();
        const studentId = selectedNotesStudentId();
        if (!studentId) {
            showToast("Please select a learner.", "error");
            return;
        }
        const noteInput = document.getElementById("behaviour-note");
        submitNote(
            document.getElementById("btn-save-behaviour"),
            "/teacher/behaviour",
            {
                student_id: studentId,
                category: document.getElementById("behaviour-category").value,
                rating: parseInt(document.getElementById("behaviour-rating").value),
                record_date: document.getElementById("behaviour-date").value || null,
                teacher_note: noteInput.value.trim() || null
            },
            "Behaviour rating saved.",
            () => { noteInput.value = ""; }
        );
    });

    document.getElementById("observation-form").addEventListener("submit", (e) => {
        e.preventDefault();
        const studentId = selectedNotesStudentId();
        if (!studentId) {
            showToast("Please select a learner.", "error");
            return;
        }
        const textInput = document.getElementById("observation-text");
        const text = textInput.value.trim();
        if (!text) {
            showToast("Observation text cannot be empty.", "error");
            return;
        }
        submitNote(
            document.getElementById("btn-save-observation"),
            "/teacher/observations",
            {
                student_id: studentId,
                term: state.period.term,
                academic_year: state.period.academic_year,
                observation_text: text
            },
            "Observation saved.",
            () => { textInput.value = ""; }
        );
    });

    // -------------------------------------------------------------------------
    // 9. CatBoost Learner Analytics Modal Controller
    // -------------------------------------------------------------------------
    const modalBackdrop = document.getElementById("analytics-modal-backdrop");
    const modalLoading = document.getElementById("modal-loading");
    const modalError = document.getElementById("modal-error");
    const modalErrorText = document.getElementById("modal-error-text");
    const modalContent = document.getElementById("modal-content");

    function closeModal() {
        modalBackdrop.classList.remove("open");
        state.activeStudentForModal = null;
    }

    document.getElementById("btn-close-modal").addEventListener("click", closeModal);
    document.getElementById("btn-close-modal-footer").addEventListener("click", closeModal);
    modalBackdrop.addEventListener("click", (e) => {
        if (e.target === modalBackdrop) closeModal();
    });

    document.getElementById("btn-recalculate").addEventListener("click", () => {
        if (state.activeStudentForModal) {
            calculateLearnerAnalytics(state.activeStudentForModal.id);
        }
    });

    function openAnalyticsModal(studentId, studentName, studentAdm) {
        state.activeStudentForModal = { id: studentId, name: studentName, adm: studentAdm };

        document.getElementById("modal-student-name").textContent = studentName;
        document.getElementById("modal-student-meta").textContent =
            `${state.activeAssignment ? state.activeAssignment.grade_level + ' ' + state.activeAssignment.stream : ''} • Adm: ${studentAdm}`;

        modalBackdrop.classList.add("open");
        calculateLearnerAnalytics(studentId);
    }

    async function calculateLearnerAnalytics(studentId) {
        modalLoading.style.display = "block";
        modalError.style.display = "none";
        modalContent.style.display = "none";

        try {
            const res = await apiFetch(`/analytics/calculate/${studentId}`, {
                method: "POST",
                body: JSON.stringify(state.period)
            });

            const data = await res.json();

            if (!res.ok) {
                // Real API error display
                throw new Error(data.detail || "Unable to calculate analytics.");
            }

            // Cache result
            state.analyticsCache[studentId] = data;

            // Render Results in Modal
            renderModalAnalytics(data);

            // Update row in table
            updateRosterRowWithAnalytics(studentId, data);

        } catch (err) {
            console.error("CatBoost Analytics Error:", err);
            modalLoading.style.display = "none";
            modalError.style.display = "block";
            modalErrorText.innerHTML = `
                <strong>Prediction Unavailable:</strong> ${err.message}
            `;
        }
    }

    function renderModalAnalytics(data) {
        modalLoading.style.display = "none";
        modalError.style.display = "none";
        modalContent.style.display = "block";

        const prob = data.support_probability;
        const probPct = (prob * 100).toFixed(1) + "%";
        const status = data.support_status;

        // Prob & Status
        document.getElementById("modal-risk-probability").textContent = probPct;
        const badge = document.getElementById("modal-risk-badge");
        const meter = document.getElementById("modal-risk-meter");

        badge.className = "status-pill";
        meter.className = "risk-meter-fill";
        meter.style.width = probPct;

        if (status === "On Track") {
            badge.classList.add("status-on-track");
            badge.textContent = "● On Track";
            meter.classList.add("fill-on-track");
        } else if (status === "Monitoring Suggested") {
            badge.classList.add("status-monitoring");
            badge.textContent = "● Monitoring Suggested";
            meter.classList.add("fill-monitoring");
        } else {
            badge.classList.add("status-targeted");
            badge.textContent = "● Targeted Support Recommended";
            meter.classList.add("fill-targeted");
        }

        // Indicators
        document.getElementById("modal-stat-average").textContent =
            data.overall_average !== null ? `${data.overall_average.toFixed(1)}%` : "—";
        document.getElementById("modal-stat-percentile").textContent =
            data.cohort_percentile !== null ? `${data.cohort_percentile.toFixed(1)}th` : "—";
        document.getElementById("modal-stat-absences").textContent =
            data.absences_count !== null ? `${data.absences_count} days` : "0 days";

        // Recommendations
        const recList = document.getElementById("modal-recommendations-list");
        recList.innerHTML = "";

        if (!data.recommendations || data.recommendations.length === 0) {
            recList.innerHTML = `
                <div class="rec-card" style="background: var(--pastel-green-bg); border-color: var(--pastel-green-border);">
                    <p style="color: var(--pastel-green-text); font-weight: 600;">
                        🌟 Learner is currently performing on track. No high-priority intervention rules were triggered.
                    </p>
                </div>
            `;
            return;
        }

        data.recommendations.forEach(rec => {
            const priorityClass = rec.priority === "High"
                ? "priority-high"
                : (rec.priority === "Medium" ? "priority-medium" : "priority-low");

            const div = document.createElement("div");
            div.className = "rec-card";
            div.innerHTML = `
                <div class="rec-card-header">
                    <span class="rec-badge-priority ${priorityClass}">Priority: ${rec.priority}</span>
                    <span class="rec-badge-audience">Target: ${rec.target_audience}</span>
                </div>
                <div class="rec-text">${rec.recommendation_text}</div>
            `;
            recList.appendChild(div);
        });
    }

    function updateRosterRowWithAnalytics(studentId, data) {
        // Average
        const avgCell = document.getElementById(`cell-avg-${studentId}`);
        if (avgCell && data.overall_average !== null && data.overall_average !== undefined) {
            avgCell.innerHTML = `<strong>${data.overall_average.toFixed(1)}%</strong>`;
        }

        // Status
        const statusCell = document.getElementById(`cell-status-${studentId}`);
        if (statusCell && data.support_status) {
            statusCell.innerHTML = renderStatusPill(data.support_status, data.support_probability);
        }
    }

    // -------------------------------------------------------------------------
    // 10. Bootstrap Dashboard
    // -------------------------------------------------------------------------
    loadAssignments();

});