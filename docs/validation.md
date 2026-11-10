# Demonstration validation — 10 November 2026

## Environment

- Linux, Python 3.12.3; exact runtime/test/browser packages recorded in `backend/requirements-demo.lock`.
- Temporary SQLite databases for automated tests. Tests never use the configured school database.
- Separate MySQL 8.0.46 instance and fictional `ipd_demo` database under `/tmp` for database/browser rehearsal. The configured school database was not seeded or modified.
- Chromium via Playwright, desktop 1440 × 1000 and mobile 390 × 844 viewports.

## Checks performed

- Automated suite: **68 passed**. Includes existing API/model/learning-path/notification/workload tests and nine new demo regression tests.
- Genuine saved CatBoost model/calibrator loading and inference; no training or artifact replacement.
- Teacher assessment saves refresh the affected cohort, recommendations and parent-facing analytics.
- Model failure preserves the assessment, marks analytics unavailable, withholds old predictions/recommendations/learning paths, and recovers through recalculation. Includes failure before a learner's first prediction.
- Attendance correction changes term absences; behaviour rules respect term date windows and dispatch classroom guidance.
- Parent progress filters by period, separates recorded attendance from missing records, and enforces linked-learner access. Teacher and parent write/access restrictions are tested.
- Repeated demo seeding does not duplicate source records or unread notification entries. Recently read matching notifications use read time for the 24-hour cooldown.
- Generated learning-path reasons fit the MySQL VARCHAR(500) limit. MySQL rehearsal originally exposed an overlong explanation; the final explanation preserves the benchmark and topic-evidence qualifications within the established limit.
- Browser rehearsal passed: real login for each role; teacher assessment, attendance and behaviour entry; parent update through the real 30-second poll; notification display; period switching and empty state; manual refresh; teacher recalculation retry; desktop and mobile page layout.
- Mobile rehearsal exposed overflowing class/learner selectors; both now remain within the viewport. Tables retain local horizontal scrolling.
- Python parsing and Node JavaScript syntax checks passed for modified application code.

Screenshots from rehearsal are in `/tmp/ipd-demo-screenshots/` (`parent-desktop.png`, `parent-mobile.png`, `teacher-mobile.png`). Run `python -m scripts.browser_demo` against a seeded demonstration server to reproduce screenshots; the script adds fictional records as documented.

## Limits of this evidence

The suite reports existing Pydantic configuration and naive-UTC datetime deprecation warnings. They do not fail these checks. This is functional prototype verification, not a stakeholder usability study, production load test or validation of model accuracy on Kenyan learners. Recalculation runs synchronously for small cohorts; concurrent multi-user workloads and background job delivery remain pilot work. Benchmark evaluation metrics are reproduced from the existing evaluation report, not newly measured here.

The local configured MySQL connection was unavailable, so all MySQL writes and browser checks used an isolated instance. No changes were made to the user's existing database credentials or real learner records.

## Subsequent CRUD completion

The later lifecycle/correction build passed **96 automated tests**, with **28 CRUD/lifecycle cases passing separately on MySQL**. The browser lifecycle rehearsal covers account edit/deactivate/restore, learner edit/archive/restore, teaching assignment and parent-link edits, teacher record corrections/deletions, and saved attendance reload/update/removal. The complete teacher-to-parent desktop/mobile rehearsal was rerun after these additions. See [CRUD completion](crud-audit.md) for APIs, controls, protected correction history and remaining phase-2 scope.

## Phase 2A assignment tracking

The assignment release passed **110 automated tests**, including **14 assignment-specific cases** that also passed separately on isolated MySQL. These cover automatic missing status, the Nairobi calendar-day boundary, late reasons, atomic register validation, zero-denominator rates, enrollment/transfers/archive/restore, withdrawal/deadline correction, notification preferences/deduplication/recovery, read-only GETs, and additive demo seeding. Tests confirm assignment creation leaves assessment records and stored prediction values/timestamps unchanged; assignment guidance also works without assessment/model availability.

The Chromium assignment rehearsal passed create/edit/withdraw/restore, completion saving with late reasons, actual parent polling and desktop/mobile layout. Screenshots are in `/tmp/ipd-assignment-screenshots`. See [assignment tracking](assignment-tracking.md) for usage, endpoints, seed flags and the absence of scheduled reminders. No model retraining was performed.

## Phase 2B competency tracking

The complete regression run passed **126 tests**. A subsequent focused check for catalog edits refreshing an existing parent alert also passed (**1 additional test**); the current suite therefore contains 127 tests. All **17 competency-specific cases passed on isolated MySQL** (16 in the initial batch, followed by the final catalog-edit notification check). The equivalent competency checks passed on SQLite. The final notification-only correction was verified with the focused check rather than rerunning unrelated tests.

