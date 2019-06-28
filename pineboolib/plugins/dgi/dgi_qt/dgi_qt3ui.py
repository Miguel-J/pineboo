# -*- coding: utf-8 -*-

from PyQt5 import QtCore, QtGui, QtWidgets

from xml.etree import ElementTree as ET
from binascii import unhexlify
import logging
import zlib
from PyQt5.QtCore import QObject
from pineboolib.core.utils.utils_base import load2xml
from pineboolib import pncontrolsfactory
from pineboolib import project

ICONS = {}
root = None
logger = logging.getLogger("pnqt3ui")


class Options:
    DEBUG_LEVEL = 100


# TODO: Refactorizar este fichero como una clase. ICONS es la lista de iconos
#      para un solo formulario. Debe existir una clase LoadUI y que ICONS sea
#      una variable de ésta. Para cada nuevo formulario se debería instanciar
#      una nueva clase.


def loadUi(form_path, widget, parent=None):

    global ICONS, root
    # parser = etree.XMLParser(
    #    ns_clean=True,
    #    encoding="UTF-8",
    #    remove_blank_text=True,
    # )

    tree = load2xml(form_path)

    if not tree:
        return parent

    root = tree.getroot()
    ICONS = {}

    if parent is None:
        parent = widget

    # if project._DGI.localDesktop():
    widget.hide()

    for xmlimage in root.findall("images//image"):
        loadIcon(xmlimage)

    for xmlwidget in root.findall("widget"):
        loadWidget(xmlwidget, widget, parent)

    # print("----------------------------------")
    # for xmlwidget in root.xpath("actions"):
    #     loadWidget(xmlwidget, widget, parent)
    # print("----------------------------------")

    # Debe estar despues de loadWidget porque queremos el valor del UI de Qt3
    formname = widget.objectName()
    logger.info("form: %s", formname)

    # Cargamos actions...
    for action in root.findall("actions//action"):
        loadAction(action, widget)

    for xmlconnection in root.findall("connections//connection"):
        sender_name = xmlconnection.find("sender").text
        signal_name = xmlconnection.find("signal").text
        receiv_name = xmlconnection.find("receiver").text
        slot_name = xmlconnection.find("slot").text

        receiver = None
        if isinstance(widget, pncontrolsfactory.QMainWindow):
            if signal_name == "activated()":
                signal_name = "triggered()"

        if sender_name == formname:
            sender = widget
        else:
            sender = widget.findChild(QObject, sender_name, QtCore.Qt.FindChildrenRecursively)

        # if not project._DGI.localDesktop():
        #    wui = hasattr(widget, "ui_") and sender_name in widget.ui_
        #    if sender is None and wui:
        #        sender = widget.ui_[sender_name]

        sg_name = signal_name

        if signal_name.find("(") > -1:
            sg_name = signal_name[: signal_name.find("(")]

        sl_name = slot_name
        if slot_name.find("(") > -1:
            sl_name = slot_name[: slot_name.find("(")]

        if sender is None:
            logger.warning("Connection sender not found:%s", sender_name)
        if receiv_name == formname:
            receiver = (
                widget
                if not isinstance(widget, pncontrolsfactory.QMainWindow)
                else project.actions[sender_name]
                if sender_name in project.actions.keys()
                else None
            )
            fn_name = slot_name.rstrip("()")
            logger.debug("Conectando de UI a QS: (%r.%r -> %r.%r)", sender_name, signal_name, receiv_name, fn_name)

            ifx = widget
            # if hasattr(widget, "iface"):
            #    ifx = widget.iface
            if hasattr(ifx, fn_name):
                try:

                    # getattr(sender, sg_name).connect(
                    #    getattr(ifx, fn_name))
                    pncontrolsfactory.connect(sender, signal_name, ifx, fn_name)
                except Exception:
                    logger.exception("Error connecting: %s %s %s %s %s", sender, signal_name, receiver, slot_name, getattr(ifx, fn_name))
                continue

        if receiver is None:
            receiver = widget.findChild(QObject, receiv_name, QtCore.Qt.FindChildrenRecursively)

        if receiver is None:
            from pineboolib import qsa

            receiver = getattr(qsa, receiv_name, None)

        if receiver is None:
            logger.warning("Connection receiver not found:%s", receiv_name)
        if sender is None or receiver is None:
            continue
        try:
            getattr(sender, sg_name).connect(getattr(receiver, sl_name))
        except Exception:
            logger.exception("Error connecting:", sender, signal_name, receiver, slot_name)

    # Cargamos menubar ...
    xmlmenubar = root.find("menubar")
    if xmlmenubar:
        # nameMB_ = xmlmenubar.find("./property[@name='name']/cstring").text
        # bar = widget.menuBar()
        # for itemM in xmlmenubar.findall("item"):
        #    menubar = bar.addMenu(itemM.get("text"))
        #    loadWidget(itemM, menubar, parent, widget)
        loadMenuBar(xmlmenubar, widget)

    # Cargamos toolbars ...
    for xmltoolbar in root.findall("toolbars//toolbar"):
        # nameTB_ = xmltoolbar.find("./property[@name='name']/cstring").text
        # toolbar = widget.addToolBar(nameTB_)
        loadToolBar(xmltoolbar, widget)

    if not project._DGI.localDesktop():
        project._DGI.showWidget(widget)
    else:
        widget.show()


