Running tests
=============

The tests here must run on the target machine, not on developer's laptop and not on manager.
Missing safety file (`/tmp/do-run-chef-tests`) should help against accidental runs.


Setting up target machine
-------------------------

Sample:

    apt-get install python-virtualenv
    # If your Chef server has no DNS resolve:
    grep -q YOUR_CHEF_SERVER_HOSTNAME /etc/hosts || echo "YOUR_CHEF_SERVER_IP YOUR_CHEF_SERVER_HOSTNAME" >> /etc/hosts
    su - ilya
    virtualenv E
    source E/bin/activate
    pip install https://github.com/CloudifySource/cosmo-celery-common/archive/develop.zip
    pip install https://github.com/Fewbytes/cosmo-plugin-common/archive/master.zip

Running the tests
-----------------

Sample run on VirtualBox with port forwarding (2223 -> 22)

    DST=/home/ilya/E/lib/python2.7/site-packages/cloudify_plugin_chef; rsync --exclude='*.swp' --exclude='*.pyc' -aP --delete --rsh='ssh -p2223' cloudify_plugin_chef/ ilya@127.0.0.1:$DST/ && ssh -p 2223 ilya@127.0.0.1 "touch /tmp/do-run-chef-tests; source E/bin/activate && python -m cloudify_plugin_chef.tests.test ChefPluginClientTest"
    DST=/home/ilya/E/lib/python2.7/site-packages/cloudify_plugin_chef; rsync --exclude='*.swp' --exclude='*.pyc' -aP --delete --rsh='ssh -p2223' cloudify_plugin_chef/ ilya@127.0.0.1:$DST/ && ssh -p 2223 ilya@127.0.0.1 "touch /tmp/do-run-chef-tests; source E/bin/activate && python -m cloudify_plugin_chef.tests.test ChefPluginSoloTest"

Or some specific test:

    DST=/home/ilya/E/lib/python2.7/site-packages/cloudify_plugin_chef; rsync --exclude='*.swp' --exclude='*.pyc' -aP --delete --rsh='ssh -p2223' cloudify_plugin_chef/ ilya@127.0.0.1:$DST/ && ssh -p 2223 ilya@127.0.0.1 "touch /tmp/do-run-chef-tests; source E/bin/activate && python -m cloudify_plugin_chef.tests.test ChefPluginSoloTest.test_chef_operation"
