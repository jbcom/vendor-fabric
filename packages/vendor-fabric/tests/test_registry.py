"""Targeted tests for the registry dispatch machinery.

These tests cover the adapter classes, spec/info data classes, and
internal helpers that ``test_connectors.py`` and the per-connector
suites only exercise incidentally.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedList

from vendor_fabric.base import ConnectorBase
from vendor_fabric.registry import (
    BUILTIN_CONNECTOR_ADAPTERS,
    BUILTIN_CONNECTORS,
    BuiltinConnectorAdapter,
    BuiltinConnectorSpec,
    ConnectorAdapter,
    ConnectorInfo,
    RegisteredConnectorAdapter,
    _available_connector_info,
    _builtin_connector_info,
    _class_connector_info,
    _discover_connectors,
    _get_capabilities,
    _get_category,
    _get_description,
    _list_connector_classes,
    _missing_builtin_connector_info,
    _missing_builtin_connectors,
    _normalize_catalog_token,
    _normalize_connector_name,
    _raise_missing_builtin_connector,
    _raise_unregistered_builtin_connector,
    clear_cache,
    get_connector_adapter,
    get_connector_class,
    get_connector_info,
    list_available_connectors,
    list_connector_capabilities,
    list_connector_categories,
    list_connector_info,
    list_connectors,
    list_connectors_by_capability,
    list_connectors_by_category,
)


# --- data classes ---------------------------------------------------------


class TestBuiltinConnectorSpec:
    """Tests for the BuiltinConnectorSpec frozen dataclass."""

    def test_defaults(self):
        spec = BuiltinConnectorSpec("m", "C", "extra")
        assert spec.module_path == "m"
        assert spec.class_name == "C"
        assert spec.extra == "extra"
        assert spec.category == "external"
        assert spec.capabilities == ()

    def test_frozen(self):
        spec = BuiltinConnectorSpec("m", "C", "extra")
        with pytest.raises(AttributeError, match="cannot assign"):
            spec.module_path = "other"  # type: ignore[misc]


class TestConnectorInfo:
    """Tests for the ConnectorInfo frozen dataclass + as_dict."""

    def _info(self, **overrides):
        defaults = {
            "name": "aws",
            "available": True,
            "source": "builtin",
            "extra": "aws",
            "category": "cloud",
            "capabilities": ("identity", "secrets"),
            "install": "pip install vendor-fabric[aws]",
            "requirements": ("boto3",),
            "missing": (),
            "class_name": "AWSConnector",
            "module": "vendor_fabric.aws",
            "base_url": None,
            "description": "AWS connector",
            "error": None,
        }
        defaults.update(overrides)
        return ConnectorInfo(**defaults)

    def test_as_dict_shape(self):
        info = self._info()
        data = info.as_dict()
        assert isinstance(data, ExtendedDict)
        assert data["name"] == "aws"
        assert data["available"] is True
        assert data["capabilities"] == ["identity", "secrets"]
        assert data["requirements"] == ["boto3"]
        assert data["class"] == "AWSConnector"
        assert data["module"] == "vendor_fabric.aws"
        assert data["error"] is None

    def test_as_dict_missing_lists_normalize_to_empty(self):
        info = self._info(requirements=(), capabilities=())
        data = info.as_dict()
        assert data["requirements"] == []
        assert data["capabilities"] == []

    def test_frozen(self):
        info = self._info()
        with pytest.raises(AttributeError, match="cannot assign"):
            info.name = "other"  # type: ignore[misc]


# --- adapter contract -----------------------------------------------------


class TestConnectorAdapterABC:
    """ConnectorAdapter is abstract; subclasses must implement the contract."""

    def test_cannot_instantiate_abc_directly(self):
        with pytest.raises(TypeError, match="abstract"):
            ConnectorAdapter()  # type: ignore[abstract]

    def test_subclass_without_methods_is_abstract(self):
        class Bare(ConnectorAdapter):
            name = "bare"

        with pytest.raises(TypeError, match="abstract"):
            Bare()  # type: ignore[abstract]


class TestBuiltinConnectorAdapter:
    """BuiltinConnectorAdapter property surface + unavailable path."""

    def test_extra_property_reads_spec(self):
        adapter = BuiltinConnectorAdapter(name="aws", spec=BUILTIN_CONNECTORS["aws"])
        assert adapter.extra == "aws"

    def test_load_class_missing_dependencies_raises_import_error(self):
        adapter = BuiltinConnectorAdapter(name="aws", spec=BUILTIN_CONNECTORS["aws"])
        with patch("vendor_fabric.registry.get_missing_connector_requirements", return_value=["boto3"]):
            with pytest.raises(ImportError, match="built in but"):
                adapter.load_class()

    def test_load_class_missing_class_raises_runtime_error(self):
        spec = BuiltinConnectorSpec("vendor_fabric.does_not_exist", "MissingClass", "extra")
        adapter = BuiltinConnectorAdapter(name="missing", spec=spec)
        with patch("vendor_fabric.registry.get_missing_connector_requirements", return_value=[]):
            with patch("importlib.import_module", return_value=MagicMock(spec=[])):
                with pytest.raises(RuntimeError, match="does not exist"):
                    adapter.load_class()

    def test_unavailable_error_includes_install_hint(self):
        adapter = BuiltinConnectorAdapter(name="aws", spec=BUILTIN_CONNECTORS["aws"])
        with patch("vendor_fabric.registry.get_missing_connector_requirements", return_value=["boto3"]):
            err = adapter.unavailable_error()
        assert "pip install vendor-fabric[aws]" in str(err)
        assert "boto3" in str(err)

    def test_unavailable_error_redacts_original_error(self):
        adapter = BuiltinConnectorAdapter(name="aws", spec=BUILTIN_CONNECTORS["aws"])
        with patch("vendor_fabric.registry.get_missing_connector_requirements", return_value=[]):
            err = adapter.unavailable_error(ImportError("token=ghp_super_secret_value"))
        assert "ghp_super_secret_value" not in str(err)

    def test_validate_dependencies_raises_when_missing(self):
        adapter = BuiltinConnectorAdapter(name="aws", spec=BUILTIN_CONNECTORS["aws"])
        with patch("vendor_fabric.registry.get_missing_connector_requirements", return_value=["boto3"]):
            with pytest.raises(ImportError):
                adapter.validate_dependencies()

    def test_info_returns_unavailable_when_missing(self):
        adapter = BuiltinConnectorAdapter(name="aws", spec=BUILTIN_CONNECTORS["aws"])
        with patch("vendor_fabric.registry.get_missing_connector_requirements", return_value=["boto3"]):
            info = adapter.info()
        assert info.available is False
        assert info.error is not None
        assert "boto3" in tuple(info.requirements) + tuple(info.missing)

    def test_as_dict_delegates_to_info(self):
        adapter = BuiltinConnectorAdapter(name="aws", spec=BUILTIN_CONNECTORS["aws"])
        sentinel = ConnectorInfo(
            name="aws", available=True, source="builtin", extra="aws",
            category="cloud", capabilities=(), install=None,
            requirements=(), missing=(), class_name="AWSConnector",
            module="vendor_fabric.aws", base_url=None, description=None, error=None,
        )
        with patch("vendor_fabric.registry.get_missing_connector_requirements", return_value=[]):
            with patch.object(BuiltinConnectorAdapter, "info", return_value=sentinel) as info_mock:
                data = adapter.as_dict()
        info_mock.assert_called_once()
        assert isinstance(data, ExtendedDict)


class TestRegisteredConnectorAdapter:
    """RegisteredConnectorAdapter wraps an already-loaded class."""

    def test_load_class_returns_loaded_class(self):
        cls = type("Fake", (), {})
        adapter = RegisteredConnectorAdapter(name="fake", connector_class=cls)  # type: ignore[arg-type]
        assert adapter.load_class() is cls

    def test_info_returns_entry_point_source(self):
        class Fake(ConnectorBase):
            __doc__ = "A fake connector."

        adapter = RegisteredConnectorAdapter(name="fake", connector_class=Fake)
        info = adapter.info()
        assert info.source == "entry_point"
        assert info.class_name == "Fake"
        assert info.description == "A fake connector."

    def test_info_with_error_returns_unavailable(self):
        class Fake(ConnectorBase):
            pass

        adapter = RegisteredConnectorAdapter(name="fake", connector_class=Fake)
        info = adapter.info(error=ImportError("token=ghp_hunter2"))
        assert info.available is False
        assert info.error is not None
        assert "ghp_hunter2" not in (info.error or "")

    def test_create_instantiates(self):
        class Fake(ConnectorBase):
            def __init__(self, label):
                self.label = label

        adapter = RegisteredConnectorAdapter(name="fake", connector_class=Fake)
        instance = adapter.create(label="x")
        assert isinstance(instance, Fake)
        assert instance.label == "x"


# --- normalization helpers ------------------------------------------------


class TestNormalizeConnectorName:
    def test_strips_whitespace(self):
        assert _normalize_connector_name("  aws  ") == "aws"

    def test_lowercases(self):
        assert _normalize_connector_name("AWS") == "aws"

    def test_preserves_internal_spaces(self):
        assert _normalize_connector_name("my aws") == "my aws"


class TestNormalizeCatalogToken:
    def test_lowercases_and_replaces_underscores(self):
        assert _normalize_catalog_token("Identity_Token") == "identity-token"

    def test_strips_whitespace(self):
        assert _normalize_catalog_token("  files  ") == "files"

    def test_stringifies_non_string(self):
        assert _normalize_catalog_token(42) == "42"


# --- builtin catalog ------------------------------------------------------


class TestBuiltinConnectorsCatalog:
    """The shipped BUILTIN_CONNECTORS catalog is internally consistent."""

    @pytest.mark.parametrize("name,spec", sorted(BUILTIN_CONNECTORS.items()))
    def test_each_spec_has_module_path_class_name_and_extra(self, name, spec):
        assert spec.module_path.startswith("vendor_fabric.")
        assert spec.class_name.endswith("Connector")
        assert spec.extra
        assert spec.category

    def test_adapters_index_matches_specs(self):
        assert set(BUILTIN_CONNECTOR_ADAPTERS) == set(BUILTIN_CONNECTORS)
        for name, adapter in BUILTIN_CONNECTOR_ADAPTERS.items():
            assert adapter.name == name
            assert adapter.spec is BUILTIN_CONNECTORS[name]


# --- internal info builders ----------------------------------------------


class _FakeConnector(ConnectorBase):
    """Stand-in connector for info-builder tests."""

    BASE_URL = "https://example.test"
    CONNECTOR_CATEGORY = "fake"
    CONNECTOR_CAPABILITIES = ("alpha", "beta")
    __doc__ = "Fake connector for tests."


class TestClassConnectorInfo:
    def test_builtin_source_uses_spec_extra(self):
        spec = BuiltinConnectorSpec("m", "C", "fake-extra", category="fake", capabilities=("alpha",))
        info = _class_connector_info("fake", _FakeConnector, spec=spec)
        assert info.source == "builtin"
        assert info.extra == "fake-extra"
        assert info.class_name == "_FakeConnector"
        assert info.module == _FakeConnector.__module__
        assert info.base_url == "https://example.test"
        assert info.description == "Fake connector for tests."

    def test_entry_point_source_falls_back_to_class_attrs(self):
        info = _class_connector_info("fake", _FakeConnector, spec=None)
        assert info.source == "entry_point"
        assert info.category == "fake"
        assert info.capabilities == ("alpha", "beta")


class TestGetDescription:
    def test_returns_first_non_blank_line(self):
        class C(ConnectorBase):
            """First.

            Second.
            """

        assert _get_description(C) == "First."

    def test_returns_none_when_no_docstring(self):
        class C(ConnectorBase):
            pass

        assert _get_description(C) is None

    def test_returns_none_when_docstring_is_only_whitespace(self):
        class C(ConnectorBase):
            """

    """

        assert _get_description(C) is None


class TestGetCategory:
    def test_uses_spec_category_when_provided(self):
        spec = BuiltinConnectorSpec("m", "C", "extra", category="Cloud_Services")
        assert _get_category(_FakeConnector, spec) == "cloud-services"

    def test_falls_back_to_class_attribute(self):
        assert _get_category(_FakeConnector, None) == "fake"

    def test_defaults_to_external(self):
        class C(ConnectorBase):
            pass

        assert _get_category(C, None) == "external"


class TestGetCapabilities:
    def test_uses_spec_capabilities_when_provided(self):
        spec = BuiltinConnectorSpec("m", "C", "extra", capabilities=("Identity_Token", "files"))
        caps = _get_capabilities(_FakeConnector, spec)
        assert caps == ("identity-token", "files")

    def test_falls_back_to_class_attribute(self):
        assert _get_capabilities(_FakeConnector, None) == ("alpha", "beta")

    def test_string_capability_wraps_to_tuple(self):
        spec = BuiltinConnectorSpec("m", "C", "extra", capabilities="single")
        assert _get_capabilities(_FakeConnector, spec) == ("single",)

    def test_dedupes_preserving_order(self):
        class C(ConnectorBase):
            CONNECTOR_CAPABILITIES = ("alpha", "beta", "alpha")

        assert _get_capabilities(C, None) == ("alpha", "beta")

    def test_drops_empty_tokens(self):
        class C(ConnectorBase):
            CONNECTOR_CAPABILITIES = ("alpha", "", "  ", "beta")

        assert _get_capabilities(C, None) == ("alpha", "beta")


class TestAvailableAndMissingBuiltinInfo:
    def test_available_connector_info_uses_builtin_spec(self):
        info = _available_connector_info("aws", _FakeConnector)
        assert info.source == "builtin"
        assert info.class_name == "_FakeConnector"

    def test_builtin_connector_info_when_unavailable(self):
        adapter = BuiltinConnectorAdapter(name="aws", spec=BUILTIN_CONNECTORS["aws"])
        info = _builtin_connector_info(adapter, available=False, error=None)
        assert info.available is False
        assert info.source == "builtin"
        assert info.error is not None
        assert info.class_name == BUILTIN_CONNECTORS["aws"].class_name

    def test_missing_builtin_connector_info_delegates_to_adapter(self):
        sentinel = ConnectorInfo(
            name="aws", available=False, source="builtin", extra="aws",
            category="cloud", capabilities=(), install=None,
            requirements=(), missing=(), class_name=None, module=None,
            base_url=None, description=None, error="boom",
        )
        with patch.object(BuiltinConnectorAdapter, "info", return_value=sentinel) as info_mock:
            result = _missing_builtin_connector_info("aws", None)
        info_mock.assert_called_once()
        assert result is sentinel


# --- raise helpers --------------------------------------------------------


class TestRaiseHelpers:
    def test_raise_missing_builtin_connector_uses_adapter(self):
        with patch.object(BuiltinConnectorAdapter, "unavailable_error", return_value=ImportError("boom")) as err_mock:
            with pytest.raises(ImportError, match="boom"):
                _raise_missing_builtin_connector("aws", ImportError("orig"))
        err_mock.assert_called_once()

    def test_raise_unregistered_builtin_connector_names_spec(self):
        with pytest.raises(RuntimeError, match="declared but is not registered"):
            _raise_unregistered_builtin_connector("aws")


# --- discovery + cache ----------------------------------------------------


class TestDiscoveryAndCache:
    """Entry-point discovery, caching, and clear_cache behavior."""

    def setup_method(self):
        clear_cache()

    def teardown_method(self):
        clear_cache()

    def test_discover_caches_after_first_call(self):
        with patch("importlib.metadata.entry_points", return_value=iter([])) as ep_mock:
            _discover_connectors()
            _discover_connectors()
        ep_mock.assert_called_once()

    def test_clear_cache_resets_discovery(self):
        with patch("importlib.metadata.entry_points", return_value=iter([])):
            _discover_connectors()
            clear_cache()
            assert _list_connector_classes() == {}

    def test_discover_skips_missing_builtin_and_records_error(self):
        class FakeEP:
            name = "aws"
            def load(self):
                raise ImportError("no boto3")

        with patch("importlib.metadata.entry_points", return_value=iter([FakeEP()])):
            connectors = _discover_connectors()
        assert "aws" not in connectors
        assert "aws" in _missing_builtin_connectors

    def test_discover_warns_on_unknown_entry_point_failure(self):
        class FakeEP:
            name = "unknown"
            def load(self):
                raise ImportError("nope")

        with patch("importlib.metadata.entry_points", return_value=iter([FakeEP()])):
            with pytest.warns(UserWarning, match="Failed to load connector"):
                _discover_connectors()

    def test_discover_warns_on_non_import_error(self):
        class FakeEP:
            name = "unknown"
            def load(self):
                raise RuntimeError("weird")

        with patch("importlib.metadata.entry_points", return_value=iter([FakeEP()])):
            with pytest.warns(UserWarning, match="Failed to load connector"):
                _discover_connectors()


# --- public API surface ---------------------------------------------------


class TestPublicApi:
    """End-to-end exercises of the public list/get helpers."""

    def setup_method(self):
        clear_cache()

    def teardown_method(self):
        clear_cache()

    def test_list_connectors_includes_all_builtins(self):
        names = list_connectors(include_unavailable=True)
        for builtin in BUILTIN_CONNECTORS:
            assert builtin in names

    def test_list_available_connectors_filters_unavailable(self):
        all_names = list_connectors(include_unavailable=True)
        available = list_available_connectors()
        assert set(available).issubset(set(all_names))

    def test_list_connector_info_returns_extended_list(self):
        info = list_connector_info()
        assert isinstance(info, ExtendedList)
        assert len(info) >= len(BUILTIN_CONNECTORS)
        assert all(isinstance(item, ExtendedDict) for item in info)

    def test_list_connector_categories_contains_known(self):
        categories = list_connector_categories()
        catalog_categories = {spec.category for spec in BUILTIN_CONNECTORS.values()}
        for category in catalog_categories:
            assert _normalize_catalog_token(category) in categories

    def test_list_connector_capabilities_contains_known(self):
        capabilities = list_connector_capabilities()
        catalog_capabilities: set[str] = set()
        for spec in BUILTIN_CONNECTORS.values():
            catalog_capabilities.update(_normalize_catalog_token(cap) for cap in spec.capabilities)
        for cap in catalog_capabilities:
            assert cap in capabilities

    def test_list_connectors_by_category_matches(self):
        matches = list_connectors_by_category("cloud")
        matched_names = [item["name"] for item in matches]
        assert "google" in matched_names
        assert "aws" in matched_names

    def test_list_connectors_by_capability_matches(self):
        matches = list_connectors_by_capability("secrets")
        matched_names = [item["name"] for item in matches]
        assert "aws" in matched_names

    def test_list_connectors_by_capability_matches_vault_kv(self):
        matches = list_connectors_by_capability("kv")
        matched_names = [item["name"] for item in matches]
        assert "vault" in matched_names

    def test_get_connector_info_returns_extended_dict(self):
        info = get_connector_info("aws")
        assert isinstance(info, ExtendedDict)
        assert info["name"] == "aws"
        assert info["source"] == "builtin"

    def test_get_connector_info_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown connector"):
            get_connector_info("not-a-real-connector")

    def test_get_connector_info_normalizes_name(self):
        info = get_connector_info("  AWS  ")
        assert info["name"] == "aws"

    def test_get_connector_info_unavailable_raises_when_include_false(self):
        with patch("vendor_fabric.registry.get_missing_connector_requirements", return_value=["boto3"]):
            with pytest.raises(ImportError):
                get_connector_info("aws", include_unavailable=False)

    def test_get_connector_adapter_builtin_returns_builtin_adapter(self):
        adapter = get_connector_adapter("aws")
        assert isinstance(adapter, BuiltinConnectorAdapter)

    def test_get_connector_adapter_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown connector"):
            get_connector_adapter("not-a-real-connector")

    def test_get_connector_class_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown connector"):
            get_connector_class("not-a-real-connector")

    def test_raise_unregistered_builtin_connector_message_shape(self):
        # This path is only reachable if a builtin spec exists without a
        # matching adapter, which the catalog construction prevents in
        # normal operation. Test the helper directly.
        with pytest.raises(RuntimeError, match="declared but is not registered"):
            _raise_unregistered_builtin_connector("aws")


# --- ConnectorAdapter.create plumbing ------------------------------------


class TestAdapterCreate:
    def test_builtin_adapter_create_delegates_to_load_class(self):
        class Fake(ConnectorBase):
            def __init__(self, label):
                self.label = label

        adapter = BuiltinConnectorAdapter(name="fake", spec=BuiltinConnectorSpec("m", "C", "extra"))
        with patch.object(BuiltinConnectorAdapter, "load_class", return_value=Fake):
            instance = adapter.create(label="x")
        assert isinstance(instance, Fake)
        assert instance.label == "x"
