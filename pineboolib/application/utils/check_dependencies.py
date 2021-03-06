# -*- coding: utf-8 -*-
"""Check the application dependencies."""

import sys
from pineboolib.core.utils import logging
from pineboolib.core.utils.utils_base import is_deployed
from pineboolib.core.utils.check_dependencies import get_dependency_errors
from pineboolib.core.utils.check_dependencies import DependencyCheck, DependencyError

from pineboolib import application

LOGGER = logging.getLogger(__name__)


def check_dependencies(dict_: DependencyCheck, exit: bool = True) -> bool:
    """
    Check if a package is installed and return the result.

    @param dict_. Dict with the name of the agency and the module to be checked.
    @param exit . Exit if dependence fails.
    """
    dep_error: DependencyError = get_dependency_errors(dict_)
    if not dep_error:
        return True
    msg = ""
    LOGGER.debug("Error trying to import modules:\n%s", "\n\n".join(dep_error.values()))
    LOGGER.warning("Unmet dependences:")
    for (dep, suggestedpkg), errormsg in dep_error.items():
        LOGGER.warning("Install package %s for %s", suggestedpkg, dep)
        msg += "Instale el paquete %s.\n%s" % (suggestedpkg, errormsg)
        if dep == "pyfpdf":
            msg += "\n\n\n Use pip3 install -i https://test.pypi.org/simple/ pyfpdf==1.7.3"

    if exit:
        if application.PROJECT.DGI.useDesktop() and application.PROJECT.DGI.localDesktop():
            from pineboolib.q3widgets.messagebox import MessageBox

            MessageBox.warning(None, "Pineboo - Dependencias Incumplidas -", msg, MessageBox.Ok)

        if not is_deployed():
            sys.exit(32)

    return False
