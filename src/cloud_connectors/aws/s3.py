"""AWS S3 operations.

This module provides operations for working with S3 buckets and objects.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC
from typing import TYPE_CHECKING, Any, cast

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, to_builtin
from extended_data.io import wrap_raw_data_for_export
from extended_data.io.files import decode_file
from extended_data.primitives import unhump_map

from cloud_connectors.aws._diagnostics import safe_aws_ref, safe_aws_text


if TYPE_CHECKING:
    from boto3.resources.base import ServiceResource
    from botocore.exceptions import ClientError
else:
    try:
        from botocore.exceptions import ClientError
    except ImportError:

        class ClientError(Exception):
            """Fallback exception used until botocore is imported."""


def _safe_s3_uri(bucket: str, key: str | None = None) -> str:
    """Return a diagnostic-safe S3 URI."""
    uri = f"s3://{bucket}" if key is None else f"s3://{bucket}/{key}"
    return safe_aws_text(uri, bucket, key)


class AWSS3Mixin:
    """Mixin providing AWS S3 operations.

    This mixin requires the base AWSConnector class to provide:
    - get_aws_client()
    - get_aws_resource()
    - logger
    - execution_role_arn
    """

    if TYPE_CHECKING:
        logger: Any
        execution_role_arn: str | None

        def get_aws_client(
            self,
            client_name: str,
            execution_role_arn: str | None = None,
            role_session_name: str | None = None,
            config: Any | None = None,
            **client_args: Any,
        ) -> Any: ...

        def get_aws_resource(
            self,
            service_name: str,
            execution_role_arn: str | None = None,
            role_session_name: str | None = None,
            config: Any | None = None,
            **resource_args: Any,
        ) -> ServiceResource: ...

        def extend_result(self, value: Any) -> Any: ...

    def list_s3_buckets(
        self,
        unhump_buckets: bool = True,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """List all S3 buckets.

        Args:
            unhump_buckets: Convert keys to snake_case. Defaults to True.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Dictionary mapping bucket names to bucket data.
        """
        self.logger.info("Listing S3 buckets")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        s3 = self.get_aws_client(
            client_name="s3",
            execution_role_arn=role_arn,
        )

        response = s3.list_buckets()
        buckets: dict[str, dict[str, Any]] = {}

        for bucket in response.get("Buckets", []):
            name = bucket["Name"]
            buckets[name] = bucket

        if unhump_buckets:
            buckets = {k: unhump_map(v) for k, v in buckets.items()}

        self.logger.info(f"Retrieved {len(buckets)} buckets")
        return self.extend_result(buckets)

    def get_bucket_location(
        self,
        bucket_name: str,
        execution_role_arn: str | None = None,
    ) -> ExtendedString:
        """Get the region of an S3 bucket.

        Args:
            bucket_name: Name of the S3 bucket.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            The AWS region where the bucket is located.
        """
        safe_bucket = safe_aws_ref(bucket_name)
        self.logger.debug(f"Getting location for bucket: {safe_bucket}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        s3 = self.get_aws_client(
            client_name="s3",
            execution_role_arn=role_arn,
        )

        response = s3.get_bucket_location(Bucket=bucket_name)
        return self.extend_result(response.get("LocationConstraint") or "us-east-1")

    def get_object(
        self,
        bucket: str,
        key: str,
        decode: bool = True,
        execution_role_arn: str | None = None,
    ) -> ExtendedString | bytes | None:
        """Get an object from S3.

        Args:
            bucket: S3 bucket name.
            key: S3 object key.
            decode: Decode bytes to string. Defaults to True.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            The object contents, or None if not found.
        """
        safe_uri = _safe_s3_uri(bucket, key)
        self.logger.debug(f"Getting S3 object: {safe_uri}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        s3 = self.get_aws_client(
            client_name="s3",
            execution_role_arn=role_arn,
        )

        try:
            response = s3.get_object(Bucket=bucket, Key=key)
            body = response["Body"].read()

            if decode:
                return self.extend_result(body.decode("utf-8"))
            return body
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                self.logger.warning(f"S3 object not found: {safe_uri}")
                return None
            raise

    def get_json_object(
        self,
        bucket: str,
        key: str,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict | ExtendedList[Any] | None:
        """Get a JSON object from S3.

        Args:
            bucket: S3 bucket name.
            key: S3 object key.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            The parsed JSON object, or None if not found.
        """
        content = self.get_object(
            bucket=bucket,
            key=key,
            decode=False,
            execution_role_arn=execution_role_arn,
        )

        if content is None:
            return None

        file_data = str(content) if isinstance(content, ExtendedString) else content
        return cast(ExtendedDict | ExtendedList[Any], decode_file(file_data, suffix="json", as_extended=True))

    def put_object(
        self,
        bucket: str,
        key: str,
        body: str | bytes,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Put an object to S3.

        Args:
            bucket: S3 bucket name.
            key: S3 object key.
            body: Object content.
            content_type: Content-Type header. Auto-detected if not provided.
            metadata: Optional metadata to attach to object.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            The S3 put_object response.
        """
        safe_uri = _safe_s3_uri(bucket, key)
        self.logger.debug(f"Putting S3 object: {safe_uri}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        s3 = self.get_aws_client(
            client_name="s3",
            execution_role_arn=role_arn,
        )

        if isinstance(body, str):
            body = body.encode("utf-8")

        put_args: dict[str, Any] = {
            "Bucket": bucket,
            "Key": key,
            "Body": body,
        }

        if content_type:
            put_args["ContentType"] = content_type
        elif key.endswith((".json", ".tf.json")):
            put_args["ContentType"] = "application/json"
        elif key.endswith((".yaml", ".yml")):
            put_args["ContentType"] = "text/yaml"

        if metadata:
            put_args["Metadata"] = {str(key): str(value) for key, value in metadata.items()}

        response = s3.put_object(**put_args)
        self.logger.debug(f"Put object to {safe_uri}")
        return self.extend_result(response)

    def put_json_object(
        self,
        bucket: str,
        key: str,
        data: Mapping[str, Any] | Sequence[Any],
        indent: int = 2,
        metadata: Mapping[str, str] | None = None,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Put a JSON object to S3.

        Args:
            bucket: S3 bucket name.
            key: S3 object key.
            data: Data to serialize to JSON.
            indent: JSON indentation. Defaults to 2.
            metadata: Optional metadata to attach to object.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            The S3 put_object response.
        """
        body = wrap_raw_data_for_export(data, allow_encoding="json", indent_2=bool(indent))
        return self.put_object(
            bucket=bucket,
            key=key,
            body=body,
            content_type="application/json",
            metadata=metadata,
            execution_role_arn=execution_role_arn,
        )

    def delete_object(
        self,
        bucket: str,
        key: str,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Delete an object from S3.

        Args:
            bucket: S3 bucket name.
            key: S3 object key.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            The S3 delete_object response.
        """
        safe_uri = _safe_s3_uri(bucket, key)
        self.logger.debug(f"Deleting S3 object: {safe_uri}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        s3 = self.get_aws_client(
            client_name="s3",
            execution_role_arn=role_arn,
        )

        response = s3.delete_object(Bucket=bucket, Key=key)
        self.logger.debug(f"Deleted object {safe_uri}")
        return self.extend_result(response)

    def list_objects(
        self,
        bucket: str,
        prefix: str | None = None,
        delimiter: str | None = None,
        max_keys: int | None = None,
        unhump_objects: bool = True,
        execution_role_arn: str | None = None,
    ) -> ExtendedList[ExtendedDict]:
        """List objects in an S3 bucket.

        Args:
            bucket: S3 bucket name.
            prefix: Key prefix to filter by.
            delimiter: Delimiter for hierarchical listing.
            max_keys: Maximum number of keys to return.
            unhump_objects: Convert keys to snake_case. Defaults to True.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            List of object metadata dictionaries.
        """
        safe_uri = _safe_s3_uri(bucket, prefix or None)
        self.logger.debug(f"Listing objects in {safe_uri}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        s3 = self.get_aws_client(
            client_name="s3",
            execution_role_arn=role_arn,
        )

        objects: list[dict[str, Any]] = []
        paginator = s3.get_paginator("list_objects_v2")

        paginate_args: dict[str, Any] = {"Bucket": bucket}
        if prefix:
            paginate_args["Prefix"] = prefix
        if delimiter:
            paginate_args["Delimiter"] = delimiter
        if max_keys:
            paginate_args["MaxKeys"] = max_keys

        for page in paginator.paginate(**paginate_args):
            for obj in page.get("Contents", []):
                objects.append(obj)

            if max_keys and len(objects) >= max_keys:
                objects = objects[:max_keys]
                break

        if unhump_objects:
            objects = [unhump_map(o) for o in objects]

        self.logger.debug(f"Found {len(objects)} objects")
        return self.extend_result(objects)

    def copy_object(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Copy an object within S3.

        Args:
            source_bucket: Source bucket name.
            source_key: Source object key.
            dest_bucket: Destination bucket name.
            dest_key: Destination object key.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            The S3 copy_object response.
        """
        safe_source_uri = _safe_s3_uri(source_bucket, source_key)
        safe_dest_uri = _safe_s3_uri(dest_bucket, dest_key)
        self.logger.debug(f"Copying {safe_source_uri} to {safe_dest_uri}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        s3 = self.get_aws_client(
            client_name="s3",
            execution_role_arn=role_arn,
        )

        response = s3.copy_object(
            Bucket=dest_bucket,
            Key=dest_key,
            CopySource={"Bucket": source_bucket, "Key": source_key},
        )
        self.logger.debug(f"Copied object to {safe_dest_uri}")
        return self.extend_result(response)

    # =========================================================================
    # Bucket Features and Configuration
    # =========================================================================

    def get_bucket_features(
        self,
        bucket_name: str,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Get bucket configuration features (logging, versioning, lifecycle, policy).

        Args:
            bucket_name: S3 bucket name.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Dictionary with logging, versioning, lifecycle_rules, and policy.
        """
        safe_bucket = safe_aws_ref(bucket_name)
        self.logger.debug(f"Getting features for bucket: {safe_bucket}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        s3_resource: ServiceResource = self.get_aws_resource(
            service_name="s3",
            execution_role_arn=role_arn,
        )

        bucket = s3_resource.Bucket(bucket_name)

        # Check if bucket exists
        if not bucket.creation_date:
            self.logger.warning(f"Bucket does not exist: {safe_bucket}")
            return self.extend_result({})

        features: dict[str, Any] = {}

        # Logging
        try:
            logging_config = bucket.Logging()
            features["logging"] = logging_config.logging_enabled
        except ClientError:
            self.logger.debug("No logging configuration for bucket")
            features["logging"] = None

        # Versioning
        try:
            versioning = bucket.Versioning()
            features["versioning"] = versioning.status
        except ClientError:
            self.logger.debug("No versioning configuration for bucket")
            features["versioning"] = None

        # Lifecycle rules
        try:
            lifecycle = bucket.LifecycleConfiguration()
            features["lifecycle_rules"] = lifecycle.rules
        except ClientError:
            self.logger.debug("No lifecycle configuration for bucket")
            features["lifecycle_rules"] = None

        # Bucket policy
        try:
            policy = bucket.Policy()
            features["policy"] = policy.policy
        except ClientError:
            self.logger.debug("No policy for bucket")
            features["policy"] = None

        return self.extend_result(features)

    def find_buckets_by_name(
        self,
        name_contains: str,
        include_features: bool = False,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Find S3 buckets with names containing a string.

        Args:
            name_contains: Substring to search for in bucket names.
            include_features: Include bucket features for each match. Defaults to False.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Dictionary mapping bucket names to bucket data/features.
        """
        safe_search = safe_aws_ref(name_contains)
        self.logger.info(f"Finding S3 buckets containing: {safe_search}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        s3_resource: ServiceResource = self.get_aws_resource(
            service_name="s3",
            execution_role_arn=role_arn,
        )

        buckets: dict[str, dict[str, Any]] = {}

        for bucket in s3_resource.buckets.all():
            if name_contains in bucket.name:
                self.logger.debug(f"Found matching bucket: {safe_aws_ref(bucket.name)}")

                if include_features:
                    buckets[bucket.name] = to_builtin(
                        self.get_bucket_features(
                            bucket_name=bucket.name,
                            execution_role_arn=role_arn,
                        )
                    )
                else:
                    buckets[bucket.name] = {
                        "name": bucket.name,
                        "creation_date": str(bucket.creation_date) if bucket.creation_date else None,
                    }

        self.logger.info(f"Found {len(buckets)} matching buckets")
        return self.extend_result(buckets)

    def create_bucket(
        self,
        bucket_name: str,
        region: str | None = None,
        acl: str = "private",
        enable_versioning: bool = False,
        tags: Mapping[str, str] | None = None,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Create an S3 bucket.

        Args:
            bucket_name: Bucket name (must be globally unique).
            region: AWS region. Uses default if not specified.
            acl: Bucket ACL. Defaults to 'private'.
            enable_versioning: Enable versioning. Defaults to False.
            tags: Optional tags to apply.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Create bucket response.
        """
        safe_bucket = safe_aws_ref(bucket_name)
        self.logger.info(f"Creating S3 bucket: {safe_bucket}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        s3 = self.get_aws_client(
            client_name="s3",
            execution_role_arn=role_arn,
        )

        create_args: dict[str, Any] = {
            "Bucket": bucket_name,
            "ACL": acl,
        }

        # LocationConstraint required for non-us-east-1
        if region and region != "us-east-1":
            create_args["CreateBucketConfiguration"] = {
                "LocationConstraint": region,
            }

        result = s3.create_bucket(**create_args)
        self.logger.info(f"Created bucket: {safe_bucket}")

        # Enable versioning if requested
        if enable_versioning:
            s3.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={"Status": "Enabled"},
            )
            self.logger.info(f"Enabled versioning for bucket: {safe_bucket}")

        # Apply tags if provided
        if tags:
            tag_set = [{"Key": str(k), "Value": str(v)} for k, v in tags.items()]
            s3.put_bucket_tagging(
                Bucket=bucket_name,
                Tagging={"TagSet": tag_set},
            )
            self.logger.info(f"Applied {len(tags)} tags to bucket: {safe_bucket}")

        return self.extend_result(result)

    def delete_bucket(
        self,
        bucket_name: str,
        force: bool = False,
        execution_role_arn: str | None = None,
    ) -> None:
        """Delete an S3 bucket.

        Args:
            bucket_name: Bucket name.
            force: Delete all objects first. Defaults to False.
            execution_role_arn: ARN of role to assume for cross-account access.

        Raises:
            ClientError: If bucket not empty and force=False.
        """
        safe_bucket = safe_aws_ref(bucket_name)
        self.logger.info(f"Deleting S3 bucket: {safe_bucket}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if force:
            s3_resource: ServiceResource = self.get_aws_resource(
                service_name="s3",
                execution_role_arn=role_arn,
            )
            bucket = s3_resource.Bucket(bucket_name)

            # Delete all objects
            self.logger.info(f"Deleting all objects in bucket: {safe_bucket}")
            bucket.objects.all().delete()

            # Delete all versions
            self.logger.info(f"Deleting all versions in bucket: {safe_bucket}")
            bucket.object_versions.all().delete()

        s3 = self.get_aws_client(
            client_name="s3",
            execution_role_arn=role_arn,
        )

        s3.delete_bucket(Bucket=bucket_name)
        self.logger.info(f"Deleted bucket: {safe_bucket}")

    def get_bucket_tags(
        self,
        bucket_name: str,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Get tags for an S3 bucket.

        Args:
            bucket_name: Bucket name.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Dictionary of tag key-value pairs.
        """
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        s3 = self.get_aws_client(
            client_name="s3",
            execution_role_arn=role_arn,
        )

        try:
            response = s3.get_bucket_tagging(Bucket=bucket_name)
            return self.extend_result({tag["Key"]: tag["Value"] for tag in response.get("TagSet", [])})
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchTagSet":
                return self.extend_result({})
            raise

    def set_bucket_tags(
        self,
        bucket_name: str,
        tags: Mapping[str, str],
        execution_role_arn: str | None = None,
    ) -> None:
        """Set tags for an S3 bucket.

        Args:
            bucket_name: Bucket name.
            tags: Dictionary of tag key-value pairs.
            execution_role_arn: ARN of role to assume for cross-account access.
        """
        safe_bucket = safe_aws_ref(bucket_name)
        self.logger.info(f"Setting {len(tags)} tags on bucket: {safe_bucket}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        s3 = self.get_aws_client(
            client_name="s3",
            execution_role_arn=role_arn,
        )

        tag_set = [{"Key": str(k), "Value": str(v)} for k, v in tags.items()]
        s3.put_bucket_tagging(
            Bucket=bucket_name,
            Tagging={"TagSet": tag_set},
        )
        self.logger.info(f"Set tags on bucket: {safe_bucket}")

    def get_bucket_sizes(
        self,
        bucket_names: Sequence[str] | None = None,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Get sizes of S3 buckets using CloudWatch metrics.

        Args:
            bucket_names: Specific buckets to check. All buckets if None.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Dictionary mapping bucket names to size info (bytes, object_count).
        """
        from datetime import datetime, timedelta

        self.logger.info("Getting S3 bucket sizes from CloudWatch")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        cloudwatch = self.get_aws_client(
            client_name="cloudwatch",
            execution_role_arn=role_arn,
        )

        if bucket_names is None:
            buckets = self.list_s3_buckets(
                unhump_buckets=False,
                execution_role_arn=role_arn,
            )
            bucket_names = list(buckets.keys())

        end_time = datetime.now(tz=UTC)
        start_time = end_time - timedelta(days=2)

        bucket_sizes: dict[str, dict[str, Any]] = {}

        for bucket_name in bucket_names:
            safe_bucket = safe_aws_ref(bucket_name)
            size_bytes = 0
            object_count = 0

            # Get bucket size
            try:
                size_response = cloudwatch.get_metric_statistics(
                    Namespace="AWS/S3",
                    MetricName="BucketSizeBytes",
                    Dimensions=[
                        {"Name": "BucketName", "Value": bucket_name},
                        {"Name": "StorageType", "Value": "StandardStorage"},
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=["Average"],
                )
                if size_response.get("Datapoints"):
                    size_bytes = int(max(size_response["Datapoints"], key=lambda x: x["Timestamp"])["Average"])
            except Exception as e:
                self.logger.debug(f"Could not get size for {safe_bucket}: {safe_aws_text(e, bucket_name)}")

            # Get object count
            try:
                count_response = cloudwatch.get_metric_statistics(
                    Namespace="AWS/S3",
                    MetricName="NumberOfObjects",
                    Dimensions=[
                        {"Name": "BucketName", "Value": bucket_name},
                        {"Name": "StorageType", "Value": "AllStorageTypes"},
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=["Average"],
                )
                if count_response.get("Datapoints"):
                    object_count = int(max(count_response["Datapoints"], key=lambda x: x["Timestamp"])["Average"])
            except Exception as e:
                self.logger.debug(f"Could not get count for {safe_bucket}: {safe_aws_text(e, bucket_name)}")

            bucket_sizes[bucket_name] = {
                "size_bytes": size_bytes,
                "size_gb": round(size_bytes / (1024**3), 2),
                "object_count": object_count,
            }

        self.logger.info(f"Retrieved sizes for {len(bucket_sizes)} buckets")
        return self.extend_result(bucket_sizes)