Coverage includes catalog/evidence CRUD, archive/restore without losing evidence, latest-date and same-day-ID ordering, selected-period history, explicit unassessed states, guidance changes, class/subject and parent-link authorization, archived learners, transfers, repeatable fictional seeding, notification preferences/deduplication/resolution/retry, both periods after a correction, and preservation of stored prediction snapshots. No competency evidence is added to CatBoost inputs.

Chromium rehearsal covers teacher catalog creation/edit/archive/restore, learner evidence create/correct/delete, parent updates through the actual 30-second poll, period switching, evidence history, and desktop/mobile layouts. A learner without scored assessments still displays competency progress while academic analytics is Pending. Screenshots are written to `/tmp/ipd-competency-screenshots`; reproduce with `python -m scripts.browser_competencies --base-url http://127.0.0.1:8000` on a separately seeded demo database.

The live local demo received additive competency tables and explicit fictional examples; its existing analytics probabilities and calculation timestamps were checked unchanged. Python compilation and modified JavaScript syntax checks passed. Existing library/Pydantic/naive-UTC deprecation warnings remain non-failing prototype maintenance work. These checks do not establish official curriculum alignment, Kenyan predictive accuracy, production concurrency or stakeholder acceptance.

## Phase 2C private parent–teacher messaging

The complete regression suite passed **144 tests**, with **1 skipped** MySQL-only row-lock concurrency test. That concurrency test passed against disposable MySQL. All **18 messaging-specific cases passed on MySQL** (17 in the initial batch plus the explicit-seed/teacher-initiation case). The SQLite regression covers the other 17 messaging cases.

Coverage includes initiation by both roles; teacher contact deduplication across subjects; private membership and administrator denial; current learner/contact access; retained read-only history after parent unlink, teacher assignment removal, transfer, archive, role change or recipient deactivation; reply restoration; inactive caller rejection; trimmed text validation and immutable endpoints; history/list pagination; read-only GETs; monotonic and partial read cursors; unread counts and read receipts; idempotent retries/conflicting identifiers; generic notification content/preferences/deduplication/new alerts after reading; preservation and retry after notification failure; repeatable explicit fictional examples; and unchanged stored prediction snapshots. Concurrent MySQL checks verify one stored message for simultaneous identical retries and one unread alert for concurrent incoming messages.

Chromium rehearsal verifies both directions of private messaging through the actual 30-second refresh, Sent/Read display, literal HTML-looking text, and a lost response *after* the server saves the message followed by a safe duplicate-free retry. It also covers older-message pagination and desktop/mobile layouts. Final UI checks verify hidden pagination controls, refresh preserving learner selection, and retained history with all demo parent links removed, followed by restoration. Rehearsal changes only fictional data in the isolated browser database. Screenshots: `/tmp/ipd-messaging-screenshots`.

Message storage and alerts are separate from academic analytics. No model training or new Kenyan accuracy evaluation was performed. Messaging uses additive tables and synchronous, post-commit generic alerts; production retention, durable notification retry jobs, deployment/security review and load testing remain future work. Browser drafts are in memory, not durable storage. Existing deprecation warnings remain non-failing.

## Phase 2D school-wide reporting

The full regression suite passed **161 tests**, with **1 skipped** existing MySQL-only concurrency case. All **17 reporting integration cases passed on isolated MySQL** as well as SQLite. Focused MySQL checks after the final population-query refinement also passed, including archived/blank-stream handling, year boundaries and the absence of report-side writes. The existing messaging concurrency case was already exercised on MySQL in Phase 2C; it is intentionally skipped in the SQLite regression.

Report coverage includes school/class/grade/subject aggregation; equal weighting per assessed learner; no-data/zero-denominator handling; grade/stream filters including null/blank streams; archived-learner exclusion; previous-term/year comparison and earliest supported year; attendance Late/Excused handling and monthly counts; due/excused/withdrawn assignment semantics; competency slot coverage and latest evidence with transfer history; invalid/stale prediction suppression; learner issue filters and pagination; all-matching CSV exports; spreadsheet formula safety and UTF-8 metadata; administrator-only authorization; and unchanged database record counts/prediction timestamps after repeated report/export reads. Reports do not query private message content or teacher evidence text and do not call the prediction pipeline.

Chromium rehearsal passed filters, previous-period comparison, a class without assessments, learner follow-up selection, authenticated CSV download and content, empty historical periods, simulated API failure with old outputs hidden/export disabled, recovery, and desktop/mobile layout. Mobile verification exposed a comparison table without a local scrolling wrapper; the final table scrolls within its card, and the page fits a 390px viewport. Screenshots and a fictional learner CSV: `/tmp/ipd-report-screenshots`.

No new database tables, model artifacts or learner fixtures are required for reports. Rehearsal used the existing separate MySQL browser database; the local demo was restarted with the updated API/UI. Python compilation and JavaScript syntax checks passed. Report limitations remain explicit: one configured school, current enrollment/catalog for historical periods, recorded rather than scheduled attendance denominators, synchronous in-memory aggregation for prototype cohorts, no official curriculum completeness or causal intervention claims, and no new Kenyan model validation.
