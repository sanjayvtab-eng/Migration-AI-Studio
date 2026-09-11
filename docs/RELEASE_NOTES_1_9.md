# Release Notes 1.9.0 — Issue Governance

## Added
- Clickable Issues grid rows and an issue detail drawer.
- Resolve, Close, Reopen actions with mandatory operator comments.
- Structured issue detail: issue ID, object, run ID, error, recommendation, status and action audit history.
- Re-check Evidence action. A deployment issue can be automatically resolved when successful deployment evidence exists for the same object.
- View Logs from the issue drawer, filtered to the linked run/object.
- Structured run ID / failed-object details on new deployment blocker issues.
- Open deployment blocker deduplication.

## Governance behavior
- Only OPEN BLOCKER issues prevent DEV precheck/deployment. RESOLVED and CLOSED issues do not block.
- A successful object deployment/resume automatically resolves matching open DEPLOYMENT issues.
- Manual resolution/closure requires a reason and is recorded as immutable ISSUE_ACTION evidence.
- Reopen restores the issue to OPEN and makes it eligible to block again.

## Validation
- Backend Python compile: PASS.
- Existing + new backend automated tests: 39 PASSED.
- Issue lifecycle API test covers mandatory comments, resolve and reopen.
