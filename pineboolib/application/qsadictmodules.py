"""
QSADictModules.

Manages read and writting QSA dynamic properties that are loaded during project startup.
"""
from typing import Any, TYPE_CHECKING
from pineboolib.core.utils import logging
from pineboolib.application.xmlaction import XMLAction
from pineboolib.application.proxy import DelayedObjectProxyLoader
from pineboolib.application.safeqsa import SafeQSA

LOGGER = logging.getLogger("qsadictmodules")


class QSADictModules:
    """
    Manage read and write dynamic properties for QSA.
    """

    _qsa_dict_modules: Any = None

    @classmethod
    def qsa_dict_modules(cls) -> Any:
        """Retrieve QSA module, hidding it from MyPy."""
        if cls._qsa_dict_modules is None:
            # FIXME: This loads from QSA module. Avoid if possible. (how?)
            if TYPE_CHECKING:
                qsa_dict_modules: Any = None
            else:
                from pineboolib.qsa import qsa as qsa_dict_modules

            cls._qsa_dict_modules = qsa_dict_modules
        return cls._qsa_dict_modules

    @classmethod
    def from_project(cls, scriptname: str) -> Any:
        """
        Return project object for given name.
        """
        module_name = scriptname if scriptname != "sys" else "sys_module"

        return getattr(cls.qsa_dict_modules(), module_name, None)

    @classmethod
    def action_exists(cls, scriptname: str) -> bool:
        """
        Check if action is already loaded.
        """
        return hasattr(cls.qsa_dict_modules(), scriptname)

    @classmethod
    def save_action(cls, scriptname: str, delayed_action: DelayedObjectProxyLoader) -> None:
        """
        Save Action into project for QSA.
        """
        setattr(cls.qsa_dict_modules(), scriptname, delayed_action)

    @classmethod
    def save_other(cls, scriptname: str, other: Any) -> None:
        """
        Save other objects for QSA.
        """
        setattr(cls.qsa_dict_modules(), scriptname, other)

    @classmethod
    def save_action_for_root_module(cls, action: XMLAction) -> bool:
        """Save a new module as an action."""

        module_name = action.name if action.name != "sys" else "sys_module"
        if cls.action_exists(module_name):
            if module_name != "sys_module":
                LOGGER.warning("Module found twice, will not be overriden: %s", module_name)
            return False

        # Se crea la action del módulo
        proxy = DelayedObjectProxyLoader(action.load, name="QSA.Module.%s" % module_name)
        cls.save_action(module_name, proxy)
        SafeQSA.save_root_module(module_name, proxy)
        return True

    @classmethod
    def save_action_for_mainform(cls, action: XMLAction):
        """Save a new mainform."""
        name = action.name
        module = action.mod
        if module is None:
            raise ValueError("Action.module must be set before calling")

        actionname = "form%s" % name
        if cls.action_exists(actionname):
            LOGGER.debug(
                "No se sobreescribe variable de entorno %s. Hay una definición previa en %s",
                "%s.form%s" % (module.module_name, name),
                module.module_name,
            )
            return False
        # Se crea la action del form
        delayed_action = DelayedObjectProxyLoader(
            action.load, name="QSA.Module.%s.Action.form%s" % (module.mod.name, name)
        )
        cls.save_action(actionname, delayed_action)
        SafeQSA.save_mainform(actionname, delayed_action)
        return True

    @classmethod
    def save_action_for_formrecord(cls, action: XMLAction):
        """Save a new formrecord."""
        name = action.name
        module = action.mod
        if module is None:
            raise ValueError("Action.module must be set before calling")
        actionname = "formRecord" + name
        if cls.action_exists(actionname):
            LOGGER.debug("No se sobreescribe variable de entorno %s", "formRecord" + name)
            return False
        # Se crea la action del formRecord
        delayed_action = DelayedObjectProxyLoader(
            action.formRecordWidget,
            name="QSA.Module.%s.Action.formRecord%s" % (module.mod.name, name),
        )

        cls.save_action(actionname, delayed_action)
        SafeQSA.save_formrecord(actionname, delayed_action)
        return True

    @classmethod
    def clean_all(cls):
        """Clean all saved data."""
        qsa_dict_modules = cls.qsa_dict_modules()

        SafeQSA.clean_all()
        list_ = [attr for attr in dir(qsa_dict_modules) if not attr[0] == "_"]
        for name in list_:
            att = getattr(qsa_dict_modules, name)
            if isinstance(att, DelayedObjectProxyLoader):
                delattr(qsa_dict_modules, name)
