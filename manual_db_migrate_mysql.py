"""
Manual schema migration for MySQL: create missing tables and add missing columns/unique constraints, non-destructively.

Usage:
  - Production (MySQL): FLASK_ENV=production python manual_db_migrate_mysql.py
  - Development (SQLite, for testing): python manual_db_migrate_mysql.py

Notes:
  - This script is idempotent and safe to re-run.
  - It will NOT drop or alter existing types; it only creates missing tables, adds missing columns,
    and ensures named unique constraints exist by creating unique indexes.
  - For new columns with nullable=False but no safe server default, it will add them as NULL to avoid migration failure.
"""

from typing import Tuple, List, Set
from extensions import db
from app import app  # ensures models are imported and metadata is populated
from sqlalchemy import inspect, text, Boolean, Integer, Float, String, DateTime, Text as SAText
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.sql.schema import Table, Column
import sys
import traceback


def _q(name: str) -> str:
    """Backtick-quote an identifier for MySQL."""
    if name is None:
        return ""
    n = str(name).replace("`", "``")
    return f"`{n}`"


def _engine_url_safe():
    try:
        url = db.engine.url
        if hasattr(url, "render_as_string"):
            return url.render_as_string(hide_password=True)
        return str(url)
    except Exception:
        return "(unknown URL)"


def _is_text_like(col: Column) -> bool:
    return isinstance(col.type, SAText)


def _is_numeric(col: Column) -> bool:
    return isinstance(col.type, (Integer, Float))


def _is_string(col: Column) -> bool:
    return isinstance(col.type, String)


def _is_bool(col: Column) -> bool:
    return isinstance(col.type, Boolean)


def _is_datetime(col: Column) -> bool:
    return isinstance(col.type, DateTime)


def _compile_coltype(col: Column) -> str:
    """Compile a column's SQL type for the current engine dialect."""
    return col.type.compile(dialect=db.engine.dialect)


def _default_clause_for_add(col: Column) -> str:
    """
    Build a safe DEFAULT clause for ADD COLUMN when possible.
    Avoid defaults for TEXT/BLOB or callable defaults (e.g., datetime.utcnow).
    """
    try:
        # Server default (rare in this app)
        if getattr(col, "server_default", None):
            # Best-effort render; may already be a SQL expression. Use as-is.
            sd = col.server_default
            try:
                # Some dialects expose .arg or .text for literal; fallback to str
                val = getattr(sd, "arg", None) or getattr(sd, "text", None) or str(sd)
                s = str(val)
                if s:
                    return f" DEFAULT {s}"
            except Exception:
                pass
            return ""

        # Python-side default
        d = getattr(col, "default", None)
        if d is None:
            return ""
        val = getattr(d, "arg", None)
        if callable(val):
            # e.g., datetime.utcnow - cannot set safe DB default
            return ""
        if val is None:
            return ""

        # Skip defaults on TEXT/BLOB (not allowed in MySQL)
        if _is_text_like(col):
            return ""

        if _is_bool(col):
            return f" DEFAULT {1 if bool(val) else 0}"
        if _is_numeric(col):
            try:
                # normalize ints/floats
                return f" DEFAULT {int(val) if isinstance(val, bool) else float(val) if isinstance(val, float) or isinstance(val, int) else 0}"
            except Exception:
                return ""
        if _is_string(col):
            # Quote string, escape single quotes
            sval = str(val).replace("'", "\\'")
            return f" DEFAULT '{sval}'"
        if _is_datetime(col):
            # Skip unless it's a known SQL function; typical here is callable -> already skipped
            return ""

        # Other types: skip by default
        return ""
    except Exception:
        return ""


def _nullability_clause_for_add(col: Column, has_safe_default: bool) -> str:
    """
    Prefer NOT NULL only when model requires it AND we have a safe default.
    Otherwise allow NULL to avoid failing on existing rows.
    """
    try:
        if (col.nullable is False) and has_safe_default:
            return " NOT NULL"
    except Exception:
        pass
    return " NULL"


