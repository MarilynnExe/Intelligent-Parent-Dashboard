/**
 * Adaptive In-App Notifications Controller.
 * Connects Parent and Teacher Dashboards to:
 *   - GET /api/notifications
 *   - GET /api/notifications/unread-count
 *   - PATCH /api/notifications/{id}/read
 *   - PATCH /api/notifications/mark-all-read
 *   - GET /api/notifications/preferences
 *   - PUT /api/notifications/preferences
 */

(function () {
    const NotificationController = {
        filterUnreadOnly: false,
        cachedCount: 0,

        init() {
            this.bindElements();
            this.bindEvents();
            this.refreshUnreadCount();

            // Refresh unread count every 30 seconds
            setInterval(() => this.refreshUnreadCount(), 30000);
        },

        bindElements() {
            this.bellBtn = document.getElementById("nav-notifications-btn");
            this.badge = document.getElementById("notification-badge");
            this.backdrop = document.getElementById("notif-backdrop");
            this.drawer = document.getElementById("notif-drawer");
            this.closeDrawerBtn = document.getElementById("btn-close-notif-drawer");
            this.listContainer = document.getElementById("notif-list-container");
            this.tabAll = document.getElementById("notif-tab-all");
            this.tabUnread = document.getElementById("notif-tab-unread");
            this.markAllBtn = document.getElementById("btn-mark-all-read");
            this.prefsBtn = document.getElementById("btn-notif-prefs");
            this.prefsModal = document.getElementById("notif-prefs-modal");
            this.closePrefsBtn = document.getElementById("btn-close-prefs-modal");
            this.cancelPrefsBtn = document.getElementById("btn-cancel-prefs");
            this.prefsForm = document.getElementById("notif-prefs-form");
        },

        bindEvents() {
            if (this.bellBtn) {
                this.bellBtn.addEventListener("click", () => this.openDrawer());
            }

            if (this.backdrop) {
                this.backdrop.addEventListener("click", () => this.closeDrawer());
            }

            if (this.closeDrawerBtn) {
                this.closeDrawerBtn.addEventListener("click", () => this.closeDrawer());
            }

            if (this.tabAll) {
                this.tabAll.addEventListener("click", () => {
                    this.filterUnreadOnly = false;
                    this.tabAll.classList.add("active");
                    this.tabUnread.classList.remove("active");
                    this.loadNotifications();
                });
            }

            if (this.tabUnread) {
                this.tabUnread.addEventListener("click", () => {
                    this.filterUnreadOnly = true;
                    this.tabUnread.classList.add("active");
                    this.tabAll.classList.remove("active");
                    this.loadNotifications();
                });
            }

            if (this.markAllBtn) {
                this.markAllBtn.addEventListener("click", () => this.markAllAsRead());
            }

            if (this.prefsBtn) {
                this.prefsBtn.addEventListener("click", () => this.openPreferencesModal());
            }

            if (this.closePrefsBtn) {
                this.closePrefsBtn.addEventListener("click", () => this.closePreferencesModal());
            }

            if (this.cancelPrefsBtn) {
                this.cancelPrefsBtn.addEventListener("click", () => this.closePreferencesModal());
            }

            if (this.prefsForm) {
                this.prefsForm.addEventListener("submit", (e) => {
                    e.preventDefault();
                    this.savePreferences();
                });
            }
        },

        openDrawer() {
            if (this.backdrop) this.backdrop.classList.add("open");
            if (this.drawer) this.drawer.classList.add("open");
            this.loadNotifications();
        },

        closeDrawer() {
            if (this.backdrop) this.backdrop.classList.remove("open");
            if (this.drawer) this.drawer.classList.remove("open");
        },

        async refreshUnreadCount() {
            if (!Auth.getToken()) return;

            try {
                const res = await apiFetch("/notifications/unread-count");
                if (res.ok) {
                    const data = await res.json();
                    this.cachedCount = data.unread_count || 0;
                    this.renderBadge();
                }
            } catch (err) {
                console.error("Failed to fetch unread notification count:", err);
            }
        },

        renderBadge() {
            if (!this.badge) return;

            if (this.cachedCount > 0) {
                this.badge.textContent = this.cachedCount > 99 ? "99+" : this.cachedCount;
                this.badge.classList.remove("hidden");
            } else {
                this.badge.textContent = "0";
                this.badge.classList.add("hidden");
            }
        },

        async loadNotifications() {
            if (!this.listContainer) return;

            this.listContainer.innerHTML = `
                <div class="notif-empty-state">
                    <div class="notif-spinner"></div>
                    <p>Loading updates...</p>
                </div>
            `;

            try {
                const url = `/notifications?unread_only=${this.filterUnreadOnly}&limit=50`;
                const res = await apiFetch(url);
                if (!res.ok) {
                    throw new Error("Unable to retrieve notifications.");
                }

                const notifs = await res.json();

                if (!notifs || notifs.length === 0) {
                    this.listContainer.innerHTML = `
                        <div class="notif-empty-state">
                            <span class="notif-empty-icon">✨</span>
                            <p style="font-weight: 700; color: #1e293b; margin-top: 0.25rem;">You're all caught up!</p>
                            <p style="font-size: 0.82rem;">No ${this.filterUnreadOnly ? "unread " : ""}notifications at this time.</p>
                        </div>
                    `;
                    return;
                }

                this.listContainer.innerHTML = notifs.map(n => this.renderCardHtml(n)).join("");

                // Attach mark as read handlers
                this.listContainer.querySelectorAll(".btn-mark-read").forEach(btn => {
                    btn.addEventListener("click", async () => {
                        const id = btn.dataset.id;
                        await this.markAsRead(id, btn);
                    });
                });

            } catch (err) {
                console.error("Error loading notifications:", err);
                this.listContainer.innerHTML = `
                    <div class="notif-empty-state" style="color: #dc2626;">
                        <span class="notif-empty-icon">⚠️</span>
                        <p>Failed to load updates.</p>
                    </div>
                `;
            }
        },

        renderCardHtml(n) {
            const priorityClass = `priority-${(n.priority || "low").toLowerCase()}`;
            const timeAgo = this.formatTimeAgo(n.created_at);
            const learnerTag = n.student_name ? `<span class="notif-category-badge" style="background: #e0f2fe; color: #0369a1;">🎓 ${this.escapeHtml(n.student_name)}</span>` : "";

            return `
                <div class="notif-card ${n.is_read ? "read" : "unread"}" id="notif-card-${n.notification_id}">
                    <div class="notif-card-header">
                        <div class="notif-badges-group">
                            <span class="notif-priority-badge ${priorityClass}">${this.escapeHtml(n.priority)}</span>
                            <span class="notif-category-badge">${this.escapeHtml(n.category)}</span>
                            ${learnerTag}
                        </div>
                        <span class="notif-time">${timeAgo}</span>
                    </div>

                    <div class="notif-card-title">${this.escapeHtml(n.title)}</div>
                    <div class="notif-card-message">${this.escapeHtml(n.message)}</div>

                    ${n.suggested_action ? `
                        <div class="notif-action-box">
                            <span class="notif-action-icon">🎯</span>
                            <div><strong>Suggested Action:</strong> ${this.escapeHtml(n.suggested_action)}</div>
                        </div>
                    ` : ""}

                    <div class="notif-card-footer">
                        ${!n.is_read ? `
                            <button class="notif-read-btn btn-mark-read" data-id="${n.notification_id}">
                                ✓ Mark as read
                            </button>
                        ` : `
                            <span style="font-size: 0.75rem; color: #94a3b8;">✓ Read</span>
                        `}
                    </div>
                </div>
            `;
        },

        async markAsRead(notificationId, btnEl) {
            try {
                if (btnEl) btnEl.disabled = true;

                const res = await apiFetch(`/notifications/${notificationId}/read`, {
                    method: "PATCH",
                });

                if (res.ok) {
                    const card = document.getElementById(`notif-card-${notificationId}`);
                    if (card) {
                        card.classList.remove("unread");
                        card.classList.add("read");
                        const footer = card.querySelector(".notif-card-footer");
                        if (footer) {
                            footer.innerHTML = `<span style="font-size: 0.75rem; color: #94a3b8;">✓ Read</span>`;
                        }
                    }

                    if (this.cachedCount > 0) {
                        this.cachedCount--;
                        this.renderBadge();
                    }

                    if (this.filterUnreadOnly && card) {
                        card.style.opacity = "0";
                        card.style.transform = "translateX(20px)";
                        card.style.transition = "all 0.25s ease";
                        setTimeout(() => card.remove(), 250);
                    }
                }
            } catch (err) {
                console.error("Failed to mark notification as read:", err);
                if (btnEl) btnEl.disabled = false;
            }
        },

        async markAllAsRead() {
            try {
                if (this.markAllBtn) this.markAllBtn.disabled = true;

                const res = await apiFetch("/notifications/mark-all-read", {
                    method: "PATCH",
                });

                if (res.ok) {
                    this.cachedCount = 0;
                    this.renderBadge();
                    await this.loadNotifications();
                }
            } catch (err) {
                console.error("Failed to mark all as read:", err);
            } finally {
                if (this.markAllBtn) this.markAllBtn.disabled = false;
            }
        },

        async openPreferencesModal() {
            if (!this.prefsModal) return;

            try {
                const res = await apiFetch("/notifications/preferences");
                if (res.ok) {
                    const data = await res.json();
                    document.getElementById("pref-notifications-enabled").checked = data.notifications_enabled;
                    document.getElementById("pref-academic-updates").checked = data.academic_updates;
                    document.getElementById("pref-attendance-updates").checked = data.attendance_updates;
                    document.getElementById("pref-behaviour-updates").checked = data.behaviour_updates;
                    document.getElementById("pref-support-updates").checked = data.support_updates;
                    document.getElementById("pref-comm-style").value = data.communication_style || "DETAILED";
                }
            } catch (err) {
                console.error("Error loading preferences:", err);
            }

            this.prefsModal.classList.add("open");
        },

        closePreferencesModal() {
            if (this.prefsModal) {
                this.prefsModal.classList.remove("open");
            }
        },

        async savePreferences() {
            const saveBtn = document.getElementById("btn-save-prefs");
            if (saveBtn) {
                saveBtn.disabled = true;
                saveBtn.textContent = "Saving...";
            }

            try {
                const payload = {
                    notifications_enabled: document.getElementById("pref-notifications-enabled").checked,
                    academic_updates: document.getElementById("pref-academic-updates").checked,
                    attendance_updates: document.getElementById("pref-attendance-updates").checked,
                    behaviour_updates: document.getElementById("pref-behaviour-updates").checked,
                    support_updates: document.getElementById("pref-support-updates").checked,
                    communication_style: document.getElementById("pref-comm-style").value,
                };

                const res = await apiFetch("/notifications/preferences", {
                    method: "PUT",
                    body: JSON.stringify(payload),
                });

                if (res.ok) {
                    this.closePreferencesModal();
                    if (typeof showToast === "function") {
                        showToast("Communication preferences saved successfully!", "success");
                    }
                } else {
                    const err = await res.json();
                    alert(err.detail || "Failed to save preferences.");
                }
            } catch (err) {
                console.error("Error saving preferences:", err);
                alert("Failed to save communication preferences.");
            } finally {
                if (saveBtn) {
                    saveBtn.disabled = false;
                    saveBtn.textContent = "Save Preferences";
                }
            }
        },

        formatTimeAgo(isoString) {
            if (!isoString) return "";
            try {
                const date = new Date(isoString);
                const now = new Date();
                const diffMs = now - date;
                const diffSec = Math.floor(diffMs / 1000);
                const diffMin = Math.floor(diffSec / 60);
                const diffHour = Math.floor(diffMin / 60);
                const diffDay = Math.floor(diffHour / 24);

                if (diffSec < 60) return "Just now";
                if (diffMin < 60) return `${diffMin}m ago`;
                if (diffHour < 24) return `${diffHour}h ago`;
                if (diffDay < 7) return `${diffDay}d ago`;
                return date.toLocaleDateString();
            } catch {
                return "";
            }
        },

        escapeHtml(str) {
            if (!str && str !== 0) return "";
            return String(str)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        },
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => NotificationController.init());
    } else {
        NotificationController.init();
    }

    // Expose globally for manual triggers if needed (e.g. after calculating analytics)
    window.NotificationController = NotificationController;
})();
