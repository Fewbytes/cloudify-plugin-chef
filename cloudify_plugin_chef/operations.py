from cloudify.decorators import operation

from cloudify_plugin_chef.chef_client import run_chef

# op -> ctx.method
operations_report_method = {
    'start': 'set_started',
    'stop': 'set_stop',
}

# Remember: attributes
@operation
def node_operation(ctx, **kwargs):
    _, _, op = ctx.operation.rpartition('.')
    if op not in ctx.properties['runlists']:
        raise ValueError("runlists do not have an entry for operation '{0}', "
            "only {1}".format(op, ','.join(ctx.properties['runlists'].keys())))
    run_chef(ctx, ctx.properties['runlists'][op])

    report_method = operations_report_method.get(op)
    if report_method:
        getattr(ctx, report_method)()

@operation
def relation_operation(ctx, **kwargs):
    raise NotImplemented("cloudify_plugin_chef.relation_operation() is not implemented yet")
