"""Local SQLite history; no task data leaves this machine."""

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Column, Integer, String, Text, create_engine, select
from sqlalchemy.orm import Session, declarative_base

Base = declarative_base()


class Drawing(Base):
    __tablename__ = "drawings"
    id = Column(Integer, primary_key=True)
    created_at = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    result = Column(Text, nullable=False)


class History:
    def __init__(self, url=None):
        if url is None:
            folder = Path(__file__).resolve().parents[1] / "data"
            folder.mkdir(exist_ok=True)
            url = f"sqlite:///{(folder / 'history.sqlite3').as_posix()}"
        self.engine = create_engine(url)
        Base.metadata.create_all(self.engine)

    def save(self, text, result):
        with Session(self.engine) as session:
            row = Drawing(
                created_at=datetime.now(timezone.utc).isoformat(),
                text=text,
                result=json.dumps(result, ensure_ascii=False),
            )
            session.add(row)
            session.commit()
            return row.id

    def list(self, limit=30):
        with Session(self.engine) as session:
            rows = session.scalars(select(Drawing).order_by(Drawing.id.desc()).limit(limit))
            return [{"id": r.id, "created_at": r.created_at, "text": r.text} for r in rows]

    def get(self, item_id):
        with Session(self.engine) as session:
            row = session.get(Drawing, item_id)
            return (
                None
                if row is None
                else {"id": row.id, "text": row.text, "result": json.loads(row.result)}
            )
