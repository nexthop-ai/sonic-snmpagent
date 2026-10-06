import sys
from unittest import TestCase

import tests.mock_tables.dbconnector
from sonic_ax_impl import mibs

if sys.version_info.major == 3:
    from unittest import mock
else:
    import mock


from sonic_ax_impl.mibs import Namespace
from sonic_ax_impl import mibs

class TestGetNextPDU(TestCase):
    @classmethod
    def setUpClass(cls):
        #For single namespace scenario, load database_config.json
        tests.mock_tables.dbconnector.load_database_config()

    def test_scan_keys_paginates(self):
        db_conn = mock.MagicMock()
        # The middle page is a shape redis is allowed to return and the loop
        # has to keep going through: a non-terminal cursor carrying no keys.
        db_conn.scan = mock.MagicMock(side_effect=[(17, ['a', 'b']), (9, []), (0, ['b', 'c'])])

        mibs._scan_usable = True
        try:
            keys = mibs.scan_keys(db_conn, mibs.APPL_DB, 'X:*')
        finally:
            mibs._scan_usable = True

        self.assertEqual(sorted(keys), ['a', 'b', 'c'])
        db_conn.scan.assert_any_call(mibs.APPL_DB, 0, 'X:*', mibs.REDIS_SCAN_COUNT)
        db_conn.scan.assert_any_call(mibs.APPL_DB, 17, 'X:*', mibs.REDIS_SCAN_COUNT)
        db_conn.scan.assert_called_with(mibs.APPL_DB, 9, 'X:*', mibs.REDIS_SCAN_COUNT)

    def test_scan_keys_falls_back_to_keys(self):
        db_conn = mock.MagicMock()
        db_conn.scan = mock.MagicMock(return_value=object())
        db_conn.keys = mock.MagicMock(return_value=['k1'])

        try:
            self.assertEqual(mibs.scan_keys(db_conn, mibs.APPL_DB, 'X:*'), ['k1'])
            db_conn.keys.assert_called_with(mibs.APPL_DB, 'X:*')

            db_conn.scan.reset_mock()
            self.assertEqual(mibs.scan_keys(db_conn, mibs.APPL_DB, 'X:*'), ['k1'])
            db_conn.scan.assert_not_called()
        finally:
            mibs._scan_usable = True

    def test_scan_keys_restarts_once_after_connection_loss(self):
        db_conn = mock.MagicMock()
        db_conn.scan = mock.MagicMock(side_effect=[(5, ['a']), RuntimeError('conn'), (0, ['b'])])

        keys = mibs.scan_keys(db_conn, mibs.APPL_DB, 'X:*')

        # The restart begins again at cursor 0 on a new connection, so 'a'
        # from the dead connection's walk is not carried over.
        self.assertEqual(keys, ['b'])
        self.assertEqual(db_conn.scan.call_args_list[-1], mock.call(mibs.APPL_DB, 0, 'X:*', mibs.REDIS_SCAN_COUNT))
        db_conn.close.assert_called_once_with(mibs.APPL_DB)
        db_conn.connect.assert_called_once_with(mibs.APPL_DB)
        db_conn.keys.assert_not_called()

    def test_scan_keys_raises_after_second_connection_loss(self):
        db_conn = mock.MagicMock()
        db_conn.scan = mock.MagicMock(side_effect=RuntimeError('conn'))

        with self.assertRaises(RuntimeError):
            mibs.scan_keys(db_conn, mibs.APPL_DB, 'X:*')
        self.assertEqual(db_conn.scan.call_count, 2)
        db_conn.keys.assert_not_called()

    def test_scan_keys_latches_off_when_walk_does_not_converge(self):
        db_conn = mock.MagicMock()
        db_conn.scan = mock.MagicMock(return_value=(1, []))
        db_conn.keys = mock.MagicMock(return_value=['k1'])

        try:
            with mock.patch.object(mibs, 'REDIS_SCAN_MAX_ITERATIONS', 3):
                self.assertEqual(mibs.scan_keys(db_conn, mibs.APPL_DB, 'X:*'), ['k1'])
                self.assertEqual(db_conn.scan.call_count, 3)

                db_conn.scan.reset_mock()
                self.assertEqual(mibs.scan_keys(db_conn, mibs.APPL_DB, 'X:*'), ['k1'])
                db_conn.scan.assert_not_called()
        finally:
            mibs._scan_usable = True

    def test_init_sync_d_lag_tables(self):
        db_conn = Namespace.init_namespace_dbs()

        lag_name_if_name_map, \
        if_name_lag_name_map, \
        oid_lag_name_map, \
        lag_sai_map, _ = Namespace.get_sync_d_from_all_namespace(mibs.init_sync_d_lag_tables, db_conn)

        self.assertTrue("PortChannel04" in lag_name_if_name_map)
        self.assertTrue(lag_name_if_name_map["PortChannel04"] == ["Ethernet124"])
        self.assertTrue("Ethernet124" in if_name_lag_name_map)
        self.assertTrue(if_name_lag_name_map["Ethernet124"] == "PortChannel04")

        self.assertTrue("PortChannel_Temp" in lag_name_if_name_map)
        self.assertTrue(lag_name_if_name_map["PortChannel_Temp"] == [])
        self.assertTrue(lag_sai_map["PortChannel01"] == "2000000000006")

        # Member rows with no member name, or under a LAG with no LAG_TABLE
        # entry, are skipped.
        self.assertNotIn("PortChannel05", lag_name_if_name_map)
        self.assertNotIn("PortChannel99", lag_name_if_name_map)
        self.assertNotIn("Ethernet0", if_name_lag_name_map)

    @mock.patch('swsscommon.swsscommon.SonicV2Connector.get_all', mock.MagicMock(return_value=({})))
    def test_init_sync_d_interface_tables(self):
        db_conn = Namespace.init_namespace_dbs()

        if_name_map, \
        if_alias_map, \
        if_id_map, \
        oid_name_map = Namespace.get_sync_d_from_all_namespace(mibs.init_sync_d_interface_tables, db_conn)
        self.assertTrue(if_name_map == {})
        self.assertTrue(if_alias_map == {})
        self.assertTrue(if_id_map == {})
        self.assertTrue(oid_name_map == {})

    @mock.patch('swsscommon.swsscommon.SonicV2Connector.get_all', mock.MagicMock(return_value=({})))
    def test_init_sync_d_queue_tables(self):
        mock_queue_stat_map = {}
        db_conn = Namespace.init_namespace_dbs()

        port_queues_map, queue_stat_map, port_queue_list_map = \
            Namespace.get_sync_d_from_all_namespace(mibs.init_sync_d_queue_tables, db_conn)
        self.assertTrue(port_queues_map == {})
        self.assertTrue(queue_stat_map == {})
        self.assertTrue(port_queue_list_map == {})

    @mock.patch('swsscommon.swsscommon.SonicV2Connector.get_all', mock.MagicMock(return_value=({})))
    def test_init_sync_d_vlan_tables(self):
        db_conn = Namespace.init_namespace_dbs()

        vlan_name_map, \
        vlan_oid_sai_map, \
        vlan_oid_name_map = Namespace.get_sync_d_from_all_namespace(mibs.init_sync_d_vlan_tables, db_conn)

        self.assertTrue(vlan_name_map == {})
        self.assertTrue(vlan_oid_sai_map == {})
        self.assertTrue(vlan_oid_name_map == {})
