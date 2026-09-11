# Release 1.8.0 — Review Governance & Safe Approval Controls

## Governed review actions
The Reviews page now supports four auditable review decisions:
- `APPROVED`
- `REJECTED`
- `REVOKED`
- `CHANGES_REQUESTED`

Every state change is stored as an immutable review event with object/version, reviewer, comments/reason and timestamp. The latest event for the current artifact version is the effective review state.

## Approval safety controls
Approval is denied by both API and UI when either condition is true:
1. The current artifact is not executable (`NON_EXECUTABLE` / architecture-review marker).
2. Static validation has not PASSED for the exact current artifact version.

The Reviews page exposes a **Validate** action and shows `Executable`, `Validation`, and `Review status` columns. When approval is blocked, the reason is shown directly beneath the action controls.

## Revoke / Reject / Request Changes
- **Revoke Approval** is available only when the effective state is `APPROVED` and requires a reason.
- **Reject** records an explicit rejected decision and requires a reason.
- **Request Changes** records `CHANGES_REQUESTED` and requires comments describing what must change.
- A revoked/rejected/change-requested current version is not deployment-eligible until a later valid approval event is recorded.

## Deployment / promotion enforcement
DEV deployment and generic environment-promotion prechecks now evaluate the latest review decision rather than accepting any historical approval. Therefore, revoking an approval immediately removes that artifact version from effective approval eligibility without deleting audit history.

## Validation evidence
Static validation writes a project-scoped `migration_validation` record tied to the exact current artifact version, including validation status and issues. A new artifact version therefore requires a fresh validation before approval.

## Compatibility
All existing 1.7 AI remediation, current-version artifacting, DEV execution, reconciliation, quality-gate, log view/download and review-history enrichment capabilities remain available.
