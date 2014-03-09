from cloudify.decorators import operation as _operation

from cloudify_plugin_chef.chef_client import run_chef

EXPECTED_OP_PREFIX = 'cloudify.interfaces.lifecycle'

def _extract_op(ctx):
    prefix, _, op = ctx.operation.rpartition('.')
    if prefix != EXPECTED_OP_PREFIX:
        ctx.warn("Node operation is expected to start with '{0}' "
            "but starts with '{1}'".format(EXPECTED_OP_PREFIX, prefx))
    if op not in ctx.properties['chef_config']['runlists']:
        raise ValueError("chef_config.runlists does not have an entry for operation '{0}', "
            "only {1}".format(op, ','.join(ctx.properties['chef_config']['runlists'].keys())))
    return op

# Remember: attributes
@_operation
def operation(ctx, **kwargs):

    if 'runlist' in ctx.properties['chef_config']:
        runlist = ctx.properties['chef_config']['runlist']
    else:
        op = _extract_op(ctx)
        ctx.logger.info("Using Chef runlist for operation {0}".format(op))
        runlist = ctx.properties['chef_config']['runlists'][op]

    ctx.logger.info("Chef runlist: {0}".format(runlist))
    run_chef(ctx, runlist)
