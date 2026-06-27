# ruff: noqa: I001
"""Tests for AWS S3 operations."""

from __future__ import annotations

import json

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("boto3")
pytest.importorskip("botocore")

from botocore.exceptions import ClientError

from vendor_fabric.aws import AWSConnector
from vendor_fabric.aws import s3 as s3_module
from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data


def _logged_text(logger: MagicMock) -> str:
    """Return concatenated mock logger messages."""
    return "\n".join(str(arg) for call in logger.method_calls for arg in call.args)


@pytest.fixture
def aws_connector():
    """Create AWS connector with mocked clients."""
    with patch("vendor_fabric.aws.boto3"):
        connector = AWSConnector()
        connector.logger = MagicMock()
        return connector


class TestS3BucketOperations:
    """Tests for S3 bucket operations."""

    def test_list_s3_buckets(self, aws_connector):
        """Test listing S3 buckets."""
        mock_s3 = MagicMock()
        mock_s3.list_buckets.return_value = {
            "Buckets": [
                {"Name": "bucket1", "CreationDate": datetime(2023, 1, 1)},
                {"Name": "bucket2", "CreationDate": datetime(2023, 2, 1)},
            ]
        }
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.list_s3_buckets(unhump_buckets=False)

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["bucket1"], ExtendedDict)
        assert len(result) == 2
        assert "bucket1" in result
        assert "bucket2" in result
        aws_connector.get_aws_client.assert_called_once_with(client_name="s3", execution_role_arn=None)

    def test_list_s3_buckets_with_unhump(self, aws_connector):
        """Test listing S3 buckets with unhump."""
        mock_s3 = MagicMock()
        mock_s3.list_buckets.return_value = {"Buckets": [{"Name": "bucket1", "CreationDate": datetime(2023, 1, 1)}]}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.list_s3_buckets(unhump_buckets=True)

        assert len(result) == 1
        assert "bucket1" in result
        # unhump_map transforms CamelCase keys to snake_case
        # If unhump was applied, we should have snake_case keys
        # The actual transformation happens in extended_data.primitives.unhump_map

    def test_get_bucket_location(self, aws_connector):
        """Test getting bucket location."""
        mock_s3 = MagicMock()
        mock_s3.get_bucket_location.return_value = {"LocationConstraint": "us-west-2"}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.get_bucket_location("my-bucket")

        assert isinstance(result, ExtendedString)
        assert result == "us-west-2"
        mock_s3.get_bucket_location.assert_called_once_with(Bucket="my-bucket")

    def test_get_bucket_location_us_east_1(self, aws_connector):
        """Test getting bucket location for us-east-1."""
        mock_s3 = MagicMock()
        mock_s3.get_bucket_location.return_value = {"LocationConstraint": None}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.get_bucket_location("my-bucket")

        assert isinstance(result, ExtendedString)
        assert result == "us-east-1"

    def test_get_bucket_tags(self, aws_connector):
        """Test getting bucket tags."""
        mock_s3 = MagicMock()
        mock_s3.get_bucket_tagging.return_value = {
            "TagSet": [
                {"Key": "Environment", "Value": "dev"},
                {"Key": "Owner", "Value": "team"},
            ]
        }
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.get_bucket_tags("my-bucket")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["Environment"], ExtendedString)
        assert result == {"Environment": "dev", "Owner": "team"}

    def test_get_bucket_tags_no_tags(self, aws_connector):
        """Test getting bucket tags when none exist."""
        mock_s3 = MagicMock()
        error = ClientError({"Error": {"Code": "NoSuchTagSet"}}, "GetBucketTagging")
        mock_s3.get_bucket_tagging.side_effect = error
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.get_bucket_tags("my-bucket")

        assert isinstance(result, ExtendedDict)
        assert result == {}

    def test_get_bucket_tags_other_error(self, aws_connector):
        """Test getting bucket tags with other error."""
        mock_s3 = MagicMock()
        error = ClientError({"Error": {"Code": "AccessDenied"}}, "GetBucketTagging")
        mock_s3.get_bucket_tagging.side_effect = error
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        with pytest.raises(ClientError):
            aws_connector.get_bucket_tags("my-bucket")

    def test_set_bucket_tags(self, aws_connector):
        """Test setting bucket tags."""
        mock_s3 = MagicMock()
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        aws_connector.set_bucket_tags("my-bucket", {"Env": "prod", "App": "web"})

        mock_s3.put_bucket_tagging.assert_called_once()
        call_args = mock_s3.put_bucket_tagging.call_args
        assert call_args[1]["Bucket"] == "my-bucket"
        tag_set = call_args[1]["Tagging"]["TagSet"]
        assert len(tag_set) == 2
        assert {"Key": "Env", "Value": "prod"} in tag_set
        assert {"Key": "App", "Value": "web"} in tag_set


