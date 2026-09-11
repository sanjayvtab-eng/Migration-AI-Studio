# Governed Databricks Environment Provisioning — Release 1

Release 1 adds project-scoped Databricks connection metadata and a governed DEV provisioning workflow. It creates only the approved DEV catalog and its `bronze`, `silver`, and `gold` schemas. TEST, UAT, and PROD provisioning remain deliberately disabled until promotion controls are completed.

## Security model

- The API never accepts, returns, logs, or stores a Databricks token.
- Each project stores only an environment-variable secret reference, such as `CLIENT_A_DATABRICKS_TOKEN`.
- The matching secret must be configured in the backend runtime (for example, Render Environment).
- Configuration changes reset the connection status and invalidate the current plan approval.
- Configuration, tests, preflight, approvals, and provisioning create audit records.
- Configuration changes, approval, and provisioning require an administrator token.

## Enablement

Keep the feature disabled while configuring and testing:

```text
DATABRICKS_ENVIRONMENT_PROVISIONING_ENABLED=false
CLIENT_A_DATABRICKS_TOKEN=<client-token-from-secret-store>
```

In **Environment Setup**:

1. Select the migration project.
2. Enter the workspace hostname, SQL warehouse HTTP path, token secret reference, and catalog prefix.
3. Save the configuration and test the connection.
4. Create the DEV plan.
5. Run preflight and inspect every `CREATE` or `SKIP` action.
6. Approve the plan as an administrator.
7. Set `DATABRICKS_ENVIRONMENT_PROVISIONING_ENABLED=true` and restart the backend.
8. Provision DEV.

The generated statements use `IF NOT EXISTS`, validated identifiers, and no destructive operations. A completed plan is idempotent: repeating the provision request performs no additional SQL.

## Release boundary

This release does not load source data and does not provision TEST, UAT, or PROD. Existing discovery, Medallion artifact generation, review, DEV deployment, reconciliation, and promotion flows are unchanged.
