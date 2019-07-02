from pineboolib.core.utils.utils_base import StructMyDict
from functools import total_ordering

from PyQt5 import QtCore

import logging

logger = logging.getLogger(__name__)


def Boolean(x=False):
    """
    Retorna Booelan de una cadena de texto
    """
    ret = False
    if x in ["true", "True", True, 1] or isinstance(x, int) > 0 or isinstance(x, float) > 0:
        ret = True

    return ret


class QString(str):
    """
    Clase QString para simular la original que no existe en PyQt5
    """

    def mid(self, start, length=None):
        """
        Recoje una sub cadena a partir de una cadena
        @param start. Posición inicial
        @param length. Longitud de la cadena. Si no se especifica , es hasta el final
        @return sub cadena de texto.
        """
        if length is None:
            return self[start:]
        else:
            return self[start : start + length]


def Function(*args):

    import importlib
    import sys as python_sys

    # Leer código QS embebido en Source
    # asumir que es una funcion anónima, tal que:
    #  -> function($args) { source }
    # compilar la funcion y devolver el puntero
    arguments = args[: len(args) - 1]
    source = args[len(args) - 1]
    qs_source = """

function anon(%s) {
    %s
} """ % (
        ", ".join(arguments),
        source,
    )

    # print("Compilando QS en línea: ", qs_source)
    from pineboolib.flparser import flscriptparse
    from pineboolib.flparser import postparse
    from pineboolib.flparser.pytnyzer import write_python_file

    prog = flscriptparse.parse(qs_source)
    tree_data = flscriptparse.calctree(prog, alias_mode=0)
    ast = postparse.post_parse(tree_data)
    dest_filename = "%s/anon.py" % aqApp.tmp_dir()
    # f1 = io.StringIO()
    if os.path.exists(dest_filename):
        os.remove(dest_filename)

    f1 = open(dest_filename, "w", encoding="UTF-8")

    write_python_file(f1, ast)
    f1.close()
    mod = None
    module_path = "tempdata.anon"

    if module_path in python_sys.modules:
        mod = importlib.reload(python_sys.modules[module_path])
    else:
        mod = importlib.import_module(module_path)
    return mod.FormInternalObj().anon


def Object(x: None = None) -> StructMyDict:
    """
    Objeto tipo object
    """
    if x is None:
        x = {}

    from pineboolib.core.utils.utils_base import StructMyDict

    return StructMyDict(x)


def String(value):
    """
    Devuelve una cadena de texto
    @param value. Valor a convertir
    @return cadena de texto.
    """
    return str(value)


class Array(object):
    """
    Objeto tipo Array
    """

    dict_ = None
    key_ = None
    names_ = None
    pos_iter = None

    def __init__(self, *args) -> None:
        import collections

        self.dict_ = collections.OrderedDict()

        if not len(args):
            return
        elif isinstance(args[0], int) and len(args) == 1:
            return
        elif isinstance(args[0], list):
            for field in args[0]:

                field_key = field
                while field_key in self.dict_.keys():
                    field_key = "%s_bis" % field_key

                self.dict_[field_key] = field

        elif isinstance(args[0], str):
            for f in args:
                self.__setitem__(f, f)
        else:
            self.dict_ = args

    def __iter__(self):
        """
        iterable
        """
        self.pos_iter = 0
        return self

    def __next__(self):
        """
        iterable
        """
        ret_ = None
        i = 0
        if self.dict_:
            for k in self.dict_.keys():
                if i == self.pos_iter:
                    ret_ = self.dict_[k]
                    break

                i += 1

        if ret_ is None:
            raise StopIteration
        else:
            self.pos_iter += 1

        return ret_

    def __setitem__(self, key, value):
        """
        Especificamos una nueva entrada
        @param key. Nombre del registro
        @param value. Valor del registro
        """

        self.dict_[key] = value

    def __getitem__(self, key):
        """
        Recogemos el valor de un registro
        @param key. Valor que idenfica el registro a recoger
        @return Valor del registro especificado
        """
        if isinstance(key, int):
            i = 0
            for k in self.dict_.keys():
                if key == i:
                    return self.dict_[k]
                i += 1

        elif isinstance(key, slice):
            logger.warning("FIXME: Array __getitem__%s con slice" % key)
        else:
            return self.dict_[key] if key in self.dict_.keys() else None

        return None

    def __getattr__(self, k):
        if k == "length":
            return len(self.dict_)
        else:
            return self.dict_[k]

    def splice(self, *args):
        if len(args) == 2:  # Delete
            pos_ini = args[0]
            length_ = args[1]
            i = 0
            x = 0
            new = {}
            for m in self.dict_.keys():
                if i >= pos_ini and x <= length_:
                    new[m] = self.dict_[m]
                    x += 1

                i += 1

            self.dict_ = new

        elif len(args) > 2 and args[1] == 0:  # Insertion
            for i in range(2, len(args)):
                self.append(args[i])
        elif len(args) > 2 and args[1] > 0:  # Replacement
            pos_ini = args[0]
            replacement_size = args[1]
            new_values = args[2:]

            i = 0
            x = 0
            new = {}
            for m in self.dict_.keys():
                if i < pos_ini:
                    new[m] = self.dict_[m]
                else:
                    if x < replacement_size:
                        if x == 0:
                            for n in new_values:
                                new[n] = n

                        x += 1
                    else:
                        new[m] = self.dict_[m]

                i += 1

            self.dict_ = new

    def __len__(self):
        return len(self.dict_)

    def __str__(self):
        return " ".join(self.dict_.keys())

    def append(self, val):
        k = repr(val)
        while True:
            if hasattr(self.dict_, k):
                k = "%s_" % k
            else:
                break

        self.dict_[k] = val


