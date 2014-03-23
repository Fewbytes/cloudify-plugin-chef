#!/bin/bash -e

DST=test-app/plugins/cloudify-plugin-chef

mkdir -p $DST
rsync --exclude=.git --exclude='*.swp' --exclude=test-app --exclude=tests -aP ../ $DST/
for res in environments roles cookbooks data_bags;do
	echo "+ Packing $res"
	tar -C tests -czf $DST/cloudify_plugin_chef/chef/$res.tar.gz $res
	ls -l $DST/cloudify_plugin_chef/chef/$res.tar.gz | sed -e 's/^/  /'
done
