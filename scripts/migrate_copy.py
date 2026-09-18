#!/usr/bin/env python3
"""Validate a SQLite upgrade on a new copy; never opens the source writable."""
import argparse
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    source=args.source.resolve();target=args.destination.resolve()
    if not source.is_file() or target.exists():
        parser.error('source must exist and destination must be a new file')
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as old, sqlite3.connect(target) as new:
        old.backup(new)
    with tempfile.TemporaryDirectory(prefix='auralis-migrate-') as config:
        os.environ['AURALIS_CONFIG_DIR']=config
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'SonicVale'))
        from sqlalchemy import create_engine,text
        from app.db.database import Base
        from app.models import po
        from app.db.migrations import apply_schema_migrations,CURRENT_SCHEMA_VERSION
        engine=create_engine(f'sqlite:///{target}')
        Base.metadata.create_all(engine)
        apply_schema_migrations(engine)
        with engine.connect() as conn:
            integrity=conn.execute(text('PRAGMA integrity_check')).scalar_one()
            foreign_keys=conn.execute(text('PRAGMA foreign_key_check')).all()
        engine.dispose()
        if integrity!='ok' or foreign_keys:raise RuntimeError(f'integrity={integrity}, foreign_key_errors={len(foreign_keys)}')
        print(f'Validated copy at schema {CURRENT_SCHEMA_VERSION}; source unchanged: {target}')

if __name__=='__main__':main()
