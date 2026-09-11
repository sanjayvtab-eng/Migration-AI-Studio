from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, Float, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class ProjectScoped:
    project_id: Mapped[str] = mapped_column(String(64), index=True)

class MigrationProject(Base):
    __tablename__ = "migration_project"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class MigrationSource(Base, ProjectScoped):
    __tablename__ = "migration_source"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    server_name: Mapped[str] = mapped_column(String(255))
    database_name: Mapped[str] = mapped_column(String(255))
    profile_name: Mapped[str] = mapped_column(String(255))

class MigrationObject(Base, ProjectScoped):
    __tablename__ = "migration_object"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    database_name: Mapped[str] = mapped_column(String(255))
    schema_name: Mapped[str] = mapped_column(String(255))
    object_name: Mapped[str] = mapped_column(String(255))
    object_type: Mapped[str] = mapped_column(String(64), index=True)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (UniqueConstraint("project_id","source_id","database_name","schema_name","object_name","object_type", name="uq_obj_scope"),)

class MigrationColumn(Base, ProjectScoped):
    __tablename__ = "migration_column"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    column_name: Mapped[str] = mapped_column(String(255))
    ordinal: Mapped[int] = mapped_column(Integer)
    data_type: Mapped[str] = mapped_column(String(128))
    max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scale: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nullable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_identity: Mapped[bool] = mapped_column(Boolean, default=False)
    is_computed: Mapped[bool] = mapped_column(Boolean, default=False)
    default_definition: Mapped[str | None] = mapped_column(Text, nullable=True)

class MigrationDependency(Base, ProjectScoped):
    __tablename__ = "migration_dependency"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    referenced_database: Mapped[str | None] = mapped_column(String(255), nullable=True)
    referenced_schema: Mapped[str | None] = mapped_column(String(255), nullable=True)
    referenced_object: Mapped[str] = mapped_column(String(255))
    referenced_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dependency_type: Mapped[str] = mapped_column(String(32), default="LOCAL")

class MigrationClassification(Base, ProjectScoped):
    __tablename__ = "migration_classification"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    recommended_layer: Mapped[str] = mapped_column(String(16))
    selected_layer: Mapped[str] = mapped_column(String(16))
    classification_reason: Mapped[str] = mapped_column(Text)
    confidence_score: Mapped[float] = mapped_column(Float)
    classification_method: Mapped[str] = mapped_column(String(64))
    override_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

class MigrationMapping(Base, ProjectScoped):
    __tablename__ = "migration_mapping"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    source_fqn: Mapped[str] = mapped_column(String(1024))
    target_fqn: Mapped[str] = mapped_column(String(1024))
    target_layer: Mapped[str] = mapped_column(String(16))
    environment: Mapped[str] = mapped_column(String(16))

class MigrationArtifact(Base, ProjectScoped):
    __tablename__ = "migration_artifact"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    artifact_type: Mapped[str] = mapped_column(String(64))
    current_version: Mapped[int] = mapped_column(Integer, default=0)

class MigrationArtifactVersion(Base, ProjectScoped):
    __tablename__ = "migration_artifact_version"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    source_hash: Mapped[str] = mapped_column(String(64))
    target_hash: Mapped[str] = mapped_column(String(64))
    generator_version: Mapped[str] = mapped_column(String(64), default="enterprise-1.0")
    rule_version: Mapped[str] = mapped_column(String(64), default="rules-1.0")
    ai_provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("artifact_id","version", name="uq_artifact_version"),)

class MigrationReview(Base, ProjectScoped):
    __tablename__ = "migration_review"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_version_id: Mapped[str] = mapped_column(String(64), index=True)
    review_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    reviewer: Mapped[str] = mapped_column(String(255))
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class MigrationIssue(Base, ProjectScoped):
    __tablename__ = "migration_issue"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    issue_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    technical_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="OPEN")

class MigrationRun(Base, ProjectScoped):
    __tablename__ = "migration_run"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stage: Mapped[str] = mapped_column(String(64), index=True)
    environment: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    checkpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)

class MigrationQualityGate(Base, ProjectScoped):
    __tablename__ = "migration_quality_gate"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    environment: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(32))
    pass_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    blocker_count: Mapped[int] = mapped_column(Integer, default=0)
    deployment_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class MigrationSchemaDrift(Base, ProjectScoped):
    __tablename__ = "migration_schema_drift"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    drift_type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(32))
    details: Mapped[str] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "migration_user"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(32), default="VIEWER")
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)

