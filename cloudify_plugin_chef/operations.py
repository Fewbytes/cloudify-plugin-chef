from cloudify.decorators import operation as _operation

from cloudify_plugin_chef.chef_client import run_chef

EXPECTED_OP_PREFIXES = (
    'cloudify.interfaces.lifecycle',
    'cloudify.interfaces.relationship_lifecycle')


def _extract_op(ctx):
    prefix, _, op = ctx.operation.rpartition('.')
    if prefix not in EXPECTED_OP_PREFIXES:
        ctx.logger.warn("Node operation is expected to start with '{0}' "
                        "but starts with '{1}'".format(
                            ' or '.join(EXPECTED_OP_PREFIXES), prefix))
    return op


@_operation
def operation(ctx, **kwargs):

    if 'runlist' in ctx.properties['chef_config']:
        ctx.logger.info("Using explicitly provided Chef runlist")
        runlist = ctx.properties['chef_config']['runlist']
    else:
        op = _extract_op(ctx)
        if op not in ctx.properties['chef_config']['runlists']:
            ctx.logger.warn("No Chef runlist for operation {0}".format(op))
        ctx.logger.info("Using Chef runlist for operation {0}".format(op))
        runlist = ctx.properties['chef_config']['runlists'].get(op)

    if isinstance(runlist, list):
        runlist = ','.join(runlist)

    ctx.logger.info("Chef runlist: {0}".format(runlist))
    run_chef(ctx, runlist)
