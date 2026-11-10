"""Assignment rehearsal against a fictional, seeded demo server."""
import argparse
from datetime import date, timedelta, datetime
from pathlib import Path
from time import time_ns
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, expect


def rehearse(base, screenshots):
    today=datetime.now(ZoneInfo('Africa/Nairobi')).date()
    term='Term 1' if today.month<=4 else 'Term 2' if today.month<=8 else 'Term 3'
    start=date(today.year,{'Term 1':1,'Term 2':5,'Term 3':9}[term],1)
    if today==start: raise RuntimeError('Rehearse overdue work after the first day of term.')
    title='Browser work '+str(time_ns())
    with sync_playwright() as p:
        browser=p.chromium.launch();errors=[]
        def login(role):
            page=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='Africa/Nairobi').new_page()
            page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
            page.goto(base+'/portal/login.html');page.locator('#username').fill('demo.'+role)
            page.locator('#password').fill('DemoSchool2026!');page.locator('#submit-btn').click()
            page.wait_for_url('**/'+role+'-dashboard.html');return page
        teacher=login('teacher')
        teacher.locator('#period-year').fill(str(today.year));teacher.locator('#period-year').press('Tab');teacher.locator('#period-term').select_option(term)
        expect(teacher.locator('#work-class-context')).to_contain_text('Mathematics')
        teacher.locator('#tab-class-assignments').click();teacher.locator('#work-title').fill(title)
        teacher.locator('#work-instructions').fill('Complete the worksheet.')
        teacher.locator('#work-assigned-date').fill(max(start,today-timedelta(days=5)).isoformat())
        teacher.locator('#work-due-date').fill((today-timedelta(days=1)).isoformat())
        with teacher.expect_response(lambda r:'/api/teacher/class-assignments' in r.url and r.request.method=='POST') as response:
            teacher.locator('#work-create').click()
        assert response.value.status==201,response.value.text()
        key=response.value.json()['assignment_id'];card=teacher.locator(f'[data-work-id="{key}"]')
        expect(card).to_contain_text(title)
        parent=login('parent');parent.locator('#parent-year').fill(str(today.year));parent.locator('#parent-term').select_option(term)
        parent.locator('#parent-refresh').click();parent.locator('#tab-assignments').click()
        parent_card=parent.locator('#parent-assignment-list .work-card').filter(has_text=title)
        expect(parent_card).to_contain_text('Missing')
        card.locator('[data-work-action="register"]').click()
        row=teacher.locator('#completion-register-body tr').filter(has_text='Amina')
        expect(row).to_contain_text('Missing');row.locator('.work-completion-status').select_option('SUBMITTED')
        row.locator('.work-submitted-on').fill(today.isoformat())
        assert row.locator('.work-late-reason').evaluate('(el)=>el.required')
        row.locator('.work-late-reason').fill('Fictional illness delayed completion.')
        with teacher.expect_response(lambda r:f'/class-assignments/{key}/completions' in r.url and r.request.method=='PUT') as response:
            teacher.locator('#work-save-register').click()
        assert response.value.status==200,response.value.text()
        expect(row).to_contain_text('Submitted late')
        expect(parent_card).to_contain_text('Submitted late',timeout=35000)
        expect(parent_card).to_contain_text('Fictional illness')
        screenshots.mkdir(parents=True,exist_ok=True)
        parent.screenshot(path=str(screenshots/'assignments-parent-desktop.png'),full_page=True)
        parent.set_viewport_size({'width':390,'height':844})
        assert parent.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Parent mobile overflow'
        parent.screenshot(path=str(screenshots/'assignments-parent-mobile.png'),full_page=True)
        teacher.set_viewport_size({'width':390,'height':844})
        assert teacher.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Teacher mobile overflow'
        teacher.screenshot(path=str(screenshots/'assignments-teacher-mobile.png'),full_page=True)
        teacher.set_viewport_size({'width':1440,'height':1000});teacher.locator('#work-close-register').click()
        card.locator('[data-work-action="edit"]').click();teacher.locator('#edit-title').fill(title+' edited')
        teacher.locator('#record-editor-save').click();expect(card).to_contain_text(title+' edited')
        card.locator('[data-work-action="status"]').click();expect(card).to_have_count(0)
        parent.locator('#parent-refresh').click();expect(parent_card).to_have_count(0)
        teacher.locator('#work-include-withdrawn').check();expect(card).to_contain_text('Withdrawn')
        card.locator('[data-work-action="status"]').click();expect(card).not_to_contain_text('Withdrawn')
        parent.locator('#parent-refresh').click();expect(parent_card).to_contain_text('Submitted late')
        browser.close();assert not errors,errors
        print('PASS: assignment CRUD, missing/late status, required reason, completion register, parent auto-refresh and desktop/mobile layouts')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base-url',default='http://127.0.0.1:18082')
    parser.add_argument('--screenshots',type=Path,default=Path('/tmp/ipd-assignment-screenshots'));args=parser.parse_args()
    rehearse(args.base_url.rstrip('/'),args.screenshots)
