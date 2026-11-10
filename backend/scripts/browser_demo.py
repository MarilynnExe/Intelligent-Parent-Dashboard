"""Browser rehearsal against a seeded demo database; writes fictional assessment, attendance and behaviour records."""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def rehearse(base_url, screenshot_dir):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        errors = []
        failures = []
        def observe(page):
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: failures.append(f"{response.status} {response.url}")
                    if response.status >= 400 and not (response.status == 404 and "/analytics/student/" in response.url) else None)
        def login(page, role):
            observe(page)
            page.goto(f"{base_url}/portal/login.html")
            page.locator("#username").fill(f"demo.{role}")
            page.locator("#password").fill("DemoSchool2026!")
            page.locator("#submit-btn").click()
            page.wait_for_url(f"**/{role}-dashboard.html")
        parent_context = browser.new_context(viewport={"width": 1440, "height": 1000})
        parent = parent_context.new_page()
        login(parent, "parent")
        parent.locator("#parent-year").fill("2026")
        parent.locator("#parent-term").select_option("Term 3")
        parent.locator("#parent-refresh").click()
        expect(parent.locator("#analytics-freshness")).to_contain_text("Analytics: current")
        original = parent.locator("#stat-academic-average").inner_text()
        teacher_context = browser.new_context(viewport={"width": 1440, "height": 1000})
        teacher = teacher_context.new_page()
        login(teacher, "teacher")
        teacher.locator("#period-year").fill("2026")
        teacher.locator("#period-year").press("Tab")
        teacher.locator("#period-term").select_option("Term 3")
        expect(teacher.locator("#roster-tbody")).to_contain_text("Amina")
        teacher.locator("#tab-assessments").click()
        teacher.locator("#assessment-student-id").select_option(teacher.locator("#assessment-student-id option").filter(has_text="Amina").get_attribute("value"))
        teacher.locator("#assessment-subject").select_option("Mathematics")
        teacher.locator("#assessment-score").fill("96")
        teacher.locator("#assessment-max-score").fill("100")
        # Select the period seeded for this browser rehearsal.
        teacher.locator("#assessment-term").select_option("Term 3")
        teacher.locator("#assessment-year").fill("2026")
        teacher.locator("#assessment-date").fill("2026-09-25")
        with teacher.expect_response(lambda response: "/teacher/assessments" in response.url and response.request.method == "POST") as saved:
            teacher.locator("#btn-save-assessment").click()
        assert saved.value.status == 200, saved.value.text()
        # Verify the real 30-second polling path, without refreshing or signing in again.
        parent.wait_for_function("previous => document.querySelector('#stat-academic-average').textContent !== previous", arg=original, timeout=35000)
        expect(parent.locator("#analytics-freshness")).to_contain_text("Analytics: current")
        teacher.locator("#tab-attendance").click()
        teacher.locator("#attendance-date").fill("2026-09-26")
        teacher.locator("#btn-load-register").click()
        expect(teacher.locator("#register-status")).to_contain_text("saved entries loaded")
        teacher.locator('.att-status-btn[data-status="Absent"]').first.click()
        with teacher.expect_response(lambda response: "/teacher/attendance/bulk" in response.url and response.request.method == "POST") as attendance:
            teacher.locator("#btn-submit-attendance").click()
        assert attendance.value.status == 200
        teacher.locator("#tab-behaviour").click()
        teacher.locator("#notes-student-id").select_option(teacher.locator("#notes-student-id option").filter(has_text="Amina").get_attribute("value"))
        teacher.locator("#behaviour-rating").select_option("2")
        teacher.locator("#behaviour-date").fill("2026-09-26")
        teacher.locator("#behaviour-note").fill("Fictional browser demonstration")
        with teacher.expect_response(lambda response: "/teacher/behaviour" in response.url and response.request.method == "POST") as behaviour:
            teacher.locator("#btn-save-behaviour").click()
        assert behaviour.value.status == 200
        parent.locator("#parent-refresh").click()
        expect(parent.locator("#parent-refresh-status")).to_contain_text("Updated")
        parent.locator("#tab-academics").click()
        expect(parent.locator("#assessment-progress meter").first).to_be_visible()
        parent.locator("#tab-attendance").click()
        expect(parent.locator("#attendance-summary")).to_contain_text("recorded days")
        parent.locator("#nav-notifications-btn").click()
        expect(parent.locator("#notif-list-container")).to_contain_text("Amina")
        parent.locator("#btn-close-notif-drawer").click()
        parent.locator("#notif-drawer").wait_for(state="hidden")
        parent.locator("#tab-overview").click()
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        parent.screenshot(path=str(screenshot_dir / "parent-desktop.png"), full_page=True)
        parent.set_viewport_size({"width": 390, "height": 844})
        parent.screenshot(path=str(screenshot_dir / "parent-mobile.png"), full_page=True)
        assert parent.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Parent page overflows mobile viewport"
        parent.locator("#parent-year").fill("2025")
        parent.locator("#parent-year").press("Tab")
        expect(parent.locator("#analytics-freshness")).to_contain_text("Term 3 2025")
        expect(parent.locator("#hero-risk-probability")).to_have_text("Pending")
        parent.locator("#parent-refresh").click()
        expect(parent.locator("#parent-refresh-status")).to_contain_text("Updated")
        teacher.locator("#tab-overview").click()
        teacher.locator("#roster-tbody tr").filter(has_text="Amina").locator(".btn-analyze").click()
        expect(teacher.locator("#teacher-analytics-freshness")).to_contain_text("Analytics: current")
        teacher.locator("#btn-recalculate").click()
        expect(teacher.locator("#teacher-analytics-freshness")).to_contain_text("Analytics: current")
        teacher.locator("#btn-close-modal").click()
        teacher.set_viewport_size({"width": 390, "height": 844})
        teacher.screenshot(path=str(screenshot_dir / "teacher-mobile.png"), full_page=True)
        assert teacher.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Teacher page overflows mobile viewport"
        admin_context = browser.new_context()
        admin = admin_context.new_page()
        login(admin, "admin")
        expect(admin.locator("body")).to_contain_text("Demo")
        browser.close()
        assert not errors, errors
        assert not failures, failures
        print("PASS: MySQL browser workflow, real 30-second refresh, notifications, period/empty states, retry, desktop/mobile layout, and all three logins")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--screenshots", type=Path, default=Path("/tmp/ipd-demo-screenshots"))
    args = parser.parse_args()
    rehearse(args.base_url.rstrip("/"), args.screenshots)