class TestS3ObjectOperations:
    """Tests for S3 object operations."""

    def test_get_object_success(self, aws_connector):
        """Test getting an object from S3."""
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"test content"
        mock_s3.get_object.return_value = {"Body": mock_body}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.get_object("bucket", "key.txt", decode=True)

        assert isinstance(result, ExtendedString)
        assert result == "test content"
        mock_s3.get_object.assert_called_once_with(Bucket="bucket", Key="key.txt")

    def test_get_object_no_decode(self, aws_connector):
        """Test getting an object without decoding."""
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"test content"
        mock_s3.get_object.return_value = {"Body": mock_body}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.get_object("bucket", "key.txt", decode=False)

        assert result == b"test content"

    def test_get_object_not_found(self, aws_connector):
        """Test getting a non-existent object."""
        mock_s3 = MagicMock()
        error = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        mock_s3.get_object.side_effect = error
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.get_object("bucket", "missing.txt")

        assert result is None

    def test_get_object_not_found_logs_redact_bucket_and_key(self, aws_connector):
        """Missing object diagnostics should not expose S3 resource identifiers."""
        mock_s3 = MagicMock()
        error = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        mock_s3.get_object.side_effect = error
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.get_object("prod-secrets-bucket", "customers/acme/private.json")

        assert result is None
        mock_s3.get_object.assert_called_once_with(Bucket="prod-secrets-bucket", Key="customers/acme/private.json")
        logs = _logged_text(aws_connector.logger)
        assert "[REDACTED]" in logs
        assert "prod-secrets-bucket" not in logs
        assert "customers/acme/private.json" not in logs

    def test_get_object_other_error(self, aws_connector):
        """Test getting an object with other error."""
        mock_s3 = MagicMock()
        error = ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")
        mock_s3.get_object.side_effect = error
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        with pytest.raises(ClientError):
            aws_connector.get_object("bucket", "key.txt")

    def test_get_json_object(self, aws_connector):
        """Test getting a JSON object."""
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        test_data = {"key": "value", "number": 123}
        mock_body.read.return_value = json.dumps(test_data).encode("utf-8")
        mock_s3.get_object.return_value = {"Body": mock_body}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.get_json_object("bucket", "data.json")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["key"], ExtendedString)
        assert result == test_data

    def test_get_json_object_decodes_through_data_boundary(self, aws_connector):
        """S3 JSON reads should use the shared file decoder, not local json.loads."""
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b'{"items":[{"name":"one"}]}'
        mock_s3.get_object.return_value = {"Body": mock_body}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        with patch("vendor_fabric.aws.s3.decode_file", wraps=s3_module.decode_file) as mock_decode_file:
            result = aws_connector.get_json_object("bucket", "data.json")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["items"], ExtendedList)
        assert isinstance(result["items"][0], ExtendedDict)
        assert isinstance(result["items"][0]["name"], ExtendedString)
        mock_decode_file.assert_called_once_with(b'{"items":[{"name":"one"}]}', suffix="json", as_extended=True)

    def test_get_json_object_not_found(self, aws_connector):
        """Test getting a non-existent JSON object."""
        mock_s3 = MagicMock()
        error = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        mock_s3.get_object.side_effect = error
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.get_json_object("bucket", "missing.json")

        assert result is None

    def test_put_object_string(self, aws_connector):
        """Test putting a string object."""
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {"ETag": "abc123"}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.put_object("bucket", "key.txt", "test content")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["ETag"], ExtendedString)
        assert result["ETag"] == "abc123"
        call_args = mock_s3.put_object.call_args[1]
        assert call_args["Bucket"] == "bucket"
        assert call_args["Key"] == "key.txt"
        assert call_args["Body"] == b"test content"

    def test_put_object_bytes(self, aws_connector):
        """Test putting a bytes object."""
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {"ETag": "abc123"}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        aws_connector.put_object("bucket", "key.bin", b"binary data")

        call_args = mock_s3.put_object.call_args[1]
        assert call_args["Body"] == b"binary data"

    def test_put_object_with_content_type(self, aws_connector):
        """Test putting object with content type."""
        mock_s3 = MagicMock()
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        aws_connector.put_object("bucket", "key.txt", "content", content_type="text/plain")

        call_args = mock_s3.put_object.call_args[1]
        assert call_args["ContentType"] == "text/plain"

    def test_put_object_auto_json_content_type(self, aws_connector):
        """Test putting object with auto-detected JSON content type."""
        mock_s3 = MagicMock()
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        aws_connector.put_object("bucket", "data.json", '{"key": "value"}')

        call_args = mock_s3.put_object.call_args[1]
        assert call_args["ContentType"] == "application/json"

    def test_put_object_auto_yaml_content_type(self, aws_connector):
        """Test putting object with auto-detected YAML content type."""
        mock_s3 = MagicMock()
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        aws_connector.put_object("bucket", "config.yaml", "key: value")

        call_args = mock_s3.put_object.call_args[1]
        assert call_args["ContentType"] == "text/yaml"

    def test_put_object_with_metadata(self, aws_connector):
        """Test putting object with metadata."""
        mock_s3 = MagicMock()
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        metadata = {"user": "admin", "version": "1.0"}
        aws_connector.put_object("bucket", "key.txt", "content", metadata=metadata)

        call_args = mock_s3.put_object.call_args[1]
        assert call_args["Metadata"] == metadata

    def test_put_json_object(self, aws_connector):
        """Test putting a JSON object."""
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {"ETag": "abc123"}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        data = extend_data({"key": "value", "number": 123})
        with patch(
            "vendor_fabric.aws.s3.wrap_raw_data_for_export",
            wraps=s3_module.wrap_raw_data_for_export,
        ) as mock_wrap_for_export:
            result = aws_connector.put_json_object("bucket", "data.json", data)

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["ETag"], ExtendedString)
        assert result["ETag"] == "abc123"
        call_args = mock_s3.put_object.call_args[1]
        assert call_args["ContentType"] == "application/json"
        # Verify JSON was serialized
        body_str = call_args["Body"].decode("utf-8")
        assert json.loads(body_str) == data
        mock_wrap_for_export.assert_called_once_with(data, allow_encoding="json", indent_2=True)

    def test_delete_object(self, aws_connector):
        """Test deleting an object."""
        mock_s3 = MagicMock()
        mock_s3.delete_object.return_value = {"DeleteMarker": True}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.delete_object("bucket", "key.txt")

        assert isinstance(result, ExtendedDict)
        assert result["DeleteMarker"] is True
        mock_s3.delete_object.assert_called_once_with(Bucket="bucket", Key="key.txt")

    def test_list_objects(self, aws_connector):
        """Test listing objects in a bucket."""
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "file1.txt", "Size": 100},
                    {"Key": "file2.txt", "Size": 200},
                ]
            },
            {"Contents": [{"Key": "file3.txt", "Size": 300}]},
        ]
        mock_s3.get_paginator.return_value = mock_paginator
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.list_objects("bucket", unhump_objects=False)

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["Key"], ExtendedString)
        assert len(result) == 3
        assert result[0]["Key"] == "file1.txt"
        assert result[2]["Key"] == "file3.txt"

    def test_list_objects_with_prefix(self, aws_connector):
        """Test listing objects with prefix."""
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"Contents": [{"Key": "logs/app.log", "Size": 100}]}]
        mock_s3.get_paginator.return_value = mock_paginator
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.list_objects("bucket", prefix="logs/", unhump_objects=False)

        call_args = mock_paginator.paginate.call_args[1]
        assert call_args["Prefix"] == "logs/"
        assert len(result) == 1

    def test_list_objects_with_max_keys(self, aws_connector):
        """Test listing objects with max keys limit."""
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"Contents": [{"Key": f"file{i}.txt", "Size": 100} for i in range(10)]}]
        mock_s3.get_paginator.return_value = mock_paginator
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.list_objects("bucket", max_keys=5, unhump_objects=False)

        assert len(result) == 5

    def test_copy_object(self, aws_connector):
        """Test copying an object."""
        mock_s3 = MagicMock()
        mock_s3.copy_object.return_value = {"CopyObjectResult": {}}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.copy_object("src-bucket", "src.txt", "dst-bucket", "dst.txt")

        assert isinstance(result, ExtendedDict)
        assert "CopyObjectResult" in result
        mock_s3.copy_object.assert_called_once_with(
            Bucket="dst-bucket",
            Key="dst.txt",
            CopySource={"Bucket": "src-bucket", "Key": "src.txt"},
        )


