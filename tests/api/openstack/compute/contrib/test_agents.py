#coding:utf-8
# Copyright 2012 IBM Corp.
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

import mock
import webob.exc

from nova.api.openstack.compute.contrib import agents as agents_v2
from nova.api.openstack.compute.plugins.v3 import agents as agents_v21
from nova import context
from nova import db
from nova.db.sqlalchemy import models
from nova import exception
from nova import test

fake_agents_list = [{'hypervisor': 'kvm', 'os': 'win',
                     'architecture': 'x86',
                     'version': '7.0',
                     'url': 'http://example.com/path/to/resource',
                     'md5hash': 'add6bb58e139be103324d04d82d8f545',
                     'id': 1},
                    {'hypervisor': 'kvm', 'os': 'linux',
                     'architecture': 'x86',
                     'version': '16.0',
                     'url': 'http://example.com/path/to/resource1',
                     'md5hash': 'add6bb58e139be103324d04d82d8f546',
                     'id': 2},
                    {'hypervisor': 'xen', 'os': 'linux',
                     'architecture': 'x86',
                     'version': '16.0',
                     'url': 'http://example.com/path/to/resource2',
                     'md5hash': 'add6bb58e139be103324d04d82d8f547',
                     'id': 3},
                    {'hypervisor': 'xen', 'os': 'win',
                     'architecture': 'power',
                     'version': '7.0',
                     'url': 'http://example.com/path/to/resource3',
                     'md5hash': 'add6bb58e139be103324d04d82d8f548',
                     'id': 4},
                    ]


def fake_agent_build_get_all(context, hypervisor):
    agent_build_all = []
    for agent in fake_agents_list:
        if hypervisor and hypervisor != agent['hypervisor']:
            continue
        agent_build_ref = models.AgentBuild()
        agent_build_ref.update(agent)
        agent_build_all.append(agent_build_ref)
    return agent_build_all


def fake_agent_build_update(context, agent_build_id, values):
    pass


def fake_agent_build_destroy(context, agent_update_id):
    pass


def fake_agent_build_create(context, values):
    values['id'] = 1
    agent_build_ref = models.AgentBuild()
    agent_build_ref.update(values)
    return agent_build_ref


class FakeRequest(object):
        environ = {"nova.context": context.get_admin_context()}
        GET = {}


class FakeRequestWithHypervisor(object):
        environ = {"nova.context": context.get_admin_context()}
        GET = {'hypervisor': 'kvm'}


