"""Google connector constants for cloud and Workspace workflows.

These constants provide default configurations for Google Cloud and Workspace
operations. Override these values with environment-specific configuration.
"""

from __future__ import annotations

import os


# Default domain - MUST be overridden via environment variable
DEFAULT_DOMAIN = os.getenv("GOOGLE_WORKSPACE_DOMAIN", "example.com")

# Broad OAuth scopes for mixed Workspace, Cloud, billing, and service discovery workflows.
DEFAULT_SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/apps.alerts",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/cloud-identity",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.activity",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/gmail.settings.sharing",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/admin.directory.user",
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
    "https://www.googleapis.com/auth/admin.directory.userschema",
    "https://www.googleapis.com/auth/admin.directory.group",
    "https://www.googleapis.com/auth/admin.directory.orgunit",
    "https://www.googleapis.com/auth/apps.groups.settings",
    "https://www.googleapis.com/auth/apps.licensing",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/cloud-billing",
    "https://www.googleapis.com/auth/bigquery",
    "https://www.googleapis.com/auth/iam",
    "https://www.googleapis.com/auth/compute",
    "https://www.googleapis.com/auth/cloudkms",
    "https://www.googleapis.com/auth/logging.admin",
    "https://www.googleapis.com/auth/monitoring",
    "https://www.googleapis.com/auth/sqlservice.admin",
    "https://www.googleapis.com/auth/devstorage.full_control",
    "https://www.googleapis.com/auth/pubsub",
    "https://www.googleapis.com/auth/service.management",
]

# GCP Security Project defaults - override via environment for your org
GCP_SECURITY_PROJECT = {
    "id": os.getenv("GCP_SECURITY_PROJECT_ID", "security-admin"),
    "name": "Security Administration",
    "resource_labels": {
        "managed-by": "terraform",
        "environment": "global",
        "team": "security",
    },
}

# KMS configuration defaults for infrastructure secret material.
GCP_KMS = {
    "keyring_name": "terraform-secrets",
    "key_name": "terraform-key",
    "key_rotation_period": "7776000s",  # 90 days
}

# Required IAM roles for organization-level operations
GCP_REQUIRED_ORGANIZATION_ROLES = [
    "roles/owner",
    "roles/resourcemanager.projectIamAdmin",
    "roles/serviceusage.serviceUsageAdmin",
]

# Required IAM roles for project-level operations
GCP_REQUIRED_ROLES = [
    *GCP_REQUIRED_ORGANIZATION_ROLES,
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/storage.admin",
]

# Required APIs for standard GCP operations
GCP_REQUIRED_APIS = [
    "bigquery.googleapis.com",
    "cloudbilling.googleapis.com",
    "cloudidentity.googleapis.com",
    "cloudassets.googleapis.com",
    "cloudkms.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "container.googleapis.com",
    "iam.googleapis.com",
    "orgpolicy.googleapis.com",
    "pubsub.googleapis.com",
    "serviceusage.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
]

# Default OUs for user filtering
DEFAULT_USER_OUS = ["/Users", "Users/2FANotEnforced", "/Contract"]

__all__ = [
    "DEFAULT_DOMAIN",
    "DEFAULT_SCOPES",
    "DEFAULT_USER_OUS",
    "GCP_KMS",
    "GCP_REQUIRED_APIS",
    "GCP_REQUIRED_ORGANIZATION_ROLES",
    "GCP_REQUIRED_ROLES",
    "GCP_SECURITY_PROJECT",
]
