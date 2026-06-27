#!/usr/bin/env python3
"""Example: Basic Google Cloud Connector usage.

This example demonstrates how to use the Google Cloud connector to interact
with Google Workspace and Cloud Platform.

Requirements:
    pip install cloud-connectors[google]

Environment Variables:
    GOOGLE_SERVICE_ACCOUNT: JSON service account credentials
    GOOGLE_DOMAIN: Google Workspace domain (for Workspace operations)
"""

from __future__ import annotations

import os
import sys

from cloud_connectors import ConnectorFabric


def main() -> int:
    """Demonstrate Google connector usage."""
    # Check for required environment variables
    if not os.getenv("GOOGLE_SERVICE_ACCOUNT"):
        print("Error: GOOGLE_SERVICE_ACCOUNT environment variable is required.")
        return 1

    fabric = ConnectorFabric()
    info = fabric.get_connector_info("google")
    if not info["available"]:
        print(f"Error: Google connector is unavailable. Install with: {info['install']}")
        if info["missing"]:
            print(f"Missing packages: {', '.join(info['missing'])}")
        return 1

    print("Creating Google connector...")
    connector = fabric.get_connector("google")
    print("Google connector created successfully.")

    # List projects
    print("\n--- Google Cloud Projects ---")
    try:
        projects = connector.list_projects()
        for project in projects[:5]:
            print(f"  Project: {project}")
        if len(projects) > 5:
            print(f"  ... and {len(projects) - 5} more projects")
    except Exception as e:
        print(f"  Could not list projects: {e}")

    # List workspace users (if domain configured)
    if os.getenv("GOOGLE_DOMAIN"):
        print("\n--- Workspace Users ---")
        try:
            users = connector.list_users()
            for user in users[:5]:
                email = user.get("primaryEmail", "Unknown")
                print(f"  User: {email}")
            if len(users) > 5:
                print(f"  ... and {len(users) - 5} more users")
        except Exception as e:
            print(f"  Could not list users: {e}")
    else:
        print("\nSkipping Workspace users (GOOGLE_DOMAIN not set).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
