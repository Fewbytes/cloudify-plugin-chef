from cloudify.decorators import operation as _operation

from cloudify_plugin_chef.chef_client import run_chef

EXPECTED_OP_PREFIX = 'cloudify.interfaces.lifecycle'

# op -> ctx.method
operations_report_method = {
    'start': 'set_started',
    'stop': 'set_stop',
}

def _extract_op(ctx):
    prefix, _, op = ctx.operation.rpartition('.')
    if prefix != EXPECTED_OP_PREFIX:
        ctx.warn("Node operation is expected to start with '{0}' "
            "but starts with '{1}'".format(EXPECTED_OP_PREFIX, prefx))
    if op not in ctx.properties['runlists']:
        raise ValueError("runlists do not have an entry for operation '{0}', "
            "only {1}".format(op, ','.join(ctx.properties['runlists'].keys())))
    return op

# Remember: attributes
@_operation
def operation(ctx, **kwargs):
    op = _extract_op(ctx)
    if not ctx.properties['runlists'].get(op):
        ctx.logger.info("Runlist for operation {0} does not exist or "
                        "is empty. Node: {1}".format(op, ctx.node_name))

    run_chef(ctx, ctx.properties['runlists'][op])

    report_method = operations_report_method.get(op)
    if report_method:
        getattr(ctx, report_method)()
