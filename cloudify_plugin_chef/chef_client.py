#/*******************************************************************************
# * Copyright (c) 2013 GigaSpaces Technologies Ltd. All rights reserved
# *
# * Licensed under the Apache License, Version 2.0 (the "License");
# * you may not use this file except in compliance with the License.
# * You may obtain a copy of the License at
# *
# *       http://www.apache.org/licenses/LICENSE-2.0
# *
# * Unless required by applicable law or agreed to in writing, software
# * distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.
# *******************************************************************************/

"""
This module provides functions for installing, configuring and running chef-client against an existing chef-server or chef-solo.

This module is specifically meant to be used for the cosmo celery tasks
which import the `run_chef` function.
"""

import re
import requests
import os
import stat
import urllib
import tempfile
import subprocess
import json
import errno

CHEF_INSTALLER_URL = "https://www.opscode.com/chef/install.sh"
ROLES_DIR = "/var/chef/roles"
ENVS_DIR = "/var/chef/environments"
DATABAGS_DIR = "/var/chef/data_bags"

ENVS_MIN_VER = [11, 8]
ENVS_MIN_VER_STR = '.'.join([str(x) for x in ENVS_MIN_VER])


class SudoError(Exception):
    """An internal exception for failures when running an os command with sudo"""
    pass


class ChefError(Exception):
    """An exception for all chef related errors"""
    pass


