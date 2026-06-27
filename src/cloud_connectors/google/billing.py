"""Google Cloud Billing operations.

This module provides operations for managing Google Cloud billing accounts
and project billing associations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from extended_data.containers import ExtendedDict, ExtendedList, to_builtin
from extended_data.primitives import unhump_map

from cloud_connectors.google._diagnostics import safe_google_ref, safe_google_text


class GoogleBillingMixin:
    """Mixin providing Google Cloud Billing operations.

    This mixin requires the base GoogleConnector class to provide:
    - get_billing_service()
    - logger
    """

    if TYPE_CHECKING:
        logger: Any
        service_account_info: dict[str, Any]

        def get_billing_service(self) -> Any: ...

        def extend_result(self, value: Any) -> Any: ...

    def list_billing_accounts(
        self,
        filter_query: str | None = None,
        unhump_accounts: bool = False,
    ) -> ExtendedList[ExtendedDict]:
        """List Google Cloud billing accounts.

        Args:
            filter_query: Optional filter query string.
            unhump_accounts: Convert keys to snake_case. Defaults to False.

        Returns:
            List of billing account dictionaries.
        """
        self.logger.info("Listing Google Cloud billing accounts")
        service = self.get_billing_service()

        accounts: list[dict[str, Any]] = []
        page_token = None

        while True:
            params: dict[str, Any] = {}
            if filter_query:
                params["filter"] = filter_query
            if page_token:
                params["pageToken"] = page_token

            response = service.billingAccounts().list(**params).execute()
            accounts.extend(response.get("billingAccounts", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        self.logger.info(f"Retrieved {len(accounts)} billing accounts")

        if unhump_accounts:
            accounts = [unhump_map(a) for a in accounts]

        return self.extend_result(accounts)

    def get_billing_account(self, billing_account_id: str) -> ExtendedDict | None:
        """Get a specific billing account.

        Args:
            billing_account_id: The billing account ID.

        Returns:
            Billing account dictionary or None if not found.
        """
        from googleapiclient.errors import HttpError

        service = self.get_billing_service()
        name = billing_account_id
        if not name.startswith("billingAccounts/"):
            name = f"billingAccounts/{billing_account_id}"

        try:
            return self.extend_result(service.billingAccounts().get(name=name).execute())
        except HttpError as e:
            if e.resp.status == 404:
                self.logger.warning(f"Billing account not found: {safe_google_ref(billing_account_id)}")
                return None
            raise

    def get_project_billing_info(self, project_id: str) -> ExtendedDict | None:
        """Get billing info for a project.

        Args:
            project_id: The project ID.

        Returns:
            Billing info dictionary or None if not set.
        """
        from googleapiclient.errors import HttpError

        service = self.get_billing_service()

        try:
            return self.extend_result(service.projects().getBillingInfo(name=f"projects/{project_id}").execute())
        except HttpError as e:
            if e.resp.status == 404:
                self.logger.warning(f"Project billing info not found: {safe_google_ref(project_id)}")
                return None
            raise

    def update_project_billing_info(
        self,
        project_id: str,
        billing_account_name: str,
    ) -> ExtendedDict:
        """Link a project to a billing account.

        Args:
            project_id: The project ID.
            billing_account_name: Billing account name (billingAccounts/ACCOUNT_ID).

        Returns:
            Updated billing info dictionary.
        """
        safe_project = safe_google_ref(project_id)
        safe_billing_account = safe_google_ref(billing_account_name)
        self.logger.info(f"Linking project {safe_project} to {safe_billing_account}")
        service = self.get_billing_service()

        if not billing_account_name.startswith("billingAccounts/"):
            billing_account_name = f"billingAccounts/{billing_account_name}"

        result = (
            service.projects()
            .updateBillingInfo(
                name=f"projects/{project_id}",
                body={"billingAccountName": billing_account_name},
            )
            .execute()
        )

        self.logger.info(f"Linked project {safe_project} to billing account")
        return self.extend_result(result)

    def disable_project_billing(self, project_id: str) -> ExtendedDict:
        """Disable billing for a project.

        Args:
            project_id: The project ID.

        Returns:
            Updated billing info dictionary.
        """
        safe_project = safe_google_ref(project_id)
        self.logger.info(f"Disabling billing for project {safe_project}")
        service = self.get_billing_service()

        result = (
            service.projects()
            .updateBillingInfo(
                name=f"projects/{project_id}",
                body={"billingAccountName": ""},
            )
            .execute()
        )

        self.logger.info(f"Disabled billing for project {safe_project}")
        return self.extend_result(result)

    def list_billing_account_projects(
        self,
        billing_account_id: str,
        unhump_projects: bool = False,
    ) -> ExtendedList[ExtendedDict]:
        """List projects linked to a billing account.

        Args:
            billing_account_id: The billing account ID.
            unhump_projects: Convert keys to snake_case. Defaults to False.

        Returns:
            List of project billing info dictionaries.
        """
        self.logger.info(f"Listing projects for billing account {safe_google_ref(billing_account_id)}")
        service = self.get_billing_service()

        name = billing_account_id
        if not name.startswith("billingAccounts/"):
            name = f"billingAccounts/{billing_account_id}"

        projects: list[dict[str, Any]] = []
        page_token = None

        while True:
            params: dict[str, Any] = {"name": name}
            if page_token:
                params["pageToken"] = page_token

            response = service.billingAccounts().projects().list(**params).execute()
            projects.extend(response.get("projectBillingInfo", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        self.logger.info(f"Retrieved {len(projects)} projects")

        if unhump_projects:
            projects = [unhump_map(p) for p in projects]

        return self.extend_result(projects)

    def get_billing_account_iam_policy(
        self,
        billing_account_id: str,
    ) -> ExtendedDict:
        """Get IAM policy for a billing account.

        Args:
            billing_account_id: The billing account ID.

        Returns:
            IAM policy dictionary.
        """
        service = self.get_billing_service()

        name = billing_account_id
        if not name.startswith("billingAccounts/"):
            name = f"billingAccounts/{billing_account_id}"

        return self.extend_result(service.billingAccounts().getIamPolicy(resource=name).execute())

    def set_billing_account_iam_policy(
        self,
        billing_account_id: str,
        policy: dict[str, Any],
    ) -> ExtendedDict:
        """Set IAM policy for a billing account.

        Args:
            billing_account_id: The billing account ID.
            policy: IAM policy dictionary.

        Returns:
            Updated IAM policy dictionary.
        """
        self.logger.info(f"Setting IAM policy on billing account {safe_google_ref(billing_account_id)}")
        service = self.get_billing_service()

        name = billing_account_id
        if not name.startswith("billingAccounts/"):
            name = f"billingAccounts/{billing_account_id}"

        return self.extend_result(
            service.billingAccounts()
            .setIamPolicy(
                resource=name,
                body={"policy": to_builtin(policy)},
            )
            .execute()
        )

    def get_bigquery_billing_dataset(
        self,
        project_id: str,
        dataset_id: str = "billing_export",
    ) -> ExtendedDict | None:
        """Get BigQuery billing export dataset configuration.

        Args:
            project_id: The project ID containing the billing dataset.
            dataset_id: The dataset ID. Defaults to 'billing_export'.

        Returns:
            Dataset configuration dict or None if not found.
        """
        from googleapiclient.errors import HttpError

        safe_dataset_ref = safe_google_text(f"{project_id}.{dataset_id}", project_id, dataset_id)
        self.logger.info(f"Getting BigQuery billing dataset {safe_dataset_ref}")

        # Build BigQuery client
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials_class = cast(Any, service_account.Credentials)
        credentials = credentials_class.from_service_account_info(
            self.service_account_info,
            scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
        )

        service = build("bigquery", "v2", credentials=credentials, cache_discovery=False)

        try:
            dataset = service.datasets().get(projectId=project_id, datasetId=dataset_id).execute()

            # Get tables in the dataset
            tables_response = service.tables().list(projectId=project_id, datasetId=dataset_id).execute()

            tables = tables_response.get("tables", [])
            billing_tables = [
                t for t in tables if "gcp_billing_export" in t.get("tableReference", {}).get("tableId", "")
            ]

            return self.extend_result(
                {
                    "dataset": dataset,
                    "tables": tables,
                    "billing_tables": billing_tables,
                    "location": dataset.get("location"),
                    "description": dataset.get("description"),
                }
            )

        except HttpError as e:
            if e.resp.status == 404:
                self.logger.warning(f"Billing dataset not found: {safe_dataset_ref}")
                return None
            raise

    def setup_billing_export(
        self,
        billing_account_id: str,
        project_id: str,
        dataset_id: str = "billing_export",
        location: str = "US",
    ) -> ExtendedDict:
        """Set up BigQuery billing export for a billing account.

        Creates the dataset if it doesn't exist and returns configuration.

        Args:
            billing_account_id: The billing account ID.
            project_id: Project to create the export dataset in.
            dataset_id: Dataset ID to use. Defaults to 'billing_export'.
            location: Dataset location. Defaults to 'US'.

        Returns:
            Configuration dict with dataset info.
        """
        from googleapiclient.errors import HttpError

        safe_billing_account = safe_google_ref(billing_account_id)
        safe_dataset = safe_google_ref(dataset_id)
        self.logger.info(f"Setting up billing export for {safe_billing_account}")

        # Build BigQuery client
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials_class = cast(Any, service_account.Credentials)
        credentials = credentials_class.from_service_account_info(
            self.service_account_info,
            scopes=["https://www.googleapis.com/auth/bigquery"],
        )

        service = build("bigquery", "v2", credentials=credentials, cache_discovery=False)

        # Check if dataset exists
        try:
            dataset = service.datasets().get(projectId=project_id, datasetId=dataset_id).execute()
            self.logger.info(f"Dataset {safe_dataset} already exists")
        except HttpError as e:
            if e.resp.status != 404:
                raise

            # Create dataset
            dataset_body = {
                "datasetReference": {
                    "projectId": project_id,
                    "datasetId": dataset_id,
                },
                "location": location,
                "description": f"Billing export for account {billing_account_id}",
                "labels": {
                    "billing_account": billing_account_id.replace("-", "_"),
                    "managed_by": "cloud_connectors",
                },
            }

            dataset = service.datasets().insert(projectId=project_id, body=dataset_body).execute()
            self.logger.info(f"Created billing export dataset: {safe_dataset}")

        return self.extend_result(
            {
                "billing_account_id": billing_account_id,
                "project_id": project_id,
                "dataset_id": dataset_id,
                "location": dataset.get("location"),
                "full_dataset_id": f"{project_id}.{dataset_id}",
            }
        )
