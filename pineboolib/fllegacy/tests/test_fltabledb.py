"""Test_fltabledb module."""

import unittest
from pineboolib.loader.main import init_testing, finish_testing


class TestFLTableDB(unittest.TestCase):
    """Test FLTableDB class."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure pineboo is initialized for testing."""
        init_testing()

    def test_export_to_ods(self) -> None:
        """Test export to ods."""
        from pineboolib.fllegacy import fltabledb
        from pineboolib import application

        application.project.actions["flareas"].openDefaultForm()

        form = application.project.actions[  # type: ignore [attr-defined] # noqa F821
            "flareas"
        ].mainform_widget
        # form = flformdb.FLFormDB(None, action)
        # self.assertTrue(form)
        # form.load()
        fltable = form.findChild(fltabledb.FLTableDB, "tableDBRecords")
        self.assertTrue(fltable)
        fltable.exportToOds()
        # self.assertTrue(form._loaded)
        # form.close()
        # self.assertFalse(form._loaded)
        # form.close()
        # self.assertFalse(form._loaded)

    def test_order_cols(self) -> None:
        """Test order cols."""
        from pineboolib.fllegacy import fltabledb
        from pineboolib import application

        form = application.project.actions[  # type: ignore [attr-defined] # noqa F821
            "flareas"
        ].mainform_widget

        fltable = form.findChild(fltabledb.FLTableDB, "tableDBRecords")
        fltable.setOrderCols(["descripcion", "idarea", "bloqueo"])
        self.assertEqual(fltable.orderCols(), ["descripcion", "idarea", "bloqueo"])
        fltable.setOrderCols(["idarea"])
        self.assertEqual(fltable.orderCols(), ["idarea", "descripcion", "bloqueo"])

    @classmethod
    def tearDownClass(cls) -> None:
        """Ensure test clear all data."""
        finish_testing()