# Copyright 2019 Intel Ltd.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock

from oslo_serialization import jsonutils
from oslo_utils import timeutils
from oslo_utils import uuidutils

from cyborg.common import constants
from cyborg.common import exception
from cyborg.common import utils
from cyborg.conf import CONF
from cyborg import objects
from cyborg.tests.unit.db import base
from cyborg.tests.unit import fake_deployable
from cyborg.tests.unit import fake_extarq


class TestExtARQJobMixin(base.DbTestCase):

    def setUp(self):
        super(TestExtARQJobMixin, self).setUp()
        self.fake_db_extarqs = fake_extarq.get_fake_db_extarqs()
        self.fake_obj_extarqs = fake_extarq.get_fake_extarq_objs()
        self.fake_obj_fpga_extarqs = fake_extarq.get_fake_fpga_extarq_objs()
        self.deployable_uuids = ['0acbf8d6-e02a-4394-aae3-57557d209498']
        self.classes = ["gpu", "no_program", "bitstream_program",
                        "function_program", "bad_program"]
        self.class_objects = dict(
            zip(self.classes, self.fake_obj_extarqs))
        self.class_dbs = dict(
            zip(self.classes, self.fake_db_extarqs))
        self.fpga_classes = ["no_program", "bitstream_program",
                             "function_program", "bad_program"]
        self.fpga_class_objects = dict(
            zip(self.fpga_classes, self.fake_obj_fpga_extarqs))
        self.bitstream_id = self.class_objects["bitstream_program"][
            "device_profile_group"][constants.ACCEL_BITSTREAM_ID]
        self.function_id = self.class_objects["function_program"][
            "device_profile_group"][constants.ACCEL_FUNCTION_ID]

    def test_get_resources_from_device_profile_group(self):
        expect = [("GPU", 1)] + [("FPGA", 1)] * 4
        actual = [v.get_resources_from_device_profile_group()
                  for v in self.class_objects.values()]
        self.assertEqual(expect, actual)

    def test_get_suitable_ext_arq(self):
        expect_type = [objects.ExtARQ] + [objects.FPGAExtARQ] * 4
        uuid = uuidutils.generate_uuid()
        groups = [v['device_profile_group']
                  for v in self.fake_db_extarqs]
        dp_db = {
            "id": self.fake_db_extarqs[0]['device_profile_id'],
            "uuid": uuid,
            "name": self.fake_db_extarqs[0]['device_profile_name'],
            "profile_json": jsonutils.dumps({"groups": groups}),
            "created_at": timeutils.utcnow().isoformat(),
            "updated_at": timeutils.utcnow().isoformat(),
        }
        for i, v in enumerate(self.classes):
            with mock.patch.object(self.dbapi, 'extarq_get') \
                as mock_extarq_get, \
                mock.patch.object(self.dbapi,
                                  "device_profile_get_by_id") \
                as mock_dp_get, \
                mock.patch.object(self.dbapi,
                                  "attach_handle_get_by_id") \
                as mock_ah_get:
                mock_ah_get.return_value = None
                mock_dp_get.return_value = dp_db
                self.fake_db_extarqs[i].update({
                    "state": constants.ARQ_BIND_STARTED,
                    "substate": constants.ARQ_BIND_STARTED,
                    "attach_handle_id": None,
                    "created_at": timeutils.utcnow().isoformat(),
                    "updated_at": timeutils.utcnow().isoformat()
                })
                self.fake_db_extarqs[i]["deployable_id"] = None
                mock_extarq_get.return_value = self.fake_db_extarqs[i]
                obj = self.class_objects[v]
                uuid = obj.arq.uuid
                typ = obj.get_suitable_ext_arq(self.context, uuid)
                self.assertIsInstance(typ, expect_type[i])

    def test_start_bind_job_raise(self):
        obj_extarq = self.class_objects["bitstream_program"]
        instance_uuid = obj_extarq.arq.instance_uuid
        uuid = obj_extarq.arq.uuid
        valid_fields = {
            uuid: {'hostname': obj_extarq.arq.hostname,
                   'device_rp_uuid': obj_extarq.arq.device_rp_uuid,
                   'instance_uuid': instance_uuid}
            }

        self.assertRaises(
            exception.ARQInvalidState, obj_extarq.start_bind_job,
            self.context, valid_fields)

    @mock.patch('cyborg.objects.extarq.ext_arq_job.ExtARQJobMixin._bind_job')
    @mock.patch('cyborg.objects.deployable.Deployable.get_by_device_rp_uuid')
    @mock.patch('cyborg.objects.ExtARQ.update_check_state')
    def test_start_bind_job(self, mock_state, mock_get_dep, mock_job):
        obj_extarq = self.class_objects["bitstream_program"]
        obj_extarq.arq.state = constants.ARQ_UNBOUND
        instance_uuid = obj_extarq.arq.instance_uuid
        uuid = obj_extarq.arq.uuid
        dep_uuid = self.deployable_uuids[0]
        fake_dep = fake_deployable.fake_deployable_obj(self.context,
                                                       uuid=dep_uuid)
        mock_get_dep.return_value = fake_dep

        valid_fields = {
            uuid: {'hostname': obj_extarq.arq.hostname,
                   'device_rp_uuid': obj_extarq.arq.device_rp_uuid,
                   'instance_uuid': instance_uuid}
            }
        obj_extarq.start_bind_job(self.context, valid_fields)
        mock_state.assert_called_once_with(
            self.context, constants.ARQ_BIND_STARTED)
        mock_job.assert_called_once_with(self.context, fake_dep)

    @mock.patch('cyborg.objects.FPGAExtARQ.bind')
    def test_gpu_arq_start_bind_job(self, mock_aysnc_bind):
        # Test GPU ARQ does not need async bind
        obj_extarq = self.class_objects["gpu"]
        obj_extarq.arq.state = constants.ARQ_UNBOUND
        dep_uuid = self.deployable_uuids[0]
        fake_dep = fake_deployable.fake_deployable_obj(self.context,
                                                       uuid=dep_uuid)
        is_job = getattr(obj_extarq.bind, "is_job", False)
        with mock.patch.object(obj_extarq, 'bind') as mock_bind:
            mock_bind.is_job = is_job
            obj_extarq._bind_job(self.context, fake_dep)
            mock_bind.assert_called_once_with(self.context, fake_dep)
            mock_aysnc_bind.assert_not_called()

    @mock.patch('cyborg.objects.ExtARQ.bind')
    def test_fpga_sync_start_bind_job(self, mock_bind):
        # Test FPGA with no program does not need async bind
        obj_extarq = self.fpga_class_objects["no_program"]
        obj_extarq.arq.state = constants.ARQ_UNBOUND
        dep_uuid = self.deployable_uuids[0]
        fake_dep = fake_deployable.fake_deployable_obj(self.context,
                                                       uuid=dep_uuid)
        need_bind = getattr(obj_extarq.bind, "is_job", False)
        with mock.patch.object(obj_extarq, 'bind') as mock_aysnc_bind:
            mock_aysnc_bind.is_job = need_bind
            obj_extarq._bind_job(self.context, fake_dep)
            mock_aysnc_bind.assert_called_once_with(self.context, fake_dep)
            mock_bind.assert_not_called()

    @mock.patch('cyborg.objects.ExtARQ.bind')
    @mock.patch('cyborg.common.utils.ThreadWorks.spawn')
    def test_fpga_async_start_bind_job(self, mock_spawn, mock_bind):
        # Test FPGA with bitstream program need async bind
        obj_extarq = self.fpga_class_objects["bitstream_program"]
        obj_extarq.arq.state = constants.ARQ_UNBOUND
        dep_uuid = self.deployable_uuids[0]
        fake_dep = fake_deployable.fake_deployable_obj(self.context,
                                                       uuid=dep_uuid)
        need_bind = getattr(obj_extarq.bind, "is_job", False)
        with mock.patch.object(obj_extarq, 'bind') as mock_aysnc_bind:
            mock_aysnc_bind.is_job = need_bind
            obj_extarq._bind_job(self.context, fake_dep)
            mock_spawn.assert_called_once_with(
                mock_aysnc_bind, self.context, fake_dep)
            mock_bind.assert_not_called()

    @mock.patch('cyborg.objects.ext_arq.ExtARQJobMixin.check_bindings_result')
    def test_master_with_instant(self, mock_result):
        # There are no async job, so will not start to monitor the job status
        arq_binds = {
            self.class_objects["gpu"]: None,
            self.class_objects["no_program"]: None,
        }
        objects.ext_arq.ExtARQ.master(self.context, arq_binds)
        mock_result.assert_called_once_with(self.context, arq_binds.keys())

    @mock.patch('cyborg.objects.ExtARQ.bind_notify')
    @mock.patch('cyborg.objects.ExtARQ.list')
    def test_check_bindings_result_with_arq_bound(
        self, mock_list, mock_notify):
        bind_status = [
            (e.arq.uuid, constants.ARQ_BIND_STATES_STATUS_MAP[e.arq.state])
            for e in self.fake_obj_extarqs]
        extarqs = self.fake_obj_extarqs
        mock_list.return_value = extarqs
        instance_uuid = extarqs[0].arq.instance_uuid
        objects.ExtARQ.check_bindings_result(
            self.context, extarqs)
        mock_notify.assert_called_once_with(instance_uuid, bind_status)

    @mock.patch('cyborg.objects.ext_arq.ExtARQJobMixin.check_bindings_result')
    def test_job_monitor_without_jobs(self, mock_result):
        works = utils.ThreadWorks()
        works_generator = works.get_workers_result(
            [], timeout=CONF.bind_timeout)

        extarqs = [self.class_objects["bitstream_program"],
                   self.class_objects["function_program"]]

        objects.ext_arq.ExtARQ.job_monitor(
            self.context, works_generator, extarqs)
        mock_result.assert_called_once_with(self.context, extarqs)

    @mock.patch('cyborg.common.nova_client.NovaAPI.notify_binding')
    @mock.patch('cyborg.common.nova_client.NovaAPI')
    def test_bind_notify(self, mock_api, mock_notify):
        mock_api.return_value = type(
            "NovaAPI", (object,), {"notify_binding": mock_notify})
        objects.ext_arq.ExtARQJobMixin.bind_notify(
            '5922a70f-1e06-4cfd-88dd-a332120d7144',
            [('a097fefa-da62-4630-8e8b-424c0e3426dc', 'completed')])
        mock_api.assert_called_once_with()
        mock_notify.assert_called_once_with(
            '5922a70f-1e06-4cfd-88dd-a332120d7144',
            [('a097fefa-da62-4630-8e8b-424c0e3426dc', 'completed')])
