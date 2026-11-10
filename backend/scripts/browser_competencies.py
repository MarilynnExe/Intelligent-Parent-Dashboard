"""Competency CRUD and teacher-to-parent rehearsal; use fictional demo data only."""
import argparse
from datetime import datetime
from pathlib import Path
from time import time_ns
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, expect

def rehearse(base, screenshots):
    today=datetime.now(ZoneInfo('Africa/Nairobi')).date()
    term='Term 1' if today.month<=4 else 'Term 2' if today.month<=8 else 'Term 3'
    title='Browser competency '+str(time_ns())
    screenshots.mkdir(parents=True,exist_ok=True)
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        def login(role):
            context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='Africa/Nairobi')
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
            page.goto(base+'/portal/login.html');page.locator('#username').fill('demo.'+role);page.locator('#password').fill('DemoSchool2026!');page.locator('#submit-btn').click()
            page.wait_for_url('**/'+role+'-dashboard.html');return page
        teacher=login('teacher')
        teacher.locator('#period-year').fill(str(today.year));teacher.locator('#period-year').press('Tab');teacher.locator('#period-term').select_option(term)
        expect(teacher.locator('#competency-context')).to_contain_text('Mathematics')
        teacher.locator('#tab-competencies').click();teacher.locator('#competency-name').fill(title)
        teacher.locator('#competency-strand').fill('Fictional topic');teacher.locator('#competency-description').fill('Explain an example using a diagram.')
        with teacher.expect_response(lambda r:r.url.endswith('/api/teacher/competencies') and r.request.method=='POST') as response:
            teacher.locator('#competency-form button').click()
        assert response.value.status==201,response.value.text()
        card=teacher.locator('#competency-list .work-card').filter(has_text=title)
        expect(card).to_have_count(1)
        parent=login('parent');parent.locator('#parent-year').fill(str(today.year));parent.locator('#parent-term').select_option(term);parent.locator('#parent-refresh').click();parent.locator('#tab-competencies').click()
        parent_card=parent.locator('#parent-competencies .work-card').filter(has_text=title)
        expect(parent_card).to_contain_text('Not assessed')
        card.locator('[data-action="register"]').click()
        learner=teacher.locator('#competency-register .work-card').filter(has_text='Amina Demo')
        expect(learner).to_contain_text('Not assessed')
        learner.locator('[data-action="observe"]').click()
        teacher.locator('#edit-observed_on').fill(today.isoformat());teacher.locator('#edit-level').select_option('APPROACHING_EXPECTATIONS');teacher.locator('#edit-evidence').fill('Fictional evidence: needs prompts for a diagram.')
        teacher.locator('#record-editor-save').click();expect(learner).to_contain_text('needs prompts')
        # Real visible-page polling, without refresh or a second login.
        expect(parent_card).to_contain_text('Approaching expectations',timeout=35000)
        expect(parent_card).to_contain_text('needs prompts')
        learner.locator('[data-action="observe"]').click();teacher.locator('#edit-observed_on').fill(today.isoformat());teacher.locator('#edit-level').select_option('MEETING_EXPECTATIONS');teacher.locator('#edit-evidence').fill('Fictional evidence: independent diagram explanation.')
        teacher.locator('#record-editor-save').click();expect(learner).to_contain_text('independent diagram')
        parent.locator('#parent-refresh').click();expect(parent_card).to_contain_text('Improved')
        parent_card.locator('summary').click();expect(parent_card.locator('li')).to_have_count(2)
        parent.screenshot(path=str(screenshots/'competencies-parent-desktop.png'),full_page=True)
        parent.set_viewport_size({'width':390,'height':844})
        assert parent.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Parent mobile overflow'
        parent.screenshot(path=str(screenshots/'competencies-parent-mobile.png'),full_page=True)
        teacher.set_viewport_size({'width':390,'height':844})
        assert teacher.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Teacher mobile overflow'
        teacher.screenshot(path=str(screenshots/'competencies-teacher-mobile.png'),full_page=True)
        teacher.set_viewport_size({'width':1440,'height':1000})
        learner.locator('[data-action="correct"]').first.click();teacher.locator('#edit-evidence').fill('Fictional corrected evidence: independent explanation.');teacher.locator('#record-editor-save').click();expect(learner).to_contain_text('corrected evidence')
        card.locator('[data-action="edit"]').click();teacher.locator('#edit-name').fill(title+' edited');teacher.locator('#record-editor-save').click();expect(card).to_contain_text(title+' edited')
        card.locator('[data-action="archive"]').click();expect(card).to_have_count(0)
        parent.locator('#parent-refresh').click();expect(parent_card).to_have_count(0)
        teacher.locator('#competency-include-archived').check();expect(card).to_contain_text('Archived');card.locator('[data-action="archive"]').click();expect(card).not_to_contain_text('(Archived)')
        card.locator('[data-action="register"]').click();expect(learner).to_contain_text('corrected evidence')
        learner.locator('[data-action="delete"]').first.click();expect(learner.locator('li')).to_have_count(1)
        parent.locator('#parent-refresh').click();expect(parent_card).to_contain_text('Approaching expectations')
        parent.locator('#parent-term').select_option('Term 2' if term!='Term 2' else 'Term 1');expect(parent_card).to_contain_text('Not assessed')
        # David has no scored assessments; competency data must still render.
        parent.locator('#parent-term').select_option(term)
        options=parent.locator('#child-selector option').evaluate_all('(nodes)=>nodes.map(n=>({value:n.value,text:n.textContent}))')
        david=next(option for option in options if 'David Demo' in option['text'])
        parent.locator('#child-selector').select_option(david['value'])
        expect(parent.locator('#parent-competencies')).to_contain_text('Demo: Compare fractions')
        expect(parent.locator('#hero-risk-probability')).to_contain_text('Pending')
        assert not errors,errors
        browser.close()
    print('Competency CRUD, parent polling, period switching and desktop/mobile rehearsal passed.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base-url',default='http://127.0.0.1:8000');parser.add_argument('--screenshots',type=Path,default=Path('/tmp/ipd-competency-screenshots'))
    args=parser.parse_args();rehearse(args.base_url.rstrip('/'),args.screenshots)
