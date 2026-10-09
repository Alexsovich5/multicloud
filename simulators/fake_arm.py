"""
In-memory stand-in for the Azure Resource Manager REST endpoints used by
azure-mgmt-resource (resource groups) and azure-mgmt-compute (virtual
machines). The api-version query parameter is accepted and ignored.

ARM matches paths case-insensitively. Werkzeug routing is case-sensitive and
runs before any Flask hook, so create_app() wraps the WSGI app in a
middleware that keeps the original path and lower-cases PATH_INFO. Routes are
declared in lower case, resources are keyed by lower-cased names, and
responses use the original-case names from the saved path.
"""

import os

from flask import Flask, jsonify, request

ORIGINAL_PATH_KEY = 'fake_arm.original_path'

RG_ROUTE = '/subscriptions/<sub>/resourcegroups/<rg>'
VMS_ROUTE = RG_ROUTE + '/providers/microsoft.compute/virtualmachines'
VM_ROUTE = VMS_ROUTE + '/<name>'

# Positions of the variable segments in a split request path.
SUB_INDEX = 2
RG_INDEX = 4
VM_INDEX = 8


class LowerCasePathMiddleware(object):
    """Save the original PATH_INFO and lower-case it before routing."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        environ[ORIGINAL_PATH_KEY] = path
        environ['PATH_INFO'] = path.lower()
        return self.wsgi_app(environ, start_response)


def _original_segment(index):
    """Return one segment of the request path in its original case."""
    path = request.environ.get(ORIGINAL_PATH_KEY, request.path)
    return path.rstrip('/').split('/')[index]


def _arm_error(status, code, message):
    resp = jsonify({'error': {'code': code, 'message': message}})
    resp.status_code = status
    return resp


def _rg_not_found(rg_name):
    return _arm_error(404, 'ResourceGroupNotFound',
                      "Resource group '%s' could not be found." % rg_name)


def _rg_id(sub, rg_name):
    return '/subscriptions/%s/resourceGroups/%s' % (sub, rg_name)


def _vm_id(sub, rg_name, vm_name):
    return '%s/providers/Microsoft.Compute/virtualMachines/%s' % (
        _rg_id(sub, rg_name), vm_name)


def _payload():
    return request.get_json(force=True, silent=True) or {}


def create_app():
    """Build a fake ARM Flask app with its own empty in-memory store."""
    app = Flask(__name__)
    app.wsgi_app = LowerCasePathMiddleware(app.wsgi_app)

    # {(sub, rg): resource group body}, keys lower-cased
    groups = {}
    # {(sub, rg, vm): virtual machine body}, keys lower-cased
    vms = {}

    @app.route(RG_ROUTE, methods=['PUT'])
    def put_resource_group(sub, rg):
        key = (sub, rg)
        rg_name = _original_segment(RG_INDEX)
        existed = key in groups
        if existed:
            rg_name = groups[key]['name']
        data = _payload()
        groups[key] = {
            'id': _rg_id(_original_segment(SUB_INDEX), rg_name),
            'name': rg_name,
            'type': 'Microsoft.Resources/resourceGroups',
            'location': data.get('location', ''),
            'tags': data.get('tags') or {},
            'properties': {'provisioningState': 'Succeeded'},
        }
        resp = jsonify(groups[key])
        resp.status_code = 200 if existed else 201
        return resp

    @app.route(RG_ROUTE, methods=['GET'])
    def get_resource_group(sub, rg):
        group = groups.get((sub, rg))
        if request.method == 'HEAD':
            # resource_groups.check_existence expects 204 or 404.
            return '', 404 if group is None else 204
        if group is None:
            return _rg_not_found(_original_segment(RG_INDEX))
        return jsonify(group)

    @app.route(VMS_ROUTE, methods=['GET'])
    def list_virtual_machines(sub, rg):
        found = [vm for (vm_sub, vm_rg, _), vm in sorted(vms.items())
                 if (vm_sub, vm_rg) == (sub, rg)]
        return jsonify({'value': found})

    @app.route(VM_ROUTE, methods=['PUT'])
    def put_virtual_machine(sub, rg, name):
        group = groups.get((sub, rg))
        if group is None:
            return _rg_not_found(_original_segment(RG_INDEX))
        key = (sub, rg, name)
        vm_name = vms[key]['name'] if key in vms else _original_segment(VM_INDEX)
        data = _payload()
        properties = dict(data.get('properties') or {})
        properties['provisioningState'] = 'Succeeded'
        vms[key] = {
            'id': _vm_id(_original_segment(SUB_INDEX), group['name'], vm_name),
            'name': vm_name,
            'type': 'Microsoft.Compute/virtualMachines',
            'location': data.get('location', group['location']),
            'tags': data.get('tags') or {},
            'properties': properties,
        }
        return jsonify(vms[key])

    @app.route(VM_ROUTE, methods=['GET'])
    def get_virtual_machine(sub, rg, name):
        vm = vms.get((sub, rg, name))
        if vm is None:
            return _arm_error(
                404, 'ResourceNotFound',
                "The Resource 'Microsoft.Compute/virtualMachines/%s' under resource "
                "group '%s' was not found." % (_original_segment(VM_INDEX),
                                               _original_segment(RG_INDEX)))
        return jsonify(vm)

    @app.route(VM_ROUTE, methods=['DELETE'])
    def delete_virtual_machine(sub, rg, name):
        if vms.pop((sub, rg, name), None) is None:
            return '', 204
        return '', 200

    return app


def main():
    port = int(os.environ.get('PORT', '5001'))
    create_app().run(host='0.0.0.0', port=port)


if __name__ == '__main__':
    main()
