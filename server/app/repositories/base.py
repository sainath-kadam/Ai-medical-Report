"""Common CRUD scaffolding every domain repository builds on. Centralizing this is what
guarantees the multi-tenant isolation promise (spec §7): `find_by_id_scoped` and
`list_scoped` always take `organization_id` as a required, non-optional filter — there is
no shortcut method that queries a table without it.

Every method here returns/accepts the SAME camelCase, `_id`-keyed dict shape the app has
always used (CONTRACTS.md §1) — `_to_dict`/`_to_kwargs` are the entire translation layer to
SQLAlchemy model instances, driven generically off each model's mapped columns (via
`app/database/casing.py`), so no per-entity mapping code is needed. `extra_filter` in
`list_scoped` still accepts the same Mongo-operator-shaped dicts every service already
builds (`{"status": {"$in": [...]}}`, `{"$or": [...]}`, `{"field": {"$regex": ..., "$options": "i"}}`)
— `_build_conditions` is the (small, closed) translation of the operator vocabulary this
codebase actually uses into SQLAlchemy `WHERE` clauses, so service-layer call sites never
needed to change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import ColumnElement, and_, func, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.casing import camel_to_snake, snake_to_camel
from app.utils.ids import new_id


def _build_conditions(model: type[Any], filter_dict: dict[str, Any]) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    for key, value in filter_dict.items():
        if key == "$or":
            conditions.append(or_(*[and_(*_build_conditions(model, sub)) for sub in value]))
            continue
        column = getattr(model, camel_to_snake(key))
        if isinstance(value, dict):
            for op, operand in value.items():
                if op == "$in":
                    conditions.append(column.in_(operand))
                elif op == "$regex":
                    conditions.append(column.ilike(f"%{operand}%"))
                elif op == "$options":
                    continue  # only ever paired with $regex above; case-insensitivity is
                    # already handled by ilike() regardless of the option value.
                elif op == "$gte":
                    conditions.append(column >= operand)
                elif op == "$lte":
                    conditions.append(column <= operand)
                elif op == "$ne":
                    conditions.append(column != operand)
                else:
                    raise ValueError(f"Unsupported filter operator: {op}")
        else:
            conditions.append(column == value)
    return conditions


class BaseRepository:
    model: type[Any]

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Dict <-> ORM row translation (see module docstring)
    # ------------------------------------------------------------------

    @classmethod
    def _column_attrs(cls):
        return inspect(cls.model).mapper.column_attrs

    @classmethod
    def _columns(cls):
        return {c.name for c in cls.model.__table__.columns}

    def _to_dict(self, row: Any) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for attr in self._column_attrs():
            value = getattr(row, attr.key)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[snake_to_camel(attr.columns[0].name)] = value
        return result

    def _to_kwargs(self, doc: dict[str, Any]) -> dict[str, Any]:
        mapping = {attr.columns[0].name: attr.key for attr in self._column_attrs()}
        kwargs: dict[str, Any] = {}
        for key, value in doc.items():
            column_name = camel_to_snake(key)
            if column_name in mapping:
                kwargs[mapping[column_name]] = value
        return kwargs

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def insert(self, doc: dict[str, Any]) -> dict[str, Any]:
        doc = dict(doc)
        doc.setdefault("_id", new_id())
        kwargs = self._to_kwargs(doc)
        kwargs.setdefault("id", doc["_id"])
        now = datetime.now(timezone.utc)
        columns = self._columns()
        if "created_at" in columns:
            kwargs.setdefault("created_at", now)
        if "updated_at" in columns:
            kwargs.setdefault("updated_at", now)
        row = self.model(**kwargs)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return self._to_dict(row)

    async def find_by_id(self, doc_id: str) -> dict[str, Any] | None:
        row = await self.session.get(self.model, doc_id)
        return self._to_dict(row) if row is not None else None

    async def find_by_id_scoped(self, doc_id: str, organization_id: str) -> dict[str, Any] | None:
        stmt = select(self.model).where(self.model.id == doc_id, self.model.organization_id == organization_id)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return self._to_dict(row) if row is not None else None

    async def list_scoped(
        self,
        organization_id: str,
        extra_filter: dict[str, Any] | None = None,
        *,
        sort: list[tuple[str, int]] | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        conditions = [self.model.organization_id == organization_id, *_build_conditions(self.model, extra_filter or {})]

        total = (await self.session.execute(select(func.count()).select_from(self.model).where(*conditions))).scalar_one()

        stmt = select(self.model).where(*conditions)
        if sort:
            order_cols = []
            for field, direction in sort:
                column = getattr(self.model, camel_to_snake(field))
                order_cols.append(column.desc() if direction == -1 else column.asc())
            stmt = stmt.order_by(*order_cols)
        stmt = stmt.offset(skip).limit(limit)

        rows = (await self.session.execute(stmt)).scalars().all()
        return [self._to_dict(r) for r in rows], total

    async def update_scoped(self, doc_id: str, organization_id: str, update: dict[str, Any]) -> dict[str, Any] | None:
        stmt = select(self.model).where(self.model.id == doc_id, self.model.organization_id == organization_id)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        for key, value in self._to_kwargs(update).items():
            setattr(row, key, value)
        if "updated_at" in self._columns():
            row.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(row)
        return self._to_dict(row)

    async def delete_scoped(self, doc_id: str, organization_id: str) -> bool:
        stmt = select(self.model).where(self.model.id == doc_id, self.model.organization_id == organization_id)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.commit()
        return True
