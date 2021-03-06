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

"""Base classes for our unit tests.

Allows overriding of flags for use of fakes, and some black magic for
inline callbacks.

"""

import eventlet
eventlet.monkey_patch(os=False)

import copy
import gettext
import inspect
import logging
import os
import shutil
import sys
import uuid
import warnings

import fixtures
from oslo.config import cfg
from oslo.messaging import conffixture as messaging_conffixture
import testtools

from nova import context
from nova import db
from nova.db import migration
from nova.db.sqlalchemy import api as session
from nova.network import manager as network_manager
from nova import objects
from nova.objects import base as objects_base
from nova.openstack.common.fixture import logging as log_fixture
from nova.openstack.common.fixture import moxstubout
from nova.openstack.common import log as nova_logging
from nova.openstack.common import timeutils
from nova import paths
from nova import rpc
from nova import service
from nova.tests import conf_fixture
from nova.tests import policy_fixture
from nova import utils


test_opts = [
    cfg.StrOpt('sqlite_clean_db',
               default='clean.sqlite',
               help='File name of clean sqlite db'),
    ]

CONF = cfg.CONF
CONF.register_opts(test_opts)
CONF.import_opt('enabled', 'nova.api.openstack', group='osapi_v3')
CONF.set_override('use_stderr', False)

nova_logging.setup('nova')

# NOTE(comstud): Make sure we have all of the objects loaded. We do this
# at module import time, because we may be using mock decorators in our
# tests that run at import time.
objects.register_all()

_DB_CACHE = None
_TRUE_VALUES = ('True', 'true', '1', 'yes')


class Database(fixtures.Fixture):

    def __init__(self, db_session, db_migrate, sql_connection,
                    sqlite_db, sqlite_clean_db):
        self.sql_connection = sql_connection
        self.sqlite_db = sqlite_db
        self.sqlite_clean_db = sqlite_clean_db

        self.engine = db_session.get_engine()
        self.engine.dispose()
        conn = self.engine.connect()
        if sql_connection == "sqlite://":
            if db_migrate.db_version() > db_migrate.db_initial_version():
                return
        else:
            testdb = paths.state_path_rel(sqlite_db)
            if os.path.exists(testdb):
                return
        db_migrate.db_sync()
        if sql_connection == "sqlite://":
            conn = self.engine.connect()
            self._DB = "".join(line for line in conn.connection.iterdump())
            self.engine.dispose()
        else:
            cleandb = paths.state_path_rel(sqlite_clean_db)
            shutil.copyfile(testdb, cleandb)

    def setUp(self):
        super(Database, self).setUp()

        if self.sql_connection == "sqlite://":
            conn = self.engine.connect()
            conn.connection.executescript(self._DB)
            self.addCleanup(self.engine.dispose)
        else:
            shutil.copyfile(paths.state_path_rel(self.sqlite_clean_db),
                            paths.state_path_rel(self.sqlite_db))


class SampleNetworks(fixtures.Fixture):

    """Create sample networks in the database."""

    def __init__(self, host=None):
        self.host = host

    def setUp(self):
        super(SampleNetworks, self).setUp()
        ctxt = context.get_admin_context()
        network = network_manager.VlanManager(host=self.host)
        bridge_interface = CONF.flat_interface or CONF.vlan_interface
        network.create_networks(ctxt,
                                label='test',
                                cidr='10.0.0.0/8',
                                multi_host=CONF.multi_host,
                                num_networks=CONF.num_networks,
                                network_size=CONF.network_size,
                                cidr_v6=CONF.fixed_range_v6,
                                gateway=CONF.gateway,
                                gateway_v6=CONF.gateway_v6,
                                bridge=CONF.flat_network_bridge,
                                bridge_interface=bridge_interface,
                                vpn_start=CONF.vpn_start,
                                vlan_start=CONF.vlan_start,
                                dns1=CONF.flat_network_dns)
        for net in db.network_get_all(ctxt):
            network.set_network_host(ctxt, net)


class ReplaceModule(fixtures.Fixture):
    """Replace a module with a fake module."""

    def __init__(self, name, new_value):
        self.name = name
        self.new_value = new_value

    def _restore(self, old_value):
        sys.modules[self.name] = old_value

    def setUp(self):
        super(ReplaceModule, self).setUp()
        old_value = sys.modules.get(self.name)
        sys.modules[self.name] = self.new_value
        self.addCleanup(self._restore, old_value)


