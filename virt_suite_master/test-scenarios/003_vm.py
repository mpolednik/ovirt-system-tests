from ovirtlago import testlib

from ovirtsdk.xml import params

MB = 2 ** 20
GB = 2 ** 30

TEST_CLUSTER = 'test-cluster'
VM_NAME = 'test-vm'


@testlib.with_ovirt_api
def add_vm(api):
    vm_memory = 1024 * MB
    vm_params = params.VM(
        name=VM_NAME,
        memory=vm_memory,
        cluster=params.Cluster(
            name='test-cluster',
        ),
        display=params.Display(
            type_='spice',
        ),
        template=params.Template(
            name='Blank',
        ),
        os=params.OperatingSystem(
            boot=[params.Boot(dev='network')],
        ),
        delete_protected=True,
        soundcard_enabled=True,
    )
    api.vms.add(vm_params)
    testlib.assert_true_within_long(
        lambda: api.vms.get(VM_NAME).status.state == 'down',
    )
    testlib.assert_true_within_long(
        _add_nic(api.vms.get(VM_NAME))
    )
    testlib.assert_true_within_long(
        lambda: api.vms.get(VM_NAME).start(),
    )
    testlib.assert_true_within_long(
        lambda: api.vms.get(VM_NAME).status.state == 'up',
    )


def _add_nic(vm):
    NIC_NAME = 'eth0'
    nic_params = params.NIC(
        name=NIC_NAME,
        interface='virtio',
        network=params.Network(
            name='ovirtmgmt',
        ),
    )

    return vm.nics.add(nic_params)


_TEST_LIST = [
    add_vm,
]


def test_gen():
    for t in testlib.test_sequence_gen(_TEST_LIST):
        test_gen.__name__ = t.description
        yield t
