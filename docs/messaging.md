# Phase 2C — private parent–teacher messaging

## Using Messages

Both teacher and parent dashboards have a **Messages** tab. Select a learner and an eligible contact, then choose **Open conversation**. A teacher sees linked parents; a parent sees current class teachers, deduplicated across subjects. Either role can initiate. One conversation is retained per learner/parent/teacher combination across terms.

Write plain text (1–4,000 characters after trimming) and choose **Send message**. History is chronological with **Load older messages**, timestamps, Sent/Read labels and unread counts. There are no attachments, group threads, edits or deletions; send a follow-up correction instead. Administrators have no messaging endpoint or dashboard access to message content. This is application authorization; ordinary database administration remains outside the messaging interface.

Visible dashboards refresh conversation lists and unread counts every 30 seconds. An open, visible conversation also retrieves new messages and advances its read cursor. Background tabs and unopened conversations do not automatically mark messages read. **Refresh messages** retries immediately. The messaging learner selector is independent of academic year/term and the monitoring selector.

## History and authorization

Every content/read request requires an original participant. Current active accounts with PARENT or TEACHER role may read their own conversations. Contacts, starting conversations and sending additionally require both original participants to have the expected active roles, an active learner, a current parent link and a current teacher assignment to the learner's class. A teacher assigned multiple subjects is still one contact.

Removing a parent link, removing teaching assignments, transferring the learner out of the teacher's class, archiving the learner or changing/deactivating a participant makes replies unavailable. The other active original participant retains read-only history. Restoring all required conditions restores replies in the same conversation. Inactive accounts cannot authenticate; administrator-role accounts cannot access messaging, including former participation. Historical conversation access does not grant access to current learner monitoring, new contacts or unrelated conversations. Messages remain accessible even if a parent has no currently linked learners.

Conversations expose only learner/contact names, identifiers and messaging state. Messages are not copied into the administrator correction-history table. Retained history and immutable text are deliberate first-release behaviour; no self-service message deletion or retention scheduler is included.

## Reliable sending and notifications

A client-generated UUID identifies each send; the database uniquely constrains sender/UUID. Retrying the same text and conversation returns the same stored message. Reusing an identifier with different text or another conversation returns 409. Conversation uniqueness and MySQL row locks protect concurrent creation/sends, read cursors and unread-alert creation.

The message commits before alert delivery. A notification failure returns a successful saved message with `notification_delivery.status=retry_needed`; it does not roll back content. The API supports retrying the same send to retry notification delivery. The UI explains that a saved message's alert failed; the recipient can still discover it through Messages polling. There is no durable notification retry worker.

If a network response is lost, the composer preserves its draft and identifier for **Retry send**. While delivery is uncertain, the draft is locked against changes; switching threads preserves it in memory. A refresh that finds the same identifier reconciles the send. Closing/reloading the browser loses unsent in-memory drafts. Message text is escaped for display; HTML-looking text stays literal text.

New-message alerts contain no message-body preview and use SYSTEM/MEDIUM with the existing global notification preference. Detailed and concise styles receive the same generic alert. Academic/attendance/behaviour category toggles do not control private messages. There is at most one unread messaging alert per conversation/recipient; additional unread messages reuse it. A new incoming message after the alert is read can create a new alert without the analytics 24-hour cooldown. Reading all messages through the latest displayed ID clears the matching alert; reading an older page must not clear newer unread messages. Conversation unread counts are independent of alert preferences and alert read state.

## API

All endpoints are under `/api/messaging`, require authentication, and deny ADMIN.

| Method | Endpoint | Request / purpose |
|---|---|---|
| GET | `/learners` | Current authorized active learners for starting conversations |
| GET | `/contacts?student_id=ID` | Eligible opposite-role contacts |
| GET | `/conversations?limit=30&offset=0` | Participant-only conversation page and total unread messages |
| POST | `/conversations` | `{student_id, contact_user_id}`; create or return the existing conversation |
| GET | `/conversations/{id}/messages?limit=50` | Latest page, chronologically ordered |
| GET | `/conversations/{id}/messages?before_id=ID` | Older history page |
| GET | `/conversations/{id}/messages?after_id=ID` | Newer messages in ascending order; continue while `has_more` |
| POST | `/conversations/{id}/messages` | `{body, client_message_id}`; immutable idempotent send |
| POST | `/conversations/{id}/read` | `{through_message_id}`; monotonically advance the caller's cursor |

Page limits are 1–100. `before_id` and `after_id` are mutually exclusive. Message responses contain conversation metadata, `items`, `has_older` and `has_more`; GETs do not advance read state. Conversation metadata includes `can_reply`, `read_only_reason`, `unread_count` and peer read cursor. A read cursor must reference a message in that conversation. Nonparticipants receive 404 for conversation content and read operations; no membership discovery is exposed.

## Data and setup

The additive `message_conversations` and `private_messages` tables are registered on startup; read cursors live on the conversation row. Existing tables/model artifacts are not altered, and existing endpoints remain compatible. This uses the prototype's table-creation mechanism, not versioned migrations. SQLite provides isolated functional tests; MySQL tests additionally exercise row-lock concurrency.

Explicit fictional examples:

```bash
# From backend/, against a local demonstration database only:
python -m scripts.seed_demo --term 'Term 3' --year 2026 --with-assignments --with-competencies --with-messages
python -m scripts.browser_messaging --base-url http://127.0.0.1:8000
```

The new flag creates one fictional Amina parent/teacher conversation only when the pair has no existing conversation. Repeat invocations preserve existing history and read state; no messages are automatically injected into school conversations. Browser rehearsal adds fictional messages, including enough history to test pagination. Use a separate rehearsal database. Screenshots default to `/tmp/ipd-messaging-screenshots`. Verification: 144 regression tests passed, one MySQL-only test skipped on SQLite; all 18 messaging cases passed separately on MySQL. See [validation results](validation.md).
