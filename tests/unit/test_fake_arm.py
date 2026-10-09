import json

import pytest

from simulators.fake_arm import create_app

SUB = '00000000-0000-0000-0000-000000000000'
RG_PATH = '/subscriptions/%s/resourcegroups/demo-rg' % SUB
VMS_PATH = ('/subscriptions/%s/resourceGroups/demo-rg'
            '/providers/Microsoft.Compute/virtualMachines' % SUB)
API = '?api-version=2018-06-01'

VM_BODY = {
    'location': 'eastus',
    'properties': {
        'hardwareProfile': {'vmSize': 'Standard_B2s'},
        'osProfile': {'computerName': 'web1', 'adminUsername': 'azureuser'},
    },
}


def body(resp):
    return json.loads(resp.get_data(as_text=True))


def put_json(client, path, data):
    return client.put(path + API, data=json.dumps(data), content_type='application/json')


@pytest.fixture
def client():
    return create_app().test_client()


@pytest.fixture
def rg_client(client):
    assert put_json(client, RG_PATH, {'location': 'eastus'}).status_code == 201
    return client


def test_put_resource_group_creates_then_get_returns_it(client):
    resp = put_json(client, RG_PATH, {'location': 'eastus'})
    assert resp.status_code == 201
    assert body(resp)['name'] == 'demo-rg'
    got = client.get(RG_PATH + API)
    assert got.status_code == 200
    data = body(got)
    assert data['name'] == 'demo-rg'
    assert data['location'] == 'eastus'
    assert data['properties']['provisioningState'] == 'Succeeded'
    assert data['id'] == '/subscriptions/%s/resourceGroups/demo-rg' % SUB


def test_put_existing_resource_group_returns_200(rg_client):
    resp = put_json(rg_client, RG_PATH, {'location': 'eastus'})
    assert resp.status_code == 200


def test_unknown_resource_group_is_404_with_arm_error(client):
    resp = client.get('/subscriptions/%s/resourcegroups/missing' % SUB + API)
    assert resp.status_code == 404
    error = body(resp)['error']
    assert error['code'] == 'ResourceGroupNotFound'
    assert 'missing' in error['message']


def test_put_vm_succeeds_and_sets_id(rg_client):
    resp = put_json(rg_client, VMS_PATH + '/web1', VM_BODY)
    assert resp.status_code == 200
    data = body(resp)
    assert data['properties']['provisioningState'] == 'Succeeded'
    assert data['properties']['hardwareProfile']['vmSize'] == 'Standard_B2s'
    assert data['id'] == VMS_PATH + '/web1'
    assert data['name'] == 'web1'
    assert data['location'] == 'eastus'
    assert data['type'] == 'Microsoft.Compute/virtualMachines'


def test_put_vm_in_unknown_resource_group_is_404(client):
    resp = put_json(client, VMS_PATH + '/web1', VM_BODY)
    assert resp.status_code == 404
    assert body(resp)['error']['code'] == 'ResourceGroupNotFound'


def test_get_unknown_vm_is_404_with_arm_error(rg_client):
    resp = rg_client.get(VMS_PATH + '/nope' + API)
    assert resp.status_code == 404
    assert body(resp)['error']['code'] == 'ResourceNotFound'


def test_list_is_filtered_by_resource_group(rg_client):
    other_rg = '/subscriptions/%s/resourcegroups/other-rg' % SUB
    other_vms = ('/subscriptions/%s/resourceGroups/other-rg'
                 '/providers/Microsoft.Compute/virtualMachines' % SUB)
    put_json(rg_client, other_rg, {'location': 'westus'})
    put_json(rg_client, VMS_PATH + '/web1', VM_BODY)
    put_json(rg_client, VMS_PATH + '/web2', VM_BODY)
    put_json(rg_client, other_vms + '/db1', VM_BODY)

    resp = rg_client.get(VMS_PATH + API)
    assert resp.status_code == 200
    assert sorted(vm['name'] for vm in body(resp)['value']) == ['web1', 'web2']
    other = body(rg_client.get(other_vms + API))['value']
    assert [vm['name'] for vm in other] == ['db1']


def test_list_in_unknown_resource_group_is_empty(client):
    resp = client.get(VMS_PATH + API)
    assert resp.status_code == 200
    assert body(resp) == {'value': []}


def test_delete_vm_then_get_is_404(rg_client):
    put_json(rg_client, VMS_PATH + '/web1', VM_BODY)
    resp = rg_client.delete(VMS_PATH + '/web1' + API)
    assert resp.status_code == 200
    assert rg_client.get(VMS_PATH + '/web1' + API).status_code == 404
    assert body(rg_client.get(VMS_PATH + API))['value'] == []


def test_delete_absent_vm_is_204(rg_client):
    assert rg_client.delete(VMS_PATH + '/ghost' + API).status_code == 204


def test_paths_match_case_insensitively(client):
    lower = '/subscriptions/%s/resourcegroups/Demo-RG' % SUB
    camel = '/subscriptions/%s/resourceGroups/demo-rg' % SUB
    assert put_json(client, lower, {'location': 'eastus'}).status_code == 201
    assert client.get(camel + API).status_code == 200
    assert put_json(client, camel, {'location': 'eastus'}).status_code == 200

    shouty = ('/SUBSCRIPTIONS/%s/RESOURCEGROUPS/DEMO-RG'
              '/PROVIDERS/microsoft.compute/VIRTUALMACHINES' % SUB)
    assert put_json(client, shouty + '/Web1', VM_BODY).status_code == 200
    got = client.get(VMS_PATH + '/web1' + API)
    assert got.status_code == 200
    assert body(got)['name'] == 'Web1'
    assert [vm['name'] for vm in body(client.get(VMS_PATH + API))['value']] == ['Web1']


def test_vm_keeps_original_case_name(rg_client):
    resp = put_json(rg_client, VMS_PATH + '/Web1', VM_BODY)
    assert body(resp)['name'] == 'Web1'
    assert body(resp)['id'].endswith('/virtualMachines/Web1')
    assert body(rg_client.get(VMS_PATH + '/WEB1' + API))['name'] == 'Web1'


def test_resource_group_keeps_original_case_name(client):
    put_json(client, '/subscriptions/%s/resourcegroups/Demo-RG' % SUB, {'location': 'eastus'})
    got = client.get('/subscriptions/%s/resourcegroups/demo-rg' % SUB + API)
    assert body(got)['name'] == 'Demo-RG'


def test_apps_do_not_share_state():
    first = create_app().test_client()
    second = create_app().test_client()
    assert put_json(first, RG_PATH, {'location': 'eastus'}).status_code == 201
    assert second.get(RG_PATH + API).status_code == 404
    assert put_json(second, RG_PATH, {'location': 'eastus'}).status_code == 201


def test_head_resource_group_reports_existence(client):
    assert client.head(RG_PATH + API).status_code == 404
    put_json(client, RG_PATH, {'location': 'eastus'})
    assert client.head(RG_PATH.upper() + API).status_code == 204
