"""Shared base for every REQUEST-body schema (see CONTRACTS.md §1a — response bodies are
plain dicts, not Pydantic models). `CamelModel` lets each schema declare normal Python
snake_case field names while accepting the camelCase JSON the React client actually sends.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PaginationParams(BaseModel):
    page: int = 1
    page_size: int = 20
    search: str | None = None
