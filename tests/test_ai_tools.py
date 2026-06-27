"""Tests for cloud_connectors.ai_tools module."""

from __future__ import annotations

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString
from pydantic import BaseModel, Field


class TestGetPydanticSchema:
    """Tests for get_pydantic_schema function."""

    def test_basic_schema_generation(self):
        """Test that a simple Pydantic model is converted correctly."""
        from cloud_connectors.ai_tools import get_pydantic_schema

        class MyTool(BaseModel):
            """A test tool."""

            name: str = Field(..., description="The name of the item.")
            value: int = Field(..., description="The value of the item.")

        schema = get_pydantic_schema(MyTool)

        assert isinstance(schema, ExtendedDict)
        assert isinstance(schema["properties"], ExtendedDict)
        assert isinstance(schema["required"], ExtendedList)
        assert isinstance(schema["type"], ExtendedString)
        assert schema == {
            "type": "object",
            "properties": {
                "name": {"description": "The name of the item.", "title": "Name", "type": "string"},
                "value": {"description": "The value of the item.", "title": "Value", "type": "integer"},
            },
            "required": ["name", "value"],
        }

    def test_schema_with_optional_fields(self):
        """Test that optional fields are handled correctly."""
        from cloud_connectors.ai_tools import get_pydantic_schema

        class MyTool(BaseModel):
            """A test tool with optional fields."""

            required_field: str
            optional_field: int | None = None

        schema = get_pydantic_schema(MyTool)

        assert isinstance(schema, ExtendedDict)
        assert schema == {
            "type": "object",
            "properties": {
                "required_field": {"title": "Required Field", "type": "string"},
                "optional_field": {
                    "anyOf": [{"type": "integer"}, {"type": "null"}],
                    "default": None,
                    "title": "Optional Field",
                },
            },
            "required": ["required_field"],
        }

    def test_schema_with_nested_anyof(self):
        """Test that nested anyOf schemas are handled correctly."""
        from cloud_connectors.ai_tools import get_pydantic_schema

        class NestedModel(BaseModel):
            """A nested model."""

            nested_field: str = Field(..., description="A nested field.")

        class MyTool(BaseModel):
            """A test tool with a nested anyOf."""

            field: NestedModel | None = None

        schema = get_pydantic_schema(MyTool)

        assert isinstance(schema, ExtendedDict)
        assert schema == {
            "type": "object",
            "properties": {
                "field": {
                    "anyOf": [
                        {"$ref": "#/$defs/NestedModel"},
                        {"type": "null"},
                    ],
                    "default": None,
                }
            },
            "$defs": {
                "NestedModel": {
                    "description": "A nested model.",
                    "title": "NestedModel",
                    "type": "object",
                    "properties": {
                        "nested_field": {
                            "description": "A nested field.",
                            "title": "Nested Field",
                            "type": "string",
                        }
                    },
                    "required": ["nested_field"],
                }
            },
        }