def _add_column_sql(table_name: str, col: Column) -> str:
    """
    Build an ALTER TABLE ... ADD COLUMN ... statement for MySQL that is relatively safe.
    We avoid adding NOT NULL unless we can also provide a safe DEFAULT clause.
    """
    ctype = _compile_coltype(col)
    dflt_clause = _default_clause_for_add(col)
    notnull_clause = _nullability_clause_for_add(col, bool(dflt_clause))
    return f"ALTER TABLE {_q(table_name)} ADD COLUMN {_q(col.name)} {ctype}{notnull_clause}{dflt_clause}"


def _get_existing_unique_sets(inspector, table_name: str) -> Set[Tuple[str, ...]]:
    """
    Return a set of tuples representing existing unique constraints or unique indexes by column sequence.
    """
    uniq_sets: Set[Tuple[str, ...]] = set()
    try:
        uqs = inspector.get_unique_constraints(table_name) or []
        for u in uqs:
            cols = tuple(u.get("column_names") or [])
            if cols:
                uniq_sets.add(cols)
    except Exception:
        pass
    try:
        idxs = inspector.get_indexes(table_name) or []
        for ix in idxs:
            if ix.get("unique"):
                cols = tuple(ix.get("column_names") or [])
                if cols:
                    uniq_sets.add(cols)
    except Exception:
        pass
    return uniq_sets


def _ensure_unique_constraints(inspector, conn, table: Table):
    """
    Ensure UniqueConstraints declared on the model exist in DB by creating unique indexes if absent.
    Also handle single-column unique=True declarations on Column.
    """
    existing = _get_existing_unique_sets(inspector, table.name)
    # 1) Multi-column uniques declared via UniqueConstraint
    for cons in list(getattr(table, "constraints", []) or []):
        try:
            if not isinstance(cons, UniqueConstraint):
                continue
            cols = [c.name for c in cons.columns]
            col_tuple = tuple(cols)
            if col_tuple in existing:
                continue
            # MySQL allows CREATE UNIQUE INDEX
            name = cons.name or f"uq_{table.name}_{'_'.join(cols)}"
            # Ensure index name within 64 chars
            if len(name) > 60:
                name = name[:60]
            sql = f"CREATE UNIQUE INDEX {_q(name)} ON {_q(table.name)} ({', '.join(_q(c) for c in cols)})"
            try:
                print(f" - Creating unique index {name} on {table.name} ({', '.join(cols)})")
                conn.execute(text(sql))
            except Exception as e:
                print(f"   ! Failed to create unique index {name} on {table.name}: {e}")
        except Exception as e:
            print(f"   ! Error while ensuring unique constraints on {table.name}: {e}")
    # 2) Single-column unique flags on Column(unique=True)
    for col in list(getattr(table, "columns", []) or []):
        try:
            if getattr(col, "unique", False):
                cols = [col.name]
                col_tuple = tuple(cols)
                if col_tuple in existing:
                    continue
                name = f"uq_{table.name}_{col.name}"
                if len(name) > 60:
                    name = name[:60]
                sql = f"CREATE UNIQUE INDEX {_q(name)} ON {_q(table.name)} ({_q(col.name)})"
                try:
                    print(f" - Creating unique index {name} on {table.name} ({col.name})")
                    conn.execute(text(sql))
                except Exception as e:
                    print(f"   ! Failed to create unique index {name} on {table.name}: {e}")
        except Exception as e:
            print(f"   ! Error while ensuring column unique for {table.name}.{getattr(col, 'name', '?')}: {e}")


