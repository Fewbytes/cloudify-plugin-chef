Running tests
=============

The tests here must run on the target machine, not on developer's laptop and not on manager.
Missing safety file (`/tmp/do-run-chef-tests`) should help against accidental runs.


Setting up target machine
-------------------------

Sample:

    apt-get install python-virtualenv
    su - ilya
    virtualenv E
    source E/bin/activate
    pip install https://github.com/CloudifySource/cosmo-celery-common/archive/develop.zip

Running the tests
-----------------

Sample run on VirtualBox with port forwarding (2223 -> 22)

    DST=/home/ilya/E/lib/python2.7/site-packages/cloudify_plugin_chef; rsync --exclude='*.swp' --exclude='*.pyc' -aP --delete --rsh='ssh -p2223' cloudify_plugin_chef/ ilya@127.0.0.1:$DST/ && ssh -p 2223 ilya@127.0.0.1 "touch /tmp/do-run-chef-tests; source E/bin/activate && python -m cloudify_plugin_chef.tests.test ChefPluginTest"

Or some specific test:
    DST=/home/ilya/E/lib/python2.7/site-packages/cloudify_plugin_chef; rsync --exclude='*.swp' --exclude='*.pyc' -aP --delete --rsh='ssh -p2223' cloudify_plugin_chef/ ilya@127.0.0.1:$DST/ && ssh -p 2223 ilya@127.0.0.1 "touch /tmp/do-run-chef-tests; source E/bin/activate && python -m cloudify_plugin_chef.tests.test ChefPluginTest.test_chef_operation"
