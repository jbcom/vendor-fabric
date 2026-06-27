"""Google Cloud services discovery operations.

This module provides operations for discovering resources across Google Cloud
services like GKE, Compute Engine, Cloud Storage, Cloud SQL, Pub/Sub, etc.
"""

from __future__ import annotations

import datetime as dt

from collections.abc import Callable, Mapping, MutableMapping, Sized
from typing import TYPE_CHECKING, Any

from extended_data.containers import ExtendedDict, ExtendedList
from extended_data.primitives import unhump_map

from vendor_fabric.google._diagnostics import safe_google_ref, safe_google_text


_PROJECT_ACTIVITY_TIME_FIELDS = (
    "lastActivityTime",
    "lastActiveTime",
    "last_activity_time",
    "last_active_time",
    "updateTime",
    "createTime",
)


def _has_http_status(exc: BaseException, status: int) -> bool:
    """Return whether an exception exposes a Google-style HTTP response status."""
    return getattr(getattr(exc, "resp", None), "status", None) == status


def _parse_project_activity_time(value: Any) -> dt.datetime | None:
    """Parse a Google-style timestamp into an aware UTC datetime."""
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized:
        return None

    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _latest_project_activity_time(project_data: Mapping[str, Any]) -> dt.datetime | None:
    """Return the latest activity timestamp available on project metadata."""
    timestamps = [
        parsed
        for field in _PROJECT_ACTIVITY_TIME_FIELDS
        if (parsed := _parse_project_activity_time(project_data.get(field))) is not None
    ]
    return max(timestamps) if timestamps else None


def _project_activity_is_stale(
    project_data: Mapping[str, Any],
    *,
    days_since_activity: int,
    now: dt.datetime | None = None,
) -> bool:
    """Return whether project metadata indicates activity older than the threshold."""
    activity_time = _latest_project_activity_time(project_data)
    if activity_time is None:
        return True

    reference_time = now or dt.datetime.now(dt.UTC)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=dt.UTC)
    cutoff = reference_time.astimezone(dt.UTC) - dt.timedelta(days=days_since_activity)
    return activity_time <= cutoff


