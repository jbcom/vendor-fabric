"""Targeted tests for the connector data-surface introspection helpers."""

from __future__ import annotations

from extended_data.containers import ExtendedData, ExtendedDict, ExtendedList, ExtendedString

from vendor_fabric.base import ConnectorBase
from vendor_fabric.surface import (
    EXTENDED_PAYLOAD_TYPES,
    annotation_includes_extended_payload,
    connector_data_methods,
    is_connector_data_method,
    return_annotation,
)


# --- return_annotation ----------------------------------------------------


class TestReturnAnnotation:
    def test_resolves_typed_return(self):
        def f(x: int) -> str:
            return str(x)

        assert return_annotation(f) is str

    def test_returns_none_when_no_annotation(self):
        def f(x):
            return x

        assert return_annotation(f) is None

    def test_falls_back_to_raw_annotations_on_get_type_hints_failure(self):
        class Unresolvable:
            __annotations__ = {"return": "SomeForwardRef"}

        instance = Unresolvable()
        # get_type_hints fails on unresolved forward refs; the helper
        # should fall back to the raw __annotations__ dict.
        result = return_annotation(instance.__class__)
        assert result == "SomeForwardRef"


# --- annotation_includes_extended_payload --------------------------------


class TestAnnotationIncludesExtendedPayload:
    def test_none_returns_false(self):
        assert annotation_includes_extended_payload(None) is False

    def test_direct_extended_data_type(self):
        assert annotation_includes_extended_payload(ExtendedData) is True

    def test_direct_extended_dict_type(self):
        assert annotation_includes_extended_payload(ExtendedDict) is True

    def test_direct_extended_list_type(self):
        assert annotation_includes_extended_payload(ExtendedList) is True

    def test_string_annotation_containing_extended_name(self):
        assert annotation_includes_extended_payload("ExtendedDict") is True
        assert annotation_includes_extended_payload("ExtendedList[str]") is True

    def test_string_annotation_without_extended_name(self):
        assert annotation_includes_extended_payload("dict[str, str]") is False
        assert annotation_includes_extended_payload("str") is False

    def test_union_with_extended_payload(self):
        annotation = ExtendedDict | None
        assert annotation_includes_extended_payload(annotation) is True

    def test_optional_extended_payload(self):
        annotation = ExtendedString | None
        assert annotation_includes_extended_payload(annotation) is True

    def test_nested_generic_with_extended_payload(self):
        annotation = dict[str, ExtendedList]
        assert annotation_includes_extended_payload(annotation) is True

    def test_non_extended_annotation_returns_false(self):
        assert annotation_includes_extended_payload(str) is False
        assert annotation_includes_extended_payload(int) is False
        assert annotation_includes_extended_payload(list) is False


# --- is_connector_data_method --------------------------------------------


class TestIsConnectorDataMethod:
    def test_non_callable_returns_false(self):
        assert is_connector_data_method("not a method") is False
        assert is_connector_data_method(42) is False

    def test_class_itself_returns_false(self):
        assert is_connector_data_method(ConnectorBase) is False

    def test_connector_base_method_returns_false(self):
        assert is_connector_data_method(ConnectorBase.extend_result) is False

    def test_extended_return_method_returns_true(self):
        class Fake(ConnectorBase):
            def get_thing(self) -> ExtendedDict:
                return ExtendedDict({})

        assert is_connector_data_method(Fake.get_thing) is True

    def test_non_extended_return_method_returns_false(self):
        class Fake(ConnectorBase):
            def get_thing(self) -> str:
                return "x"

        assert is_connector_data_method(Fake.get_thing) is False

    def test_unannotated_method_returns_false(self):
        class Fake(ConnectorBase):
            def get_thing(self):
                return {}

        assert is_connector_data_method(Fake.get_thing) is False


# --- connector_data_methods ----------------------------------------------


class TestConnectorDataMethods:
    def test_returns_extended_return_methods(self):
        class Fake(ConnectorBase):
            def get_dict(self) -> ExtendedDict:
                return ExtendedDict({})

            def get_list(self) -> ExtendedList:
                return ExtendedList([])

            def get_str(self) -> str:
                return "x"

            def _private(self) -> ExtendedDict:
                return ExtendedDict({})

        methods = connector_data_methods(Fake)
        names = [name for name, _ in methods]
        assert "get_dict" in names
        assert "get_list" in names
        assert "get_str" not in names
        assert "_private" not in names

    def test_each_entry_is_callable(self):
        class Fake(ConnectorBase):
            def get_dict(self) -> ExtendedDict:
                return ExtendedDict({})

        methods = connector_data_methods(Fake)
        for _, method in methods:
            assert callable(method)

    def test_empty_when_no_extended_methods(self):
        class Fake(ConnectorBase):
            def get_str(self) -> str:
                return "x"

        assert connector_data_methods(Fake) == []


# --- EXTENDED_PAYLOAD_TYPES constant -------------------------------------


class TestExtendedPayloadTypes:
    def test_includes_all_six_extended_types(self):
        assert ExtendedData in EXTENDED_PAYLOAD_TYPES
        assert ExtendedDict in EXTENDED_PAYLOAD_TYPES
        assert ExtendedList in EXTENDED_PAYLOAD_TYPES
        assert ExtendedString in EXTENDED_PAYLOAD_TYPES
