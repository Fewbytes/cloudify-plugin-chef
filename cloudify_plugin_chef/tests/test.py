#!/usr/bin/env python

import os
import random
import re
import string
import subprocess
import unittest


from cloudify.mocks import MockCloudifyContext

import cloudify_plugin_chef.chef_client as chef_client
import cloudify_plugin_chef.operations as chef_operations

# Run on target machine!!!
SAFETY_FILE = '/tmp/do-run-chef-tests'
CHEF_VERSION = '11.4.4-2'
FILE_SERVER_PORT = '50000'

CHEF_CREATED_FILE_NAME = '/tmp/cloudify_plugin_chef_test.txt'
CHEF_CREATED_FILE_CONTENTS = ''.join([random.choice(
    string.ascii_uppercase + string.digits) for x in range(6)])


class ChefPluginTest(unittest.TestCase):

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
        ctx = MockCloudifyContext(
            node_id='clodufiy_app_node_id',
            operation='cloudify.interfaces.lifecycle.' +
            (operation or 'INVALID'),
            properties={
                'chef_version': CHEF_VERSION,
                'chef_cookbooks': 'http://127.0.0.1:' +
                FILE_SERVER_PORT + '/cookbooks.tar.gz',
                'chef_attributes': {
                    'create_file': {
                        'file_name': CHEF_CREATED_FILE_NAME,
                        'file_contents': CHEF_CREATED_FILE_CONTENTS,
                    }
                },
                'runlists': {
                    'install': 'recipe[create-file]'
                }
            }
        )
        return ctx

    def test_chef_installation(self):
        """Run Chef installation and check for expected"""
        # Assumption: chef-client version is the same
        ctx = self._make_context()
        chef_client.chef_manager = chef_client.get_manager(ctx)
        chef_client.chef_manager.install(ctx)
        output = subprocess.check_output(['sudo', 'chef-client', '-v'])
        m = re.match('^Chef: ([0-9.]+)', output)
        expected_version, _, _ = CHEF_VERSION.partition('-')
        self.assertEquals(m.group(1), expected_version)

    def test_chef_operation(self):
        ctx = self._make_context('install')
        chef_operations.node_operation(ctx)
        self.assertEquals(open(CHEF_CREATED_FILE_NAME).read(), CHEF_CREATED_FILE_CONTENTS)


if __name__ == '__main__':
    unittest.main()
