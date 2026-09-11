# Local SQL Server connector

The hosted backend cannot reach a laptop SQL Server by its Windows machine name.
This connector polls the application over outbound HTTPS and performs source reads
locally. It has no inbound listening port. Databricks writes still run in the backend.

## Deploy the application update

Deploy the backend and frontend from the same connector-enabled revision. New
`source_connector` and `connector_task` tables are created during normal startup;
existing source records and direct connections remain unchanged. Use a persistent
application database: queued work and registrations cannot survive loss of an
ephemeral database. No SQL Server firewall port needs to be opened to Render.

## Register and start

1. Sign in as an ADMIN. In Sources, choose Manage connector beside the existing source.
2. Register the connector. Keep the dialog open to read the one-time token.
3. On the Windows SQL Server machine, obtain the same repository revision.
4. Install Microsoft ODBC Driver 18 for SQL Server, Python 3.10 or newer, and run
   `python -m pip install -r scripts/connector-requirements.txt` from the repository root.
5. Run the command displayed in the Sources dialog. Paste the token at the hidden prompt.
6. For Windows Authentication, run under a Windows account with SQL Server access.
   For SQL Authentication, append `--username 'your-sql-login'` and enter its password
   at the hidden prompt. Never put database passwords in the hosted source profile.
7. The SQL connection uses ODBC Driver 18 with encryption. For a SQL Express instance,
   the Sources dialog automatically adds `--trust-server-certificate` so a controlled
   local/self-signed certificate can be used while transport remains encrypted. For a
   production SQL Server, install a trusted certificate and do not use this option.
8. Leave the process running. Connector status refreshes every 15 seconds.
9. Once ONLINE, click Test, then run Discovery. Discovery tests the source again before
   capturing metadata. Review artifacts, deploy DEV, reconcile, and evaluate the gate
   using the existing workflow.

The configured source ID, server, and database must match the source profile exactly.
The connector cannot be directed to another server or database by a task. Give its
SQL account SELECT and VIEW DEFINITION only for the intended source database, with
optional statistics permissions if required. Application login credentials are not
SQL Server credentials.

## Operations and data handling

- Allowed operations: connection test, fixed metadata discovery, count a source table,
  open a table read, fetch a batch, and close the read.
- No arbitrary SQL, shell command, procedure execution, or source write API exists.
- Table/column identifiers are verified against local system metadata and quoted.
  Existing datatype adapters build projections locally.
- Decimal, binary, date, and timestamp values retain types over JSON transport.
- Fetches are at most 1,000 rows and approximately 3 MiB. A single larger row or
  discovery snapshot over the response limit fails explicitly, without truncation.
- The application temporarily stores results in its task database. Results are
  deleted after consumption; abandoned records are purged on subsequent polling.
  Secure access to this database and its backups because batches contain source data.
- Tokens are source-scoped, stored hashed in the backend, and displayed only at
  registration. Registration and revocation require ADMIN permissions under the
  application's existing shared-project authorization model.

## Recovery and limits

OFFLINE means no poll was received in 45 seconds. Tasks expire after 120 seconds;
SQL queries on table streams time out after 60 seconds. SQL cursors close after
150 seconds of inactivity or agent shutdown. Run one connector process per source.
Use Windows Task Scheduler or a managed service account for unattended operation;
provide CONNECTOR_TOKEN (and optionally CONNECTOR_SQL_PASSWORD) through your
machine's protected service environment. The foreground command is intended for testing.

After a network interruption, the connector retries result delivery, not SQL reads
that already advanced a cursor. It does not automatically repeat target writes.
Review partial target data before resuming/restarting an interrupted deployment,
using the application's existing replacement approval process.

Revoke immediately disables authentication and cancels queued work. It cannot undo
a source read already running locally. Re-register to issue a new token and restart
the process. Revocation does not silently fall back to direct backend connections.

Keep the connector online throughout discovery, DEV extraction, and DEV source
reconciliation. TEST/UAT/PROD Databricks promotion behavior remains unchanged.
Hosted cold starts, process restarts and provider request limits can still interrupt
long synchronous migration requests; this connector does not replace the existing
migration execution engine with a durable background worker.

## Verification

Test an invalid token, an offline connector, incorrect SQL credentials, and a
database permission failure. Then test a valid connection, discover the source,
deploy a small table, and verify its reconciliation row count. Stop the connector
and confirm operations report OFFLINE/TIMEOUT rather than falling back to direct
access. Re-register and confirm the previous token is rejected.