class ServiceFixture(fixtures.Fixture):
    """Run a service as a test fixture."""

    def __init__(self, name, host=None, **kwargs):
        name = name
        host = host and host or uuid.uuid4().hex
        kwargs.setdefault('host', host)
        kwargs.setdefault('binary', 'nova-%s' % name)
        self.kwargs = kwargs

    def setUp(self):
        super(ServiceFixture, self).setUp()
        self.service = service.Service.create(**self.kwargs)
        self.service.start()
        self.addCleanup(self.service.kill)


class TranslationFixture(fixtures.Fixture):
    """Use gettext NullTranslation objects in tests."""

    def setUp(self):
        super(TranslationFixture, self).setUp()
        nulltrans = gettext.NullTranslations()
        gettext_fixture = fixtures.MonkeyPatch('gettext.translation',
                                               lambda *x, **y: nulltrans)
        self.gettext_patcher = self.useFixture(gettext_fixture)


class TestingException(Exception):
    pass


class NullHandler(logging.Handler):
    """custom default NullHandler to attempt to format the record.

    Used in conjunction with
    log_fixture.get_logging_handle_error_fixture to detect formatting errors in
    debug level logs without saving the logs.
    """
    def handle(self, record):
        self.format(record)

    def emit(self, record):
        pass

    def createLock(self):
        self.lock = None