class ChefManager(object):

    @classmethod
    def can_handle(cls, ctx):
        # All of the required args exist and are not None:
        return all([ctx.properties.get(arg) is not None for arg in cls.REQUIRED_ARGS])

    @classmethod
    def assert_args(cls, ctx):
        missing_fields = (cls.REQUIRED_ARGS).union({'chef_version'}).difference(ctx.properties.keys())
        if missing_fields:
            raise ChefError("The following required field(s) are missing: {0}".format(", ".join(missing_fields)))

    def get_version(self):
        """Check if chef-client is available and is of the right version"""
        binary = self._get_binary()
        if not self._prog_available_for_root(binary):
            return None

        return self._extract_chef_version(subprocess.check_output(["/usr/bin/sudo", binary, "--version"]))

    def install(self, ctx):
        """If needed, install chef-client and point it to the server"""
        chef_version = ctx.properties['chef_version']
        current_version = self.get_version()
        if current_version:
            if current_version == self._extract_chef_version(chef_version):
                ctx.logger.info("Chef version {0} is already installed. Skipping installation.".format(chef_version))
                return
            else:
                # XXX: not tested
                ctx.logger.info("Uninstalling Chef: requested version {0} does not match the installed version {1}".format(chef_version, current_version))
                self.uninstall(ctx)

        ctx.logger.info('Installing Chef [chef_version=%s]', chef_version)
        chef_install_script = tempfile.NamedTemporaryFile(suffix="install.sh", delete=False)
        chef_install_script.close()
        try:
            urllib.urlretrieve(CHEF_INSTALLER_URL, chef_install_script.name)
            os.chmod(chef_install_script.name, stat.S_IRWXU)
            self._sudo(ctx, chef_install_script.name, "-v", chef_version)
            os.remove(chef_install_script.name)  # on failure, leave for debugging
        except Exception as exc:
            raise ChefError("Chef install failed on:\n%s" % exc)

        ctx.logger.info('Setting up Chef [chef_server=\n%s]', ctx.properties.get('chef_server_url'))

        for directory in '/etc/chef', '/var/chef', '/var/log/chef', DATABAGS_DIR, ENVS_DIR, ROLES_DIR:
            self._sudo(ctx, "mkdir", "-p", directory)

        self._install_files(ctx)

    # XXX: fetch ohai plugin from file server
    def install_ohai_plugin(self, ctx):
        out, _ = self._sudo(ctx, 'ohai')
        data = json.loads(out)
        ohai_root = data['chef_packages']['ohai']['ohai_root']
        plugins_source_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ohai', 'plugins')
        plugins_destination_path = os.path.join(ohai_root)

        subprocess.Popen(
            ['sudo', 'cp', '-r', plugins_source_path, plugins_destination_path])


    def uninstall(self, ctx):
        """Uninstall chef-client - currently only supporting apt-get"""
        #TODO: I didn't find a single method encouraged by opscode,
        #      so we need to add manually for any supported platform
        def apt_platform():  # assuming that if apt-get exists, it's how chef was installed
            return self._prog_available_for_root('apt-get')

        if apt_platform():
            ctx.logger.info("Uninstalling old Chef via apt-get")
            try:
                self._sudo(ctx, "apt-get", "remove", "--purge", "chef", "-y")
            except SudoError as exc:
                raise ChefError("chef-client uninstall failed on:\n%s" % exc)
        else:
            ctx.logger.error("Chef uninstall is unimplemented for this platform, proceeding anyway")

    def run(self, ctx, runlist, chef_attributes):
        self._prepare_for_run(ctx, runlist)
        self.attribute_file = tempfile.NamedTemporaryFile(suffix="chef_attributes.json",
                                                          delete=False)
        # print(json.dumps(chef_attributes))
        json.dump(chef_attributes, self.attribute_file)
        self.attribute_file.close()

        cmd = self._get_cmd(ctx, runlist)

        try:
            self._sudo(ctx, *cmd)
            os.remove(self.attribute_file.name)  # on failure, leave for debugging
        except SudoError as exc:
            raise ChefError("The chef run failed\n"
                            "runlist: {0}\nattributes: {1}\nexception: \n{2}".format(runlist, chef_attributes, exc))

    def _prepare_for_run(self, ctx, runlist):
        pass

    # Utilities from here to end of the class

    def _extract_chef_version(self, version_string):
        match = re.search(r'(\d+\.\d+\.\d+)', version_string)
        if match:
            return match.groups()[0]
        else:
            raise ChefError("Failed to read chef version - '%s'" % version_string)

    def _prog_available_for_root(self, prog):
        with open(os.devnull, "w") as fnull:
            which_exitcode = subprocess.call(["/usr/bin/sudo", "which", prog], stdout=fnull, stderr=fnull)
        return which_exitcode == 0

    def _sudo(self, ctx, *args):
        """a helper to run a subprocess with sudo, raises SudoError"""

        def get_file_contents(f):
            f.flush()
            f.seek(0)
            return f.read()

        cmd = ["/usr/bin/sudo"] + list(args)
        ctx.logger.info("Running: '%s'", ' '.join(cmd))

        #TODO: Should we put the stdout/stderr in the celery logger? should we also keep output of successful runs?
        #      per log level? Also see comment under run_chef()
        stdout = tempfile.TemporaryFile('rw+b')
        stderr = tempfile.TemporaryFile('rw+b')
        out = None
        err = None
        try:
            subprocess.check_call(cmd, stdout=stdout, stderr=stderr)
            out = get_file_contents(stdout)
            err = get_file_contents(stderr)
            if out:
                ctx.logger.info("Chef stdout follows: \n%s", out)
            if err:
                ctx.logger.info("Chef stderr follows: \n%s", err)
        except subprocess.CalledProcessError as exc:
            raise SudoError("{exc}\nSTDOUT:\n{stdout}\nSTDERR:{stderr}".format(
                exc=exc, stdout=get_file_contents(stdout), stderr=get_file_contents(stderr))
            )
        finally:
            stdout.close()
            stderr.close()

        return out, err

    def _sudo_write_file(self, ctx, filename, contents):
        """a helper to create a file with sudo"""
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(contents)

        self._sudo(ctx, "mv", temp_file.name, filename)


