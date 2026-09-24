"""Project-scoped canonical control-plane tables not requiring specialized columns yet."""
from datetime import datetime
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

SPECIALIZED={
 'migration_project','migration_source','migration_object','migration_column','migration_dependency',
 'migration_mapping','migration_classification','migration_artifact','migration_artifact_version',
 'migration_review','migration_issue','migration_run','migration_quality_gate','migration_schema_drift'
}
REQUIRED=[
'migration_connection','migration_constraint','migration_index','migration_parameter','migration_variable',
'migration_rule','migration_assessment','migration_conversion_plan','migration_run_step','migration_validation',
'migration_reconciliation','migration_reconciliation_detail','migration_deployment','migration_environment',
'migration_wave','migration_cutover','migration_decommission','migration_audit','migration_prompt','migration_ai_run',
'migration_test_case','migration_test_run'
]

def _make(tablename:str):
    class_name=''.join(x.title() for x in tablename.split('_'))
    annotations={
        'id': Mapped[str], 'project_id': Mapped[str], 'object_id': Mapped[str|None],
        'environment': Mapped[str|None], 'status': Mapped[str|None],
        'payload_json': Mapped[str], 'created_at': Mapped[datetime]
    }
    attrs={
        '__tablename__':tablename,'__annotations__':annotations,'__module__':__name__,
        'id':mapped_column(String(64),primary_key=True),
        'project_id':mapped_column(String(64),index=True),
        'object_id':mapped_column(String(64),nullable=True,index=True),
        'environment':mapped_column(String(16),nullable=True,index=True),
        'status':mapped_column(String(32),nullable=True,index=True),
        'payload_json':mapped_column(Text,default='{}'),
        'created_at':mapped_column(DateTime,default=datetime.utcnow),
    }
    return type(class_name,(Base,),attrs)

for _t in REQUIRED:
    globals()[''.join(x.title() for x in _t.split('_'))]=_make(_t)
