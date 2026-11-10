# CRUD completion and verification — 10 November 2026

The gaps identified in the earlier CRUD audit are now implemented through API endpoints and dashboard controls. Parent monitoring remains read-only; teacher and administrative permissions still apply.

| Role / resource | Create | Read | Update | Remove |
|---|---|---|---|---|
| Admin: accounts of all roles | Yes | List with active status | Edit profile, role and optional password | Deactivate, with restore |
| Admin: learner records | Yes | List with archive status | Edit profile and class | Archive, with restore |
| Admin: teaching assignments | Yes | Yes | Edit teacher/class/subject | Delete |
| Admin: parent–learner links | Yes | Yes | Edit parent/learner/relationship | Unlink |
| Teacher: assessments | Yes | Yes | Correct score, subject, date and period | Delete incorrect record |
| Teacher: behaviour ratings | Yes | Yes | Correct rating, category, note and date | Delete incorrect record |
| Teacher: observations | Yes | Yes | Correct note, date and period | Delete incorrect record |
| Teacher: attendance | Selected entries / mark all present | Load a saved register by class/date | Resubmit corrected entries | Delete saved entry |
| Parent: linked learner information | Not permitted | Yes | Not permitted | Not permitted |
| All roles: own notifications/preferences | System initialization | Yes | Read state and preferences | Not a manual record-removal workflow |

## How to use the controls

- **Admin → Users:** use Edit for account details. Leave the password blank to retain it. Deactivate stops login and existing sessions; Restore allows a fresh login. Accounts and their historical references remain stored.
- **Admin → Students:** use Edit, Archive or Restore. Archived learners are hidden from active teacher rosters, parent learner lists, new links and cohort calculations. Existing records are preserved.
- **Admin → Assignments & Links:** use Edit to change the existing relationship, or the existing Remove/Unlink actions. Changed relationships immediately affect access checks.
- **Teacher → Assessments:** each assessment row has Edit and Delete. All retrieved assessment records are available rather than only the most recent 15.
- **Teacher → Behaviour & Notes:** select a learner, then use Edit/Delete on the relevant history row.
- **Teacher → Attendance:** choose the date. Existing entries load automatically; Load saved register retries retrieval. Unrecorded learners remain unmarked until explicitly selected or Mark All as Present is used. Saved statuses, including Excused, and remarks round-trip. Delete saved entry removes an incorrect attendance record.

## Permissions and lifecycle rules

The last active administrator cannot be demoted, and an administrator cannot deactivate their own account. Role changes require removal of existing teaching assignments/parent links first. New assignments/links require active accounts and unarchived learners. Duplicate usernames, admissions and relationships are rejected.

Password resets, role changes and deactivation invalidate existing JWT sessions. Reactivation does not make old tokens valid again. An unchanged password remains valid after restoration, with a new login.

Teachers may correct or remove records only for currently assigned classes; assessments additionally require assignment to both the original and replacement subject. A record cannot be moved to another learner through an edit. Removing an assignment or parent link revokes access on subsequent requests.

## Analytics and correction history

Assessment edits/deletions refresh affected cohort predictions, including both periods when an assessment changes term/year. Behaviour/attendance changes refresh the learner's old/new periods. Class changes, archive and restore refresh affected cohorts across their recorded periods. In this prototype, historical percentiles use current class membership; historical enrollment tracking remains future work.

Deleting a learner's last assessment leaves that period pending and suppresses old probability/recommendation output. A model failure preserves the teacher's correction/removal and audit entry, marks analytics unavailable, and supports the existing Recalculate retry.

Correction/deletion history is stored in the additive `record_changes` table: actor, record type/id, operation, timestamp, and before/after values. Passwords and password hashes are excluded. Admins can inspect entries through `GET /api/admin/change-history?entity_type=assessments&entity_id=ID` (also available in `/docs`). Teacher source records are removed by Delete; their previous values remain in this protected history.

## API additions and compatibility

- `PUT /api/admin/users/{id}`, `DELETE /api/admin/users/{id}`, `PATCH /api/admin/users/{id}/status` (`is_active`).
- `PUT /api/admin/students/{id}`, `DELETE /api/admin/students/{id}`, `PATCH /api/admin/students/{id}/status` (`is_archived`).
- `PUT /api/admin/teacher-assignments/{id}` and `PUT /api/admin/parent-links/{id}`.
- `PUT` and `DELETE /api/teacher/assessments/{id}`, `/behaviour/{id}`, `/observations/{id}`.
- `GET /api/teacher/attendance?grade_level=Grade%207&stream=Demo%20East&record_date=2026-09-26` and `DELETE /api/teacher/attendance/{id}`. Attendance updates retain the existing bulk-save endpoint.

Updates accept the full editable record shape. User updates accept an optional password; omitted/null retains the existing hash. Correction dates omitted/null retain the record's original date. Deleting users/students is explicitly a reversible lifecycle action rather than physical deletion.

Startup adds `user_lifecycle`, `student_lifecycle` and `record_changes`. Existing tables/credentials/source records are not altered or reset. Accounts/learners without lifecycle entries default to active/unarchived. Legacy JWTs default to version zero until invalidated through a lifecycle action. SQL create-table permission is required, as for the existing application startup.

## Verification

- Full automated suite: **96 tests passed**.
- CRUD and lifecycle tests: **28 passed on isolated MySQL**, in addition to the SQLite regression run.
- Browser lifecycle rehearsal passed for account edit/deactivate/restore, learner edit/archive/restore, relationship editing, all three teacher record correction/deletion workflows, and saved attendance reload/correct/delete.
- Teacher-to-parent browser rehearsal passed, including real 30-second refresh and desktop/mobile layout.
- Source changes survive model failure, and stale outputs remain suppressed. Tests cover subject/class restrictions, old-session revocation, last-admin protection, duplicate validation, access after link/assignment changes, archived learners, and deletion of the final assessment.

Tests use temporary SQLite or the explicitly configured disposable `ipd_crud_test` database. Browser writes use fictional records in `ipd_crud_browser_test`; the running demonstration database is not reset for tests.

From `backend/`, run `python -m pytest tests -q`. MySQL-specific tests use `CRUD_TEST_DATABASE_URL` pointing to a disposable database whose name ends in `_crud_test`; tests create/drop its tables. Browser checks use `python -m scripts.browser_lifecycle --base-url http://127.0.0.1:18082` and the existing `scripts.browser_demo`, against a separately seeded server. Browser scripts create fictional records and should be run only on a demonstration database.

These checks validate prototype functionality, not multi-user concurrency, production load or educational model accuracy. Assignment completion has since been implemented; see [Phase 2A](assignment-tracking.md). Structured competency tracking has also been implemented; see [Phase 2B](competency-tracking.md). Teacher catalog edit/archive/restore and evidence create/read/correct/delete are protected by current class/subject permissions, with parent summaries restricted to linked learners. Private two-way messaging is now implemented; see [Phase 2C](messaging.md). Messages intentionally have no edit/delete API; corrections use follow-up messages and administrators cannot read their content. See the [project handover](HANDOVER.md) for the remaining roadmap.
