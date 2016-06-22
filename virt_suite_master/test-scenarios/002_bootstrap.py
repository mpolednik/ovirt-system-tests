#
# Copyright 2014 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#
import os

import nose.tools as nt
from ovirtsdk.xml import params

from lago import utils
from ovirtlago import testlib


# TODO: remove once lago can gracefully handle on-demand prefixes
def _get_prefixed_name(entity_name):
    suite = os.environ.get('SUITE')
    return (
        'lago_'
        + os.path.basename(suite).replace('.', '_')
        + '_' + entity_name
    )


# DC/Cluster
DC_NAME = 'test-dc'
DC_VER_MAJ = 4
DC_VER_MIN = 1
CLUSTER_NAME = 'test-cluster'
CLUSTER_CPU_FAMILY = 'Intel Conroe Family'

# Storage
MASTER_SD_TYPE = 'iscsi'

SD_NFS_NAME = 'nfs'
SD_NFS_HOST_NAME = _get_prefixed_name('storage')
SD_NFS_PATH = '/exports/nfs_clean/share1'

SD_ISCSI_NAME = 'iscsi'
SD_ISCSI_HOST_NAME = _get_prefixed_name('storage')
SD_ISCSI_TARGET = 'iqn.2014-07.org.ovirt:storage'
SD_ISCSI_PORT = 3260
SD_ISCSI_NR_LUNS = 2

SD_GLANCE_NAME = 'ovirt-image-repository'
GLANCE_AVAIL = False

# Network
VLAN100_NET = 'VLAN100_Network'


def _get_host_ip(prefix, host_name):
    return prefix.virt_env.get_vm(host_name).ip()


@testlib.with_ovirt_api
def add_dc(api):
    p = params.DataCenter(
        name=DC_NAME,
        local=False,
        version=params.Version(
            major=DC_VER_MAJ,
            minor=DC_VER_MIN,
        ),
    )
    nt.assert_true(api.datacenters.add(p))


@testlib.with_ovirt_api
def add_cluster(api):
    p = params.Cluster(
        name=CLUSTER_NAME,
        cpu=params.CPU(
            id=CLUSTER_CPU_FAMILY,
        ),
        version=params.Version(
            major=DC_VER_MAJ,
            minor=DC_VER_MIN,
        ),
        data_center=params.DataCenter(
            name=DC_NAME,
        ),
    )
    nt.assert_true(api.clusters.add(p))


@testlib.with_ovirt_prefix
def add_hosts(prefix):
    api = prefix.virt_env.engine_vm().get_api()

    def _add_host(vm):
        p = params.Host(
            name=vm.name(),
            address=vm.ip(),
            cluster=params.Cluster(
                name=CLUSTER_NAME,
            ),
            root_password=vm.root_password(),
            override_iptables=True,
        )

        return api.hosts.add(p)

    def _host_is_up():
        cur_state = api.hosts.get(host.name()).status.state

        if cur_state == 'up':
            return True

        if cur_state == 'install_failed':
            raise RuntimeError('Host %s failed to install' % host.name())

    hosts = prefix.virt_env.host_vms()
    vec = utils.func_vector(_add_host, [(h,) for h in hosts])
    vt = utils.VectorThread(vec)
    vt.start_all()
    nt.assert_true(all(vt.join_all()))

    for host in hosts:
        testlib.assert_true_within(_host_is_up, timeout=15 * 60)


def _add_storage_domain(api, p):
    dc = api.datacenters.get(DC_NAME)
    sd = api.storagedomains.add(p)
    nt.assert_true(sd)
    nt.assert_true(
        api.datacenters.get(
            DC_NAME,
        ).storagedomains.add(
            api.storagedomains.get(
                sd.name,
            ),
        )
    )

    if dc.storagedomains.get(sd.name).status.state == 'maintenance':
        sd.activate()
        testlib.assert_true_within_long(
            lambda: dc.storagedomains.get(sd.name).status.state == 'active'
        )


@testlib.with_ovirt_prefix
def add_master_storage_domain(prefix):
    add_iscsi_storage_domain(prefix)


def add_generic_nfs_storage_domain(prefix, sd_nfs_name, nfs_host_name,
                                   mount_path, sd_format='v3', sd_type='data'):
    api = prefix.virt_env.engine_vm().get_api()
    p = params.StorageDomain(
        name=sd_nfs_name,
        data_center=params.DataCenter(
            name=DC_NAME,
        ),
        type_=sd_type,
        storage_format=sd_format,
        host=params.Host(
            name=api.hosts.list().pop().name,
        ),
        storage=params.Storage(
            type_='nfs',
            address=_get_host_ip(prefix, nfs_host_name),
            path=mount_path,
        ),
    )
    _add_storage_domain(api, p)


def add_iscsi_storage_domain(prefix):
    api = prefix.virt_env.engine_vm().get_api()

    # Find LUN GUIDs
    ret = prefix.virt_env.get_vm(
        SD_ISCSI_HOST_NAME).ssh(['multipath', '-ll', '-v1', '|sort'])
    nt.assert_equals(ret.code, 0)

    lun_guids = ret.out.splitlines()[:SD_ISCSI_NR_LUNS]

    p = params.StorageDomain(
        name=SD_ISCSI_NAME,
        data_center=params.DataCenter(
            name=DC_NAME,
        ),
        type_='data',
        storage_format='v3',
        host=params.Host(
            name=api.hosts.list().pop().name,
        ),
        storage=params.Storage(
            type_='iscsi',
            volume_group=params.VolumeGroup(
                logical_unit=[
                    params.LogicalUnit(
                        id=lun_id,
                        address=_get_host_ip(
                            prefix,
                            SD_ISCSI_HOST_NAME,
                        ),
                        port=SD_ISCSI_PORT,
                        target=SD_ISCSI_TARGET,
                    ) for lun_id in lun_guids
                ]

            ),
        ),
    )
    _add_storage_domain(api, p)


@testlib.with_ovirt_api
def add_vm_network(api):
    VLAN100 = params.Network(
        name=VLAN100_NET,
        data_center=params.DataCenter(
            name=DC_NAME,
        ),
        description='VM Network on VLAN 100',
        vlan=params.VLAN(
            id='100',
        ),
    )

    nt.assert_true(
        api.networks.add(VLAN100)
    )
    nt.assert_true(
        api.clusters.get(CLUSTER_NAME).networks.add(VLAN100)
    )


_TEST_LIST = [
    add_dc,
    add_cluster,
    add_hosts,
    add_vm_network,
    add_master_storage_domain,
]


def test_gen():
    for t in testlib.test_sequence_gen(_TEST_LIST):
        test_gen.__name__ = t.description
        yield t
