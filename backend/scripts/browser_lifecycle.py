"""Exercise edit/archive/restore/correction controls on a disposable demo server."""
import argparse
from time import time_ns
from playwright.sync_api import sync_playwright, expect


def run(base):
    with sync_playwright() as p:
        browser=p.chromium.launch()
        api=browser.new_context().request
        result=api.post(base+'/api/auth/login',data={'email_or_username':'demo.admin','password':'DemoSchool2026!'})
        assert result.status==200
        headers={'Authorization':'Bearer '+result.json()['access_token']}
        suffix=str(time_ns())
        def post(path,data):
            result=api.post(base+'/api'+path,headers=headers,data=data)
            assert result.status in (200,201),result.text()
            return result.json()
        parent=post('/admin/users',dict(full_name='Lifecycle Parent '+suffix,email_or_username='lifecycle.parent.'+suffix,password='Lifecycle2026!',role='PARENT'))
        teacher=post('/admin/users',dict(full_name='Lifecycle Teacher '+suffix,email_or_username='lifecycle.teacher.'+suffix,password='Lifecycle2026!',role='TEACHER'))
        student=post('/admin/students',dict(admission_number='LIFE-'+suffix,first_name='Lifecycle',last_name=suffix,date_of_birth='2013-01-01',grade_level='Grade 7',stream='Demo East'))
        assignment=post('/admin/teacher-assignments',dict(teacher_user_id=teacher['user_id'],grade_level='Grade 7',stream='Lifecycle',subject_name='Mathematics'))
        link=post('/admin/parent-links',dict(parent_user_id=parent['user_id'],student_id=student['student_id'],relationship_type='Guardian'))
        errors=[]
        def login(role):
            context=browser.new_context(viewport={'width':1440,'height':1000})
            page=context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('dialog',lambda dialog:dialog.accept())
            page.goto(base+'/portal/login.html')
            page.locator('#username').fill('demo.'+role);page.locator('#password').fill('DemoSchool2026!');page.locator('#submit-btn').click()
            page.wait_for_url('**/'+role+'-dashboard.html')
            return page
        def save(page):
            page.locator('#record-editor-save').click()
            expect(page.locator('#record-editor')).to_have_count(0)
        admin=login('admin')
        admin.locator('#tab-users').click()
        row=admin.locator('#users-tbody tr').filter(has_text=parent['email_or_username'])
        row.locator('[data-crud="edit-user"]').click();admin.locator('#edit-full_name').fill('Corrected Parent '+suffix);save(admin)
        expect(row).to_contain_text('Corrected Parent')
        row.locator('[data-crud="toggle-user"]').click();expect(row).to_contain_text('Deactivated')
        row.locator('[data-crud="toggle-user"]').click();expect(row).to_contain_text('Active')
        admin.locator('#tab-students').click()
        row=admin.locator('#students-tbody tr').filter(has_text=student['admission_number'])
        row.locator('[data-crud="edit-student"]').click();admin.locator('#edit-last_name').fill('Corrected '+suffix);save(admin)
        expect(row).to_contain_text('Corrected')
        row.locator('[data-crud="toggle-student"]').click();expect(row).to_contain_text('Archived')
        row.locator('[data-crud="toggle-student"]').click();expect(row).to_contain_text('Active')
        admin.locator('#tab-assignments').click()
        row=admin.locator('#assignments-tbody tr').filter(has_text=teacher['full_name'])
        row.locator('[data-crud="edit-assignment"]').click();admin.locator('#edit-subject_name').fill('English');save(admin);expect(row).to_contain_text('English')
        row=admin.locator('#parent-links-tbody tr').filter(has_text=student['admission_number'])
        row.locator('[data-crud="edit-link"]').click();admin.locator('#edit-relationship_type').select_option('Father');save(admin);expect(row).to_contain_text('Father')
        page=login('teacher')
        page.locator('#period-year').fill('2026');page.locator('#period-year').press('Tab');page.locator('#period-term').select_option('Term 3')
        expect(page.locator('#roster-tbody')).to_contain_text(student['admission_number'])
        page.locator('#tab-assessments').click();page.locator('#assessment-student-id').select_option(str(student['student_id']))
        page.locator('#assessment-subject').select_option('Mathematics');page.locator('#assessment-term').select_option('Term 3');page.locator('#assessment-year').fill('2026')
        page.locator('#assessment-score').fill('40');page.locator('#assessment-date').fill('2026-09-26')
        page.locator('#btn-save-assessment').click()
        row=page.locator('#recent-assessments-tbody tr').filter(has_text='Lifecycle')
        expect(row).to_have_count(1)
        row.locator('[data-edit]').click();page.locator('#edit-score').fill('80');save(page);expect(row).to_contain_text('80.0%')
        row.locator('[data-remove]').click();expect(row).to_have_count(0)
        page.locator('#tab-behaviour').click();page.locator('#notes-student-id').select_option(str(student['student_id']))
        page.locator('#behaviour-date').fill('2026-09-26');page.locator('#behaviour-note').fill('Initial rating');page.locator('#btn-save-behaviour').click()
        row=page.locator('#behaviour-tbody tr').filter(has_text='Initial rating');expect(row).to_have_count(1)
        row.locator('[data-edit]').click();page.locator('#edit-teacher_note').fill('Corrected rating');save(page)
        row=page.locator('#behaviour-tbody tr').filter(has_text='Corrected rating');expect(row).to_have_count(1);row.locator('[data-remove]').click();expect(row).to_have_count(0)
        page.locator('#observation-text').fill('Initial observation');page.locator('#btn-save-observation').click()
        row=page.locator('#observations-tbody tr').filter(has_text='Initial observation');expect(row).to_have_count(1)
        row.locator('[data-edit]').click();page.locator('#edit-observation_text').fill('Corrected observation');save(page)
        row=page.locator('#observations-tbody tr').filter(has_text='Corrected observation');expect(row).to_have_count(1);row.locator('[data-remove]').click();expect(row).to_have_count(0)
        page.locator('#tab-attendance').click();page.locator('#attendance-date').fill('2026-09-27');page.locator('#btn-load-register').click()
        expect(page.locator('#register-status')).to_contain_text('saved entries loaded')
        row=page.locator('#attendance-tbody tr').filter(has_text=student['admission_number'])
        expect(row).to_contain_text('Not recorded');row.locator('[data-status="Absent"]').click();page.locator('#btn-submit-attendance').click()
        expect(row).to_contain_text('Saved')
        page.locator('#btn-load-register').click();expect(row.locator('.selected-absent')).to_have_count(1)
        row.locator('[data-status="Excused"]').click();page.locator('#btn-submit-attendance').click()
        expect(row.locator('[data-status="Excused"].selected-late')).to_have_count(1)
        page.locator('#btn-load-register').click();expect(row.locator('[data-status="Excused"].selected-late')).to_have_count(1)
        row.locator('[data-remove]').click();expect(row).to_contain_text('Not recorded')
        page.set_viewport_size({'width':390,'height':844})
        page.locator('#tab-assessments').click()
        browser.close()
        assert not errors,errors
        print('PASS: account edit/deactivate/restore, learner edit/archive/restore, relationship edits, teacher corrections/deletions and saved attendance round-trip')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base-url',default='http://127.0.0.1:18082');args=parser.parse_args();run(args.base_url.rstrip('/'))
