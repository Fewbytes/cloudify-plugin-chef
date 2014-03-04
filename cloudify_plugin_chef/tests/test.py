#!/usr/bin/env python

from functools import wraps
import os
import random
import re
import string
import subprocess
import unittest


from cloudify.mocks import MockCloudifyContext

import cosmo_plugin_common as cpc

import cloudify_plugin_chef.chef_client as chef_client
import cloudify_plugin_chef.operations as chef_operations

# Run on target machine!!!
SAFETY_FILE = '/tmp/do-run-chef-tests'
FILE_SERVER_PORT = '50000'

CHEF_CREATED_FILE_NAME = '/tmp/cloudify_plugin_chef_test.txt'
CHEF_CREATED_FILE_CONTENTS = ''.join([random.choice(
    string.ascii_uppercase + string.digits) for x in range(6)])

class TestsConfig(cpc.Config):
    which = 'chef_tests'

os.environ.setdefault('CHEF_TESTS_CONFIG_PATH',
    os.path.join(os.path.dirname(os.path.realpath(__file__)), 'chef_tests.json'))

tests_config = TestsConfig().get()

def _make_context(installation_type='solo', operation=None, merge_chef_attributes=None, related=None):
    props = tests_config[installation_type]['properties']
    props.setdefault('chef_attributes', {})
    props['chef_attributes'].setdefault('create_file', {})
    props['chef_attributes']['create_file'].setdefault('file_name', CHEF_CREATED_FILE_NAME)
    props['chef_attributes']['create_file'].setdefault('file_contents', CHEF_CREATED_FILE_CONTENTS)
    props['chef_attributes'].update(merge_chef_attributes or {})
    ctx = MockCloudifyContext(
        node_id='clodufiy_app_node_id',
        operation='cloudify.interfaces.lifecycle.' +
        (operation or 'INVALID'),
        properties=props,
        related=related
    )
    return ctx

class ChefPluginTest(object):

    def _make_context(self, operation=None, merge_chef_attributes=None):
        return _make_context(self.__class__.INSTALLATION_TYPE, operation, merge_chef_attributes)


class ChefPluginWithHTTPServer(ChefPluginTest):

    def setUp(self):
        if os.getuid() == 0:
            raise RuntimeError(
                "Can not run tests as root, please use a sudo-enabled user")
        if not os.path.exists(SAFETY_FILE):
            raise RuntimeError(
                "Safety file {0} does not exist. Make sure you run these "
                "tests on target host.".format(SAFETY_FILE))
        os.chdir(os.path.dirname(__file__))
        subprocess.call(['tar', 'czf', 'cookbooks.tar.gz', 'cookbooks'])
        subprocess.call(['fuser', '-s', '-k', FILE_SERVER_PORT + '/tcp'])
        subprocess.Popen(
            ['python', '-m', 'SimpleHTTPServer', FILE_SERVER_PORT])
        # subprocess.call(['fuser', '-k', FILE_SERVER_PORT + '/tcp'])

    def tearDown(self):
        subprocess.call(['fuser', '-s', '-k', FILE_SERVER_PORT + '/tcp'])


class ChefPluginInstallationTest(ChefPluginWithHTTPServer):

    def test_chef_installation(self):
        """Run Chef installation and check for expected"""
        # Assumption: chef-client version is the same
        ctx = self._make_context()
        chef_manager = chef_client.get_manager(ctx)
        self.assertIsInstance(chef_manager, self.__class__.CORRECT_CHEF_MANAGER)
        chef_manager.install(ctx)
        output = subprocess.check_output(['sudo', 'chef-client', '-v'])
        m = re.match('^Chef: ([0-9.]+)', output)
        expected_version, _, _ = tests_config['solo']['properties']['chef_version'].partition('-')
        self.assertEquals(m.group(1), expected_version)

        # TEMP!!!
        chef_manager.install_chef_handler(ctx)

    def test_chef_operation(self):
        ctx = self._make_context(operation='install')
        chef_operations.operation(ctx)
        create_file_attrs = ctx.properties['chef_attributes']['create_file']
        f = create_file_attrs['file_name']
        c = create_file_attrs['file_contents']
        self.assertEquals(open(f).read(), c)

class ChefPluginAttrubutesPassingTestBase(object):

    """Tests referencing related node's runtime props as chef attrs.
    TODO: Depth tests, as opposed to only shallow tests now.
    """

    def _run(self, a1key, has_default, has_rel, has_prop_key, has_chef_attr_key, expect_exception=None):
        merge_chef_attributes = {
            'attr1': {
            }
        }
        merge_chef_attributes['attr1'][a1key] = 'prop1'
        if has_default:
            merge_chef_attributes['attr1']['default_value'] = 'attr1_default_val'
        if has_rel:
            runtime_properties = {}
            if has_prop_key:
                runtime_properties['prop1'] = 'prop_val'
            if has_chef_attr_key:
                runtime_properties['chef_attributes'] = {
                    'prop1': 'chef_attr_val'
                }
            related = MockCloudifyContext(
                node_id='clodufiy_db_node_id',
                runtime_properties=runtime_properties,
            )
        else:
            related = None
        ctx = _make_context(operation='install', merge_chef_attributes=merge_chef_attributes, related=related)
        if expect_exception:
            self.assertRaises(expect_exception, chef_client._prepare_chef_attributes, ctx)
        else:
            return chef_client._prepare_chef_attributes(ctx)

    def test_node_match(self):
        pass


