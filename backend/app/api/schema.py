"""Schema inspection endpoint."""

from fastapi import APIRouter
from sqlalchemy import inspect

from app.db.session import shop_engine
from app.schemas.query import ColumnInfo, ForeignKeyInfo, SchemaResponse, TableInfo
from app.services.sql_validator import DEFAULT_ALLOWED_TABLES

router = APIRouter(prefix="/api/schema", tags=["schema"])


@router.get("", response_model=SchemaResponse, summary="Inspect database schema metadata")
async def get_schema() -> SchemaResponse:
    """Inspect public tables in sample_shop and return structured schema metadata.

    Returns column names, types, nullability, defaults, primary keys, and foreign keys
    for all allowed business tables in a clean format suitable for AI agent consumption.
    """
    async with shop_engine.connect() as conn:

        def _inspect_tables(sync_conn) -> list[TableInfo]:
            inspector = inspect(sync_conn)
            table_names = inspector.get_table_names(schema="public")
            tables_metadata: list[TableInfo] = []

            for t_name in sorted(table_names):
                if t_name.lower() not in DEFAULT_ALLOWED_TABLES:
                    continue

                raw_columns = inspector.get_columns(t_name, schema="public")
                pk_data = inspector.get_pk_constraint(t_name, schema="public")
                fk_data = inspector.get_foreign_keys(t_name, schema="public")

                columns = [
                    ColumnInfo(
                        name=col["name"],
                        type=str(col["type"]),
                        nullable=col["nullable"],
                        default=str(col["default"]) if col.get("default") is not None else None,
                    )
                    for col in raw_columns
                ]

                primary_key = pk_data.get("constrained_columns", []) if pk_data else []

                foreign_keys = [
                    ForeignKeyInfo(
                        constrained_columns=fk.get("constrained_columns", []),
                        referred_table=fk.get("referred_table", ""),
                        referred_columns=fk.get("referred_columns", []),
                    )
                    for fk in (fk_data or [])
                ]

                tables_metadata.append(
                    TableInfo(
                        name=t_name,
                        columns=columns,
                        primary_key=primary_key,
                        foreign_keys=foreign_keys,
                    )
                )

            return tables_metadata

        tables = await conn.run_sync(_inspect_tables)
        return SchemaResponse(tables=tables)
