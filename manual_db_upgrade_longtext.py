from extensions import db
from app import app
from sqlalchemy import text

"""
Upgrade MySQL text columns that may overflow with AI-generated content to LONGTEXT and ensure utf8mb4 charset.
Safe to run multiple times. No-op on non-MySQL engines.

Usage on PythonAnywhere:
  1) Set FLASK_ENV=production (or set DATABASE_URL to your MySQL DSN)
  2) Run: python manual_db_upgrade_longtext.py
  3) Reload web app
"""

ALTERS = [
    # Course modules: large HTML and JSON
    "ALTER TABLE `course_module` MODIFY `content_html` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL",
    "ALTER TABLE `course_module` MODIFY `extras_json` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL",

    # Saved tasks can be big
    "ALTER TABLE `saved_task` MODIFY `tasksheet` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL",
    "ALTER TABLE `saved_task` MODIFY `solutionsheet` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL",

    # Course assets
    "ALTER TABLE `course_asset` MODIFY `content_text` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL",

    # Chat session RAG context may grow
    "ALTER TABLE `chat_session` MODIFY `rag_context` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL",
]

def upgrade():
    with app.app_context():
        engine = db.engine
        if engine.dialect.name != 'mysql':
            print(f"Skipping: engine is {engine.dialect.name}, not mysql.")
            return
        url = str(engine.url).replace(engine.url.password or '', '***') if getattr(engine, 'url', None) else '(unknown)'
        print(f"Connected to MySQL: {url}")

        with engine.begin() as conn:
            for sql in ALTERS:
                try:
                    print(f"Applying: {sql}")
                    conn.execute(text(sql))
                except Exception as e:
                    # Most likely: already LONGTEXT, or column not present (older schema), or charset already set.
                    print(f"  -> Skipped: {e}")

        print("Upgrade to LONGTEXT complete.")

if __name__ == '__main__':
    upgrade()