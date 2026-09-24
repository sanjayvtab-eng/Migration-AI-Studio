# Release 7: Prompt-native migration design

Release 7 turns a business migration prompt into a governed, versioned Bronze/Silver/Gold design. It does not treat a prompt as blanket approval.

## Workflow

1. Discover the SQL Server source and provision DEV.
2. Submit the complete business prompt in **Prompt-native design**.
3. Review metadata grounding and answer only the unresolved choices.
4. Review and approve the exact versioned plan.
5. Generate deterministic SQL artifacts.
6. Run target validation against Databricks.
7. Review every current artifact version separately.
8. Deploy to DEV and reconcile.

Changing an answer creates a new specification version and invalidates the earlier plan approval. Changing generated SQL creates a new artifact version and requires a new artifact review.

## Safety rules

- Identifiers must resolve to the captured metadata snapshot.
- Function parameters use an unqualified `p_` namespace; columns are relation-qualified.
- Incremental loaders use `MERGE` and never delete rows merely because they disappeared from the source batch.
- Stored procedures are emitted only when `DATABRICKS_SQL_PROCEDURES_SUPPORTED=true`; otherwise the design uses an explicit SQL workflow artifact.
- DEV deployment requires passed static and target validation plus approval of every current artifact version.

## Bronze target consistency repair

Prompt-native Medallion deployment treats the approved Bronze node target as the single physical destination. Bronze ingestion receives that persisted target explicitly and uses it for row checks, staging replacement, inserts, validation, and evidence. Standalone Bronze ingestion retains its source-aligned default when no approved target is supplied.

A previously verified checkpoint is reusable only when both its source object and target FQN match the current approved node. Target-mismatched evidence is retained for audit with `CHECKPOINT_TARGET_MISMATCH`; it is skipped and the deployment attempts a fresh load to the approved target. Existing source-aligned tables are never renamed or dropped by this repair.

## Configuration

```text
PROMPT_NATIVE_DESIGN_ENABLED=true
DATABRICKS_SQL_PROCEDURES_SUPPORTED=false
PROMPT_TARGET_VALIDATION_REQUIRED=true
```

Apply `backend/migrations/0007_release7_prompt_native.sql` to an existing control database. The rollback file removes only Release 7 tables.

## API sequence

The UI calls `POST /api/projects/{project_id}/prompt-specifications`, then the clarification, plan approval, generation, validation, artifact review, DEV deployment, and trace endpoints under that specification.