def _make_test(h):
    def test_method(self):
        if isinstance(h[-1], type) and issubclass(h[-1], Exception):
            test_args = h
            confirmator = None
        else:
            test_args = h[:-1]
            confirmator = h[-1]
        v = self._run(*test_args)
        if confirmator:
            confirmator(self, v, "Failed for args {0}".format(test_args))
    test_method.__name__ = 'test_' + '_'.join(map(str, h[:-1]))
    return test_method

def _make_value_confirmer(expected_value):
    def f(self, v, msg):
        self.assertIn('attr1', v)
        self.assertEquals(v['attr1'], expected_value)
    f.__name__ = 'value_confirmer_{0}'.format(expected_value)
    return f

def _confirm_no_attr(self, v, msg):
    self.assertNotIn('attr1', v, msg)

_confirm_default_val = _make_value_confirmer('attr1_default_val')
_confirm_prop_val = _make_value_confirmer('prop_val')
_confirm_chef_attr_val = _make_value_confirmer('chef_attr_val')

# args: a1key, has_default, has_rel, has_prop_key, has_chef_attr_key, confirmator_or_excpetion
# Commented out tests without related node except for the first four of them.
# They are not interesting.
b = ChefPluginAttrubutesPassingTestBase
how = (
    ('related_runtime_property',  False,  False,  False,  False,  _confirm_no_attr),
    ('related_chef_attribute',    False,  False,  False,  False,  _confirm_no_attr),
    ('related_runtime_property',  True,   False,  False,  False,  _confirm_default_val),
    ('related_chef_attribute',    True,   False,  False,  False,  _confirm_default_val),
    ('related_runtime_property',  False,  True,   False,  False,  KeyError),
    ('related_chef_attribute',    False,  True,   False,  False,  KeyError),
    ('related_runtime_property',  True,   True,   False,  False,  _confirm_default_val),
    ('related_chef_attribute',    True,   True,   False,  False,  _confirm_default_val),
    # ('related_runtime_property',  False,  False,  True,   False,  _confirm_no_attr),
    # ('related_chef_attribute',    False,  False,  True,   False,  _confirm_no_attr),
    # ('related_runtime_property',  True,   False,  True,   False,  _confirm_default_val),
    # ('related_chef_attribute',    True,   False,  True,   False,  _confirm_default_val),
    ('related_runtime_property',  False,  True,   True,   False,  _confirm_prop_val),
    ('related_chef_attribute',    False,  True,   True,   False,  KeyError),
    ('related_runtime_property',  True,   True,   True,   False,  _confirm_prop_val),
    ('related_chef_attribute',    True,   True,   True,   False,  _confirm_default_val),
    # ('related_runtime_property',  False,  False,  False,  True,   _confirm_no_attr),
    # ('related_chef_attribute',    False,  False,  False,  True,   _confirm_no_attr),
    # ('related_runtime_property',  True,   False,  False,  True,   _confirm_default_val),
    # ('related_chef_attribute',    True,   False,  False,  True,   _confirm_default_val),
    ('related_runtime_property',  False,  True,   False,  True,   KeyError),
    ('related_chef_attribute',    False,  True,   False,  True,   _confirm_chef_attr_val),
    ('related_runtime_property',  True,   True,   False,  True,   _confirm_default_val),
    ('related_chef_attribute',    True,   True,   False,  True,   _confirm_chef_attr_val),
    # ('related_runtime_property',  False,  False,  True,   True,   _confirm_no_attr),
    # ('related_chef_attribute',    False,  False,  True,   True,   _confirm_no_attr),
    # ('related_runtime_property',  True,   False,  True,   True,   _confirm_default_val),
    # ('related_chef_attribute',    True,   False,  True,   True,   _confirm_default_val),
    ('related_runtime_property',  False,  True,   True,   True,   _confirm_prop_val),
    ('related_chef_attribute',    False,  True,   True,   True,   _confirm_chef_attr_val),
    ('related_runtime_property',  True,   True,   True,   True,   _confirm_prop_val),
    ('related_chef_attribute',    True,   True,   True,   True,   _confirm_chef_attr_val),
)

methods = {m.__name__: m for m in map(_make_test, how)}
ChefPluginAttrubutesPassingTest = type('ChefPluginAttrubutesPassingTest', (ChefPluginTest, unittest.TestCase, b), methods)

class ChefPluginSoloTest(ChefPluginInstallationTest, unittest.TestCase):

    INSTALLATION_TYPE = 'solo'
    CORRECT_CHEF_MANAGER = chef_client.ChefSoloManager


class ChefPluginClientTest(ChefPluginInstallationTest, unittest.TestCase):

    INSTALLATION_TYPE = 'client'
    CORRECT_CHEF_MANAGER = chef_client.ChefClientManager

    def test_chef_installation(self):
        super(ChefPluginClientTest, self).test_chef_installation()
        ctx = self._make_context()
        chef_manager = chef_client.get_manager(ctx)
        self.assertIsInstance(chef_manager, self.__class__.CORRECT_CHEF_MANAGER)
        try:
            chef_manager.run(ctx, '', ctx.properties['chef_attributes'])
        except chef_client.ChefError:
            self.fail("Chef run failed")


class ChefPluginAttributesCaptureTest(ChefPluginWithHTTPServer, unittest.TestCase):

    def test_attributes_capture(self):
        ctx = _make_context(operation='install')
        chef_operations.operation(ctx)
        self.assertIn('chef_attributes', ctx.runtime_properties)
        for a in 'roles', 'recipes', 'tags':
            self.assertIn(a, ctx.runtime_properties['chef_attributes'])


if __name__ == '__main__':
    unittest.main()
