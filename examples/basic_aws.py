#!/usr/bin/env python3
"""Example: Basic AWS Connector usage.

This example demonstrates how to use the AWS connector to interact with
AWS Organizations and S3.

Requirements:
    pip install cloud-connectors[aws]

Environment Variables:
    AWS_ACCESS_KEY_ID: AWS access key
    AWS_SECRET_ACCESS_KEY: AWS secret key
    AWS_DEFAULT_REGION: AWS region (optional, defaults to us-east-1)
"""

from __future__ import annotations

import os
import sys

from cloud_connectors import ConnectorFabric


def main() -> int:
    """Demonstrate AWS connector usage."""
    # Check for required environment variables
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        print("Error: AWS_ACCESS_KEY_ID environment variable is required.")
        return 1

    fabric = ConnectorFabric()
    info = fabric.get_connector_info("aws")
    if not info["available"]:
        print(f"Error: AWS connector is unavailable. Install with: {info['install']}")
        if info["missing"]:
            print(f"Missing packages: {', '.join(info['missing'])}")
        return 1

    print("Creating AWS connector...")
    connector = fabric.get_connector("aws")
    print("AWS connector created successfully.")

    # List S3 buckets
    print("\n--- S3 Buckets ---")
    try:
        buckets = connector.list_s3_buckets()
        for bucket_name, bucket in list(buckets.items())[:5]:  # Show first 5
            created = bucket.get("creation_date") or bucket.get("CreationDate")
            print(f"  Bucket: {bucket_name} ({created})")
        if len(buckets) > 5:
            print(f"  ... and {len(buckets) - 5} more buckets")
    except Exception as e:
        print(f"  Could not list buckets: {e}")

    # List organization accounts (if using Organizations)
    print("\n--- Organization Accounts ---")
    try:
        accounts = connector.get_accounts()
        for account_id, account in list(accounts.items())[:5]:
            name = account.get("name") or account.get("Name") or account_id
            print(f"  Account: {account_id} ({name})")
        if len(accounts) > 5:
            print(f"  ... and {len(accounts) - 5} more accounts")
    except Exception as e:
        print(f"  Could not list accounts: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