class GoogleServicesMixin:
    """Mixin providing Google Cloud services discovery operations.

    This mixin requires the base GoogleConnector class to provide:
    - get_compute_service()
    - get_container_service()
    - get_storage_service()
    - get_sqladmin_service()
    - get_pubsub_service()
    - get_serviceusage_service()
    - get_cloudkms_service()
    - logger
    """

    if TYPE_CHECKING:
        logger: Any

        def get_compute_service(self) -> Any: ...

        def get_container_service(self) -> Any: ...

        def get_storage_service(self) -> Any: ...

        def get_sqladmin_service(self) -> Any: ...

        def get_pubsub_service(self) -> Any: ...

        def get_serviceusage_service(self) -> Any: ...

        def get_cloudkms_service(self) -> Any: ...

        def get_cloud_resource_manager_service(self) -> Any: ...

        def extend_result(self, value: Any) -> Any: ...

    # =========================================================================
    # Compute Engine
    # =========================================================================

    def list_compute_instances(
        self,
        project_id: str,
        zone: str | None = None,
        unhump_instances: bool = False,
    ) -> ExtendedList[ExtendedDict]:
        """List Compute Engine instances in a project.

        Args:
            project_id: The project ID.
            zone: Optional zone filter. If not provided, lists all zones.
            unhump_instances: Convert keys to snake_case. Defaults to False.

        Returns:
            List of instance dictionaries.
        """
        safe_project = safe_google_ref(project_id)
        self.logger.info(f"Listing Compute Engine instances in {safe_project}")
        service = self.get_compute_service()

        instances: list[dict[str, Any]] = []

        if zone:
            # List instances in specific zone
            page_token = None
            while True:
                zone_params: dict[str, Any] = {"project": project_id, "zone": zone}
                if page_token:
                    zone_params["pageToken"] = page_token

                response = service.instances().list(**zone_params).execute()
                instances.extend(response.get("items", []))

                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        else:
            # Aggregate list across all zones
            page_token = None
            while True:
                aggregate_params: dict[str, Any] = {"project": project_id}
                if page_token:
                    aggregate_params["pageToken"] = page_token

                response = service.instances().aggregatedList(**aggregate_params).execute()
                for zone_data in response.get("items", {}).values():
                    instances.extend(zone_data.get("instances", []))

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

        self.logger.info(f"Retrieved {len(instances)} instances")

        if unhump_instances:
            instances = [unhump_map(i) for i in instances]

        return self.extend_result(instances)

    # =========================================================================
    # Google Kubernetes Engine
    # =========================================================================

    def list_gke_clusters(
        self,
        project_id: str,
        location: str = "-",
        unhump_clusters: bool = False,
    ) -> ExtendedList[ExtendedDict]:
        """List GKE clusters in a project.

        Args:
            project_id: The project ID.
            location: Zone or region. Use '-' for all locations.
            unhump_clusters: Convert keys to snake_case. Defaults to False.

        Returns:
            List of cluster dictionaries.
        """
        safe_project = safe_google_ref(project_id)
        self.logger.info(f"Listing GKE clusters in {safe_project}")
        service = self.get_container_service()

        parent = f"projects/{project_id}/locations/{location}"
        response = service.projects().locations().clusters().list(parent=parent).execute()

        clusters = response.get("clusters", [])
        self.logger.info(f"Retrieved {len(clusters)} GKE clusters")

        if unhump_clusters:
            clusters = [unhump_map(c) for c in clusters]

        return self.extend_result(clusters)

    def get_gke_cluster(
        self,
        project_id: str,
        location: str,
        cluster_id: str,
    ) -> ExtendedDict | None:
        """Get a specific GKE cluster.

        Args:
            project_id: The project ID.
            location: Zone or region.
            cluster_id: The cluster ID.

        Returns:
            Cluster dictionary or None if not found.
        """
        from googleapiclient.errors import HttpError

        service = self.get_container_service()
        name = f"projects/{project_id}/locations/{location}/clusters/{cluster_id}"

        try:
            return self.extend_result(service.projects().locations().clusters().get(name=name).execute())
        except HttpError as e:
            if e.resp.status == 404:
                self.logger.warning(f"GKE cluster not found: {safe_google_ref(cluster_id)}")
                return None
            raise

    # =========================================================================
    # Cloud Storage
    # =========================================================================

    def list_storage_buckets(
        self,
        project_id: str,
        unhump_buckets: bool = False,
    ) -> ExtendedList[ExtendedDict]:
        """List Cloud Storage buckets in a project.

        Args:
            project_id: The project ID.
            unhump_buckets: Convert keys to snake_case. Defaults to False.

        Returns:
            List of bucket dictionaries.
        """
        safe_project = safe_google_ref(project_id)
        self.logger.info(f"Listing Cloud Storage buckets in {safe_project}")
        service = self.get_storage_service()

        buckets: list[dict[str, Any]] = []
        page_token = None

        while True:
            params: dict[str, Any] = {"project": project_id}
            if page_token:
                params["pageToken"] = page_token

            response = service.buckets().list(**params).execute()
            buckets.extend(response.get("items", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        self.logger.info(f"Retrieved {len(buckets)} buckets")

        if unhump_buckets:
            buckets = [unhump_map(b) for b in buckets]

        return self.extend_result(buckets)

    # =========================================================================
    # Cloud SQL
    # =========================================================================

    def list_sql_instances(
        self,
        project_id: str,
        unhump_instances: bool = False,
    ) -> ExtendedList[ExtendedDict]:
        """List Cloud SQL instances in a project.

        Args:
            project_id: The project ID.
            unhump_instances: Convert keys to snake_case. Defaults to False.

        Returns:
            List of SQL instance dictionaries.
        """
        safe_project = safe_google_ref(project_id)
        self.logger.info(f"Listing Cloud SQL instances in {safe_project}")
        service = self.get_sqladmin_service()

        instances: list[dict[str, Any]] = []
        page_token = None

        while True:
            params: dict[str, Any] = {"project": project_id}
            if page_token:
                params["pageToken"] = page_token

            response = service.instances().list(**params).execute()
            instances.extend(response.get("items", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        self.logger.info(f"Retrieved {len(instances)} SQL instances")

        if unhump_instances:
            instances = [unhump_map(i) for i in instances]

        return self.extend_result(instances)

    # =========================================================================
    # Pub/Sub
    # =========================================================================

    def list_pubsub_topics(
        self,
        project_id: str,
        unhump_topics: bool = False,
    ) -> ExtendedList[ExtendedDict]:
        """List Pub/Sub topics in a project.

        Args:
            project_id: The project ID.
            unhump_topics: Convert keys to snake_case. Defaults to False.

        Returns:
            List of topic dictionaries.
        """
        safe_project = safe_google_ref(project_id)
        self.logger.info(f"Listing Pub/Sub topics in {safe_project}")
        service = self.get_pubsub_service()

        topics: list[dict[str, Any]] = []
        page_token = None

        while True:
            params: dict[str, Any] = {"project": f"projects/{project_id}"}
            if page_token:
                params["pageToken"] = page_token

            response = service.projects().topics().list(**params).execute()
            topics.extend(response.get("topics", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        self.logger.info(f"Retrieved {len(topics)} Pub/Sub topics")

        if unhump_topics:
            topics = [unhump_map(t) for t in topics]

        return self.extend_result(topics)

    def list_pubsub_subscriptions(
        self,
        project_id: str,
        unhump_subscriptions: bool = False,
    ) -> ExtendedList[ExtendedDict]:
        """List Pub/Sub subscriptions in a project.

        Args:
            project_id: The project ID.
            unhump_subscriptions: Convert keys to snake_case. Defaults to False.

        Returns:
            List of subscription dictionaries.
        """
        safe_project = safe_google_ref(project_id)
        self.logger.info(f"Listing Pub/Sub subscriptions in {safe_project}")
        service = self.get_pubsub_service()

        subscriptions: list[dict[str, Any]] = []
        page_token = None

        while True:
            params: dict[str, Any] = {"project": f"projects/{project_id}"}
            if page_token:
                params["pageToken"] = page_token

            response = service.projects().subscriptions().list(**params).execute()
            subscriptions.extend(response.get("subscriptions", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        self.logger.info(f"Retrieved {len(subscriptions)} Pub/Sub subscriptions")

        if unhump_subscriptions:
            subscriptions = [unhump_map(s) for s in subscriptions]

        return self.extend_result(subscriptions)

    # =========================================================================
    # Service Usage (Enabled APIs)
    # =========================================================================

    def list_enabled_services(
        self,
        project_id: str,
        unhump_services: bool = False,
    ) -> ExtendedList[ExtendedDict]:
        """List enabled APIs/services in a project.

        Args:
            project_id: The project ID.
            unhump_services: Convert keys to snake_case. Defaults to False.

        Returns:
            List of service dictionaries.
        """
        safe_project = safe_google_ref(project_id)
        self.logger.info(f"Listing enabled services in {safe_project}")
        service = self.get_serviceusage_service()

        services: list[dict[str, Any]] = []
        page_token = None

        while True:
            params: dict[str, Any] = {
                "parent": f"projects/{project_id}",
                "filter": "state:ENABLED",
            }
            if page_token:
                params["pageToken"] = page_token

            response = service.services().list(**params).execute()
            services.extend(response.get("services", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        self.logger.info(f"Retrieved {len(services)} enabled services")

        if unhump_services:
            services = [unhump_map(s) for s in services]

        return self.extend_result(services)

    def enable_service(
        self,
        project_id: str,
        service_name: str,
    ) -> ExtendedDict:
        """Enable an API/service in a project.

        Args:
            project_id: The project ID.
            service_name: Service name (e.g., 'compute.googleapis.com').

        Returns:
            Operation response dictionary.
        """
        safe_project = safe_google_ref(project_id)
        safe_service_name = safe_google_ref(service_name)
        self.logger.info(f"Enabling service {safe_service_name} in {safe_project}")
        service = self.get_serviceusage_service()

        name = f"projects/{project_id}/services/{service_name}"
        result = service.services().enable(name=name).execute()

        self.logger.info(f"Enabled service {safe_service_name}")
        return self.extend_result(result)

    def disable_service(
        self,
        project_id: str,
        service_name: str,
        force: bool = False,
    ) -> ExtendedDict:
        """Disable an API/service in a project.

        Args:
            project_id: The project ID.
            service_name: Service name (e.g., 'compute.googleapis.com').
            force: Force disable even if dependencies exist.

        Returns:
            Operation response dictionary.
        """
        safe_project = safe_google_ref(project_id)
        safe_service_name = safe_google_ref(service_name)
        self.logger.info(f"Disabling service {safe_service_name} in {safe_project}")
        service = self.get_serviceusage_service()

        name = f"projects/{project_id}/services/{service_name}"
        body: dict[str, Any] = {}
        if force:
            body["disableDependentServices"] = True

        result = service.services().disable(name=name, body=body).execute()

        self.logger.info(f"Disabled service {safe_service_name}")
        return self.extend_result(result)

    def batch_enable_services(
        self,
        project_id: str,
        service_names: list[str],
    ) -> ExtendedDict:
        """Enable multiple APIs/services in a project.

        Args:
            project_id: The project ID.
            service_names: List of service names to enable.

        Returns:
            Operation response dictionary.
        """
        safe_project = safe_google_ref(project_id)
        self.logger.info(f"Batch enabling {len(service_names)} services in {safe_project}")
        service = self.get_serviceusage_service()

        parent = f"projects/{project_id}"
        result = (
            service.services()
            .batchEnable(
                parent=parent,
                body={"serviceIds": service_names},
            )
            .execute()
        )

        self.logger.info(f"Batch enabled {len(service_names)} services")
        return self.extend_result(result)

    # =========================================================================
    # Cloud KMS
    # =========================================================================

    def list_kms_keyrings(
        self,
        project_id: str,
        location: str,
        unhump_keyrings: bool = False,
    ) -> ExtendedList[ExtendedDict]:
        """List KMS key rings in a project location.

        Args:
            project_id: The project ID.
            location: The location (e.g., 'us-central1', 'global').
            unhump_keyrings: Convert keys to snake_case. Defaults to False.

        Returns:
            List of key ring dictionaries.
        """
        safe_parent = safe_google_text(f"{project_id}/{location}", project_id, location)
        self.logger.info(f"Listing KMS key rings in {safe_parent}")
        service = self.get_cloudkms_service()

        keyrings: list[dict[str, Any]] = []
        page_token = None
        parent = f"projects/{project_id}/locations/{location}"

        while True:
            params: dict[str, Any] = {"parent": parent}
            if page_token:
                params["pageToken"] = page_token

            response = service.projects().locations().keyRings().list(**params).execute()
            keyrings.extend(response.get("keyRings", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        self.logger.info(f"Retrieved {len(keyrings)} key rings")

        if unhump_keyrings:
            keyrings = [unhump_map(k) for k in keyrings]

        return self.extend_result(keyrings)

    def create_kms_keyring(
        self,
        project_id: str,
        location: str,
        keyring_id: str,
    ) -> ExtendedDict:
        """Create a KMS key ring.

        Args:
            project_id: The project ID.
            location: The location (e.g., 'us-central1', 'global').
            keyring_id: Unique key ring ID.

        Returns:
            Created key ring dictionary.
        """
        safe_parent = safe_google_text(f"{project_id}/{location}", project_id, location)
        safe_keyring = safe_google_ref(keyring_id)
        self.logger.info(f"Creating KMS key ring {safe_keyring} in {safe_parent}")
        service = self.get_cloudkms_service()

        parent = f"projects/{project_id}/locations/{location}"
        result = (
            service.projects()
            .locations()
            .keyRings()
            .create(
                parent=parent,
                keyRingId=keyring_id,
                body={},
            )
            .execute()
        )

        self.logger.info(f"Created key ring {safe_keyring}")
        return self.extend_result(result)

    def create_kms_key(
        self,
        project_id: str,
        location: str,
        keyring_id: str,
        key_id: str,
        purpose: str = "ENCRYPT_DECRYPT",
        algorithm: str = "GOOGLE_SYMMETRIC_ENCRYPTION",
    ) -> ExtendedDict:
        """Create a KMS crypto key.

        Args:
            project_id: The project ID.
            location: The location.
            keyring_id: The key ring ID.
            key_id: Unique key ID.
            purpose: Key purpose (ENCRYPT_DECRYPT, ASYMMETRIC_SIGN, etc.).
            algorithm: Key algorithm.

        Returns:
            Created crypto key dictionary.
        """
        safe_key = safe_google_ref(key_id)
        safe_keyring = safe_google_ref(keyring_id)
        self.logger.info(f"Creating KMS key {safe_key} in {safe_keyring}")
        service = self.get_cloudkms_service()

        parent = f"projects/{project_id}/locations/{location}/keyRings/{keyring_id}"

        body: dict[str, Any] = {"purpose": purpose}
        if purpose == "ENCRYPT_DECRYPT":
            body["versionTemplate"] = {"algorithm": algorithm}

        result = (
            service.projects()
            .locations()
            .keyRings()
            .cryptoKeys()
            .create(
                parent=parent,
                cryptoKeyId=key_id,
                body=body,
            )
            .execute()
        )

        self.logger.info(f"Created crypto key {safe_key}")
        return self.extend_result(result)

    # =========================================================================
    # Project Resource Summary
    # =========================================================================

    def is_project_empty(
        self,
        project_id: str,
        check_compute: bool = True,
        check_gke: bool = True,
        check_storage: bool = True,
        check_sql: bool = True,
        check_pubsub: bool = True,
    ) -> bool:
        """Check if a project has no resources.

        Args:
            project_id: The project ID.
            check_compute: Check for Compute Engine instances.
            check_gke: Check for GKE clusters.
            check_storage: Check for Cloud Storage buckets.
            check_sql: Check for Cloud SQL instances.
            check_pubsub: Check for Pub/Sub topics.

        Returns:
            True if the project has no resources.
        """
        safe_project = safe_google_ref(project_id)
        self.logger.info(f"Checking if project {safe_project} is empty")

        checks: list[tuple[str, Callable[[], Sized]]] = []
        if check_compute:
            checks.append(("compute instances", lambda: self.list_compute_instances(project_id)))
        if check_gke:
            checks.append(("GKE clusters", lambda: self.list_gke_clusters(project_id)))
        if check_storage:
            checks.append(("storage buckets", lambda: self.list_storage_buckets(project_id)))
        if check_sql:
            checks.append(("SQL instances", lambda: self.list_sql_instances(project_id)))
        if check_pubsub:
            checks.append(("Pub/Sub topics", lambda: self.list_pubsub_topics(project_id)))

        for label, check_fn in checks:
            try:
                resources = check_fn()
            except Exception as e:
                # API might not be enabled, but that should not short-circuit the
                # other resource checks.
                if _has_http_status(e, 403):
                    self.logger.debug(
                        f"API access denied for {label}, skipping check: {safe_google_text(e, project_id)}"
                    )
                    continue
                raise

            if resources:
                self.logger.info(f"Project {safe_project} has {len(resources)} {label}")
                return False

        self.logger.info(f"Project {safe_project} appears to be empty")
        return True

    def get_project_iam_users(
        self,
        project_id: str,
    ) -> ExtendedDict:
        """Get IAM users (members) with access to a project.

        Args:
            project_id: The project ID.

        Returns:
            Dictionary mapping member identifiers to their roles.
        """
        safe_project = safe_google_ref(project_id)
        self.logger.info(f"Getting IAM users for project {safe_project}")
        service = self.get_cloud_resource_manager_service()

        response = service.projects().getIamPolicy(resource=f"projects/{project_id}", body={}).execute()

        users: dict[str, dict[str, Any]] = {}
        for binding in response.get("bindings", []):
            role = binding.get("role", "")
            for member in binding.get("members", []):
                if member not in users:
                    users[member] = {"roles": [], "member_type": member.split(":")[0]}
                users[member]["roles"].append(role)

        self.logger.info(f"Found {len(users)} IAM members for project {safe_project}")
        return self.extend_result(users)

    def get_pubsub_resources_for_project(
        self,
        project_id: str,
        include_subscriptions: bool = True,
        unhump_resources: bool = False,
    ) -> ExtendedDict:
        """Get all Pub/Sub topics and subscriptions for a project.

        Args:
            project_id: The project ID.
            include_subscriptions: Include subscription details. Defaults to True.
            unhump_resources: Convert keys to snake_case. Defaults to False.

        Returns:
            Dictionary with 'topics' and 'subscriptions' lists.
        """
        self.logger.info(f"Getting Pub/Sub resources for project {safe_google_ref(project_id)}")

        topics = self.list_pubsub_topics(project_id)
        result: dict[str, Any] = {
            "topics": topics,
            "topic_count": len(topics),
        }

        if include_subscriptions:
            subscriptions = self.list_pubsub_subscriptions(project_id)
            result["subscriptions"] = subscriptions
            result["subscription_count"] = len(subscriptions)

        if unhump_resources:
            if result.get("topics"):
                result["topics"] = [unhump_map(t) for t in result["topics"]]
            if result.get("subscriptions"):
                result["subscriptions"] = [unhump_map(s) for s in result["subscriptions"]]

        self.logger.info(
            f"Found {result['topic_count']} topics"
            + (f", {result.get('subscription_count', 0)} subscriptions" if include_subscriptions else "")
        )
        return self.extend_result(result)

    def find_inactive_projects(
        self,
        projects: MutableMapping[str, MutableMapping[str, Any]] | None = None,
        check_resources: bool = True,
        days_since_activity: int = 90,
    ) -> ExtendedList[ExtendedDict]:
        """Find projects that appear to be inactive or dead.

        A project is considered inactive if:
        - Its lifecycle state is not ACTIVE
        - It has no resources and no recent activity timestamp

        Args:
            projects: Pre-fetched projects dict. Fetched if not provided.
            check_resources: Check if projects have resources. Defaults to True.
            days_since_activity: Days threshold for available project activity
                timestamps. Empty projects with recent timestamps are not marked
                inactive. Empty projects without activity timestamps are treated
                as inactive.

        Returns:
            List of inactive project dictionaries.
        """
        self.logger.info("Finding inactive projects")

        if days_since_activity < 0:
            msg = "days_since_activity must be greater than or equal to 0."
            raise ValueError(msg)

        if projects is None:
            # Get projects from cloud module - requires GoogleCloudMixin
            if hasattr(self, "list_projects"):
                projects = {str(p["projectId"]): p for p in self.list_projects()}
            else:
                self.logger.warning("list_projects not available, cannot find inactive projects")
                return self.extend_result([])

        inactive: list[MutableMapping[str, Any]] = []

        for project_id, project_data in projects.items():
            lifecycle_state = project_data.get("lifecycleState", "ACTIVE")

            # Non-active projects are definitely inactive
            if lifecycle_state != "ACTIVE":
                project_data["inactive_reason"] = f"lifecycle_state={lifecycle_state}"
                inactive.append(project_data)
                continue

            # Check if project has resources
            if check_resources:
                try:
                    is_empty = self.is_project_empty(project_id)
                    if is_empty and _project_activity_is_stale(
                        project_data,
                        days_since_activity=days_since_activity,
                    ):
                        activity_time = _latest_project_activity_time(project_data)
                        project_data["inactive_reason"] = (
                            f"no_resources_since={activity_time.date().isoformat()}"
                            if activity_time is not None
                            else "no_resources"
                        )
                        inactive.append(project_data)
                except Exception as e:
                    if _has_http_status(e, 403):
                        # Can't check, skip
                        self.logger.debug(
                            f"Cannot check resources for {safe_google_ref(project_id)}: "
                            f"{safe_google_text(e, project_id)}"
                        )
                    else:
                        raise

        self.logger.info(f"Found {len(inactive)} inactive projects out of {len(projects)}")
        return self.extend_result(inactive)
