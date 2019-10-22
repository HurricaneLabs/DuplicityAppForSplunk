#
# Copyright (c) 2015 Matthew Bentley
#
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from builtins import object
from future import standard_library
standard_library.install_aliases()

import os
import hashlib
from urllib.parse import quote_plus  # pylint: disable=import-error

import duplicity.backend
from duplicity.errors import BackendException, FatalBackendException
from duplicity import log
from duplicity import progress


class B2ProgressListener(object):
    def __enter__(self):
        pass

    def set_total_bytes(self, total_byte_count):
        self.total_byte_count = total_byte_count

    def bytes_completed(self, byte_count):
        progress.report_transfer(byte_count, self.total_byte_count)

    def close(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class B2Backend(duplicity.backend.Backend):
    u"""
    Backend for BackBlaze's B2 storage service
    """

    def __init__(self, parsed_url):
        u"""
        Authorize to B2 api and set up needed variables
        """
        duplicity.backend.Backend.__init__(self, parsed_url)

        # Import B2 API
        try:
            global b2
            import b2
            global b2sdk
            import b2sdk
            import b2.api
            import b2.account_info
            import b2.download_dest
            import b2.file_version
        except ImportError:
            raise BackendException(u'B2 backend requires B2 Python APIs (pip install b2)')

        self.service = b2.api.B2Api(b2.account_info.InMemoryAccountInfo())
        self.parsed_url.hostname = u'B2'

        account_id = parsed_url.username
        account_key = self.get_password()

        self.url_parts = [
            x for x in parsed_url.path.replace(u"@", u"/").split(u'/') if x != u''
        ]
        if self.url_parts:
            self.username = self.url_parts.pop(0)
            bucket_name = self.url_parts.pop(0)
        else:
            raise BackendException(u"B2 requires a bucket name")
        self.path = u"".join([url_part + u"/" for url_part in self.url_parts])
        self.service.authorize_account(u'production', account_id, account_key)

        log.Log(u"B2 Backend (path= %s, bucket= %s, minimum_part_size= %s)" %
                (self.path, bucket_name, self.service.account_info.get_minimum_part_size()), log.INFO)
        try:
            self.bucket = self.service.get_bucket_by_name(bucket_name)
            log.Log(u"Bucket found", log.INFO)
        except b2.exception.NonExistentBucket:
            try:
                log.Log(u"Bucket not found, creating one", log.INFO)
                self.bucket = self.service.create_bucket(bucket_name, u'allPrivate')
            except:
                raise FatalBackendException(u"Bucket cannot be created")

    def _get(self, remote_filename, local_path):
        u"""
        Download remote_filename to local_path
        """
        log.Log(u"Get: %s -> %s" % (self.path + remote_filename, local_path.name), log.INFO)
        self.bucket.download_file_by_name(quote_plus(self.path + remote_filename),
                                          b2.download_dest.DownloadDestLocalFile(local_path.name))

    def _put(self, source_path, remote_filename):
        u"""
        Copy source_path to remote_filename
        """
        log.Log(u"Put: %s -> %s" % (source_path.name, self.path + remote_filename), log.INFO)
        self.bucket.upload_local_file(source_path.name, quote_plus(self.path + remote_filename),
                                      content_type=u'application/pgp-encrypted',
                                      progress_listener=B2ProgressListener())

    def _list(self):
        u"""
        List files on remote server
        """
        return [file_version_info.file_name[len(self.path):]
                for (file_version_info, folder_name) in self.bucket.ls(self.path)]

    def _delete(self, filename):
        u"""
        Delete filename from remote server
        """
        log.Log(u"Delete: %s" % self.path + filename, log.INFO)
        file_version_info = self.file_info(quote_plus(self.path + filename))
        self.bucket.delete_file_version(file_version_info.id_, file_version_info.file_name)

    def _query(self, filename):
        u"""
        Get size info of filename
        """
        log.Log(u"Query: %s" % self.path + filename, log.INFO)
        file_version_info = self.file_info(quote_plus(self.path + filename))
        return {u'size': file_version_info.size
                if file_version_info is not None and file_version_info.size is not None else -1}

    def file_info(self, filename):
        response = self.bucket.list_file_names(filename, 1)
        for entry in response[u'files']:
            file_version_info = b2.file_version.FileVersionInfoFactory.from_api_response(entry)
            if file_version_info.file_name == filename:
                return file_version_info
        raise BackendException(u'File not found')


duplicity.backend.register_backend(u"b2", B2Backend)
