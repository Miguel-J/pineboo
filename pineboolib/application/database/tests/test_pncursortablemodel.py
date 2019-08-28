"""Test_pncursortablemodel module."""

import unittest
from pineboolib.loader.main import init_testing
from pineboolib.application.database import pnsqlcursor


class TestPNCursorTableModel(unittest.TestCase):
    """TestPNCursorTableModel Class."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure pineboo is initialized for testing."""
        init_testing()

    def test_basic_1(self) -> None:
        """Basic test 1."""

        cursor = pnsqlcursor.PNSqlCursor("fltest")
        cursor.setModeAccess(cursor.Insert)
        cursor.refreshBuffer()
        cursor.setValueBuffer("string_field", "xxx")
        cursor.setValueBuffer("double_field", 0.02)
        cursor.commitBuffer()
        cursor.setModeAccess(cursor.Insert)
        cursor.refreshBuffer()
        cursor.setValueBuffer("string_field", "zzz")
        cursor.setValueBuffer("double_field", 0.01)
        cursor.commitBuffer()
        cursor.setModeAccess(cursor.Insert)
        cursor.refreshBuffer()
        cursor.setValueBuffer("string_field", "yyy")
        cursor.setValueBuffer("double_field", 0.03)
        cursor.commitBuffer()

        cursor.setSort("string_field ASC")
        cursor.refresh()
        cursor.last()
        self.assertEqual(cursor.valueBuffer("string_field"), "zzz")
        self.assertEqual(cursor.valueBuffer("double_field"), 0.01)
        cursor.prev()
        self.assertEqual(cursor.valueBuffer("string_field"), "yyy")

    def test_basic_2(self) -> None:
        """Basic test 2."""

        cursor = pnsqlcursor.PNSqlCursor("fltest")
        cursor.select()
        cursor.last()
        cursor.refreshBuffer()
        self.assertEqual(cursor.valueBuffer("string_field"), "yyy")

        model = cursor.model()

        self.assertEqual(model.findPKRow([cursor.valueBuffer("id")]), cursor.size() - 1)
        self.assertEqual(model.pK(), "id")
        self.assertEqual(model.fieldType("string_field"), "string")
        self.assertEqual(model.alias("string_field"), "String field")
        self.assertEqual(
            model.field_metadata("string_field"), cursor.metadata().field("string_field")
        )

    def test_basic_3(self) -> None:

        cursor = pnsqlcursor.PNSqlCursor("fltest")
        cursor.setSort("string_field DESC")
        cursor.select()

        model = cursor.model()

        self.assertEqual(model.data(model.index(0, 1)), "zzz")
        self.assertEqual(model.data(model.index(0, 0)), 5)
        self.assertEqual(model.data(model.index(0, 2)), None)
        self.assertEqual(model.data(model.index(0, 4)), "0,01")
        self.assertEqual(model.data(model.index(0, 5)), "No")
        self.assertEqual(model.data(model.index(1, 1)), "yyy")
        self.assertEqual(model.data(model.index(1, 0)), 6)
