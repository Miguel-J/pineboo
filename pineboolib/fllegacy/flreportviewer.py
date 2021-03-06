"""Flreportviewer module."""
from PyQt5 import QtWidgets, QtCore, QtXml

from pineboolib.core import decorators
from pineboolib.application.qsatypes.sysbasetype import SysBaseType
from pineboolib.fllegacy.flutil import FLUtil


# from pineboolib.fllegacy.flpicture import FLPicture
from .flsqlquery import FLSqlQuery
from .flsqlcursor import FLSqlCursor

from .flreportengine import FLReportEngine
from pineboolib import logging

from typing import Any, List, Mapping, Sized, Union, Dict, Optional, Callable
from PyQt5.QtGui import QColor


AQ_USRHOME = "."  # FIXME


class internalReportViewer(QtWidgets.QWidget):
    """internalReportViewer class."""

    rptEngine_: Optional[FLReportEngine]
    dpi_: int
    report_: List[Any]
    num_copies: int

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        """Inicialize."""
        super().__init__(parent)
        self.rptEngine_ = None
        self.dpi_ = 300
        self.report_ = []
        self.num_copies = 1

    def setReportEngine(self, rptEngine: FLReportEngine) -> None:
        """Set report engine."""

        self.rptEngine_ = rptEngine

    def resolution(self) -> int:
        """Return resolution."""

        return self.dpi_

    def reportPages(self) -> List[Any]:
        """Return report pages."""

        return self.report_

    def renderReport(self, init_row: int, init_col: int, flags: List[int]) -> Any:
        """Render report."""

        if self.rptEngine_ is None:
            raise Exception("renderReport. self.rptEngine_ is empty!")

        return self.rptEngine_.renderReport(init_row, init_col, flags)

    def setNumCopies(self, num_copies: int) -> None:
        """Set number of copies."""
        self.num_copies = num_copies

    def __getattr__(self, name: str) -> Callable:
        """Return attributes from report engine."""
        return getattr(self.rptEngine_, name, None)