class AgentsTestV21(test.NoDBTestCase):
    controller = agents_v21.AgentController()
    validation_error = exception.ValidationError

    def setUp(self):
        super(AgentsTestV21, self).setUp()

        self.stubs.Set(db, "agent_build_get_all",
                       fake_agent_build_get_all)
        self.stubs.Set(db, "agent_build_update",
                       fake_agent_build_update)
        self.stubs.Set(db, "agent_build_destroy",
                       fake_agent_build_destroy)
        self.stubs.Set(db, "agent_build_create",
                       fake_agent_build_create)
        self.context = context.get_admin_context()

    def test_agents_create(self):
        req = FakeRequest()
        body = {'agent': {'hypervisor': 'kvm',
                'os': 'win',
                'architecture': 'x86',
                'version': '7.0',
                'url': 'http://example.com/path/to/resource',
                'md5hash': 'add6bb58e139be103324d04d82d8f545'}}
        response = {'agent': {'hypervisor': 'kvm',
                    'os': 'win',
                    'architecture': 'x86',
                    'version': '7.0',
                    'url': 'http://example.com/path/to/resource',
                    'md5hash': 'add6bb58e139be103324d04d82d8f545',
                    'agent_id': 1}}
        res_dict = self.controller.create(req, body=body)
        self.assertEqual(res_dict, response)

    def _test_agents_create_key_error(self, key):
        req = FakeRequest()
        body = {'agent': {'hypervisor': 'kvm',
                'os': 'win',
                'architecture': 'x86',
                'version': '7.0',
                'url': 'xxx://xxxx/xxx/xxx',
                'md5hash': 'add6bb58e139be103324d04d82d8f545'}}
        body['agent'].pop(key)
        self.assertRaises(self.validation_error,
                          self.controller.create, req, body=body)

    def test_agents_create_without_hypervisor(self):
        self._test_agents_create_key_error('hypervisor')

    def test_agents_create_without_os(self):
        self._test_agents_create_key_error('os')

    def test_agents_create_without_architecture(self):
        self._test_agents_create_key_error('architecture')

    def test_agents_create_without_version(self):
        self._test_agents_create_key_error('version')

    def test_agents_create_without_url(self):
        self._test_agents_create_key_error('url')

    def test_agents_create_without_md5hash(self):
        self._test_agents_create_key_error('md5hash')

    def test_agents_create_with_wrong_type(self):
        req = FakeRequest()
        body = {'agent': None}
        self.assertRaises(self.validation_error,
                          self.controller.create, req, body=body)

    def test_agents_create_with_empty_type(self):
        req = FakeRequest()
        body = {}
        self.assertRaises(self.validation_error,
                          self.controller.create, req, body=body)

    def test_agents_create_with_existed_agent(self):
        def fake_agent_build_create_with_exited_agent(context, values):
            raise exception.AgentBuildExists(**values)

        self.stubs.Set(db, 'agent_build_create',
                       fake_agent_build_create_with_exited_agent)
        req = FakeRequest()
        body = {'agent': {'hypervisor': 'kvm',
                'os': 'win',
                'architecture': 'x86',
                'version': '7.0',
                'url': 'xxx://xxxx/xxx/xxx',
                'md5hash': 'add6bb58e139be103324d04d82d8f545'}}
        self.assertRaises(webob.exc.HTTPConflict, self.controller.create, req,
                          body=body)

    def _test_agents_create_with_invalid_length(self, key):
        req = FakeRequest()
        body = {'agent': {'hypervisor': 'kvm',
                'os': 'win',
                'architecture': 'x86',
                'version': '7.0',
                'url': 'http://example.com/path/to/resource',
                'md5hash': 'add6bb58e139be103324d04d82d8f545'}}
        body['agent'][key] = 'x' * 256
        self.assertRaises(self.validation_error,
                          self.controller.create, req, body=body)

    def test_agents_create_with_invalid_length_hypervisor(self):
        self._test_agents_create_with_invalid_length('hypervisor')

    def test_agents_create_with_invalid_length_os(self):
        self._test_agents_create_with_invalid_length('os')

    def test_agents_create_with_invalid_length_architecture(self):
        self._test_agents_create_with_invalid_length('architecture')

    def test_agents_create_with_invalid_length_version(self):
        self._test_agents_create_with_invalid_length('version')

    def test_agents_create_with_invalid_length_url(self):
        self._test_agents_create_with_invalid_length('url')

    def test_agents_create_with_invalid_length_md5hash(self):
        self._test_agents_create_with_invalid_length('md5hash')

    def test_agents_delete(self):
        req = FakeRequest()
        self.controller.delete(req, 1)

    def test_agents_delete_with_id_not_found(self):
        with mock.patch.object(db, 'agent_build_destroy',
            side_effect=exception.AgentBuildNotFound(id=1)):
            req = FakeRequest()
            self.assertRaises(webob.exc.HTTPNotFound,
                              self.controller.delete, req, 1)

    def test_agents_list(self):
        req = FakeRequest()
        res_dict = self.controller.index(req)
        agents_list = [{'hypervisor': 'kvm', 'os': 'win',
                     'architecture': 'x86',
                     'version': '7.0',
                     'url': 'http://example.com/path/to/resource',
                     'md5hash': 'add6bb58e139be103324d04d82d8f545',
                     'agent_id': 1},
                    {'hypervisor': 'kvm', 'os': 'linux',
                     'architecture': 'x86',
                     'version': '16.0',
                     'url': 'http://example.com/path/to/resource1',
                     'md5hash': 'add6bb58e139be103324d04d82d8f546',
                     'agent_id': 2},
                    {'hypervisor': 'xen', 'os': 'linux',
                     'architecture': 'x86',
                     'version': '16.0',
                     'url': 'http://example.com/path/to/resource2',
                     'md5hash': 'add6bb58e139be103324d04d82d8f547',
                     'agent_id': 3},
                    {'hypervisor': 'xen', 'os': 'win',
                     'architecture': 'power',
                     'version': '7.0',
                     'url': 'http://example.com/path/to/resource3',
                     'md5hash': 'add6bb58e139be103324d04d82d8f548',
                     'agent_id': 4},
                    ]
        self.assertEqual(res_dict, {'agents': agents_list})

    def test_agents_list_with_hypervisor(self):
        req = FakeRequestWithHypervisor()
        res_dict = self.controller.index(req)
        response = [{'hypervisor': 'kvm', 'os': 'win',
                     'architecture': 'x86',
                     'version': '7.0',
                     'url': 'http://example.com/path/to/resource',
                     'md5hash': 'add6bb58e139be103324d04d82d8f545',
                     'agent_id': 1},
                    {'hypervisor': 'kvm', 'os': 'linux',
                     'architecture': 'x86',
                     'version': '16.0',
                     'url': 'http://example.com/path/to/resource1',
                     'md5hash': 'add6bb58e139be103324d04d82d8f546',
                     'agent_id': 2},
                    ]
        self.assertEqual(res_dict, {'agents': response})

    def test_agents_update(self):
        req = FakeRequest()
        body = {'para': {'version': '7.0',
                'url': 'http://example.com/path/to/resource',
                'md5hash': 'add6bb58e139be103324d04d82d8f545'}}
        response = {'agent': {'agent_id': 1,
                    'version': '7.0',
                    'url': 'http://example.com/path/to/resource',
                    'md5hash': 'add6bb58e139be103324d04d82d8f545'}}
        res_dict = self.controller.update(req, 1, body=body)
        self.assertEqual(res_dict, response)

    def _test_agents_update_key_error(self, key):
        req = FakeRequest()
        body = {'para': {'version': '7.0',
                'url': 'xxx://xxxx/xxx/xxx',
                'md5hash': 'add6bb58e139be103324d04d82d8f545'}}
        body['para'].pop(key)
        self.assertRaises(self.validation_error,
                          self.controller.update, req, 1, body=body)

    def test_agents_update_without_version(self):
        self._test_agents_update_key_error('version')

    def test_agents_update_without_url(self):
        self._test_agents_update_key_error('url')

    def test_agents_update_without_md5hash(self):
        self._test_agents_update_key_error('md5hash')

    def test_agents_update_with_wrong_type(self):
        req = FakeRequest()
        body = {'agent': None}
        self.assertRaises(self.validation_error,
                          self.controller.update, req, 1, body=body)

    def test_agents_update_with_empty(self):
        req = FakeRequest()
        body = {}
        self.assertRaises(self.validation_error,
                          self.controller.update, req, 1, body=body)

    def test_agents_update_value_error(self):
        req = FakeRequest()
        body = {'para': {'version': '7.0',
                'url': 1111,
                'md5hash': 'add6bb58e139be103324d04d82d8f545'}}
        self.assertRaises(self.validation_error,
                          self.controller.update, req, 1, body=body)

    def _test_agents_update_with_invalid_length(self, key):
        req = FakeRequest()
        body = {'para': {'version': '7.0',
                'url': 'http://example.com/path/to/resource',
                'md5hash': 'add6bb58e139be103324d04d82d8f545'}}
        body['para'][key] = 'x' * 256
        self.assertRaises(self.validation_error,
                          self.controller.update, req, 1, body=body)

    def test_agents_update_with_invalid_length_version(self):
        self._test_agents_update_with_invalid_length('version')

    def test_agents_update_with_invalid_length_url(self):
        self._test_agents_update_with_invalid_length('url')

    def test_agents_update_with_invalid_length_md5hash(self):
        self._test_agents_update_with_invalid_length('md5hash')

    def test_agents_update_with_id_not_found(self):
        with mock.patch.object(db, 'agent_build_update',
            side_effect=exception.AgentBuildNotFound(id=1)):
            req = FakeRequest()
            body = {'para': {'version': '7.0',
                    'url': 'http://example.com/path/to/resource',
                    'md5hash': 'add6bb58e139be103324d04d82d8f545'}}
            self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.update, req, 1, body=body)


class AgentsTestV2(AgentsTestV21):
    controller = agents_v2.AgentController()
    validation_error = webob.exc.HTTPBadRequest