class TestCase(testtools.TestCase):
    """Test case base class for all unit tests.

    Due to the slowness of DB access, please consider deriving from
    `NoDBTestCase` first.
    """
    USES_DB = True

    # NOTE(rpodolyaka): this attribute can be overridden in subclasses in order
    #                   to scale the global test timeout value set for each
    #                   test case separately. Use 0 value to disable timeout.
    TIMEOUT_SCALING_FACTOR = 1

    def setUp(self):
        """Run before each test method to initialize test environment."""
        super(TestCase, self).setUp()
        test_timeout = os.environ.get('OS_TEST_TIMEOUT', 0)
        try:
            test_timeout = int(test_timeout)
        except ValueError:
            # If timeout value is invalid do not set a timeout.
            test_timeout = 0

        if self.TIMEOUT_SCALING_FACTOR >= 0:
            test_timeout *= self.TIMEOUT_SCALING_FACTOR
        else:
            raise ValueError('TIMEOUT_SCALING_FACTOR value must be >= 0')

        if test_timeout > 0:
            self.useFixture(fixtures.Timeout(test_timeout, gentle=True))
        self.useFixture(fixtures.NestedTempfile())
        self.useFixture(fixtures.TempHomeDir())
        self.useFixture(TranslationFixture())
        self.useFixture(log_fixture.get_logging_handle_error_fixture())

        if os.environ.get('OS_STDOUT_CAPTURE') in _TRUE_VALUES:
            stdout = self.useFixture(fixtures.StringStream('stdout')).stream
            self.useFixture(fixtures.MonkeyPatch('sys.stdout', stdout))
        if os.environ.get('OS_STDERR_CAPTURE') in _TRUE_VALUES:
            stderr = self.useFixture(fixtures.StringStream('stderr')).stream
            self.useFixture(fixtures.MonkeyPatch('sys.stderr', stderr))

        rpc.add_extra_exmods('nova.test')
        self.addCleanup(rpc.clear_extra_exmods)
        self.addCleanup(rpc.cleanup)

        # set root logger to debug
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        # supports collecting debug level for local runs
        if os.environ.get('OS_DEBUG') in _TRUE_VALUES:
            level = logging.DEBUG
        else:
            level = logging.INFO

        # Collect logs
        fs = '%(asctime)s %(levelname)s [%(name)s] %(message)s'
        self.useFixture(fixtures.FakeLogger(format=fs, level=None))
        root.handlers[0].setLevel(level)

        if level > logging.DEBUG:
            # Just attempt to format debug level logs, but don't save them
            handler = NullHandler()
            self.useFixture(fixtures.LogHandler(handler, nuke_handlers=False))
            handler.setLevel(logging.DEBUG)

        self.useFixture(conf_fixture.ConfFixture(CONF))

        self.messaging_conf = messaging_conffixture.ConfFixture(CONF)
        self.messaging_conf.transport_driver = 'fake'
        self.useFixture(self.messaging_conf)

        rpc.init(CONF)

        if self.USES_DB:
            global _DB_CACHE
            if not _DB_CACHE:
                _DB_CACHE = Database(session, migration,
                        sql_connection=CONF.database.connection,
                        sqlite_db=CONF.database.sqlite_db,
                        sqlite_clean_db=CONF.sqlite_clean_db)

            self.useFixture(_DB_CACHE)

        # NOTE(danms): Make sure to reset us back to non-remote objects
        # for each test to avoid interactions. Also, backup the object
        # registry.
        objects_base.NovaObject.indirection_api = None
        self._base_test_obj_backup = copy.copy(
            objects_base.NovaObject._obj_classes)
        self.addCleanup(self._restore_obj_registry)

        # NOTE(mnaser): All calls to utils.is_neutron() are cached in
        # nova.utils._IS_NEUTRON.  We set it to None to avoid any
        # caching of that value.
        utils._IS_NEUTRON = None

        mox_fixture = self.useFixture(moxstubout.MoxStubout())
        self.mox = mox_fixture.mox
        self.stubs = mox_fixture.stubs
        self.addCleanup(self._clear_attrs)
        self.useFixture(fixtures.EnvironmentVariable('http_proxy'))
        self.policy = self.useFixture(policy_fixture.PolicyFixture())
        CONF.set_override('fatal_exception_format_errors', True)
        CONF.set_override('enabled', True, 'osapi_v3')
        CONF.set_override('force_dhcp_release', False)
        CONF.set_override('periodic_enable', False)
        # We don't need to kill ourselves in deprecation floods. Give
        # me a ping, Vasily. One ping only, please.
        warnings.simplefilter("once", DeprecationWarning)

    def _restore_obj_registry(self):
        objects_base.NovaObject._obj_classes = self._base_test_obj_backup

    def _clear_attrs(self):
        # Delete attributes that don't start with _ so they don't pin
        # memory around unnecessarily for the duration of the test
        # suite
        for key in [k for k in self.__dict__.keys() if k[0] != '_']:
            del self.__dict__[key]

    def flags(self, **kw):
        """Override flag variables for a test."""
        group = kw.pop('group', None)
        for k, v in kw.iteritems():
            CONF.set_override(k, v, group)

    def start_service(self, name, host=None, **kwargs):
        svc = self.useFixture(ServiceFixture(name, host, **kwargs))
        return svc.service

    def assertPublicAPISignatures(self, baseinst, inst):
        def get_public_apis(inst):
            methods = {}
            for (name, value) in inspect.getmembers(inst, inspect.ismethod):
                if name.startswith("_"):
                    continue
                methods[name] = value
            return methods

        baseclass = baseinst.__class__.__name__
        basemethods = get_public_apis(baseinst)
        implmethods = get_public_apis(inst)

        extranames = []
        for name in sorted(implmethods.keys()):
            if name not in basemethods:
                extranames.append(name)

        self.assertEqual([], extranames,
                         "public APIs not listed in base class %s" %
                         baseclass)

        for name in sorted(implmethods.keys()):
            baseargs = inspect.getargspec(basemethods[name])
            implargs = inspect.getargspec(implmethods[name])

            self.assertEqual(baseargs, implargs,
                             "%s args don't match base class %s" %
                             (name, baseclass))


class APICoverage(object):

    cover_api = None

    def test_api_methods(self):
        self.assertTrue(self.cover_api is not None)
        api_methods = [x for x in dir(self.cover_api)
                       if not x.startswith('_')]
        test_methods = [x[5:] for x in dir(self)
                        if x.startswith('test_')]
        self.assertThat(
            test_methods,
            testtools.matchers.ContainsAll(api_methods))


class TimeOverride(fixtures.Fixture):
    """Fixture to start and remove time override."""

    def setUp(self):
        super(TimeOverride, self).setUp()
        timeutils.set_time_override()
        self.addCleanup(timeutils.clear_time_override)


class NoDBTestCase(TestCase):
    """`NoDBTestCase` differs from TestCase in that DB access is not supported.
    This makes tests run significantly faster. If possible, all new tests
    should derive from this class.
    """
    USES_DB = False


class BaseHookTestCase(NoDBTestCase):
    def assert_has_hook(self, expected_name, func):
        self.assertTrue(hasattr(func, '__hook_name__'))
        self.assertEqual(expected_name, func.__hook_name__)
