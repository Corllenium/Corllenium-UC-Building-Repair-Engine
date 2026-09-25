import os
import psycopg
import pytest
from api.tests.db_helper import (
    ADMIN_URL,
    generate_test_db_name,
    create_test_db,
    drop_test_db,
    migrate_test_db,
)


def test_unique_test_database_names():
    name1 = generate_test_db_name()
    name2 = generate_test_db_name()
    assert name1 != name2
    assert str(os.getpid()) in name1
    assert str(os.getpid()) in name2
    assert name1.startswith("fixer_test_")


def test_concurrent_databases_lifecycle():
    # Two test sessions creating databases concurrently
    db1_name, db1_url = create_test_db()
    db2_name, db2_url = create_test_db()

    try:
        assert db1_name != db2_name

        # Verify both databases exist simultaneously in postgres
        with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT datname FROM pg_database WHERE datname IN (%s, %s)", (db1_name, db2_name))
            found = {row[0] for row in cur.fetchall()}
            assert found == {db1_name, db2_name}

        # Verify migrations can run on both independently
        migrate_test_db(db1_url)
        migrate_test_db(db2_url)

        # Verify both have tables migrated
        with psycopg.connect(db1_url.replace("+psycopg", "")) as conn:
            cur = conn.cursor()
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            tables1 = {row[0] for row in cur.fetchall()}
            assert "models" in tables1
            assert "model_versions" in tables1

        with psycopg.connect(db2_url.replace("+psycopg", "")) as conn:
            cur = conn.cursor()
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            tables2 = {row[0] for row in cur.fetchall()}
            assert "models" in tables2
            assert "model_versions" in tables2

    finally:
        drop_test_db(db1_name)
        drop_test_db(db2_name)

    # Verify both dropped cleanly
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        cur = conn.cursor()
        cur.execute("SELECT datname FROM pg_database WHERE datname IN (%s, %s)", (db1_name, db2_name))
        assert cur.fetchall() == []
