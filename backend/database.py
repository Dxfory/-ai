"""数据库连接管理 (SQLite 开发模式)"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "meiyu.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_dev_columns()


def _ensure_sqlite_dev_columns():
    """开发期 SQLite 轻量迁移；正式环境后续改 Alembic。"""
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(line_drafts)")).fetchall()
        columns = {row[1] for row in rows}
        if rows and "provider" not in columns:
            conn.execute(text("ALTER TABLE line_drafts ADD COLUMN provider VARCHAR DEFAULT 'local_edge_preview'"))