def loadToolBar(xml, widget):
    name = xml.find("./property[@name='name']/cstring").text
    label = xml.find("./property[@name='label']/string").text

    tb = pncontrolsfactory.QToolBar(name)
    tb.label = label
    for a in xml:
        if a.tag == "action":
            name = a.get("name")
            ac_ = tb.addAction(name)
            ac_.setObjectName(name)
            load_action(ac_, widget)

            # FIXME!!, meter el icono y resto de datos!!
        elif a.tag == "separator":
            tb.addSeparator()

    widget.addToolBar(tb)


def loadMenuBar(xml, widget):
    if isinstance(widget, pncontrolsfactory.QMainWindow):
        mB = widget.menuBar()
    else:
        mB = QtWidgets.QMenuBar(widget)
        widget.layout().setMenuBar(mB)
    for x in xml:
        if x.tag == "property":
            name = x.get("name")
            if name == "name":
                mB.setObjectName(x.find("cstring").text)
            elif name == "geometry":
                geo_ = x.find("rect")
                x = int(geo_.find("x").text)
                y = int(geo_.find("y").text)
                w = int(geo_.find("width").text)
                h = int(geo_.find("height").text)
                mB.setGeometry(x, y, w, h)
            elif name == "acceptDrops":
                mB.setAcceptDrops(x.find("bool").text == "true")
            elif name == "frameShape":
                continue
            elif name == "defaultUp":
                mB.setDefaultUp(x.find("bool").text == "true")
        elif x.tag == "item":
            process_item(x, mB, widget)


def process_item(xml, parent, widget):
    name = xml.get("name")
    text = xml.get("text")
    # accel = xml.get("accel")

    menu_ = parent.addMenu(text)
    menu_.setObjectName(name)
    for x in xml:
        if x.tag == "action":
            name = x.get("name")
            ac_ = menu_.addAction(name)
            ac_.setObjectName(name)
            load_action(ac_, widget)
        elif x.tag == "item":
            process_item(x, menu_, widget)


def load_action(action, widget):
    real_action = widget.findChild(QtWidgets.QAction, action.objectName())
    if real_action is not None:
        action.setText(real_action.text())
        action.setIcon(real_action.icon())
        action.setToolTip(real_action.toolTip())
        if real_action.statusTip():
            action.setStatusTip(real_action.statusTip())
        else:
            action.setStatusTip(real_action.whatsThis())
        action.setWhatsThis(real_action.whatsThis())
        action.triggered.connect(real_action.trigger)
        action.toggled.connect(real_action.toggle)


def loadAction(action, widget):
    global ICONS
    act_ = QtWidgets.QAction(widget)
    for p in action.findall("property"):
        name = p.get("name")
        if name == "name":
            act_.setObjectName(p.find("cstring").text)
        elif name == "text":
            act_.setText(p.find("string").text)
        # elif name == "menuText":
        #    act_.setMenuText(p.find("string").text)
        elif name == "iconSet":
            if p.find("iconset").text in ICONS.keys():
                act_.setIcon(ICONS[p.find("iconset").text])
        elif name == "toolTip":
            act_.setToolTip(p.find("string").text)
        elif name == "statusTip":
            act_.setStatusTip(p.find("string").text)
        elif name == "whatsThis":
            act_.setWhatsThis(p.find("string").text)


