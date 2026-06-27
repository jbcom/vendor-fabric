# ruff: noqa: I001
"""Tests for Google Cloud services discovery operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("google.oauth2.service_account")
pytest.importorskip("googleapiclient")

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data
from vendor_fabric.google import GoogleConnector


def _logged_text(logger: MagicMock) -> str:
    """Return concatenated mock logger messages."""
    return "\n".join(str(arg) for call in logger.method_calls for arg in call.args)


@pytest.fixture
def google_connector():
    """Create Google connector with mocked services."""
    service_account = {
        "type": "service_account",
        "client_email": "test@example.iam.gserviceaccount.com",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...test\n-----END RSA PRIVATE KEY-----\n",
        "private_key_id": "key123",
        "project_id": "test-project",
    }
    with patch("googleapiclient.discovery.build"):
        connector = GoogleConnector(service_account_info=service_account)
        connector.logger = MagicMock()
        return connector


class TestComputeEngine:
    """Tests for Compute Engine operations."""

    def test_list_compute_instances_all_zones(self, google_connector):
        """Test listing compute instances across all zones."""
        mock_service = MagicMock()
        mock_instances = mock_service.instances.return_value
        mock_instances.aggregatedList.return_value.execute.return_value = {
            "items": {
                "zones/us-central1-a": {
                    "instances": [
                        {"name": "instance-1", "zone": "us-central1-a"},
                        {"name": "instance-2", "zone": "us-central1-a"},
                    ]
                },
                "zones/us-east1-b": {"instances": [{"name": "instance-3", "zone": "us-east1-b"}]},
            }
        }
        google_connector.get_compute_service = MagicMock(return_value=mock_service)

        result = google_connector.list_compute_instances("test-project")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["name"], ExtendedString)
        assert len(result) == 3
        assert result[0]["name"] == "instance-1"
        assert result[2]["name"] == "instance-3"

    def test_list_compute_instances_specific_zone(self, google_connector):
        """Test listing compute instances in specific zone."""
        mock_service = MagicMock()
        mock_instances = mock_service.instances.return_value
        mock_instances.list.return_value.execute.return_value = {
            "items": [
                {"name": "instance-1", "zone": "us-central1-a"},
                {"name": "instance-2", "zone": "us-central1-a"},
            ]
        }
        google_connector.get_compute_service = MagicMock(return_value=mock_service)

        result = google_connector.list_compute_instances("test-project", zone="us-central1-a")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 2
        mock_instances.list.assert_called_once()

    def test_list_compute_instances_pagination(self, google_connector):
        """Test listing compute instances with pagination."""
        mock_service = MagicMock()
        mock_instances = mock_service.instances.return_value
        mock_instances.aggregatedList.return_value.execute.side_effect = [
            {
                "items": {"zones/us-central1-a": {"instances": [{"name": "instance-1"}]}},
                "nextPageToken": "token123",
            },
            {
                "items": {"zones/us-east1-b": {"instances": [{"name": "instance-2"}]}},
            },
        ]
        google_connector.get_compute_service = MagicMock(return_value=mock_service)

        result = google_connector.list_compute_instances("test-project")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 2
        assert mock_instances.aggregatedList.return_value.execute.call_count == 2


class TestGKE:
    """Tests for Google Kubernetes Engine operations."""

    def test_list_gke_clusters(self, google_connector):
        """Test listing GKE clusters."""
        mock_service = MagicMock()
        mock_clusters = mock_service.projects.return_value.locations.return_value.clusters.return_value
        mock_clusters.list.return_value.execute.return_value = {
            "clusters": [
                {"name": "cluster-1", "location": "us-central1"},
                {"name": "cluster-2", "location": "us-east1"},
            ]
        }
        google_connector.get_container_service = MagicMock(return_value=mock_service)

        result = google_connector.list_gke_clusters("test-project")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["name"], ExtendedString)
        assert len(result) == 2
        assert result[0]["name"] == "cluster-1"

    def test_list_gke_clusters_with_location(self, google_connector):
        """Test listing GKE clusters in specific location."""
        mock_service = MagicMock()
        mock_clusters = mock_service.projects.return_value.locations.return_value.clusters.return_value
        mock_clusters.list.return_value.execute.return_value = {
            "clusters": [{"name": "cluster-1", "location": "us-central1"}]
        }
        google_connector.get_container_service = MagicMock(return_value=mock_service)

        result = google_connector.list_gke_clusters("test-project", location="us-central1")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 1
        mock_clusters.list.assert_called_once_with(parent="projects/test-project/locations/us-central1")

    def test_get_gke_cluster(self, google_connector):
        """Test getting a specific GKE cluster."""
        mock_service = MagicMock()
        mock_clusters = mock_service.projects.return_value.locations.return_value.clusters.return_value
        mock_clusters.get.return_value.execute.return_value = {
            "name": "cluster-1",
            "location": "us-central1",
            "status": "RUNNING",
        }
        google_connector.get_container_service = MagicMock(return_value=mock_service)

        result = google_connector.get_gke_cluster("test-project", "us-central1", "cluster-1")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["name"], ExtendedString)
        assert result["name"] == "cluster-1"
        assert result["status"] == "RUNNING"

    def test_get_gke_cluster_not_found(self, google_connector):
        """Test getting non-existent GKE cluster."""
        from googleapiclient.errors import HttpError

        mock_service = MagicMock()
        mock_clusters = mock_service.projects.return_value.locations.return_value.clusters.return_value
        mock_resp = MagicMock()
        mock_resp.status = 404
        error = HttpError(mock_resp, b"Not found")
        mock_clusters.get.return_value.execute.side_effect = error
        google_connector.get_container_service = MagicMock(return_value=mock_service)

        result = google_connector.get_gke_cluster("test-project", "us-central1", "missing-cluster")

        assert result is None


class TestCloudStorage:
    """Tests for Cloud Storage operations."""

    def test_list_storage_buckets(self, google_connector):
        """Test listing Cloud Storage buckets."""
        mock_service = MagicMock()
        mock_buckets = mock_service.buckets.return_value
        mock_buckets.list.return_value.execute.return_value = {
            "items": [
                {"name": "bucket-1", "location": "US"},
                {"name": "bucket-2", "location": "EU"},
            ]
        }
        google_connector.get_storage_service = MagicMock(return_value=mock_service)

        result = google_connector.list_storage_buckets("test-project")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["name"], ExtendedString)
        assert len(result) == 2
        assert result[0]["name"] == "bucket-1"


class TestCloudSQL:
    """Tests for Cloud SQL operations."""

    def test_list_sql_instances(self, google_connector):
        """Test listing Cloud SQL instances."""
        mock_service = MagicMock()
        mock_instances = mock_service.instances.return_value
        mock_instances.list.return_value.execute.return_value = {
            "items": [
                {"name": "instance-1", "databaseVersion": "MYSQL_8_0"},
                {"name": "instance-2", "databaseVersion": "POSTGRES_13"},
            ]
        }
        google_connector.get_sqladmin_service = MagicMock(return_value=mock_service)

        result = google_connector.list_sql_instances("test-project")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["databaseVersion"], ExtendedString)
        assert len(result) == 2
        assert result[0]["databaseVersion"] == "MYSQL_8_0"


class TestPubSub:
    """Tests for Pub/Sub operations."""

    def test_list_pubsub_topics(self, google_connector):
        """Test listing Pub/Sub topics."""
        mock_service = MagicMock()
        mock_topics = mock_service.projects.return_value.topics.return_value
        mock_topics.list.return_value.execute.return_value = {
            "topics": [
                {"name": "projects/test-project/topics/topic-1"},
                {"name": "projects/test-project/topics/topic-2"},
            ]
        }
        google_connector.get_pubsub_service = MagicMock(return_value=mock_service)

        result = google_connector.list_pubsub_topics("test-project")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["name"], ExtendedString)
        assert len(result) == 2
        assert "topic-1" in result[0]["name"]

    def test_list_pubsub_subscriptions(self, google_connector):
        """Test listing Pub/Sub subscriptions."""
        mock_service = MagicMock()
        mock_subs = mock_service.projects.return_value.subscriptions.return_value
        mock_subs.list.return_value.execute.return_value = {
            "subscriptions": [
                {"name": "projects/test-project/subscriptions/sub-1"},
                {"name": "projects/test-project/subscriptions/sub-2"},
            ]
        }
        google_connector.get_pubsub_service = MagicMock(return_value=mock_service)

        result = google_connector.list_pubsub_subscriptions("test-project")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["name"], ExtendedString)
        assert len(result) == 2
        assert "sub-1" in result[0]["name"]


class TestCloudKMS:
    """Tests for Cloud KMS operations."""

    def test_list_kms_keyrings(self, google_connector):
        """Test listing KMS keyrings."""
        mock_service = MagicMock()
        mock_keyrings = mock_service.projects.return_value.locations.return_value.keyRings.return_value
        mock_keyrings.list.return_value.execute.return_value = {
            "keyRings": [
                {"name": "projects/test-project/locations/us/keyRings/keyring-1"},
                {"name": "projects/test-project/locations/us/keyRings/keyring-2"},
            ]
        }
        google_connector.get_cloudkms_service = MagicMock(return_value=mock_service)

        result = google_connector.list_kms_keyrings("test-project", "us")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["name"], ExtendedString)
        assert len(result) == 2
        assert "keyring-1" in result[0]["name"]

    def test_create_kms_keyring(self, google_connector):
        """Test creating a KMS keyring."""
        mock_service = MagicMock()
        mock_keyrings = mock_service.projects.return_value.locations.return_value.keyRings.return_value
        mock_keyrings.create.return_value.execute.return_value = {
            "name": "projects/test-project/locations/us/keyRings/new-keyring"
        }
        google_connector.get_cloudkms_service = MagicMock(return_value=mock_service)

        result = google_connector.create_kms_keyring("test-project", "us", "new-keyring")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["name"], ExtendedString)
        assert "new-keyring" in result["name"]

    def test_create_kms_key(self, google_connector):
        """Test creating a crypto key."""
        mock_service = MagicMock()
        mock_projects = mock_service.projects.return_value
        mock_locations = mock_projects.locations.return_value
        mock_keyrings = mock_locations.keyRings.return_value
        mock_keys = mock_keyrings.cryptoKeys.return_value
        mock_keys.create.return_value.execute.return_value = {
            "name": "projects/test-project/locations/us/keyRings/kr1/cryptoKeys/new-key"
        }
        google_connector.get_cloudkms_service = MagicMock(return_value=mock_service)

        result = google_connector.create_kms_key("test-project", "us", "kr1", "new-key")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["name"], ExtendedString)
        assert "new-key" in result["name"]

    def test_create_kms_key_logs_redact_identifiers_but_preserve_call_args(self, google_connector):
        """KMS mutation logs should not expose project/key resource identifiers."""
        mock_service = MagicMock()
        mock_projects = mock_service.projects.return_value
        mock_locations = mock_projects.locations.return_value
        mock_keyrings = mock_locations.keyRings.return_value
        mock_keys = mock_keyrings.cryptoKeys.return_value
        mock_keys.create.return_value.execute.return_value = {
            "name": "projects/sensitive-project/locations/us/keyRings/private-ring/cryptoKeys/private-key"
        }
        google_connector.get_cloudkms_service = MagicMock(return_value=mock_service)

        google_connector.create_kms_key("sensitive-project", "us", "private-ring", "private-key")

        assert mock_keys.create.call_args.kwargs["parent"] == (
            "projects/sensitive-project/locations/us/keyRings/private-ring"
        )
        assert mock_keys.create.call_args.kwargs["cryptoKeyId"] == "private-key"
        logs = _logged_text(google_connector.logger)
        assert "[REDACTED]" in logs
        assert "sensitive-project" not in logs
        assert "private-ring" not in logs
        assert "private-key" not in logs


class TestServiceUsage:
    """Tests for Service Usage operations."""

    def test_list_enabled_services(self, google_connector):
        """Test listing enabled APIs."""
        mock_service = MagicMock()
        mock_services = mock_service.services.return_value
        mock_services.list.return_value.execute.return_value = {
            "services": [
                {"name": "projects/test-project/services/compute.googleapis.com"},
                {"name": "projects/test-project/services/container.googleapis.com"},
            ]
        }
        google_connector.get_serviceusage_service = MagicMock(return_value=mock_service)

        result = google_connector.list_enabled_services("test-project")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["name"], ExtendedString)
        assert len(result) == 2

    def test_enable_service(self, google_connector):
        """Test enabling an API."""
        mock_service = MagicMock()
        mock_services = mock_service.services.return_value
        mock_services.enable.return_value.execute.return_value = {"name": "operations/enable-compute"}
        google_connector.get_serviceusage_service = MagicMock(return_value=mock_service)

        result = google_connector.enable_service("test-project", "compute.googleapis.com")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["name"], ExtendedString)
        assert result["name"] == "operations/enable-compute"

    def test_enable_service_logs_redact_identifiers_but_preserve_call_args(self, google_connector):
        """Service Usage logs should not expose project or service names."""
        mock_service = MagicMock()
        mock_services = mock_service.services.return_value
        mock_services.enable.return_value.execute.return_value = {"name": "operations/enable-private"}
        google_connector.get_serviceusage_service = MagicMock(return_value=mock_service)

        google_connector.enable_service("sensitive-project", "private.googleapis.com")

        assert mock_services.enable.call_args.kwargs["name"] == (
            "projects/sensitive-project/services/private.googleapis.com"
        )
        logs = _logged_text(google_connector.logger)
        assert "[REDACTED]" in logs
        assert "sensitive-project" not in logs
        assert "private.googleapis.com" not in logs

    def test_disable_service(self, google_connector):
        """Test disabling an API."""
        mock_service = MagicMock()
        mock_services = mock_service.services.return_value
        mock_services.disable.return_value.execute.return_value = {"name": "operations/disable-compute"}
        google_connector.get_serviceusage_service = MagicMock(return_value=mock_service)

        result = google_connector.disable_service("test-project", "compute.googleapis.com", force=True)

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["name"], ExtendedString)
        assert result["name"] == "operations/disable-compute"
        mock_services.disable.assert_called_once_with(
            name="projects/test-project/services/compute.googleapis.com",
            body={"disableDependentServices": True},
        )

    def test_batch_enable_services(self, google_connector):
        """Test enabling multiple APIs."""
        mock_service = MagicMock()
        mock_services = mock_service.services.return_value
        mock_services.batchEnable.return_value.execute.return_value = {"name": "operations/batch-enable"}
        google_connector.get_serviceusage_service = MagicMock(return_value=mock_service)

        result = google_connector.batch_enable_services(
            "test-project",
            ["compute.googleapis.com", "container.googleapis.com"],
        )

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["name"], ExtendedString)
        assert result["name"] == "operations/batch-enable"


class TestProjectResourceSummary:
    """Tests for derived project resource operations."""

    def test_is_project_empty_denied_check_logs_redact_project_and_error(self, google_connector):
        """Denied resource checks should not expose project IDs or raw provider details."""
        denied = RuntimeError("denied sensitive-project token=raw-token")
        denied.resp = MagicMock(status=403)  # type: ignore[attr-defined]
        google_connector.list_compute_instances = MagicMock(side_effect=denied)

        result = google_connector.is_project_empty(
            "sensitive-project",
            check_gke=False,
            check_storage=False,
            check_sql=False,
            check_pubsub=False,
        )

        assert result is True
        logs = _logged_text(google_connector.logger)
        assert "[REDACTED]" in logs
        assert "sensitive-project" not in logs
        assert "raw-token" not in logs

    def test_is_project_empty_denied_check_continues_to_other_services(self, google_connector):
        """A denied API check should not make the whole project look empty."""
        denied = RuntimeError("compute disabled")
        denied.resp = MagicMock(status=403)  # type: ignore[attr-defined]
        google_connector.list_compute_instances = MagicMock(side_effect=denied)
        google_connector.list_gke_clusters = MagicMock(return_value=[])
        google_connector.list_storage_buckets = MagicMock(return_value=[{"name": "active-bucket"}])

        result = google_connector.is_project_empty(
            "test-project",
            check_sql=False,
            check_pubsub=False,
        )

        assert result is False
        google_connector.list_gke_clusters.assert_called_once_with("test-project")
        google_connector.list_storage_buckets.assert_called_once_with("test-project")

    def test_get_project_iam_users(self, google_connector):
        """Test deriving IAM members from a project policy."""
        mock_service = MagicMock()
        mock_projects = mock_service.projects.return_value
        mock_projects.getIamPolicy.return_value.execute.return_value = {
            "bindings": [
                {"role": "roles/viewer", "members": ["user:a@example.com"]},
                {"role": "roles/editor", "members": ["user:a@example.com", "group:dev@example.com"]},
            ]
        }
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        result = google_connector.get_project_iam_users("test-project")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["user:a@example.com"], ExtendedDict)
        assert isinstance(result["user:a@example.com"]["roles"], ExtendedList)
        assert result["user:a@example.com"]["roles"] == ["roles/viewer", "roles/editor"]

    def test_get_pubsub_resources_for_project(self, google_connector):
        """Test aggregating Pub/Sub resources."""
        google_connector.list_pubsub_topics = MagicMock(
            return_value=extend_data([{"name": "projects/test-project/topics/topic-1"}])
        )
        google_connector.list_pubsub_subscriptions = MagicMock(
            return_value=extend_data([{"name": "projects/test-project/subscriptions/sub-1"}])
        )

        result = google_connector.get_pubsub_resources_for_project("test-project")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["topics"], ExtendedList)
        assert isinstance(result["topics"][0], ExtendedDict)
        assert isinstance(result["subscriptions"], ExtendedList)
        assert result["topic_count"] == 1
        assert result["subscription_count"] == 1

    def test_find_inactive_projects(self, google_connector):
        """Test finding inactive projects from supplied project metadata."""
        projects = extend_data(
            {
                "active-project": {
                    "projectId": "active-project",
                    "lifecycleState": "ACTIVE",
                    "updateTime": "2026-06-01T00:00:00Z",
                },
                "deleted-project": {
                    "projectId": "deleted-project",
                    "lifecycleState": "DELETE_REQUESTED",
                },
            }
        )
        google_connector.is_project_empty = MagicMock(return_value=True)

        result = google_connector.find_inactive_projects(
            projects=projects,
            days_since_activity=30,
        )

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert result[0]["projectId"] == "deleted-project"
        assert result[0]["inactive_reason"] == "lifecycle_state=DELETE_REQUESTED"
