import sys
from unittest import TestCase

if sys.version_info.major == 3:
    from unittest import mock
else:
    import mock


from sonic_ax_impl.mibs.ietf.rfc4292 import RouteUpdater

class TestRouteUpdater(TestCase):

    @mock.patch('sonic_py_common.multi_asic.get_all_namespaces', mock.MagicMock(return_value=({"front_ns": ['']})))
    @mock.patch('swsscommon.swsscommon.SonicV2Connector.get_all', mock.MagicMock(return_value=({"nexthop": "10.0.0.1", "ifname": "Ethernet0"})))
    def test_RouteUpdater_route_has_next_hop_and_iframe(self):
        updater = RouteUpdater()

        with mock.patch('sonic_ax_impl.mibs.logger.warning') as mocked_warning:
            updater.update_data()
            
            # check warning
            mocked_warning.assert_not_called()

        self.assertTrue(len(updater.route_dest_list) == 1)
        self.assertTrue(updater.route_dest_list[0] == (0, 0, 0, 0, 0, 0, 0, 0, 0, 10, 0, 0, 1))

    @mock.patch('sonic_py_common.multi_asic.get_all_namespaces', mock.MagicMock(return_value=({"front_ns": ['']})))
    @mock.patch('swsscommon.swsscommon.SonicV2Connector.get_all', mock.MagicMock(return_value=({"ifname": "Ethernet0"})))
    def test_RouteUpdater_route_no_next_hop(self):
        updater = RouteUpdater()

        with mock.patch('sonic_ax_impl.mibs.logger.warning') as mocked_warning:
            updater.update_data()
            
            # check warning
            expected = [
                mock.call("Route has no nexthop: ROUTE_TABLE:0.0.0.0/0 {'ifname': 'Ethernet0'}")
            ]
            mocked_warning.assert_has_calls(expected)

        self.assertTrue(len(updater.route_dest_list) == 0)

    @mock.patch('sonic_py_common.multi_asic.get_all_namespaces', mock.MagicMock(return_value=({"front_ns": ['']})))
    @mock.patch('swsscommon.swsscommon.SonicV2Connector.get_all')
    def test_RouteUpdater_route_nexthop_group(self, mocked_get_all):
        # fpmsyncd with use-next-hop-groups: empty inline nexthop, members in NEXTHOP_GROUP_TABLE
        tables = {
            "ROUTE_TABLE:0.0.0.0/0": {"nexthop": "", "ifname": "", "nexthop_group": "12", "protocol": "bgp"},
            "NEXTHOP_GROUP_TABLE:12": {"nexthop": "10.0.0.1", "ifname": "Ethernet0"},
        }
        mocked_get_all.side_effect = lambda db, key, blocking=False: tables.get(key)
        updater = RouteUpdater()

        with mock.patch('sonic_ax_impl.mibs.logger.warning') as mocked_warning:
            updater.update_data()
            mocked_warning.assert_not_called()

        self.assertTrue(len(updater.route_dest_list) == 1)
        self.assertTrue(updater.route_dest_list[0] == (0, 0, 0, 0, 0, 0, 0, 0, 0, 10, 0, 0, 1))

    @mock.patch('sonic_py_common.multi_asic.get_all_namespaces', mock.MagicMock(return_value=({"front_ns": ['']})))
    @mock.patch('swsscommon.swsscommon.SonicV2Connector.get_all')
    def test_RouteUpdater_route_class_based_nexthop_group(self, mocked_get_all):
        tables = {
            "ROUTE_TABLE:0.0.0.0/0": {"nexthop": "", "ifname": "", "nexthop_group": "cbf1"},
            "CLASS_BASED_NEXT_HOP_GROUP_TABLE:cbf1": {"members": "12,13", "selection_map": "AZURE"},
            "NEXTHOP_GROUP_TABLE:12": {"nexthop": "10.0.0.1,10.0.0.3", "ifname": "Ethernet0,Ethernet4"},
            "NEXTHOP_GROUP_TABLE:13": {"nexthop": "10.0.0.3", "ifname": "Ethernet4"},
        }
        mocked_get_all.side_effect = lambda db, key, blocking=False: tables.get(key)
        updater = RouteUpdater()

        with mock.patch('sonic_ax_impl.mibs.logger.warning') as mocked_warning:
            updater.update_data()
            mocked_warning.assert_not_called()

        self.assertEqual(updater.route_dest_list, [
            (0, 0, 0, 0, 0, 0, 0, 0, 0, 10, 0, 0, 1),
            (0, 0, 0, 0, 0, 0, 0, 0, 0, 10, 0, 0, 3),
        ])

    @mock.patch('sonic_py_common.multi_asic.get_all_namespaces', mock.MagicMock(return_value=({"front_ns": ['']})))
    @mock.patch('swsscommon.swsscommon.SonicV2Connector.get_all')
    def test_RouteUpdater_route_class_based_nexthop_group_member_missing(self, mocked_get_all):
        # Member 13 has no group row: it is warned and skipped, the rest still resolve.
        tables = {
            "ROUTE_TABLE:0.0.0.0/0": {"nexthop": "", "ifname": "", "nexthop_group": "cbf1"},
            "CLASS_BASED_NEXT_HOP_GROUP_TABLE:cbf1": {"members": "12,13", "selection_map": "AZURE"},
            "NEXTHOP_GROUP_TABLE:12": {"nexthop": "10.0.0.1", "ifname": "Ethernet0"},
        }
        mocked_get_all.side_effect = lambda db, key, blocking=False: tables.get(key)
        updater = RouteUpdater()

        with mock.patch('sonic_ax_impl.mibs.logger.warning') as mocked_warning:
            updater.update_data()
            mocked_warning.assert_called_once_with("Nexthop group cbf1 member missing: 13")

        self.assertEqual(updater.route_dest_list, [(0, 0, 0, 0, 0, 0, 0, 0, 0, 10, 0, 0, 1)])

    @mock.patch('sonic_py_common.multi_asic.get_all_namespaces', mock.MagicMock(return_value=({"front_ns": ['']})))
    @mock.patch('swsscommon.swsscommon.SonicV2Connector.get_all')
    def test_RouteUpdater_route_nested_nexthop_group(self, mocked_get_all):
        # A NEXTHOP_GROUP_TABLE row listing member groups, one of them class-based.
        tables = {
            "ROUTE_TABLE:0.0.0.0/0": {"nexthop": "", "ifname": "", "nexthop_group": "30"},
            "NEXTHOP_GROUP_TABLE:30": {"nexthop_group": "11,cbf1"},
            "NEXTHOP_GROUP_TABLE:11": {"nexthop": "10.0.0.1", "ifname": "Ethernet0"},
            "CLASS_BASED_NEXT_HOP_GROUP_TABLE:cbf1": {"members": "12,30"},
            "NEXTHOP_GROUP_TABLE:12": {"nexthop": "10.0.0.1,10.0.0.3", "ifname": "Ethernet0,Ethernet4"},
        }
        mocked_get_all.side_effect = lambda db, key, blocking=False: tables.get(key)
        updater = RouteUpdater()

        with mock.patch('sonic_ax_impl.mibs.logger.warning') as mocked_warning:
            updater.update_data()
            mocked_warning.assert_not_called()

        self.assertEqual(updater.route_dest_list, [
            (0, 0, 0, 0, 0, 0, 0, 0, 0, 10, 0, 0, 1),
            (0, 0, 0, 0, 0, 0, 0, 0, 0, 10, 0, 0, 3),
        ])

    @mock.patch('sonic_py_common.multi_asic.get_all_namespaces', mock.MagicMock(return_value=({"front_ns": ['']})))
    @mock.patch('swsscommon.swsscommon.SonicV2Connector.get_all')
    def test_RouteUpdater_route_nexthop_group_missing(self, mocked_get_all):
        route = {"nexthop": "", "ifname": "", "nexthop_group": "12"}
        tables = {"ROUTE_TABLE:0.0.0.0/0": route}
        mocked_get_all.side_effect = lambda db, key, blocking=False: tables.get(key)
        updater = RouteUpdater()

        with mock.patch('sonic_ax_impl.mibs.logger.warning') as mocked_warning:
            updater.update_data()
            mocked_warning.assert_called_once_with(
                "Route nexthop group missing: ROUTE_TABLE:0.0.0.0/0 {}".format(route))

        self.assertEqual(updater.route_dest_list, [])

    @mock.patch('sonic_py_common.multi_asic.get_all_namespaces', mock.MagicMock(return_value=({"front_ns": ['']})))
    @mock.patch('swsscommon.swsscommon.SonicV2Connector.get_all', mock.MagicMock(return_value=({"nexthop": "10.0.0.1", "ifname": ""})))
    def test_RouteUpdater_route_empty_iframe(self):
        updater = RouteUpdater()

        with mock.patch('sonic_ax_impl.mibs.logger.warning') as mocked_warning:
            updater.update_data()
            mocked_warning.assert_called_once_with(
                "Route has no ifname: ROUTE_TABLE:0.0.0.0/0 {'nexthop': '10.0.0.1', 'ifname': ''}")

        self.assertEqual(updater.route_dest_list, [])

    @mock.patch('sonic_py_common.multi_asic.get_all_namespaces', mock.MagicMock(return_value=({"front_ns": ['']})))
    @mock.patch('swsscommon.swsscommon.SonicV2Connector.get_all', mock.MagicMock(return_value=({"nexthop": "10.0.0.1,,10.0.0.3", "ifname": "Ethernet0,,Ethernet4"})))
    def test_RouteUpdater_route_empty_next_hop_member(self):
        updater = RouteUpdater()
        updater.update_data()

        self.assertEqual(updater.route_dest_list, [
            (0, 0, 0, 0, 0, 0, 0, 0, 0, 10, 0, 0, 1),
            (0, 0, 0, 0, 0, 0, 0, 0, 0, 10, 0, 0, 3),
        ])

    @mock.patch('sonic_py_common.multi_asic.get_all_namespaces', mock.MagicMock(return_value=({"front_ns": ['']})))
    @mock.patch('swsscommon.swsscommon.SonicV2Connector.get_all', mock.MagicMock(return_value=({"nexthop": "10.0.0.1"})))
    def test_RouteUpdater_route_no_iframe(self):
        updater = RouteUpdater()

        with mock.patch('sonic_ax_impl.mibs.logger.warning') as mocked_warning:
            updater.update_data()
            
            # check warning
            expected = [
                mock.call("Route has no ifname: ROUTE_TABLE:0.0.0.0/0 {'nexthop': '10.0.0.1'}")
            ]
            mocked_warning.assert_has_calls(expected)

        self.assertTrue(len(updater.route_dest_list) == 0)


    @mock.patch('sonic_ax_impl.mibs.Namespace.dbs_keys', mock.MagicMock(return_value=(None)))
    def test_RouteUpdater_re_init_redis_exception(self):
        updater = RouteUpdater()

        with mock.patch('sonic_ax_impl.mibs.Namespace.connect_all_dbs') as connect_all_dbs:
            updater.reinit_connection()

            # check re-init
            connect_all_dbs.assert_called()