def createWidget(classname, parent=None):
    from pineboolib import pncontrolsfactory

    cls = getattr(pncontrolsfactory, classname, None) or getattr(QtWidgets, classname, None)

    if cls is None:
        logger.warning("WARN: Class name not found in QtWidgets:", classname)
        widgt = QtWidgets.QWidget(parent)
        widgt.setStyleSheet("* { background-color: #fa3; } ")
        return widgt

    return cls(parent)


def loadWidget(xml, widget=None, parent=None, origWidget=None):
    translate_properties = {
        "caption": "windowTitle",
        "name": "objectName",
        "icon": "windowIcon",
        "iconSet": "icon",
        "accel": "shortcut",
        "layoutMargin": "contentsMargins",
    }
    if widget is None:
        raise ValueError
    if parent is None:
        parent = widget
    if origWidget is None:
        origWidget = widget
    # if project._DGI.localDesktop():
    #    if not hasattr(origWidget, "ui_"):
    #        origWidget.ui_ = {}
    # else:
    #    origWidget.ui_ = {}

    def process_property(xmlprop, widget=widget):
        pname = xmlprop.get("name")
        if pname in translate_properties:
            pname = translate_properties[pname]
        setpname = "set" + pname[0].upper() + pname[1:]
        if pname == "layoutSpacing":
            set_fn = widget.layout.setSpacing
        elif pname == "margin":
            set_fn = widget.setContentsMargins
        elif pname in ("paletteBackgroundColor", "paletteForegroundColor"):
            set_fn = widget.setStyleSheet
        elif pname == "menuText":
            if not isinstance(widget, pncontrolsfactory.QAction):
                set_fn = widget.menuText
            else:
                return
        elif pname == "movingEnabled":
            set_fn = widget.setMovable
        elif pname == "toggleAction":
            set_fn = widget.setChecked
        elif pname == "label" and isinstance(widget, pncontrolsfactory.QToolBar):
            return
        elif pname == "maxValue" and isinstance(widget, pncontrolsfactory.QSpinBox):
            set_fn = widget.setMaximum
        elif pname == "minValue" and isinstance(widget, pncontrolsfactory.QSpinBox):
            set_fn = widget.setMinimum
        elif pname == "lineStep" and isinstance(widget, pncontrolsfactory.QSpinBox):
            set_fn = widget.setSingleStep
        elif pname == "newLine":
            set_fn = origWidget.addToolBarBreak
        elif pname == "functionGetColor":
            set_fn = widget.setFunctionGetColor

        else:
            set_fn = getattr(widget, setpname, None)

        if set_fn is None:
            logger.warning("qt3ui: Missing property %s for %r", pname, widget.__class__)
            return
        if pname == "contentsMargins" or pname == "layoutSpacing":
            try:
                value = int(xmlprop.get("stdset"))
                value /= 2
            except Exception:
                value = 0
            if pname == "contentsMargins":
                value = QtCore.QMargins(value, value, value, value)

        elif pname == "margin":
            try:
                value = loadVariant(xmlprop)
            except Exception:
                value = 0
            value = QtCore.QMargins(value, value, value, value)

        elif pname == "paletteBackgroundColor":
            value = "background-color:" + loadVariant(xmlprop).name()

        elif pname == "paletteForegroundColor":
            value = "color:" + loadVariant(xmlprop).name()

        elif pname in ["windowIcon", "icon"]:
            value = loadVariant(xmlprop, widget)
            if isinstance(value, str):
                logger.warning("Icono %s.%s no encontrado." % (widget.objectName(), value))
                return

        else:
            value = loadVariant(xmlprop, widget)

        try:
            set_fn(value)
        except Exception:
            logger.exception(ET.tostring(xmlprop))
            # if Options.DEBUG_LEVEL > 50:
            #    print(e, repr(value))
            # if Options.DEBUG_LEVEL > 50:
            #    print(etree.ElementTree.tostring(xmlprop))

    def process_action(xmlaction, toolBar):
        action = createWidget("QAction")
        for p in xmlaction:
            pname = p.get("name")
            if pname in translate_properties:
                pname = translate_properties[pname]

            process_property(p, action)
        toolBar.addAction(action)
        # origWidget.ui_[action.objectName()] = action

    def process_layout_box(xmllayout, widget=widget, mode="box"):
        for c in xmllayout:
            try:
                row = int(c.get("row")) or 0
                col = int(c.get("column")) or 0
            except Exception:
                row = col = None

            if c.tag == "property":  # Ya se han procesado previamente ...
                continue
            elif c.tag == "widget":
                new_widget = createWidget(c.get("class"), parent=widget)
                # FIXME: Should check interfaces.
                from pineboolib.plugins.dgi.dgi_qt.dgi_objects import qbuttongroup, qtoolbutton

                if isinstance(widget, qbuttongroup.QButtonGroup):
                    if isinstance(new_widget, qtoolbutton.QToolButton):
                        widget.addButton(new_widget)
                        continue

                loadWidget(c, new_widget, parent, origWidget)
                # path = c.find("./property[@name='name']/cstring").text
                # if not pineboolib.project._DGI.localDesktop():
                #    origWidget.ui_[path] = new_widget
                # if pineboolib.project._DGI.localDesktop():
                #    new_widget.show()
                if mode == "box":
                    try:
                        widget.layout.addWidget(new_widget)
                    except Exception:
                        logger.warning("qt3ui: No se ha podido añadir %s a %s", new_widget, widget.layout)

                elif mode == "grid":
                    rowSpan = c.get("rowspan") or 1
                    colSpan = c.get("colspan") or 1
                    try:
                        widget.layout.addWidget(new_widget, row, col, int(rowSpan), int(colSpan))
                    except Exception:
                        logger.warning("qt3ui: No se ha podido añadir %s a %s", new_widget, widget)
                        logger.trace("Detalle:", stack_info=True)

            elif c.tag == "spacer":
                # sH = None
                # sV = None
                hPolicy = QtWidgets.QSizePolicy.Fixed
                vPolicy = QtWidgets.QSizePolicy.Fixed
                orient_ = None
                policy_ = None
                rowSpan = c.get("rowspan") or 1
                colSpan = c.get("colspan") or 1
                # policy_name = None
                spacer_name = None
                for p in c.findall("property"):
                    pname, value = loadProperty(p)
                    if pname == "sizeHint":
                        width = value.width()
                        height = value.height()
                    elif pname == "orientation":
                        orient_ = 1 if value == 1 else 2  # 1 Horizontal, 2 Vertical

                    elif pname == "sizeType":
                        # print("Convirtiendo %s a %s" % (p.find("enum").text, value))
                        from pineboolib.fllegacy.flsettings import FLSettings

                        settings = FLSettings()
                        if settings.readBoolEntry("ebcomportamiento/spacerLegacy", False) or orient_ == 1:
                            policy_ = QtWidgets.QSizePolicy.Policy(value)
                        else:
                            policy_ = 7  # Siempre Expanding

                    elif pname == "name":
                        spacer_name = value  # noqa: F841

                if orient_ == 1:
                    hPolicy = policy_
                else:
                    vPolicy = policy_

                # print("Nuevo spacer %s (%s,%s,(%s,%s), %s, %s" % (spacer_name, "Horizontal" if orient_ ==
                #                                                  1 else "Vertical", policy_name, width, height, hPolicy, vPolicy))
                new_spacer = QtWidgets.QSpacerItem(width, height, hPolicy, vPolicy)
                if row is not None or col is not None and mode == "grid":
                    widget.layout.addItem(new_spacer, row, col, int(rowSpan), int(colSpan))
                else:
                    widget.layout.addItem(new_spacer)
                # print("Spacer %s.%s --> %s" % (spacer_name, new_spacer, widget.objectName()))
            else:
                logger.warning("qt3ui: Unknown layout xml tag", repr(c.tag))

        widget.setLayout(widget.layout)
        # widget.layout.setContentsMargins(1, 1, 1, 1)
        # widget.layout.setSpacing(1)
        # widget.layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)

    nwidget = None
    if widget == origWidget:
        class_ = None
        if xml.get("class"):
            class_ = xml.get("class")
        else:
            class_ = type(widget).__name__

        nwidget = createWidget(class_, parent=origWidget)
        parent = nwidget
    layouts_pending_process = []
    properties = []
    unbold_fonts = []
    has_layout_defined = False

    for c in xml:
        if c.tag == "layout":
            # logger.warning("Trying to replace layout. Ignoring. %s, %s", repr(c.tag), widget.layout)
            lay_ = getattr(QtWidgets, c.get("class"))()
            lay_.setObjectName(c.get("name"))
            widget.setLayout(lay_)
            continue

        if c.tag == "property":
            properties.append(c)
            continue

        if c.tag in ("vbox", "hbox", "grid"):
            if has_layout_defined:  # nos saltamos una nueva definición del layout ( mezclas de ui incorrectas)
                # El primer layout que se define es el que se respeta
                continue

            # from pineboolib.fllegacy.flsettings import FLSettings

            # settings = FLSettings()
            if c.tag.find("box") > -1:
                layout_type = "Q%s%sLayout" % (c.tag[0:2].upper(), c.tag[2:])
            else:
                layout_type = "QGridLayout"

            widget.layout = getattr(QtWidgets, layout_type)()

            lay_name = None
            lay_margin_v = 2
            lay_margin_h = 2
            lay_spacing = 2
            for p in c.findall("property"):
                p_name = p.get("name")

                if p_name == "name":
                    lay_name = p.find("cstring").text
                elif p_name == "margin":
                    lay_margin = int(p.find("number").text)

                    if c.tag == "hbox":
                        lay_margin_h = lay_margin
                    elif c.tag == "vbox":
                        lay_margin_v = lay_margin
                    else:
                        lay_margin_h = lay_margin_v = lay_margin

                elif p_name == "spacing":
                    lay_spacing = int(p.find("number").text)
                elif p_name == "sizePolicy":
                    widget.setSizePolicy(loadVariant(p, widget))

            widget.layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
            widget.layout.setObjectName(lay_name)
            widget.layout.setContentsMargins(lay_margin_h, lay_margin_v, lay_margin_h, lay_margin_v)
            widget.layout.setSpacing(lay_spacing)

            lay_type = "grid" if c.tag == "grid" else "box"
            layouts_pending_process += [(c, lay_type)]
            has_layout_defined = True
            continue

        if c.tag == "item":
            if isinstance(widget, pncontrolsfactory.QMenu):
                continue
            else:
                prop1 = {}
                for p in c.findall("property"):
                    k, v = loadProperty(p)
                    prop1[k] = v

                widget.addItem(prop1["text"])
            continue

        if c.tag == "attribute":
            k = c.get("name")
            v = loadVariant(c)
            attrs = getattr(widget, "_attrs", None)
            if attrs is not None:
                attrs[k] = v
            else:
                logger.warning("qt3ui: [NOT ASSIGNED] attribute %r => %r" % (k, v), widget.__class__, repr(c.tag))
            continue
        if c.tag == "widget":
            # Si dentro del widget hay otro significa
            # que estamos dentro de un contenedor.
            # Según el tipo de contenedor, los widgets
            # se agregan de una forma u otra.
            new_widget = createWidget(c.get("class"), parent=parent)
            new_widget.hide()
            new_widget._attrs = {}
            loadWidget(c, new_widget, parent, origWidget)
            path = c.find("./property[@name='name']/cstring").text
            if not project._DGI.localDesktop():
                origWidget.ui_[path] = new_widget
            new_widget.setContentsMargins(0, 0, 0, 0)
            new_widget.show()

            gb = isinstance(widget, QtWidgets.QGroupBox)
            wd = isinstance(widget, QtWidgets.QWidget)
            if isinstance(widget, QtWidgets.QTabWidget):
                title = new_widget._attrs.get("title", "UnnamedTab")
                widget.addTab(new_widget, title)
            elif gb or wd:
                lay = getattr(widget, "layout")()
                if not lay and not isinstance(widget, pncontrolsfactory.QToolBar):
                    lay = QtWidgets.QVBoxLayout()
                    widget.setLayout(lay)

                if isinstance(widget, pncontrolsfactory.QToolBar):
                    if isinstance(new_widget, QtWidgets.QAction):
                        widget.addAction(new_widget)
                    else:
                        widget.addWidget(new_widget)
                else:
                    lay.addWidget(new_widget)
            else:
                if Options.DEBUG_LEVEL > 50:
                    logger.warning("qt3ui: Unknown container widget xml tag", widget.__class__, repr(c.tag))
            unbold_fonts.append(new_widget)
            continue

        if c.tag == "action":
            acName = c.get("name")
            for xmlaction in root.findall("actions//action"):
                if xmlaction.find("./property[@name='name']/cstring").text == acName:
                    process_action(xmlaction, widget)
                    continue

            continue

        if c.tag == "separator":
            widget.addSeparator()
            continue

        if c.tag == "column":
            prop1 = {}
            for p in c.findall("property"):
                k, v = loadProperty(p)
                if k == "text":
                    widget.setHeaderLabel(v)
                elif k == "clickable":
                    widget.setClickable(bool(v))
                elif k == "resizable":
                    widget.setResizable(bool(v))

            continue

        if Options.DEBUG_LEVEL > 50:
            logger.warning("%s: Unknown widget xml tag %s %s", __name__, widget.__class__, repr(c.tag))

    for c in properties:
        process_property(c)
    for c, m in layouts_pending_process:
        process_layout_box(c, mode=m)
    for new_widget in unbold_fonts:
        f = new_widget.font()
        f.setBold(False)
        f.setItalic(False)
        new_widget.setFont(f)

    # if not pineboolib.project._DGI.localDesktop():
    #    if nwidget is not None and origWidget.objectName() not in origWidget.ui_:
    #        origWidget.ui_[origWidget.objectName()] = nwidget


