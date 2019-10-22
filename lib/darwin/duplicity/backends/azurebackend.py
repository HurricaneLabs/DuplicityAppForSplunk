# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2013 Matthieu Huin <mhu@enovance.com>
# Copyright 2015 Scott McKenzie <noizyland@gmail.com>
#
# This file is part of duplicity.
#
# Duplicity is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.
#
# Duplicity is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with duplicity; if not, write to the Free Software Foundation,
# Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

from builtins import str
import os

import duplicity.backend
from duplicity import globals
from duplicity import log
from duplicity.errors import BackendException
from duplicity.util import fsdecode


class AzureBackend(duplicity.backend.Backend):
    u"""
    Backend for Azure Blob Storage Service
    """
    def __init__(self, parsed_url):
        duplicity.backend.Backend.__init__(self, parsed_url)

        # Import Microsoft Azure Storage SDK for Python library.
        try:
            import azure
            import azure.storage
            if hasattr(azure.storage, u'BlobService'):
                # v0.11.1 and below
                from azure.storage import BlobService
                self.AzureMissingResourceError = azure.WindowsAzureMissingResourceError
                self.AzureConflictError = azure.WindowsAzureConflictError
            else:
                # v1.0.0 and above
                import azure.storage.blob
                if hasattr(azure.storage.blob, u'BlobService'):
                    from azure.storage.blob import BlobService
                else:
                    from azure.storage.blob.blockblobservice import BlockBlobService as BlobService
                self.AzureMissingResourceError = azure.common.AzureMissingResourceHttpError
                self.AzureConflictError = azure.common.AzureConflictHttpError
        except ImportError as e:
            raise BackendException(u"""\
Azure backend requires Microsoft Azure Storage SDK for Python (https://pypi.python.org/pypi/azure-storage/).
Exception: %s""" % str(e))

        # TODO: validate container name
        self.container = parsed_url.path.lstrip(u'/')

        if u'AZURE_ACCOUNT_NAME' not in os.environ:
            raise BackendException(u'AZURE_ACCOUNT_NAME environment variable not set.')

        if u'AZURE_ACCOUNT_KEY' in os.environ:
            if u'AZURE_ENDPOINT_SUFFIX' in os.environ:
                self.blob_service = BlobService(account_name=os.environ[u'AZURE_ACCOUNT_NAME'],
                                                account_key=os.environ[u'AZURE_ACCOUNT_KEY'],
                                                endpoint_suffix=os.environ[u'AZURE_ENDPOINT_SUFFIX'])
            else:
                self.blob_service = BlobService(account_name=os.environ[u'AZURE_ACCOUNT_NAME'],
                                                account_key=os.environ[u'AZURE_ACCOUNT_KEY'])
            self._create_container()
        elif u'AZURE_SHARED_ACCESS_SIGNATURE' in os.environ:
            if u'AZURE_ENDPOINT_SUFFIX' in os.environ:
                self.blob_service = BlobService(account_name=os.environ[u'AZURE_ACCOUNT_NAME'],
                                                sas_token=os.environ[u'AZURE_SHARED_ACCESS_SIGNATURE'],
                                                endpoint_suffix=os.environ[u'AZURE_ENDPOINT_SUFFIX'])
            else:
                self.blob_service = BlobService(account_name=os.environ[u'AZURE_ACCOUNT_NAME'],
                                                sas_token=os.environ[u'AZURE_SHARED_ACCESS_SIGNATURE'])
        else:
            raise BackendException(
                u'Neither AZURE_ACCOUNT_KEY nor AZURE_SHARED_ACCESS_SIGNATURE environment variable not set.')

        if globals.azure_max_single_put_size:
            # check if we use azure-storage>=0.30.0
            try:
                _ = self.blob_service.MAX_SINGLE_PUT_SIZE
                self.blob_service.MAX_SINGLE_PUT_SIZE = globals.azure_max_single_put_size
            # fallback for azure-storage<0.30.0
            except AttributeError:
                self.blob_service._BLOB_MAX_DATA_SIZE = globals.azure_max_single_put_size

        if globals.azure_max_block_size:
            # check if we use azure-storage>=0.30.0
            try:
                _ = self.blob_service.MAX_BLOCK_SIZE
                self.blob_service.MAX_BLOCK_SIZE = globals.azure_max_block_size
            # fallback for azure-storage<0.30.0
            except AttributeError:
                self.blob_service._BLOB_MAX_CHUNK_DATA_SIZE = globals.azure_max_block_size

    def _create_container(self):
        try:
            self.blob_service.create_container(self.container, fail_on_exist=True)
        except self.AzureConflictError:
            # Indicates that the resource could not be created because it already exists.
            pass
        except Exception as e:
            log.FatalError(u"Could not create Azure container: %s"
                           % str(e.message).split(u'\n', 1)[0],
                           log.ErrorCode.connection_failed)

    def _put(self, source_path, remote_filename):
        remote_filename = fsdecode(remote_filename)
        kwargs = {}
        if globals.azure_max_connections:
            kwargs[u'max_connections'] = globals.azure_max_connections

        # https://azure.microsoft.com/en-us/documentation/articles/storage-python-how-to-use-blob-storage/#upload-a-blob-into-a-container
        try:
            self.blob_service.create_blob_from_path(self.container, remote_filename, source_path.name, **kwargs)
        except AttributeError:  # Old versions use a different method name
            self.blob_service.put_block_blob_from_path(self.container, remote_filename, source_path.name, **kwargs)

        self._set_tier(remote_filename)

    def _set_tier(self, remote_filename):
        if globals.azure_blob_tier is not None:
            try:
                self.blob_service.set_standard_blob_tier(self.container, remote_filename, globals.azure_blob_tier)
            except AttributeError:  # might not be available in old API
                pass

    def _get(self, remote_filename, local_path):
        # https://azure.microsoft.com/en-us/documentation/articles/storage-python-how-to-use-blob-storage/#download-blobs
        self.blob_service.get_blob_to_path(self.container, fsdecode(remote_filename), local_path.name)

    def _list(self):
        # https://azure.microsoft.com/en-us/documentation/articles/storage-python-how-to-use-blob-storage/#list-the-blobs-in-a-container
        blobs = []
        marker = None
        while True:
            batch = self.blob_service.list_blobs(self.container, marker=marker)
            blobs.extend(batch)
            if not batch.next_marker:
                break
            marker = batch.next_marker
        return [blob.name for blob in blobs]

    def _delete(self, filename):
        # http://azure.microsoft.com/en-us/documentation/articles/storage-python-how-to-use-blob-storage/#delete-blobs
        self.blob_service.delete_blob(self.container, fsdecode(filename))

    def _query(self, filename):
        prop = self.blob_service.get_blob_properties(self.container, fsdecode(filename))
        try:
            info = {u'size': int(prop.properties.content_length)}
        except AttributeError:
            # old versions directly returned the properties
            info = {u'size': int(prop[u'content-length'])}
        return info

    def _error_code(self, operation, e):
        if isinstance(e, self.AzureMissingResourceError):
            return log.ErrorCode.backend_not_found


duplicity.backend.register_backend(u'azure', AzureBackend)
