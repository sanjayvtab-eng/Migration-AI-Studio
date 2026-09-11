"""Separate tables keep existing source profiles and databases compatible."""
from datetime import datetime
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SourceConnector(Base):
    __tablename__ = "source_connector"
    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    enabled: Mapped[str] = mapped_column(String(16), default="ENABLED")
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    instance_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ConnectorTask(Base):
    __tablename__ = "connector_task"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    operation: Mapped[str] = mapped_column(String(32))
    payload: Mapped[str] = mapped_column(Text, default="{}")
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", index=True)
    lease: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
