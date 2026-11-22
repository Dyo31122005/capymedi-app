#!/usr/bin/env python3
"""Service `migrate` (Docker Compose): tao database ung dung NEU CHUA CO.

Volume Postgres da co san thi script init cua image khong chay lai, nen DB moi
(vd `capytest` cho demo) phai tao tay. KHONG xoa/ghi de gi; DB da co -> bo qua.
Khong in mat khau.
"""

import os
import sys
from urllib.parse import unquote, urlsplit

import psycopg2

url = urlsplit(os.environ["DATABASE_URL"])
ten_db = url.path.lstrip("/")
if not ten_db.replace("_", "").isalnum():
    sys.exit(f"Ten database khong hop le: {ten_db!r}")
conn = psycopg2.connect(host=url.hostname, port=url.port or 5432, user=unquote(url.username or ""),
                        password=unquote(url.password or ""), dbname="postgres")
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("select 1 from pg_database where datname = %s", (ten_db,))
    if cur.fetchone():
        print(f"[migrate] database '{ten_db}' da ton tai - giu nguyen.")
    else:
        cur.execute(f'create database "{ten_db}"')
        print(f"[migrate] da tao database '{ten_db}'.")
conn.close()