def loadIcon(xml):
    global ICONS

    name = xml.get("name")
    xmldata = xml.find("data")
    img_format = xmldata.get("format")
    data = unhexlify(xmldata.text.strip())
    pixmap = QtGui.QPixmap()
    if img_format == "XPM.GZ":
        data = zlib.decompress(data, 15)
        img_format = "XPM"
    pixmap.loadFromData(data, img_format)
    icon = QtGui.QIcon(pixmap)
    ICONS[name] = icon


def loadVariant(xml, widget=None):
    for variant in xml:
        return _loadVariant(variant, widget)


def loadProperty(xml):
    for variant in xml:
        return (xml.get("name"), _loadVariant(variant))


def u(x):
    if isinstance(x, str):
        return x
    return str(x)


def b(x):
    x = x.lower()
    if x[0] == "t":
        return True
    if x[0] == "f":
        return False
    if x[0] == "1":
        return True
    if x[0] == "0":
        return False
    if x == "on":
        return True
    if x == "off":
        return False
    logger.warning("Bool?:", repr(x))
    return None


def _loadVariant(variant, widget=None):
    text = variant.text or ""
    text = text.strip()
    if variant.tag == "cstring":
        return text
    if variant.tag in ["iconset", "pixmap"]:
        global ICONS
        return ICONS.get(text, text)
    if variant.tag == "string":
        return u(text)
    if variant.tag == "number":
        if text.find(".") >= 0:
            return float(text)
        return int(text)
    if variant.tag == "bool":
        return b(text)
    if variant.tag == "rect":
        k = {}
        for c in variant:
            k[c.tag] = int(c.text.strip())
        return QtCore.QRect(k["x"], k["y"], k["width"], k["height"])

    if variant.tag == "sizepolicy":

        p = QtWidgets.QSizePolicy()
        for c in variant:
            value = int(c.text.strip())
            if c.tag == "hsizetype":
                p.setHorizontalPolicy(value)
            if c.tag == "vsizetype":
                p.setVerticalPolicy(value)
            if c.tag == "horstretch":
                p.setHorizontalStretch(value)
            if c.tag == "verstretch":
                p.setVerticalStretch(value)
        return p
    if variant.tag == "size":
        p = QtCore.QSize()
        for c in variant:
            value = int(c.text.strip())
            if c.tag == "width":
                p.setWidth(value)
            if c.tag == "height":
                p.setHeight(value)
        return p
    if variant.tag == "font":
        p = QtGui.QFont()
        for c in variant:
            value = c.text.strip()
            bv = False
            if c.tag not in ("family", "pointsize"):
                bv = b(value)
            try:
                if c.tag == "bold":
                    p.setBold(bv)
                elif c.tag == "italic":
                    p.setItalic(bv)
                elif c.tag == "family":
                    p.setFamily(value)
                elif c.tag == "pointsize":
                    p.setPointSize(int(value))
                else:
                    logger.warning("unknown font style type %s", repr(c.tag))
            except Exception as e:
                if Options.DEBUG_LEVEL > 50:
                    logger.error(e)
        return p

    if variant.tag == "set":
        v = None
        final = 0
        text = variant.text
        libs = [QtCore.Qt]

        if text.find("WordBreak|") > -1:
            widget.setWordWrap(True)
            text = text.replace("WordBreak|", "")

        for lib in libs:
            for t in text.split("|"):
                v = getattr(lib, t, None)
                if v is not None:
                    final = final + v

            aF = QtCore.Qt.AlignmentFlag(final)

        return aF

    if variant.tag == "enum":
        v = None
        libs = [QtCore.Qt, QtWidgets.QFrame, QtWidgets.QSizePolicy, QtWidgets.QTabWidget]
        for lib in libs:
            v = getattr(lib, text, None)
            if v is not None:
                return v
        if text in ["GroupBoxPanel", "LineEditPanel"]:
            return QtWidgets.QFrame.StyledPanel
        if text in ("Single", "SingleRow"):
            return QtWidgets.QAbstractItemView.SingleSelection
        if text == "FollowStyle":
            return "QtWidgets.QTableView {selection-background-color: red;}"
        if text == "MultiRow":
            return QtWidgets.QAbstractItemView.MultiSelection

        att_found = getattr(widget, text, None)
        if att_found is not None:
            return att_found

    if variant.tag == "color":
        c = QtGui.QColor()
        red_ = 0
        green_ = 0
        blue_ = 0
        for color in variant:
            if color.tag == "red":
                red_ = int(color.text.strip())
            elif color.tag == "green":
                green_ = int(color.text.strip())
            elif color.tag == "blue":
                blue_ = int(color.text.strip())

        c.setRgb(red_, green_, blue_)
        return c

    if variant.tag == "palette":
        p = QtGui.QPalette()
        for state in variant:
            print("FIXME: Procesando palette", state.tag)
            for color in state:
                r_ = 0
                g_ = 0
                b_ = 0
                for c in color:
                    if c.tag == "red":
                        r_ = int(c.text)
                    elif c.tag == "green":
                        g_ = int(c.text)
                    elif c.tag == "blue":
                        b_ = int(c.text)

                if state.tag == "active":
                    # p.setColor(p.Active, Qt.QColor(r_, g_, b_))
                    pass
                elif state.tag == "disabled":
                    # p.setColor(p.Disabled, Qt.QColor(r_, g_, b_))
                    pass
                elif state.tag == "inactive":
                    # p.setColor(p.Inactive, Qt.QColor(r_, g_, b_))
                    pass
                elif state.tag == "normal":
                    # p.setColor(p.Normal, Qt.QColor(r_, g_, b_))
                    pass
                else:
                    logger.warning("Unknown palette state %s", state.tag)
                logger.debug("pallete color: %s %s %s", r_, g_, b_)

        return p

    if variant.tag == "date":

        y_ = None
        m_ = None
        d_ = None
        for v in variant:
            if v.tag == "year":
                y_ = int(v.text)
            elif v.tag == "month":
                m_ = int(v.text)
            elif v.tag == "day":
                d_ = int(v.text)

        d = QtCore.QDate(y_, m_, d_)
        return d

    if Options.DEBUG_LEVEL > 50:
        logger.warning("qt3ui: Unknown variant: %s --> %s ", repr(widget), ET.tostring(variant))
