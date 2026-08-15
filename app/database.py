from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    # pool_pre_ping: validates a pooled connection with a cheap SELECT 1
    # before handing it to a request, transparently reconnecting if it's
    # dead - without this, a connection dropped server-side (a free-tier
    # Postgres restart, an idle timeout) leaves every subsequent request
    # trying to use a stale connection until the process itself restarts.
    # pool_recycle: proactively recycles connections older than this many
    # seconds, since managed Postgres tiers often close connections that
    # have been idle/open longer than some server-side limit.
    pool_pre_ping=True,
    pool_recycle=280,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
