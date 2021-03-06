"""Flinvalidator module."""

# -*- coding: utf-8 -*-
from PyQt5 import QtGui  # type: ignore
from typing import Any, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt5 import QtWidgets


class FLIntValidator(QtGui.QIntValidator):
    """FLIntValidator Class."""

    _formatting: bool

    def __init__(self, minimum: int, maximum: int, parent: "QtWidgets.QWidget") -> None:
        """Inicialize."""

        super().__init__(minimum, maximum, parent)
        self._formatting = False

    def validate(self, input_: str, pos_cursor: int) -> Tuple[Any, str, int]:
        """Return validate result."""

        if not input_ or self._formatting:
            return (self.Acceptable, input_, pos_cursor)

        state = super().validate(input_, pos_cursor)

        ret_0 = None
        ret_1 = state[1]
        ret_2 = state[2]

        if state[0] in (self.Invalid, self.Intermediate) and len(input_) > 0:
            s = input_[1:]
            if (
                input_[0] == "-"
                and super().validate(s, pos_cursor)[0] == self.Acceptable
                or s == ""
            ):
                ret_0 = self.Acceptable
            else:
                ret_0 = self.Invalid
        else:
            ret_0 = self.Acceptable

        return (ret_0, ret_1, ret_2)
