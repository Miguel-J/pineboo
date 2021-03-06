"""Test_xmlaction module."""
import unittest
from pineboolib.loader.main import init_testing, finish_testing
from pineboolib import application
from . import fixture_path


class TestXMLAction(unittest.TestCase):
    """TestXMLAction Class."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure pineboo is initialized for testing."""
        init_testing()

    def test_basic(self) -> None:
        """Test basic."""

        from pineboolib.fllegacy import systype
        import os

        qsa_sys = systype.SysType()
        path = fixture_path("principal.eneboopkg")
        self.assertTrue(os.path.exists(path))
        qsa_sys.loadModules(path, False)
        application.PROJECT.actions["flareas"].execMainScript("formareas")
        application.PROJECT.actions["flreinit"].execDefaultScript()
        application.PROJECT.actions["flareas"].formRecordWidget()
        self.assertTrue(application.PROJECT.actions["flareas"].formRecordWidget()._loaded)

    @classmethod
    def tearDownClass(cls) -> None:
        """Ensure test clear all data."""
        finish_testing()
