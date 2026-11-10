"""Private message rehearsal against fictional demo accounts on a separate database."""
import argparse
from pathlib import Path
from time import time_ns
from playwright.sync_api import sync_playwright, expect

def rehearse(base,screenshots):
    unique=str(time_ns());question='Fictional browser question '+unique
    reply='Fictional teacher reply '+unique
    retry='Fictional retry-safe message '+unique
    screenshots.mkdir(parents=True,exist_ok=True)
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        def login(role):
            page=browser.new_context(viewport={'width':1440,'height':1000}).new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base+'/portal/login.html');page.locator('#username').fill('demo.'+role);page.locator('#password').fill('DemoSchool2026!');page.locator('#submit-btn').click();page.wait_for_url('**/'+role+'-dashboard.html')
            page.locator('#tab-messages').click();expect(page.locator('#message-learner option')).not_to_have_count(1)
            return page
        parent=login('parent');teacher=login('teacher')
        def open_amina(page):
            options=page.locator('#message-learner option').evaluate_all('(nodes)=>nodes.map(n=>({value:n.value,text:n.textContent}))')
            amina=next(o for o in options if 'Amina Demo' in o['text'])
            page.locator('#message-learner').select_option(amina['value']);expect(page.locator('#message-start-button')).to_be_enabled()
            page.locator('#message-start-button').click();expect(page.locator('#message-thread-title')).to_contain_text('Amina Demo')
        open_amina(parent);open_amina(teacher)
        expect(parent.locator('#message-contact option')).to_have_count(1)
        parent.locator('#message-body').fill(question+' <img src=x onerror="window.messageXss=true">')
        parent.locator('#message-send').click();expect(parent.locator('#message-history')).to_contain_text(question)
        # Wait for the other role's actual 30-second visible-page refresh.
        expect(teacher.locator('#message-history')).to_contain_text(question,timeout=35000)
        assert not teacher.evaluate('Boolean(window.messageXss)')
        assert teacher.locator('#message-history img').count()==0
        teacher.locator('#message-body').fill(reply);teacher.locator('#message-send').click()
        expect(parent.locator('#message-history')).to_contain_text(reply,timeout=35000)
        selected=parent.locator('#message-learner').input_value()
        parent.locator('#messages-refresh').click()
        expect(parent.locator('#message-learner')).to_have_value(selected)
        expect(parent.locator('#messages-more-conversations')).to_be_hidden()
        expect(parent.locator('#message-history li').filter(has_text=question)).to_contain_text('Read')
        # Server saves the message, but its response is lost. Retrying must not duplicate it.
        pattern='**/api/messaging/conversations/*/messages'
        def lose_response(route):
            if route.request.method=='POST':
                route.fetch();route.abort()
            else:route.continue_()
        parent.route(pattern,lose_response);parent.locator('#message-body').fill(retry);parent.locator('#message-send').click()
        expect(parent.locator('#messages-status')).to_contain_text('could not be confirmed')
        expect(parent.locator('#message-body')).to_have_value(retry)
        parent.unroute(pattern,lose_response)
        parent.locator('#message-send').click();expect(parent.locator('#message-history li').filter(has_text=retry)).to_have_count(1)
        expect(parent.locator('#message-body')).to_have_value('')
        # Check older-page control using explicit fictional messages via the same API.
        token=teacher.evaluate('Auth.getToken()')
        conversations=teacher.request.get(base+'/api/messaging/conversations',headers={'Authorization':'Bearer '+token}).json()
        key=next(c['conversation_id'] for c in conversations['items'] if c['student_name']=='Amina Demo')
        from uuid import uuid4
        for i in range(51):
            result=teacher.request.post(base+f'/api/messaging/conversations/{key}/messages',headers={'Authorization':'Bearer '+token},data={'body':f'Fictional history {unique} entry {i}','client_message_id':str(uuid4())})
            assert result.ok,result.text()
        parent.locator('#message-conversations [data-conversation]').filter(has_text='Amina Demo').click()
        expect(parent.locator('#message-history li')).to_have_count(50)
        expect(parent.locator('#messages-older')).to_be_visible();parent.locator('#messages-older').click()
        expect(parent.locator('#message-history li')).not_to_have_count(50)
        parent.screenshot(path=str(screenshots/'messages-parent-desktop.png'),full_page=True)
        for role,page in [('parent',parent),('teacher',teacher)]:
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),role+' mobile overflow'
            page.screenshot(path=str(screenshots/f'messages-{role}-mobile.png'),full_page=True)
        # Former parent with no current links must still reach read-only history.
        admin_login=parent.request.post(base+'/api/auth/login',data={'email_or_username':'demo.admin','password':'DemoSchool2026!'})
        assert admin_login.ok
        admin_headers={'Authorization':'Bearer '+admin_login.json()['access_token']}
        parent_id=parent.evaluate('Auth.getUser().user_id')
        links=parent.request.get(base+'/api/admin/parent-links',headers=admin_headers).json()
        links=[link for link in links if link['parent_user_id']==parent_id]
        removed=[]
        try:
            for link in links:
                result=parent.request.delete(base+f"/api/admin/parent-links/{link['id']}",headers=admin_headers)
                assert result.ok,result.text()
                removed.append(link)
            parent.reload();parent.locator('#tab-messages').click()
            expect(parent.locator('#message-learner')).to_contain_text('No currently linked learners')
            parent.locator('#message-conversations [data-conversation]').filter(has_text='Amina Demo').click()
            expect(parent.locator('#message-reply-state')).to_contain_text('Read-only history')
            expect(parent.locator('#message-send')).to_be_disabled()
            expect(parent.locator('#message-history')).to_contain_text('Fictional history')
            parent.screenshot(path=str(screenshots/'messages-unlinked-parent-mobile.png'),full_page=True)
        finally:
            for link in removed:
                result=parent.request.post(base+'/api/admin/parent-links',headers=admin_headers,data={name:link[name] for name in ['parent_user_id','student_id','relationship_type']})
                assert result.ok,result.text()
        parent.locator('#messages-refresh').click();expect(parent.locator('#message-send')).to_be_enabled()
        assert not errors,errors
        browser.close()
    print('Messaging browser rehearsal passed: both directions, actual polling, safe rendering, lost-response retry, pagination and desktop/mobile.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base-url',default='http://127.0.0.1:8000');parser.add_argument('--screenshots',type=Path,default=Path('/tmp/ipd-messaging-screenshots'))
    args=parser.parse_args();rehearse(args.base_url.rstrip('/'),args.screenshots)
