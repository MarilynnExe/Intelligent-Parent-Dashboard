"""Read-only admin reporting rehearsal against separately seeded fictional data."""
import argparse
import csv
import io
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, expect

def rehearse(base,screenshots):
    today=datetime.now(ZoneInfo('Africa/Nairobi')).date()
    term='Term 1' if today.month<=4 else 'Term 2' if today.month<=8 else 'Term 3'
    errors=[];screenshots.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base+'/portal/login.html');page.locator('#username').fill('demo.admin');page.locator('#password').fill('DemoSchool2026!');page.locator('#submit-btn').click();page.wait_for_url('**/admin-dashboard.html')
        expect(page.locator('#report-grade option')).not_to_have_count(1)
        page.locator('#tab-reports').click();page.locator('#report-year').fill(str(today.year));page.locator('#report-term').select_option(term);page.locator('#report-generate').click()
        expect(page.locator('#report-results')).to_be_visible();expect(page.locator('#report-generated')).to_contain_text(str(today.year))
        expect(page.locator('#report-classes')).to_contain_text('Demo East');expect(page.locator('#report-classes')).to_contain_text('Demo West')
        expect(page.locator('#report-subjects')).to_contain_text('Mathematics')
        expect(page.locator('#report-comparison-note')).to_contain_text('Compared with')
        page.locator('#report-grade').select_option('Grade 7');page.locator('#report-stream').select_option('"Demo West"')
        expect(page.locator('#report-generated')).to_contain_text('Demo West')
        expect(page.locator('#report-learners')).to_contain_text('Esther Demo')
        expect(page.locator('#report-subjects')).to_contain_text('No recorded data')
        page.locator('#report-stream').select_option('');expect(page.locator('#report-generated')).to_contain_text('All streams')
        page.locator('#report-issue').select_option('no_assessments');expect(page.locator('#report-learners')).to_contain_text('Not assessed')
        expect(page.locator('#report-learners')).not_to_contain_text('Amina Demo')
        page.locator('#report-export-dataset').select_option('learners')
        with page.expect_download() as download:page.locator('#report-export').click()
        path=screenshots/'learners.csv';download.value.save_as(path)
        rows=list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
        assert rows and all(row['academic_average']=='' for row in rows)
        assert all(row['learner_issue_filter']=='no_assessments' for row in rows)
        page.locator('#report-issue').select_option('all');expect(page.locator('#report-learners')).to_contain_text('Amina Demo')
        page.locator('#report-year').fill('2001');page.locator('#report-year').press('Tab')
        expect(page.locator('#report-generated')).to_contain_text('2001');expect(page.locator('#report-subjects')).to_contain_text('No recorded data')
        page.locator('#report-year').fill(str(today.year));page.locator('#report-year').press('Tab');expect(page.locator('#report-subjects')).to_contain_text('Mathematics')
        # A failed refresh must hide old results and disable exports, then recover.
        pattern='**/api/admin/reports/overview?*'
        page.route(pattern,lambda route:route.fulfill(status=503,content_type='application/json',body='{"detail":"Reporting temporarily unavailable"}'))
        page.locator('#report-generate').click();expect(page.locator('#report-status')).to_contain_text('temporarily unavailable')
        expect(page.locator('#report-results')).to_be_hidden();expect(page.locator('#report-export')).to_be_disabled()
        page.unroute(pattern);page.locator('#report-generate').click();expect(page.locator('#report-results')).to_be_visible()
        page.screenshot(path=str(screenshots/'reports-admin-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Admin mobile overflow'
        page.screenshot(path=str(screenshots/'reports-admin-mobile.png'),full_page=True)
        assert not errors,errors
        browser.close()
    print('School report rehearsal passed: filters, comparisons, CSV, empty/error recovery and desktop/mobile.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base-url',default='http://127.0.0.1:8000');parser.add_argument('--screenshots',type=Path,default=Path('/tmp/ipd-report-screenshots'))
    args=parser.parse_args();rehearse(args.base_url.rstrip('/'),args.screenshots)
