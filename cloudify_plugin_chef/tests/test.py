#!/usr/bin/env python

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

class ChefPluginTest(object):

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
        subprocess.call(['fuser', '-k', FILE_SERVER_PORT + '/tcp'])
        subprocess.Popen(
            ['python', '-m', 'SimpleHTTPServer', FILE_SERVER_PORT])

    def tearDown(self):
        subprocess.call(['fuser', '-k', FILE_SERVER_PORT + '/tcp'])

    def _make_context(self, operation=None):
        inst = self.__class__.INSTALLATION_TYPE
        props = tests_config[inst]['properties']
        props.setdefault('chef_attributes', {})
        props['chef_attributes'].setdefault('create_file', {})
        props['chef_attributes']['create_file'].setdefault('file_name', CHEF_CREATED_FILE_NAME)
        props['chef_attributes']['create_file'].setdefault('file_contents', CHEF_CREATED_FILE_CONTENTS)
        ctx = MockCloudifyContext(
            node_id='clodufiy_app_node_id',
            operation='cloudify.interfaces.lifecycle.' +
            (operation or 'INVALID'),
            properties=props
        )
        return ctx

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

    def test_chef_operation(self):
        ctx = self._make_context(operation='install')
        chef_operations.node_operation(ctx)
        create_file_attrs = ctx.properties['chef_attributes']['create_file']
        f = create_file_attrs['file_name']
        c = create_file_attrs['file_contents']
        self.assertEquals(open(f).read(), c)


class ChefPluginSoloTest(ChefPluginTest, unittest.TestCase):

    INSTALLATION_TYPE = 'solo'
    CORRECT_CHEF_MANAGER = chef_client.ChefSoloManager


class ChefPluginClientTest(ChefPluginTest, unittest.TestCase):

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

if __name__ == '__main__':
    unittest.main()
