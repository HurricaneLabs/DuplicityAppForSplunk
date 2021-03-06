# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2009 Eric EJ Johnson <ej.johnson@rackspace.com>
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
from duplicity import log
from duplicity import util
from duplicity.errors import BackendException


class CloudFilesBackend(duplicity.backend.Backend):
    u"""
    Backend for Rackspace's CloudFiles
    """
    def __init__(self, parsed_url):
        try:
            from cloudfiles import Connection
            from cloudfiles.errors import ResponseError
            from cloudfiles import consts
            from cloudfiles.errors import NoSuchObject
        except ImportError as e:
            raise BackendException(u"""\
Cloudfiles backend requires the cloudfiles library available from Rackspace.
Exception: %s""" % str(e))

        self.resp_exc = ResponseError
        conn_kwargs = {}

        if u'CLOUDFILES_USERNAME' not in os.environ:
            raise BackendException(u'CLOUDFILES_USERNAME environment variable'
                                   u'not set.')

        if u'CLOUDFILES_APIKEY' not in os.environ:
            raise BackendException(u'CLOUDFILES_APIKEY environment variable not set.')

        conn_kwargs[u'username'] = os.environ[u'CLOUDFILES_USERNAME']
        conn_kwargs[u'api_key'] = os.environ[u'CLOUDFILES_APIKEY']

        if u'CLOUDFILES_AUTHURL' in os.environ:
            conn_kwargs[u'authurl'] = os.environ[u'CLOUDFILES_AUTHURL']
        else:
            conn_kwargs[u'authurl'] = consts.default_authurl

        container = parsed_url.path.lstrip(u'/')

        try:
            conn = Connection(**conn_kwargs)
        except Exception as e:
            log.FatalError(u"Connection failed, please check your credentials: %s %s"
                           % (e.__class__.__name__, util.uexc(e)),
                           log.ErrorCode.connection_failed)
        self.container = conn.create_container(container)

    def _error_code(self, operation, e):
        if isinstance(e, NoSuchObject):
            return log.ErrorCode.backend_not_found
        elif isinstance(e, self.resp_exc):
            if e.status == 404:
                return log.ErrorCode.backend_not_found

    def _put(self, source_path, remote_filename):
        sobject = self.container.create_object(remote_filename)
        sobject.load_from_filename(source_path.name)

    def _get(self, remote_filename, local_path):
        sobject = self.container.create_object(remote_filename)
        with open(local_path.name, u'wb') as f:
            for chunk in sobject.stream():
                f.write(chunk)

    def _list(self):
        # Cloud Files will return a max of 10,000 objects.  We have
        # to make multiple requests to get them all.
        objs = self.container.list_objects()
        keys = objs
        while len(objs) == 10000:
            objs = self.container.list_objects(marker=keys[-1])
            keys += objs
        return keys

    def _delete(self, filename):
        self.container.delete_object(filename)

    def _query(self, filename):
        sobject = self.container.get_object(filename)
        return {u'size': sobject.size}