def _ensure_fk_mysql(conn, table_name: str, column_name: str, ref_table: str, ref_column: str, constraint_name: str, on_delete: str = 'CASCADE'):
    try:
        # Check if constraint exists and its delete rule
        sql = text("""
            SELECT rc.CONSTRAINT_NAME, rc.DELETE_RULE, kcu.COLUMN_NAME, kcu.REFERENCED_TABLE_NAME, kcu.REFERENCED_COLUMN_NAME
            FROM information_schema.REFERENTIAL_CONSTRAINTS rc
            JOIN information_schema.KEY_COLUMN_USAGE kcu
              ON rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
             AND rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
            WHERE rc.CONSTRAINT_SCHEMA = DATABASE()
              AND rc.TABLE_NAME = :table
              AND rc.CONSTRAINT_NAME = :name
        """)
        res = conn.execute(sql, {"table": table_name, "name": constraint_name}).fetchone()
        if res:
            delete_rule = (res.DELETE_RULE or '').upper()
            ref_tab = res.REFERENCED_TABLE_NAME
            ref_col = res.REFERENCED_COLUMN_NAME
            if delete_rule == (on_delete or '').upper() and ref_tab == ref_table and ref_col == ref_column:
                print(f"= FK exists: {constraint_name} ON DELETE {delete_rule}")
                return
            print(f"! FK {constraint_name} exists with DELETE_RULE={delete_rule} -> recommend manual change to ON DELETE {on_delete}.")
            print(f"  SQL:")
            print(f"    ALTER TABLE {_q(table_name)} DROP FOREIGN KEY {_q(constraint_name)};")
            print(f"    ALTER TABLE {_q(table_name)} ADD CONSTRAINT {_q(constraint_name)} FOREIGN KEY ({_q(column_name)}) REFERENCES {_q(ref_table)}({_q(ref_column)}) ON DELETE {on_delete};")
            return
        # Not found: add it
        try:
            add_sql = f"ALTER TABLE {_q(table_name)} ADD CONSTRAINT {_q(constraint_name)} FOREIGN KEY ({_q(column_name)}) REFERENCES {_q(ref_table)}({_q(ref_column)}) ON DELETE {on_delete}"
            print(f"+ Adding FK {constraint_name} on {table_name}.{column_name} -> {ref_table}.{ref_column} ON DELETE {on_delete}")
            conn.execute(text(add_sql))
        except Exception as e:
            print(f"! Failed to add FK {constraint_name} on {table_name}.{column_name}: {e}")
    except Exception as e:
        print(f"! Error inspecting/ensuring FK {constraint_name}: {e}")

def migrate():
    with app.app_context():
        engine = db.engine
        url = _engine_url_safe()
        print(f"Connecting to: {url}")
        insp = inspect(engine)

        meta = db.Model.metadata  # loaded via app import
        tables: List[Table] = list(meta.sorted_tables)

        # Step 1: Create any missing tables
        existing_tables = set(insp.get_table_names())
        for t in tables:
            try:
                if t.name not in existing_tables:
                    print(f"+ Creating missing table: {t.name}")
                    t.create(bind=engine, checkfirst=True)
                else:
                    print(f"= Table exists: {t.name}")
            except Exception as e:
                print(f"! Failed to create table {t.name}: {e}")

        # Step 2: Add missing columns safely
        conn = engine.connect()
        try:
            for t in tables:
                try:
                    db_cols = {c["name"] for c in (insp.get_columns(t.name) or [])}
                except Exception as e:
                    print(f"! Could not introspect columns for {t.name}: {e}")
                    continue

                for col in t.columns:
                    if col.name in db_cols:
                        continue
                    try:
                        sql = _add_column_sql(t.name, col)
                        print(f"+ Adding column: {t.name}.{col.name} --> {sql}")
                        conn.execute(text(sql))
                    except Exception as e:
                        print(f"! Failed to add column {t.name}.{col.name}: {e}")

            # Step 3: Ensure unique constraints via unique indexes
            for t in tables:
                try:
                    _ensure_unique_constraints(insp, conn, t)
                except Exception as e:
                    print(f"! Failed ensuring unique constraints for {t.name}: {e}")

            # Step 4: Ensure critical foreign keys with ON DELETE CASCADE (MySQL only)
            if engine.dialect.name == 'mysql':
                try:
                    _ensure_fk_mysql(conn, 'message', 'session_id', 'chat_session', 'id', 'fk_message_session', on_delete='CASCADE')
                    _ensure_fk_mysql(conn, 'chat_analysis', 'session_id', 'chat_session', 'id', 'fk_chat_analysis_session', on_delete='CASCADE')
                    _ensure_fk_mysql(conn, 'chat_analysis', 'message_id', 'message', 'id', 'fk_chat_analysis_message', on_delete='CASCADE')
                except Exception as e:
                    print(f"! Failed ensuring foreign keys: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass

        print("Migration complete.")


if __name__ == '__main__':
    try:
        migrate()
    except Exception as e:
        print("Fatal error during migration:", e)
        traceback.print_exc()
        sys.exit(1)
