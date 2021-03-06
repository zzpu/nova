#coding:utf-8
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os

from migrate import exceptions as versioning_exceptions
from migrate.versioning import api as versioning_api
from migrate.versioning.repository import Repository
import sqlalchemy

from nova import exception
from nova.i18n import _
from nova.virt.baremetal.db.sqlalchemy import session

INIT_VERSION = 0
_REPOSITORY = None


def db_sync(version=None):
    if version is not None:
        try:
            version = int(version)
        except ValueError:
            raise exception.NovaException(_("version should be an integer"))

    current_version = db_version()
    repository = _find_migrate_repo()
    if version is None or version > current_version:
        return versioning_api.upgrade(session.get_engine(), repository,
                version)
    else:
        return versioning_api.downgrade(session.get_engine(), repository,
                                        version)


def db_version():
    repository = _find_migrate_repo()
    try:
        return versioning_api.db_version(session.get_engine(), repository)
    except versioning_exceptions.DatabaseNotControlledError:
        meta = sqlalchemy.MetaData()
        engine = session.get_engine()
        meta.reflect(bind=engine)
        tables = meta.tables
        if len(tables) == 0:
            db_version_control(INIT_VERSION)
            return versioning_api.db_version(session.get_engine(), repository)
        else:
            # Some pre-Essex DB's may not be version controlled.
            # Require them to upgrade using Essex first.
            raise exception.NovaException(
                _("Upgrade DB using Essex release first."))


def db_initial_version():
    return INIT_VERSION


def db_version_control(version=None):
    repository = _find_migrate_repo()
    versioning_api.version_control(session.get_engine(), repository, version)
    return version


def _find_migrate_repo():
    """Get the path for the migrate repository."""
    global _REPOSITORY
    path = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                        'migrate_repo')
    assert os.path.exists(path)
    if _REPOSITORY is None:
        _REPOSITORY = Repository(path)
    return _REPOSITORY
