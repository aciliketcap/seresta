"""Persistence: the shared ORM, the shared repositories and the engine bootstrap.

Not imported by `serespar/__init__.py`: the driver packages are an optional
extra (`serespar[postgres]`), so a parser that stores its results some other
way -- or a test suite that stores nothing -- does not need SQLAlchemy
installed. Import what you need explicitly::

    from serespar.db.orm import Base, AbstractParsedEntityORM
    from serespar.db.repos import SqlAlchemyEntityRepository
    from serespar.db.postgres import build_engine_from_env
"""