@total_ordering
class Date(object):
    """
    Case que gestiona un objeto tipo Date
    """

    date_ = None
    time_ = None

    def __init__(self, *args):
        super(Date, self).__init__()
        if not args:
            self.date_ = QtCore.QDate.currentDate()
            self.time_ = QtCore.QTime.currentTime()
        elif len(args) <= 2:
            date_ = args[0]
            format_ = args[1] if len(args) == 2 else "yyyy-MM-dd"
            self.time_ = None
            if isinstance(date_, str):
                if len(date_) == 10:
                    tmp = date_.split("-")
                    if len(tmp[2]) == 4:
                        from pineboolib.application.utils.date_conversion import date_dma_to_amd

                        date_ = date_dma_to_amd(date_)

                    self.date_ = QtCore.QDate.fromString(date_, format_)
                else:
                    self.date_ = QtCore.QDate.fromString(date_[0:10], format_)
                    self.time_ = QtCore.QTime.fromString(date_[11:], "hh:mm:ss")

            elif isinstance(date_, Date):
                self.date_ = date_.date_
                self.time_ = date_.time_

            elif isinstance(date_, QtCore.QDate):
                self.date_ = date_
            if not self.time_:
                self.time_ = QtCore.QTime(0, 0)
        else:
            self.date_ = QtCore.QDate(args[0], args[1], args[2])
            self.time_ = QtCore.QTime(0, 0)

    def toString(self, pattern=None):
        """
        Retorna una cadena de texto con los datos de fecha y hora.
        @return cadena de texto con los datos de fecha y hora
        """
        if pattern:
            texto = self.date_.toString(pattern)

        texto = "%s-%s-%sT%s:%s:%s" % (
            self.date_.toString("yyyy"),
            self.date_.toString("MM"),
            self.date_.toString("dd"),
            self.time_.toString("hh"),
            self.time_.toString("mm"),
            self.time_.toString("ss"),
        )
        return texto

    def getYear(self):
        """
        Retorna el año
        @return año
        """
        return self.date_.year()

    def setYear(self, yyyy):
        """
        Setea un año dado
        @param yyyy. Año a setear
        """
        if yyyy is not None:
            self.date_ = QtCore.QDate.fromString("%s-%s-%s" % (yyyy, self.date_.toString("MM"), self.date_.toString("dd")), "yyyy-MM-dd")

        return self

    def getMonth(self):
        """
        Retorna el mes
        @return mes
        """
        return self.date_.month()

    def setMonth(self, mm):
        """
        Setea un mes dado
        @param mm. Mes a setear
        """

        if mm is not None:
            if len(str(mm)) == 1:
                mm = "0%s" % mm
            self.date_ = QtCore.QDate.fromString("%s-%s-%s" % (self.date_.toString("yyyy"), mm, self.date_.toString("dd")), "yyyy-MM-dd")

        return self

    def getDay(self):
        """
        Retorna el día
        @return día
        """
        return self.date_.day()

    def setDay(self, dd):
        """
        Setea un dia dado
        @param dd. Dia a setear
        """
        if dd is not None:
            if len(str(dd)) == 1:
                dd = "0%s" % dd

            self.date_ = QtCore.QDate.fromString("%s-%s-%s" % (self.date_.toString("yyyy"), self.date_.toString("mm"), dd), "yyyy-MM-dd")

        return self

    def getHours(self):
        """
        Retorna horas
        @return horas
        """
        return self.time_.hour()

    def getMinutes(self):
        """
        Retorna minutos
        @return minutos
        """
        return self.time_.minute()

    def getSeconds(self):
        """
        Retorna segundos
        @return segundos
        """
        return self.time_.second()

    def getMilliseconds(self):
        """
        Retorna milisegundos
        @return milisegundos
        """
        return self.time_.msec()

    def setDate(self, date):
        """
        Se especifica fecha
        @param date. Fecha a setear
        """
        year_ = self.date_.toString("yyyy")
        month_ = self.date_.toString("MM")
        day_ = str(date)
        if len(day_) == 1:
            day_ = "0" + day_

        str_ = "%s-%s-%s" % (year_, month_, day_)
        self.date_ = QtCore.QDate.fromString(str_, "yyyy-MM-dd")

        return self

    def addDays(self, d):
        """
        Se añaden dias a una fecha dada
        @param d. Dias a sumar (o restar) a la fecha dada
        @return nueva fecha calculada
        """
        return Date(self.date_.addDays(d).toString("yyyy-MM-dd"))

    def addMonths(self, m):
        """
        Se añaden meses a una fecha dada
        @param m. Meses a sumar (o restar) a la fecha dada
        @return nueva fecha calculada
        """
        return Date(self.date_.addMonths(m).toString("yyyy-MM-dd"))

    def addYears(self, y):
        """
        Se añaden años a una fecha dada
        @param y. Años a sumar (o restar) a la fecha dada
        @return nueva fecha calculada
        """
        return Date(self.date_.addYears(y).toString("yyyy-MM-dd"))

    @classmethod
    def parse(cls, value):
        return QtCore.QDate.fromString(value, "yyyy-MM-dd")

    def __str__(self):
        return self.toString()

    def __le__(self, other):
        """
        Esta función junto con total_ordering, sirve para poder comparar este tipo con otro similar
        return Boolean. True si este objeto es menor que el comparado
        """
        return self.toString() < other.toString() if not isinstance(other, str) else other

    def __eq__(self, other):
        if str(other) == self.toString():
            return True
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)