class ChefClientManager(ChefManager):

    """ Installs Chef client """

    NAME = 'client'
    REQUIRED_ARGS = {'chef_server_url', 'chef_validator_name', 'chef_validation', 'chef_environment'}

    def _get_cmd(self, ctx, runlist):
        return ["chef-client", "-o", runlist, "-j", self.attribute_file.name, "--force-formatter"]

    def _get_binary(self):
        return 'chef-client'

    def _install_files(self, ctx):
        if ctx.properties.get('chef_validation'):
            self._sudo_write_file(ctx, '/etc/chef/validation.pem', ctx.properties['chef_validation'])
        self._sudo_write_file(ctx, '/etc/chef/client.rb',
            '# This file was generated by Cloudify Chef plugin\n'
            '# Also, Chef client was installed by Cloudify Chef plugin\n'
            'log_level              :info\n'
            'log_location           "/var/log/chef/client.log"\n'
            'ssl_verify_mode        :verify_none\n'
            'validation_client_name "{chef_validator_name}"\n'
            'validation_key         "/etc/chef/validation.pem"\n'
            'client_key             "/etc/chef/client.pem"\n'
            'chef_server_url        "{chef_server_url}"\n'
            'environment            "{chef_environment}"\n'
            'file_cache_path        "/var/chef/cache"\n'
            'file_backup_path       "/var/chef/backup"\n'
            'pid_file               "/var/run/chef/client.pid"\n'
            'Chef::Log::Formatter.show_time = true\n'.format(**ctx.properties)
        )


class ChefSoloManager(ChefManager):

    """ Installs Chef solo """

    NAME = 'solo'
    REQUIRED_ARGS = {'chef_cookbooks'}

    def _url_to_dir(self, ctx, url, dst_dir):
        """Downloads .tar.gz from `url` and extracts to `dst_dir`"""

        if url is None:
            return

        ctx.logger.info("Downloading from {0} and unpacking to {1}".format(url, dst_dir))
        temp_archive = tempfile.NamedTemporaryFile(suffix='.url_to_dir.tar.gz', delete=False)
        temp_archive.write(requests.get(url).content)
        temp_archive.flush()
        temp_archive.close()
        command_list = ['tar', '-C', dst_dir, '--xform', 's#^' + os.path.basename(dst_dir) + '/##', '-xzf', temp_archive.name]
        try:
            ctx.logger.info("Running: '%s'", ' '.join(command_list))
            subprocess.check_call(command_list)
        except subprocess.CalledProcessError as exc:
            raise ChefError("Failed to extract file {0} to directory {1} which was downloaded from {2}. Command: {3} Exception: {4}".format(temp_archive.name, dst_dir, url, command_list, exc))
        os.remove(temp_archive.name)  # on failure, leave for debugging
        try:
            os.rmdir(os.path.join(dst_dir, os.path.basename(dst_dir)))
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise e

    def _prepare_for_run(self, ctx, runlist):
        for dl in ('chef_environments', ENVS_DIR), ('chef_databags', DATABAGS_DIR), ('chef_roles', ROLES_DIR):
            self._url_to_dir(ctx, ctx.properties.get(dl[0]), dl[1])

    def _get_cmd(self, ctx, runlist):
        cmd = ["chef-solo"]

        if ctx.properties.get('chef_environment', '_default') != '_default':
            v = self.get_version()
            if [int(x) for x in v.split('.')] < ENVS_MIN_VER:
                raise ChefError("Chef solo environments are supported starting at {0} but you are using {1}".
                                format(ENVS_MIN_VER_STR, v))
            cmd += ["-E", ctx.properties['chef_environment']]
        cmd += [
            "-o", runlist,
            "-j", self.attribute_file.name,
            "--force-formatter",
            "-r", ctx.properties['chef_cookbooks']
        ]
        return cmd

    def _get_binary(self):
        return 'chef-solo'

    def _install_files(self, ctx):
        # Do not put 'environment' in this file.
        # It causes chef solo to act as client (than fails when certificate is missing)
        self._sudo_write_file(ctx, '/etc/chef/solo.rb',
            'log_location       "/var/log/chef/solo.log"')


