"""DigitalOcean Spaces client with tenant-aware object hierarchy."""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger(__name__)


@dataclass
class SpacesLocation:
    """Represents a location in DigitalOcean Spaces."""
    bucket: str
    object_key: str
    region: str
    tenant_id: Optional[str] = None

    @property
    def url(self) -> str:
        """Get the public URL for this object."""
        return f"https://{self.bucket}.{self.region}.digitaloceanspaces.com/{self.object_key}"

    @property
    def s3_uri(self) -> str:
        """Get the S3-style URI for this object."""
        return f"s3://{self.bucket}/{self.object_key}"


class SpacesClient:
    """DigitalOcean Spaces client with tenant-aware object hierarchy."""

    def __init__(self, bucket: str, region: str, endpoint_url: str,
                 tenant_id: str = None, profile: Optional[str] = None):
        """Initialize Spaces client.

        Args:
            bucket: Spaces bucket name
            region: DigitalOcean region
            endpoint_url: Spaces endpoint URL
            tenant_id: Tenant identifier for object hierarchy
            profile: AWS profile name for credentials
        """
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url
        self.tenant_id = tenant_id
        self.profile = profile

        # Initialize boto3 session
        session_kwargs = {}
        if self.profile:
            try:
                session_kwargs["profile_name"] = self.profile
            except Exception:
                pass

        session = boto3.Session(**session_kwargs)
        self._s3 = session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            config=BotoConfig(s3={"addressing_style": "path"})
        )

        logger.info(f"Spaces client initialized for tenant {tenant_id}, bucket {bucket}")

    def store_document_with_tenant_path(self, local_path: Path, case_ref: str,
                                      document_type: str = "raw") -> SpacesLocation:
        """Store document using tenant-based object key hierarchy.

        Args:
            local_path: Local file path
            case_ref: Case reference
            document_type: Type of document (raw, processed_text, etc.)

        Returns:
            SpacesLocation object
        """
        # Create tenant-based object key
        object_key = f"{self.tenant_id}/documents/{document_type}/{case_ref}/{local_path.name}"

        self.upload_file(local_path, object_key)

        return SpacesLocation(
            bucket=self.bucket,
            object_key=object_key,
            region=self.region,
            tenant_id=self.tenant_id
        )

    def upload_file(self, local_path: Path, object_key: str,
                   metadata: Optional[dict] = None) -> None:
        """Upload file to Spaces.

        Args:
            local_path: Local file path
            object_key: Object key in Spaces
            metadata: Optional metadata to store with object
        """
        try:
            # Determine content type
            content_type = mimetypes.guess_type(str(local_path))[0]
            if not content_type:
                content_type = 'application/octet-stream'

            # Prepare upload arguments
            extra_args = {
                'ContentType': content_type
            }

            # Add metadata if provided
            if metadata:
                extra_args['Metadata'] = metadata

            # Add tenant metadata
            if self.tenant_id:
                if 'Metadata' not in extra_args:
                    extra_args['Metadata'] = {}
                extra_args['Metadata']['tenant-id'] = self.tenant_id

            # Upload file
            self._s3.upload_file(
                str(local_path),
                self.bucket,
                object_key,
                ExtraArgs=extra_args
            )

            logger.info(f"Uploaded {local_path} to {object_key}")

        except Exception as e:
            logger.error(f"Failed to upload {local_path} to {object_key}: {e}")
            raise

    def download_file(self, object_key: str, local_path: Path) -> None:
        """Download file from Spaces.

        Args:
            object_key: Object key in Spaces
            local_path: Local destination path
        """
        try:
            # Ensure local directory exists
            local_path.parent.mkdir(parents=True, exist_ok=True)

            self._s3.download_file(self.bucket, object_key, str(local_path))
            logger.info(f"Downloaded {object_key} to {local_path}")

        except Exception as e:
            logger.error(f"Failed to download {object_key} to {local_path}: {e}")
            raise

    def upload_text(self, text: str, object_key: str,
                   metadata: Optional[dict] = None) -> SpacesLocation:
        """Upload text content directly to Spaces.

        Args:
            text: Text content to upload
            object_key: Object key in Spaces
            metadata: Optional metadata

        Returns:
            SpacesLocation object
        """
        try:
            # Prepare upload arguments
            extra_args = {
                'ContentType': 'text/plain; charset=utf-8'
            }

            # Add metadata if provided
            if metadata:
                extra_args['Metadata'] = metadata

            # Add tenant metadata
            if self.tenant_id:
                if 'Metadata' not in extra_args:
                    extra_args['Metadata'] = {}
                extra_args['Metadata']['tenant-id'] = self.tenant_id

            # Upload text
            self._s3.put_object(
                Bucket=self.bucket,
                Key=object_key,
                Body=text.encode('utf-8'),
                **extra_args
            )

            logger.info(f"Uploaded text content to {object_key}")

            return SpacesLocation(
                bucket=self.bucket,
                object_key=object_key,
                region=self.region,
                tenant_id=self.tenant_id
            )

        except Exception as e:
            logger.error(f"Failed to upload text to {object_key}: {e}")
            raise

    def get_object_metadata(self, object_key: str) -> dict:
        """Get object metadata from Spaces.

        Args:
            object_key: Object key in Spaces

        Returns:
            Metadata dictionary
        """
        try:
            response = self._s3.head_object(Bucket=self.bucket, Key=object_key)
            return {
                'size': response.get('ContentLength', 0),
                'content_type': response.get('ContentType', ''),
                'last_modified': response.get('LastModified'),
                'metadata': response.get('Metadata', {}),
                'tenant_id': response.get('Metadata', {}).get('tenant-id')
            }

        except Exception as e:
            logger.error(f"Failed to get metadata for {object_key}: {e}")
            raise

    def list_objects(self, prefix: str = "", max_keys: int = 1000) -> list:
        """List objects in bucket with optional prefix filter.

        Args:
            prefix: Object key prefix filter
            max_keys: Maximum number of objects to return

        Returns:
            List of object information dictionaries
        """
        try:
            # Add tenant prefix if specified
            if self.tenant_id and not prefix.startswith(f"{self.tenant_id}/"):
                prefix = f"{self.tenant_id}/{prefix}" if prefix else f"{self.tenant_id}/"

            response = self._s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                MaxKeys=max_keys
            )

            objects = []
            for obj in response.get('Contents', []):
                objects.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'storage_class': obj.get('StorageClass', 'STANDARD')
                })

            return objects

        except Exception as e:
            logger.error(f"Failed to list objects with prefix {prefix}: {e}")
            raise

    def delete_object(self, object_key: str) -> None:
        """Delete object from Spaces.

        Args:
            object_key: Object key to delete
        """
        try:
            self._s3.delete_object(Bucket=self.bucket, Key=object_key)
            logger.info(f"Deleted object {object_key}")

        except Exception as e:
            logger.error(f"Failed to delete object {object_key}: {e}")
            raise

    def generate_presigned_url(self, object_key: str, expiration: int = 3600) -> str:
        """Generate presigned URL for object access.

        Args:
            object_key: Object key
            expiration: URL expiration time in seconds

        Returns:
            Presigned URL string
        """
        try:
            url = self._s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': object_key},
                ExpiresIn=expiration
            )

            logger.debug(f"Generated presigned URL for {object_key}")
            return url

        except Exception as e:
            logger.error(f"Failed to generate presigned URL for {object_key}: {e}")
            raise

    def get_bucket_info(self) -> dict:
        """Get bucket information and usage statistics.

        Returns:
            Dictionary with bucket information
        """
        try:
            # Get bucket location
            location = self._s3.get_bucket_location(Bucket=self.bucket)

            # Count objects and total size for this tenant
            tenant_prefix = f"{self.tenant_id}/" if self.tenant_id else ""
            objects = self.list_objects(prefix=tenant_prefix)

            total_size = sum(obj['size'] for obj in objects)
            object_count = len(objects)

            return {
                'bucket': self.bucket,
                'region': location.get('LocationConstraint', self.region),
                'tenant_id': self.tenant_id,
                'object_count': object_count,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2)
            }

        except Exception as e:
            logger.error(f"Failed to get bucket info: {e}")
            raise

    def cleanup_temp_objects(self, prefix: str = "temp/") -> int:
        """Clean up temporary objects.

        Args:
            prefix: Prefix for temporary objects

        Returns:
            Number of objects deleted
        """
        try:
            # Add tenant context to prefix
            if self.tenant_id:
                full_prefix = f"{self.tenant_id}/{prefix}"
            else:
                full_prefix = prefix

            objects = self.list_objects(prefix=full_prefix)
            deleted_count = 0

            for obj in objects:
                try:
                    self.delete_object(obj['key'])
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete temp object {obj['key']}: {e}")

            logger.info(f"Cleaned up {deleted_count} temporary objects")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup temp objects: {e}")
            return 0