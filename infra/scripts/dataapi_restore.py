"""Load table CSVs into Aurora through the RDS Data API (spec 002 T012).

Aurora in the app stack has no reachable port (no public access, no VPC route),
so pg_restore cannot connect. Instead: export each table from the home server
to CSV with psql (docs/runbook-aws.md, T012), run the migrate Lambda so the
schema exists, then run this script with credentials that may call rds-data.

    python infra/scripts/dataapi_restore.py --cluster-arn ARN --secret-arn ARN \
        --database storyengine --dir dump/ [--batch 50] [--dry-run]

Each CSV is named <table>.csv, has a header row, and writes NULL as \\N
(psql: WITH (FORMAT csv, HEADER, NULL '\\N')). Every value is sent as a string
and cast to the column's real type in SQL (uuid, timestamptz, vector, jsonb...),
read from the target catalog, so no Data API type hints are needed. Tables load
parents first (foreign keys from pg_constraint), each table in one transaction,
then row counts are compared with the CSV. Exit code 1 on any mismatch.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Iterable

NULL_MARK = "\\N"
SKIP_TABLES = {"alembic_version"}  # owned by the migrate Lambda

COLUMNS_SQL = (
    "SELECT a.attname, format_type(a.atttypid, a.atttypmod) "
    "FROM pg_attribute a JOIN pg_class c ON a.attrelid = c.oid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public' AND c.relname = :t AND a.attnum > 0 "
    "AND NOT a.attisdropped ORDER BY a.attnum"
)
FK_SQL = (
    "SELECT ch.relname, pa.relname FROM pg_constraint k "
    "JOIN pg_class ch ON k.conrelid = ch.oid JOIN pg_class pa ON k.confrelid = pa.oid "
    "WHERE k.contype = 'f' AND ch.relname <> pa.relname"
)


class DataApi:
    """Thin wrapper over the boto3 rds-data client."""

    def __init__(self, client: Any, cluster_arn: str, secret_arn: str, database: str):
        self.c = client
        self.base = {"resourceArn": cluster_arn, "secretArn": secret_arn, "database": database}

    def query(self, sql: str, params: list[dict] | None = None, tx: str | None = None) -> list[list[Any]]:
        kw: dict[str, Any] = {**self.base, "sql": sql}
        if params:
            kw["parameters"] = params
        if tx:
            kw["transactionId"] = tx
        out = self.c.execute_statement(**kw)
        return [[next(iter(f.values())) for f in rec] for rec in out.get("records", [])]

    def begin(self) -> str:
        return self.c.begin_transaction(**self.base)["transactionId"]

    def commit(self, tx: str) -> None:
        self.c.commit_transaction(resourceArn=self.base["resourceArn"],
                                  secretArn=self.base["secretArn"], transactionId=tx)

    def rollback(self, tx: str) -> None:
        self.c.rollback_transaction(resourceArn=self.base["resourceArn"],
                                    secretArn=self.base["secretArn"], transactionId=tx)

    def batch(self, sql: str, sets: list[list[dict]], tx: str) -> None:
        self.c.batch_execute_statement(**self.base, sql=sql, parameterSets=sets, transactionId=tx)


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def load_order(tables: Iterable[str], edges: list[list[str]]) -> list[str]:
    """Parents before children (Kahn); ties and cycles fall back to name order."""
    tables = sorted(set(tables))
    deps = {t: {p for c, p in edges if c == t and p in tables} for t in tables}
    order: list[str] = []
    while deps:
        ready = sorted(t for t, d in deps.items() if not d) or [sorted(deps)[0]]
        for t in ready:
            order.append(t)
            deps.pop(t)
        for d in deps.values():
            d.difference_update(ready)
    return order


def insert_sql(table: str, cols: list[str], types: dict[str, str]) -> str:
    names = ", ".join(quote_ident(c) for c in cols)
    vals = ", ".join(f"CAST(:p{i} AS {types[c]})" for i, c in enumerate(cols))
    return f"INSERT INTO {quote_ident(table)} ({names}) VALUES ({vals})"


def to_params(row: list[str]) -> list[dict]:
    return [
        {"name": f"p{i}", "value": {"isNull": True} if v == NULL_MARK else {"stringValue": v}}
        for i, v in enumerate(row)
    ]


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise ValueError(f"{path} is empty (no header)")
    return rows[0], rows[1:]


def restore(api: DataApi, folder: Path, batch: int = 50, dry_run: bool = False,
            log=print) -> dict[str, tuple[int, int]]:
    """Load every <table>.csv in folder. Returns {table: (csv_rows, db_rows)}."""
    files = {p.stem: p for p in folder.glob("*.csv") if p.stem not in SKIP_TABLES}
    order = load_order(files, api.query(FK_SQL))
    result: dict[str, tuple[int, int]] = {}
    for table in order:
        header, rows = read_csv(files[table])
        types = dict(api.query(COLUMNS_SQL, [{"name": "t", "value": {"stringValue": table}}]))
        missing = [c for c in header if c not in types]
        if missing:
            raise ValueError(f"{table}: columns not in Aurora: {missing}")
        sql = insert_sql(table, header, types)
        log(f"{table}: {len(rows)} rows")
        if dry_run:
            result[table] = (len(rows), -1)
            continue
        tx = api.begin()
        try:
            for i in range(0, len(rows), batch):
                api.batch(sql, [to_params(r) for r in rows[i:i + batch]], tx)
            api.commit(tx)
        except Exception:
            api.rollback(tx)
            raise
        count = int(api.query(f"SELECT count(*) FROM {quote_ident(table)}")[0][0])
        result[table] = (len(rows), count)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cluster-arn", required=True)
    ap.add_argument("--secret-arn", required=True)
    ap.add_argument("--database", default="storyengine")
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    import boto3  # imported late so the module loads without boto3 for --help

    api = DataApi(boto3.client("rds-data", region_name=a.region),
                  a.cluster_arn, a.secret_arn, a.database)
    res = restore(api, a.dir, a.batch, a.dry_run)
    bad = {t: v for t, v in res.items() if not a.dry_run and v[0] != v[1]}
    for t, (want, got) in res.items():
        print(f"{'OK ' if t not in bad else 'BAD'} {t}: csv={want} aurora={got}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