def get_manager(ctx):
    managers = ChefClientManager, ChefSoloManager
    for cls in managers:
        if cls.can_handle(ctx):
            ctx.logger.info("Chef manager class to be used: {0}".format(cls.__name__))
            cls.assert_args(ctx)
            return cls()
    arguments_sets = '; '.join(['(for ' + m.NAME + '): ' + ', '.join(list(m.REQUIRED_ARGS)) for m in managers])
    raise ChefError("Failed to find appropriate Chef manager for the specified arguments ({0}). Possible arguments sets are: {1}".format(ctx.properties, arguments_sets))


def _context_to_struct(ctx):
    return {
        'node_id': ctx.node_id,
        'runtime_properties': ctx.runtime_properties,
        'capabilities': ctx.capabilities.get_all(),
    }

def run_chef(ctx, runlist):
    """Run given runlist using Chef.
    ctx.properties.chef_attributes can be a dict or a JSON.
    """

    if runlist is None:
        return

    chef_attributes = ctx.properties.get('chef_attributes', {})

    # If chef_attributes is JSON
    if isinstance(chef_attributes, basestring) and chef_attributes != '':
        try:
            chef_attributes = json.loads(chef_attributes)
        except ValueError:
            raise ChefError("Failed json validation of chef chef_attributes:\n%s" % chef_attributes)

    if 'cloudify' in chef_attributes:
        raise ValueError("Chef attributes must not contain 'cloudify'")

    chef_attributes['cloudify'] = _context_to_struct(ctx)

    if ctx.related:
        chef_attributes['cloudify']['related'] = _context_to_struct(ctx.related)

    chef_manager = get_manager(ctx)
    chef_manager.install(ctx)
    chef_manager.run(ctx, runlist, chef_attributes)

if __name__ == '__main__':
    raise NotImplemented("cloudify_plugin_chef - running from CLI is outdated")
    import argparse
    import logging as l
    parser = argparse.ArgumentParser(
        description="Installs and runs Chef (client or solo)"
    )
    # common
    parser.add_argument(
        '-r', '--run-list',
        type=str
    )
    parser.add_argument(
        '-a', '--attributes',
        type=str
    )
    # solo
    parser.add_argument(
        '--cookbooks',
        help='Cookbooks .tar.gz URL',
        type=str
    )
    parser.add_argument(
        '--databags',
        help='Data bags .tar.gz URL',
        type=str
    )
    parser.add_argument(
        '--environments',
        help='Environments .tar.gz URL',
        type=str
    )
    parser.add_argument(
        '--roles',
        help='Roles .tar.gz URL',
        type=str
    )
    # client
    parser.add_argument(
        '-e', '--environment',
        type=str,
        default='_default',
    )
    parser.add_argument(
        '-u', '--url',
        help='Server URL',
        type=str,
    )
    parser.add_argument(
        '--val-c',
        help='Validation certificate. You can use caret (^) characters instead of newlines for convenience to pass the certificate in one line.',
        type=str,
    )

    parser.add_argument(
        '--val-n',
        help='Validator name',
        type=str,
    )

    parser.add_argument(
        '--as-source-properties',
        default=False,
        dest='as_source_properties',
        action='store_true',
    )

    parser.set_defaults(as_source_properties=False)
    args = parser.parse_args()

    if args.val_c:
        chef_validation = args.val_c.replace('^', '\n')
    else:
        chef_validation = None

    if args.attributes:
        chef_attributes = json.loads(args.attributes)
    else:
        chef_attributes = {}

    # Setup global logger:
    logger = l.getLogger('cosmo_plugin_chef_client_common')
    logger.setLevel(l.DEBUG)
    ch = l.StreamHandler()
    ch.setLevel(l.DEBUG)
    logger.addHandler(ch)

    kwargs = dict(
        chef_environment=args.environment,
        chef_version='11.8.0',

        chef_cookbooks=args.cookbooks,
        chef_databags=args.databags,
        chef_environments=args.environments,
        chef_roles=args.roles,

        chef_server_url=args.url,
        chef_validator_name=args.val_n,
        chef_validation=chef_validation
    )
    if args.as_source_properties:
        kwargs = {'__source_properties': kwargs}
    run_chef(args.run_list, chef_attributes, **kwargs)