# Generic project-scoped control tables required by the canonical model but represented compactly.
class CanonicalRecord(Base, ProjectScoped):
    __tablename__ = "migration_canonical_record"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    record_type: Mapped[str] = mapped_column(String(64), index=True)
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    environment: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# 2.3.0 semantic Medallion planning models. These are intentionally separate from
# the source-object mapping tables because one SQL Server object can produce
# multiple Databricks targets across Bronze, Silver and Gold.
class MigrationSemanticDefinition(Base, ProjectScoped):
    __tablename__ = "migration_semantic_definition"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    semantic_role: Mapped[str] = mapped_column(String(32), index=True)  # FACT/DIMENSION/AGGREGATE/KPI/REPORTING/ENTITY
    target_name: Mapped[str] = mapped_column(String(255))
    grain_json: Mapped[str] = mapped_column(Text, default="[]")
    business_keys_json: Mapped[str] = mapped_column(Text, default="[]")
    dimension_keys_json: Mapped[str] = mapped_column(Text, default="[]")
    attributes_json: Mapped[str] = mapped_column(Text, default="[]")
    measures_json: Mapped[str] = mapped_column(Text, default="[]")
    scd_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    definition_source: Mapped[str] = mapped_column(String(32), default="INFERRED")
    status: Mapped[str] = mapped_column(String(32), default="INFERRED", index=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("project_id","object_id","semantic_role","target_name", name="uq_semantic_scope"),)

class MigrationConsumer(Base, ProjectScoped):
    __tablename__ = "migration_consumer"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    producer_object_id: Mapped[str] = mapped_column(String(64), index=True)
    consumer_object_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    consumer_name: Mapped[str] = mapped_column(String(512))
    consumer_type: Mapped[str] = mapped_column(String(64))
    usage_type: Mapped[str] = mapped_column(String(64), default="READ")
    dependency_depth: Mapped[int] = mapped_column(Integer, default=1)
    evidence_type: Mapped[str] = mapped_column(String(64), default="SQL_DEPENDENCY")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class MigrationMedallionNode(Base, ProjectScoped):
    __tablename__ = "migration_medallion_node"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_object_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    semantic_definition_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    environment: Mapped[str] = mapped_column(String(16), index=True)
    layer: Mapped[str] = mapped_column(String(16), index=True)  # SOURCE/BRONZE/SILVER/GOLD
    node_type: Mapped[str] = mapped_column(String(64), index=True)  # DATA/VIEW/ROUTINE/FUNCTION/SEMANTIC_MODEL
    model_role: Mapped[str] = mapped_column(String(32), default="ENTITY")
    target_name: Mapped[str] = mapped_column(String(255))
    target_fqn: Mapped[str] = mapped_column(String(1024))
    generation_strategy: Mapped[str] = mapped_column(String(64))
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(32), default="PLANNED")
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    lineage_json: Mapped[str] = mapped_column(Text, default="{}")
    transformation_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("project_id","environment","target_fqn", name="uq_medallion_target"),)

class MigrationMedallionEdge(Base, ProjectScoped):
    __tablename__ = "migration_medallion_edge"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    environment: Mapped[str] = mapped_column(String(16), index=True)
    from_node_id: Mapped[str] = mapped_column(String(64), index=True)
    to_node_id: Mapped[str] = mapped_column(String(64), index=True)
    edge_type: Mapped[str] = mapped_column(String(64), default="LINEAGE")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("project_id","environment","from_node_id","to_node_id","edge_type", name="uq_medallion_edge"),)

class MigrationStageArtifact(Base, ProjectScoped):
    __tablename__ = "migration_stage_artifact"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    node_id: Mapped[str] = mapped_column(String(64), index=True)
    artifact_type: Mapped[str] = mapped_column(String(64))
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("project_id","node_id", name="uq_stage_artifact_node"),)

class MigrationStageArtifactVersion(Base, ProjectScoped):
    __tablename__ = "migration_stage_artifact_version"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    node_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    executable: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_status: Mapped[str] = mapped_column(String(32), default="NOT_RUN")
    validation_json: Mapped[str] = mapped_column(Text, default="{}")
    review_status: Mapped[str] = mapped_column(String(32), default="PENDING_REVIEW")
    reviewer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    generator_version: Mapped[str] = mapped_column(String(64), default="medallion-2.3.0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("artifact_id","version", name="uq_stage_artifact_version"),)