class FLReportViewer(QtWidgets.QWidget):
    """FLReportViewer class."""

    pdfFile: str
    Append: int
    Display: int
    PageBreak: int
    spnResolution_: int
    report_: List[Any]
    qry_: Any
    xmlData_: Any
    template_: Any
    autoClose_: bool
    styleName_: str

    PrintGrayScale = 0
    PrintColor = 1

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        name: Optional[str] = None,
        embedInParent: bool = False,
        rptEngine: Optional[FLReportEngine] = None,
    ) -> None:
        """Inicialize."""

        super(FLReportViewer, self).__init__(parent)
        self.logger = logging.getLogger("FLReportViewer")
        self.loop_ = False
        self.eventloop = QtCore.QEventLoop()
        self.reportPrinted_ = False
        self.rptEngine_: Optional[Any] = None
        self.report_ = []
        self.slotsPrintDisabled_ = False
        self.slotsExportedDisabled_ = False
        self.printing_ = False
        self.embedInParent_ = True if parent and embedInParent else False
        self.ui_: Dict[str, QtCore.QObject] = {}

        self.Display = 1
        self.Append = 1
        self.PageBreak = 1

        self.rptViewer_ = internalReportViewer(self)
        self.setReportEngine(FLReportEngine(self) if rptEngine is None else rptEngine)

        if self.rptViewer_ is None:
            raise Exception("self.rptViewer_ is empty!")

        self.report_ = self.rptViewer_.reportPages()

    def rptViewer(self) -> internalReportViewer:
        """Return report viewer."""
        return self.rptViewer_

    def rptEngine(self) -> FLReportEngine:
        """Return report engine."""

        if self.rptEngine_ is None:
            raise Exception("rptEngine_ is not defined!")
        return self.rptEngine_

    def setReportEngine(self, r: Optional[FLReportEngine] = None) -> None:
        """Set report engine."""

        if self.rptEngine_ == r:
            return

        sender = self.sender()
        noSigDestroy = not (sender and sender == self.rptEngine_)

        self.rptEngine_ = r
        if self.rptEngine_ is not None:
            self.template_ = self.rptEngine_.rptNameTemplate()
            self.qry_ = self.rptEngine_.rptQueryData()

            if noSigDestroy:
                self.rptViewer_.setReportEngine(self.rptEngine_)

    def exec_(self) -> None:
        """Show report."""
        # if self.loop_:
        #    print("FLReportViewer::exec(): Se ha detectado una llamada recursiva")
        #    return
        if self.rptViewer_.rptEngine_ and hasattr(self.rptViewer_.rptEngine_, "parser_"):
            pdf_file = self.rptViewer_.rptEngine_.parser_.get_file_name()

            SysBaseType.openUrl(pdf_file)
        # self.eventloop.exec_()

        # if self.embedInParent_:
        #    return

        # self.loop_ = True
        # self.clearWFlags(Qt.WShowModal) # FIXME

    @decorators.BetaImplementation
    def csvData(self) -> str:
        """Return csv data."""

        return self.rptEngine_.csvData() if self.rptEngine_ else ""

    def renderReport(
        self,
        init_row: int = 0,
        init_col: int = 0,
        append_or_flags: Union[bool, Sized, Mapping[int, Any]] = None,
        display_report: bool = False,
    ) -> bool:
        """Render report."""
        if not self.rptEngine_:
            return False

        flags = [self.Append, self.Display]

        if isinstance(append_or_flags, bool):
            flags[0] = append_or_flags

            if display_report is not None:
                flags[0] = display_report
        elif isinstance(append_or_flags, list):
            if len(append_or_flags) > 0:
                flags[0] = append_or_flags[0]  # display
            if len(append_or_flags) > 1:
                flags[1] = append_or_flags[1]  # append
            if len(append_or_flags) > 2:
                flags.append(append_or_flags[2])  # page_break

        ret = self.rptViewer_.renderReport(init_row, init_col, flags)
        self.report_ = self.rptViewer_.reportPages()
        return ret

    def setReportData(self, d: Union[FLSqlCursor, FLSqlQuery, QtXml.QDomNode]) -> bool:
        """Set data to report."""
        if isinstance(d, FLSqlQuery):
            self.qry_ = d
            if self.rptEngine_ and self.rptEngine_.setReportData(d):
                self.xmlData_ = self.rptEngine_.rptXmlData()
                return True
            return False
        elif isinstance(d, FLSqlCursor):
            if not self.rptEngine_:
                return False
            return self.rptEngine_.setReportData(d)
        elif isinstance(d, QtXml.QDomNode):
            self.xmlData_ = d
            self.qry_ = None
            if not self.rptEngine_:
                return False
            return self.rptEngine_.setReportData(d)
        return False

    def setReportTemplate(self, t: Union[QtXml.QDomNode, str], style: Optional[str] = None) -> bool:
        """Set template to report."""
        if isinstance(t, QtXml.QDomNode):
            self.xmlTemplate_ = t
            self.template_ = ""

            if not self.rptEngine_:
                return False

            if style is not None:
                self.setStyleName(style)

            self.rptEngine_.setFLReportTemplate(t)

            return True
        else:
            self.template_ = t
            self.styleName_ = style
            if self.rptEngine_ and self.rptEngine_.setFLReportTemplate(t):
                # self.setStyleName(style)
                self.xmlTemplate_ = self.rptEngine_.rptXmlTemplate()
                return True

        return False

    @decorators.BetaImplementation
    def sizeHint(self) -> QtCore.QSize:
        """Return sizeHint."""
        return self.rptViewer_.sizeHint()

    @decorators.BetaImplementation
    def setNumCopies(self, numCopies: int) -> None:
        """Set number of copies."""
        self.rptViewer_.setNumCopies(numCopies)

    @decorators.BetaImplementation
    def setPrinterName(self, pName: str) -> None:
        """Set printer name."""
        self.rptViewer_.setPrinterName(pName)

    @decorators.BetaImplementation
    def reportPrinted(self) -> bool:
        """Return if report was printed."""
        return self.reportPrinted_

    @decorators.pyqtSlot(int)
    @decorators.BetaImplementation
    def setResolution(self, dpi: int) -> None:
        """Set resolution."""
        util = FLUtil()
        util.writeSettingEntry("rptViewer/dpi", str(dpi))
        self.rptViewer_.setResolution(dpi)

    @decorators.pyqtSlot(int)
    @decorators.BetaImplementation
    def setPixel(self, relDpi: int) -> None:
        """Set pixel size."""
        util = FLUtil()
        util.writeSettingEntry("rptViewer/pixel", str(float(relDpi / 10.0)))
        if self.rptEngine_:
            self.rptEngine_.setRelDpi(relDpi / 10.0)

    @decorators.BetaImplementation
    def setDefaults(self) -> None:
        """Set default values."""
        import platform

        self.spnResolution_ = 300
        system = platform.system()
        if system == "Linux":
            self.spnPixel_ = 780
        elif system == "Windows":
            # FIXME
            pass
        elif system == "Darwin":
            # FIXME
            pass

    @decorators.BetaImplementation
    def updateReport(self) -> None:
        """Update report."""
        self.requestUpdateReport.emit()

        if self.qry_ or (self.xmlData_ and self.xmlData_ != ""):
            if not self.rptEngine_:
                self.setReportEngine(FLReportEngine(self))

            self.setResolution(self.spnResolution_)
            self.setPixel(self.spnPixel_)

            if self.template_ and self.template_ != "":
                self.setReportTemplate(self.template_, self.styleName_)
            else:
                self.setReportTemplate(self.xmlTemplate_, self.styleName_)

            if self.qry_:
                self.setReportData(self.qry_)
            else:
                self.setReportData(self.xmlData_)

            self.renderReport(0, 0, False, False)

        self.updateDisplay()

    @decorators.BetaImplementation
    def getCurrentPage(self) -> Any:
        """Return curent page."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     return FLPicture(self.report_.getCurrentPage(), self)
        return 0

    @decorators.BetaImplementation
    def getFirstPage(self) -> Any:
        """Return first page."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     return FLPicture(self.report_.getFirstPage(), self)
        return 0

    @decorators.BetaImplementation
    def getPreviousPage(self) -> Any:
        """Return previous page."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     return FLPicture(self.report_.getPreviousPage(), self)
        return 0

    @decorators.BetaImplementation
    def getNextPage(self) -> Any:
        """Return next page."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     return FLPicture(self.report_.getNextPage(), self)
        return 0

    @decorators.BetaImplementation
    def getLastPage(self) -> Any:
        """Return last page."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     return FLPicture(self.report_.getLastPage(), self)
        return 0

    @decorators.BetaImplementation
    def getPageAt(self, i: int) -> Any:
        """Return actual page."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     return FLPicture(self.report_.getPageAt(i), self)
        return 0

    @decorators.BetaImplementation
    def updateDisplay(self) -> None:
        """Update display."""
        self.rptViewer_.slotUpdateDisplay()

    @decorators.BetaImplementation
    def clearPages(self) -> None:
        """Clear report pages."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     self.report_.clear()
        pass

    @decorators.BetaImplementation
    def appendPage(self) -> None:
        """Add a new page."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     self.report_.appendPage()
        pass

    @decorators.BetaImplementation
    def getCurrentIndex(self) -> int:
        """Return current index position."""

        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     return self.report_.getCurrentIndex()
        return -1

    @decorators.BetaImplementation
    def setCurrentPage(self, idx: int) -> None:
        """Set current page index."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     self.report_.setCurrentPage(idx)
        pass

    @decorators.BetaImplementation
    def setPageSize(self, w: Union[QtCore.QSize, int], h: Optional[int] = None) -> None:
        """Set page size."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     self.report_.setPageSize(s)
        pass

    @decorators.BetaImplementation
    def setPageOrientation(self, o: int) -> None:
        """Set page orientation."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     self.report_.setPageOrientation(o)
        pass

    @decorators.BetaImplementation
    def setPageDimensions(self, dim: QtCore.QSize) -> None:
        """Set page dimensions."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     self.report_.setPageDimensions(dim)
        pass

    @decorators.BetaImplementation
    def pageSize(self) -> QtCore.QSize:
        """Return page size."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     return self.report_.pageSize()
        return -1

    @decorators.BetaImplementation
    def pageOrientation(self) -> int:
        """Return page orientation."""
        # FIXME: self.report_ is just a List[]
        # if self.report_:
        #     return self.report_.pageOrientation()
        return -1

    def pageDimensions(self) -> QtCore.QSize:
        """Return page dimensions."""
        if self.rptViewer_.rptEngine_ and hasattr(self.rptViewer_.rptEngine_, "parser_"):
            return self.rptViewer_.rptEngine_.parser_._page_size
        return -1

    def pageCount(self) -> int:
        """Return number of pages."""
        if self.rptViewer_.rptEngine_:
            return self.rptViewer_.rptEngine_.number_pages()
        return -1

    @decorators.BetaImplementation
    def setStyleName(self, style: str) -> None:
        """Set style name."""
        self.styleName_ = style

    @decorators.BetaImplementation
    def setReportPages(self, pgs: Any) -> None:
        """Add pages to actual report."""
        self.setReportEngine(None)
        self.qry_ = None
        self.xmlData_ = QtXml.QDomNode()
        self.rptViewer_.setReportPages(pgs.pageCollection() if pgs else 0)
        self.report_ = self.rptViewer_.reportPages()

    @decorators.BetaImplementation
    def setColorMode(self, c: QColor) -> None:
        """Set color mode."""

        self.rptViewer_.setColorMode(c)

    @decorators.BetaImplementation
    def colorMode(self) -> QColor:
        """Return color mode."""
        return self.rptViewer_.colorMode()

    @decorators.BetaImplementation
    def setName(self, n: str) -> None:
        """Set report name."""
        self.name_ = n

    @decorators.BetaImplementation
    def name(self) -> str:
        """Return report name."""
        return self.name_

    def __getattr__(self, name: str) -> Any:
        """Return attribute from inernal object."""
        return getattr(self.rptViewer_, name, None)
