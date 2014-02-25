# WIP !

require 'json'
require 'rest_client'


CLOUDIFY_CONFIG_FILE = '/etc/cloudify/config.json'

config = JSON.parse(IO.read(CLOUDIFY_CONFIG_FILE))

provides "cloudify"

cloudify Mash.new

# data = RestClient.get('http://www.json-generator.com/j/bIrOknVmBe?indent=4', {:accept => :json})
data = RestClient.get(config['rest']['url'] + '/nodes/' + config['node_id'], {:accept => :json})
data = JSON.parse(data)
cloudify[:info] = data

