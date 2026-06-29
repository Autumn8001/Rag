from pathlib import Path
import logging
import hashlib
import shutil
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

from core.config import settings
from core.models import APIKeyMap, Base, ChatHistory, DocumentRecord, User
from core.rag_engine import clear_all_data


logger = logging.getLogger(__name__)

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    sqlite_path = SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "", 1)
    if sqlite_path.startswith("./") or sqlite_path.startswith(".\\"):
        Path(sqlite_path).resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    logger.info("Initializing relational database schema")
    Base.metadata.create_all(bind=engine)
    upgrade_schema()
    seed_demo_data()


def upgrade_schema() -> None:
    """Backfill columns for deployments that predate the temp visitor schema."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    statements: list[str] = []
    dialect = engine.dialect.name

    if "is_temporary" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN is_temporary BOOLEAN NOT NULL DEFAULT FALSE")
    if "expires_at" not in existing_columns:
        if dialect == "postgresql":
            statements.append("ALTER TABLE users ADD COLUMN expires_at TIMESTAMP")
        else:
            statements.append("ALTER TABLE users ADD COLUMN expires_at DATETIME")
    if "last_active_at" not in existing_columns:
        if dialect == "postgresql":
            statements.append("ALTER TABLE users ADD COLUMN last_active_at TIMESTAMP")
        else:
            statements.append("ALTER TABLE users ADD COLUMN last_active_at DATETIME")

    if not statements:
        return

    logger.info("Upgrading users schema with %s missing column(s)", len(statements))
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def seed_demo_data() -> None:
    from core.auth import get_password_hash
    from core.crud import create_document_record
    from core.rag_engine import ingest_knowledge

    db = SessionLocal()
    try:
        if db.query(APIKeyMap).count() == 0:
            db.bulk_save_objects(
                [
                    APIKeyMap(
                        api_key="key_company_a",
                        tenant_id="tenant_company_A",
                        user_id="user_A",
                    ),
                    APIKeyMap(
                        api_key="key_company_b",
                        tenant_id="tenant_company_B",
                        user_id="user_B",
                    ),
                    APIKeyMap(
                        api_key="key_default",
                        tenant_id="default_tenant",
                        user_id="default_user",
                    ),
                ]
            )
            db.commit()

        if not settings.SEED_STATIC_VISITOR_DEMO:
            return

        visitor = db.query(User).filter(User.username == "visitor").first()
        if visitor is None:
            visitor = User(
                username="visitor",
                hashed_password=get_password_hash("visitor123"),
                tenant_id="tenant_visitor",
                is_temporary=False,
            )
            db.add(visitor)
            db.commit()

        doc_exists = (
            db.query(DocumentRecord)
            .filter(DocumentRecord.tenant_id == "tenant_visitor")
            .count()
            > 0
        )
        if not doc_exists:
            demo_doc_content = """# Employee Handbook

## Working Hours
Standard working hours are Monday to Friday, 09:30-18:30.

## Security Policy
Sensitive internal data must not be uploaded to uncontrolled external AI tools.
All access to enterprise data should respect tenant isolation and authorization boundaries.
"""
            filename = "employee_handbook.md"
            if ingest_knowledge(demo_doc_content, filename, "tenant_visitor"):
                create_document_record(
                    db=db,
                    filename=filename,
                    file_hash=hashlib.md5(demo_doc_content.encode("utf-8")).hexdigest(),
                    tenant_id="tenant_visitor",
                    user_id="visitor",
                )
    except Exception:
        db.rollback()
        logger.exception("Failed to seed demo data")
    finally:
        db.close()


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _cleanup_tenant_upload_dir(tenant_id: str) -> None:
    upload_dir = Path("data") / "uploads" / tenant_id
    if upload_dir.exists():
        shutil.rmtree(upload_dir)


def cleanup_expired_temporary_visitors() -> int:
    """Delete expired visitor tenants and their tenant-scoped data."""
    db = SessionLocal()
    cleaned_count = 0
    try:
        expired_users = (
            db.query(User)
            .filter(
                User.is_temporary.is_(True),
                User.expires_at.isnot(None),
                User.expires_at <= _utc_now_naive(),
            )
            .all()
        )

        for user in expired_users:
            try:
                tenant_id = user.tenant_id
                db.query(DocumentRecord).filter(DocumentRecord.tenant_id == tenant_id).delete()
                db.query(ChatHistory).filter(ChatHistory.tenant_id == tenant_id).delete()
                clear_all_data(tenant_id)
                _cleanup_tenant_upload_dir(tenant_id)
                db.delete(user)
                db.commit()
                cleaned_count += 1
                logger.info("Cleaned expired temporary visitor tenant %s", tenant_id)
            except Exception:
                db.rollback()
                logger.exception(
                    "Failed to clean expired temporary visitor tenant %s",
                    getattr(user, "tenant_id", "<unknown>"),
                )
        return cleaned_count
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
