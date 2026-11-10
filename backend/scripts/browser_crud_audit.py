"""Rehearse existing admin CRUD forms on a disposable, seeded demo server."""
import argparse
from time import time_ns
from playwright.sync_api import sync_playwright, expect


def audit(base_url):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("dialog", lambda dialog: dialog.accept())
        page.goto(base_url + "/portal/login.html")
        page.locator("#username").fill("demo.admin")
        page.locator("#password").fill("DemoSchool2026!")
        page.locator("#submit-btn").click()
        page.wait_for_url("**/admin-dashboard.html")
        suffix = str(time_ns())
        names = {}
        page.locator("#tab-users").click()
        for role in ("ADMIN", "TEACHER", "PARENT"):
            name = f"Audit {role} {suffix}"
            names[role] = name
            page.locator("#user-full-name").fill(name)
            page.locator("#user-email-username").fill(f"audit.{role.lower()}.{suffix}")
            page.locator("#user-password").fill("AuditPass2026!")
            page.locator("#user-role").select_option(role)
            with page.expect_response(lambda response: response.url.endswith("/api/admin/users") and response.request.method == "POST") as response:
                page.locator("#btn-save-user").click()
            assert response.value.status == 201, response.value.text()
            expect(page.locator("#users-tbody")).to_contain_text(name)
        page.locator("#tab-students").click()
        admission = "AUDIT-" + suffix
        for selector, value in {"#student-adm-no": admission, "#student-first-name": "Audit", "#student-last-name": suffix,
                                "#student-dob": "2013-01-01", "#student-grade": "Grade 7", "#student-stream": "Audit"}.items():
            page.locator(selector).fill(value)
        with page.expect_response(lambda response: response.url.endswith("/api/admin/students") and response.request.method == "POST") as response:
            page.locator("#btn-save-student").click()
        assert response.value.status == 201, response.value.text()
        expect(page.locator("#students-tbody")).to_contain_text(admission)
        page.locator("#tab-assignments").click()
        option = page.locator("#assign-teacher-select option").filter(has_text=names["TEACHER"])
        expect(option).to_have_count(1)
        page.locator("#assign-teacher-select").select_option(option.get_attribute("value"))
        page.locator("#assign-grade").fill("Grade 7")
        page.locator("#assign-stream").fill("Audit")
        page.locator("#assign-subject").fill("Mathematics")
        with page.expect_response(lambda response: response.url.endswith("/api/admin/teacher-assignments") and response.request.method == "POST") as response:
            page.locator("#btn-save-assignment").click()
        assert response.value.status == 201, response.value.text()
        row = page.locator("#assignments-tbody tr").filter(has_text=names["TEACHER"])
        expect(row).to_have_count(1)
        with page.expect_response(lambda response: "/api/admin/teacher-assignments/" in response.url and response.request.method == "DELETE") as response:
            row.locator(".btn-delete-assignment").click()
        assert response.value.status == 200
        expect(row).to_have_count(0)
        option = page.locator("#link-parent-select option").filter(has_text=names["PARENT"])
        page.locator("#link-parent-select").select_option(option.get_attribute("value"))
        option = page.locator("#link-student-select option").filter(has_text=admission)
        page.locator("#link-student-select").select_option(option.get_attribute("value"))
        with page.expect_response(lambda response: response.url.endswith("/api/admin/parent-links") and response.request.method == "POST") as response:
            page.locator("#btn-save-link").click()
        assert response.value.status == 201, response.value.text()
        row = page.locator("#parent-links-tbody tr").filter(has_text=admission)
        expect(row).to_have_count(1)
        with page.expect_response(lambda response: "/api/admin/parent-links/" in response.url and response.request.method == "DELETE") as response:
            row.locator(".btn-delete-link").click()
        assert response.value.status == 200
        expect(row).to_have_count(0)
        browser.close()
        assert not errors, errors
        print("PASS: browser account creation for all roles, student enrollment, assignment/link create-read-delete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18082")
    args = parser.parse_args()
    audit(args.base_url.rstrip("/"))
