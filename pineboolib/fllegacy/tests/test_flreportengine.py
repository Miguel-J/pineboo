"""Test_flreportengine module."""

import unittest
from pineboolib.loader.main import init_testing, finish_testing
from . import fixture_path


class TestFLReportEngine(unittest.TestCase):
    """TestSysType Class."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure pineboo is initialized for testing."""
        init_testing()

    def test_report_data(self) -> None:
        """Test eneboopkgs load."""
        from pineboolib.qsa import qsa
        import os

        path = fixture_path("principal.eneboopkg")
        self.assertTrue(os.path.exists(path))
        qsa.sys.loadModules(path, False)

        qry = qsa.FLSqlQuery()
        qry.setTablesList("flfiles")
        qry.setSelect("count(nombre)")
        qry.setFrom("flfiles")
        qry.setWhere("1=1")
        self.assertTrue(qry.exec_())
        self.assertTrue(qry.first())
        res = qsa.sys.toXmlReportData(qry)
        self.assertTrue(res.toString(2).find("</KugarData>") > -1)

    @classmethod
    def tearDownClass(cls) -> None:
        """Ensure test clear all data."""
        finish_testing()
