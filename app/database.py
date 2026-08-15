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
    # Route handlers here are sync `def`s, which Starlette runs in a bounded
    # threadpool. If the DB is unreachable and psycopg2's connect() has no
    # timeout, it can hang far longer than any client will wait - each hung
    # request then pins a threadpool worker indefinitely. Enough of those
    # exhausts the pool and starves *every* route, including /health, which
    # needs a free worker too even though it never touches the DB. A short,
    # explicit connect_timeout makes a dead DB fail fast instead of hanging.
    connect_args={"connect_timeout": 5},
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