class TestS3BucketFeatures:
    """Tests for S3 bucket features."""

    def test_get_bucket_features(self, aws_connector):
        """Test getting bucket features."""
        mock_bucket = MagicMock()
        mock_bucket.creation_date = datetime(2023, 1, 1)

        # Mock logging
        mock_logging = MagicMock()
        mock_logging.logging_enabled = {"TargetBucket": "logs"}
        mock_bucket.Logging.return_value = mock_logging

        # Mock versioning
        mock_versioning = MagicMock()
        mock_versioning.status = "Enabled"
        mock_bucket.Versioning.return_value = mock_versioning

        # Mock lifecycle
        mock_lifecycle = MagicMock()
        mock_lifecycle.rules = [{"Id": "rule1"}]
        mock_bucket.LifecycleConfiguration.return_value = mock_lifecycle

        # Mock policy
        mock_policy = MagicMock()
        mock_policy.policy = '{"Version": "2012-10-17"}'
        mock_bucket.Policy.return_value = mock_policy

        mock_resource = MagicMock()
        mock_resource.Bucket.return_value = mock_bucket
        aws_connector.get_aws_resource = MagicMock(return_value=mock_resource)

        result = aws_connector.get_bucket_features("my-bucket")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["logging"], ExtendedDict)
        assert isinstance(result["lifecycle_rules"], ExtendedList)
        assert result["logging"] == {"TargetBucket": "logs"}
        assert result["versioning"] == "Enabled"
        assert result["lifecycle_rules"] == [{"Id": "rule1"}]
        assert result["policy"] == '{"Version": "2012-10-17"}'

    def test_get_bucket_features_no_bucket(self, aws_connector):
        """Test getting features for non-existent bucket."""
        mock_bucket = MagicMock()
        mock_bucket.creation_date = None

        mock_resource = MagicMock()
        mock_resource.Bucket.return_value = mock_bucket
        aws_connector.get_aws_resource = MagicMock(return_value=mock_resource)

        result = aws_connector.get_bucket_features("missing-bucket")

        assert isinstance(result, ExtendedDict)
        assert result == {}

    def test_get_bucket_features_errors(self, aws_connector):
        """Test getting bucket features with errors."""
        mock_bucket = MagicMock()
        mock_bucket.creation_date = datetime(2023, 1, 1)

        # All features raise errors
        error = ClientError({"Error": {"Code": "NoSuchConfiguration"}}, "GetBucketLogging")
        mock_bucket.Logging.side_effect = error
        mock_bucket.Versioning.side_effect = error
        mock_bucket.LifecycleConfiguration.side_effect = error
        mock_bucket.Policy.side_effect = error

        mock_resource = MagicMock()
        mock_resource.Bucket.return_value = mock_bucket
        aws_connector.get_aws_resource = MagicMock(return_value=mock_resource)

        result = aws_connector.get_bucket_features("my-bucket")

        assert result["logging"] is None
        assert result["versioning"] is None
        assert result["lifecycle_rules"] is None
        assert result["policy"] is None

    def test_find_buckets_by_name(self, aws_connector):
        """Test finding buckets by name."""
        mock_bucket1 = MagicMock()
        mock_bucket1.name = "prod-app-bucket"
        mock_bucket1.creation_date = datetime(2023, 1, 1)

        mock_bucket2 = MagicMock()
        mock_bucket2.name = "dev-app-bucket"
        mock_bucket2.creation_date = datetime(2023, 2, 1)

        mock_bucket3 = MagicMock()
        mock_bucket3.name = "other-bucket"
        mock_bucket3.creation_date = datetime(2023, 3, 1)

        mock_resource = MagicMock()
        mock_resource.buckets.all.return_value = [mock_bucket1, mock_bucket2, mock_bucket3]
        aws_connector.get_aws_resource = MagicMock(return_value=mock_resource)

        result = aws_connector.find_buckets_by_name("app")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["prod-app-bucket"], ExtendedDict)
        assert len(result) == 2
        assert "prod-app-bucket" in result
        assert "dev-app-bucket" in result
        assert "other-bucket" not in result

    def test_create_bucket_simple(self, aws_connector):
        """Test creating a simple bucket."""
        mock_s3 = MagicMock()
        mock_s3.create_bucket.return_value = {"Location": "/my-bucket"}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        result = aws_connector.create_bucket("my-bucket")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["Location"], ExtendedString)
        assert result["Location"] == "/my-bucket"
        call_args = mock_s3.create_bucket.call_args[1]
        assert call_args["Bucket"] == "my-bucket"
        assert call_args["ACL"] == "private"

    def test_create_bucket_logs_redact_bucket_name_but_preserve_call_args(self, aws_connector):
        """Bucket creation logs should redact resource names without changing API args."""
        mock_s3 = MagicMock()
        mock_s3.create_bucket.return_value = {"Location": "/prod-secrets-bucket"}
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        aws_connector.create_bucket("prod-secrets-bucket")

        assert mock_s3.create_bucket.call_args.kwargs["Bucket"] == "prod-secrets-bucket"
        logs = _logged_text(aws_connector.logger)
        assert "[REDACTED]" in logs
        assert "prod-secrets-bucket" not in logs

    def test_create_bucket_with_region(self, aws_connector):
        """Test creating bucket in specific region."""
        mock_s3 = MagicMock()
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        aws_connector.create_bucket("my-bucket", region="us-west-2")

        call_args = mock_s3.create_bucket.call_args[1]
        assert "CreateBucketConfiguration" in call_args
        assert call_args["CreateBucketConfiguration"]["LocationConstraint"] == "us-west-2"

    def test_create_bucket_us_east_1(self, aws_connector):
        """Test creating bucket in us-east-1 (no LocationConstraint)."""
        mock_s3 = MagicMock()
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        aws_connector.create_bucket("my-bucket", region="us-east-1")

        call_args = mock_s3.create_bucket.call_args[1]
        assert "CreateBucketConfiguration" not in call_args

    def test_create_bucket_with_versioning(self, aws_connector):
        """Test creating bucket with versioning enabled."""
        mock_s3 = MagicMock()
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        aws_connector.create_bucket("my-bucket", enable_versioning=True)

        mock_s3.put_bucket_versioning.assert_called_once_with(
            Bucket="my-bucket",
            VersioningConfiguration={"Status": "Enabled"},
        )

    def test_create_bucket_with_tags(self, aws_connector):
        """Test creating bucket with tags."""
        mock_s3 = MagicMock()
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        tags = {"Environment": "dev", "Owner": "team"}
        aws_connector.create_bucket("my-bucket", tags=tags)

        mock_s3.put_bucket_tagging.assert_called_once()
        call_args = mock_s3.put_bucket_tagging.call_args[1]
        tag_set = call_args["Tagging"]["TagSet"]
        assert len(tag_set) == 2

    def test_delete_bucket_simple(self, aws_connector):
        """Test deleting a bucket."""
        mock_s3 = MagicMock()
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        aws_connector.delete_bucket("my-bucket")

        mock_s3.delete_bucket.assert_called_once_with(Bucket="my-bucket")

    def test_delete_bucket_with_force(self, aws_connector):
        """Test force deleting a bucket with objects."""
        mock_bucket = MagicMock()
        mock_bucket.objects.all.return_value.delete = MagicMock()
        mock_bucket.object_versions.all.return_value.delete = MagicMock()

        mock_resource = MagicMock()
        mock_resource.Bucket.return_value = mock_bucket
        aws_connector.get_aws_resource = MagicMock(return_value=mock_resource)

        mock_s3 = MagicMock()
        aws_connector.get_aws_client = MagicMock(return_value=mock_s3)

        aws_connector.delete_bucket("my-bucket", force=True)

        mock_bucket.objects.all.return_value.delete.assert_called_once()
        mock_bucket.object_versions.all.return_value.delete.assert_called_once()
        mock_s3.delete_bucket.assert_called_once_with(Bucket="my-bucket")

    def test_get_bucket_sizes(self, aws_connector):
        """Test getting bucket sizes from CloudWatch."""
        mock_cloudwatch = MagicMock()

        # Mock size response
        mock_cloudwatch.get_metric_statistics.side_effect = [
            {
                "Datapoints": [
                    {"Timestamp": datetime(2023, 1, 2), "Average": 1073741824}  # 1 GB
                ]
            },
            {"Datapoints": [{"Timestamp": datetime(2023, 1, 2), "Average": 100}]},
        ]

        mock_s3 = MagicMock()
        mock_s3.list_buckets.return_value = {"Buckets": [{"Name": "test-bucket"}]}

        def get_client(client_name, **kwargs):
            if client_name == "cloudwatch":
                return mock_cloudwatch
            return mock_s3

        aws_connector.get_aws_client = MagicMock(side_effect=get_client)
        aws_connector.list_s3_buckets = MagicMock(return_value={"test-bucket": {}})

        result = aws_connector.get_bucket_sizes(bucket_names=["test-bucket"])

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["test-bucket"], ExtendedDict)
        assert "test-bucket" in result
        assert result["test-bucket"]["size_bytes"] == 1073741824
        assert result["test-bucket"]["size_gb"] == 1.0
        assert result["test-bucket"]["object_count"] == 100

    def test_get_bucket_sizes_error_logs_redact_bucket_name(self, aws_connector):
        """CloudWatch metric diagnostics should not leak bucket names."""
        mock_cloudwatch = MagicMock()
        mock_cloudwatch.get_metric_statistics.side_effect = RuntimeError("denied for prod-secrets-bucket")
        aws_connector.get_aws_client = MagicMock(return_value=mock_cloudwatch)

        result = aws_connector.get_bucket_sizes(bucket_names=["prod-secrets-bucket"])

        assert result["prod-secrets-bucket"]["size_bytes"] == 0
        assert result["prod-secrets-bucket"]["object_count"] == 0
        logs = _logged_text(aws_connector.logger)
        assert "[REDACTED]" in logs
        assert "prod-secrets-bucket" not in logs
