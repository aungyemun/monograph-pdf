"""Font box you can type into: matching fonts appear in a list as you type.

Typing ``ti`` lists every installed font containing "ti" (Times New Roman, Tahoma Italic
families, Constantia …), case-insensitive. Nothing is applied while you type; the font is
applied when you pick it from the list, choose it from the drop-down, or press Enter on a
font name that exists. Unknown text is reverted to the current font.

Built on a plain ``QComboBox`` with Monograph PDF's own list model and row painter. Earlier versions
wrapped the row painter of Qt's ``QFontComboBox``; Qt owns and may replace or delete that painter
(style changes, font-database changes, the box being destroyed), and a call into a deleted painter
while the list was open or scrolling ended the whole application (access violation). Nothing here
depends on an object Qt can delete behind our back:

* one font list per process (``font_families()``), refreshed when the font database changes;
* the row painter belongs to the box (strong reference, parent = the box) and never raises;
* every row has the same height (no per-row measuring in each font while scrolling);
* while the list is open the box is never changed from outside (``set_family`` waits until it
  closes) and owners can ask ``popup_open()`` before rebuilding or deleting the box.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QSize, QStringListModel, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QCompleter, QStyle, QStyledItemDelegate, QStyleOptionViewItem

# ---------------------------------------------------------------------------------------- font list
_FAMILIES: list[str] | None = None
_DB_HOOKED = False


def _reset_families() -> None:
    global _FAMILIES
    _FAMILIES = None


def font_families() -> list[str]:
    """Installed + bundled font families, sorted case-insensitively, without Windows' vertical
    ``@`` variants and private system families. Built once per process (a copy is returned)."""
    global _FAMILIES, _DB_HOOKED
    if _FAMILIES is None:
        try:  # bundled fonts appear in the list together with the installed ones
            from core.editing.font_resolver import register_bundled_fonts

            register_bundled_fonts()
        except Exception:  # noqa: BLE001 — the installed fonts still work
            pass
        seen: dict[str, str] = {}
        for fam in QFontDatabase.families():
            if not fam or fam.startswith("@"):
                continue
            try:
                if QFontDatabase.isPrivateFamily(fam):
                    continue
                # Old Windows bitmap fonts (8514oem, Fixedsys, Terminal, MS Sans Serif …) cannot be put
                # in a PDF and DirectWrite cannot even open some of them: not offered
                if not QFontDatabase.isSmoothlyScalable(fam):
                    continue
            except Exception:  # noqa: BLE001
                pass
            seen.setdefault(fam.casefold(), fam)
        _FAMILIES = sorted(seen.values(), key=lambda s: s.casefold())
        app = QGuiApplication.instance()
        if app is not None and not _DB_HOOKED and hasattr(app, "fontDatabaseChanged"):
            try:
                app.fontDatabaseChanged.connect(_reset_families)
                _DB_HOOKED = True
            except Exception:  # noqa: BLE001
                pass
    return list(_FAMILIES)


_NAME_CACHE: dict[str, tuple[str, ...]] = {}


def font_family_names(family: str) -> tuple[str, ...]:
    """Every family name (all languages) recorded in the installed font file for *family* (Windows
    font registry + the font's name table); empty when not found."""
    key = family.strip().lower()
    if key in _NAME_CACHE:
        return _NAME_CACHE[key]
    names: list[str] = []
    try:
        from fontTools.ttLib import TTCollection, TTFont

        from core.editing.system_fonts import find_font_file, is_collection

        path = find_font_file(family)
        if path is not None:
            fonts = TTCollection(str(path), lazy=True).fonts if is_collection(str(path)) else [TTFont(str(path), lazy=True)]
            for tt in fonts:
                table = tt["name"]
                fam = {r.toUnicode().strip() for r in table.names if r.nameID in (1, 16)}
                if any(n.lower() == key for n in fam) or len(fonts) == 1:
                    names.extend(sorted(fam))
    except Exception:  # noqa: BLE001 — no file or unreadable: no other names
        names = []
    _NAME_CACHE[key] = tuple(dict.fromkeys(names))
    return _NAME_CACHE[key]


# ------------------------------------------------------------------------------------- row painter
class FontRowDelegate(QStyledItemDelegate):
    """Draws each family name in its own font (fonts without Latin letters, such as symbol or
    CJK-only fonts, show their name in the interface font and a short sample in the font itself) and
    marks the font in use: a tinted row, an accent bar and a check mark — readable in both themes."""

    def __init__(self, picker: "FontPicker") -> None:
        super().__init__(picker)
        self._picker = picker
        self._fonts: dict[str, tuple[QFont, str]] = {}

    def _font_for(self, family: str, base: QFont) -> tuple[QFont, str]:
        """(font for the name, sample text or "") for *family*; cached."""
        hit = self._fonts.get(family)
        if hit is not None:
            return hit
        font = QFont(base)
        sample = ""
        try:
            systems = QFontDatabase.writingSystems(family)
            if QFontDatabase.WritingSystem.Latin in systems:
                font.setFamilies([family])
            else:
                for ws in systems:
                    if ws not in (QFontDatabase.WritingSystem.Any, QFontDatabase.WritingSystem.Latin):
                        sample = QFontDatabase.writingSystemSample(ws)[:6]
                        break
                if not sample:
                    sample = "Aa"
        except Exception:  # noqa: BLE001 — draw the name in the interface font
            pass
        self._fonts[family] = (font, sample)
        return self._fonts[family]

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        # Width of the name in the interface font (the list is as wide as the box; long names are
        # elided). Never the option's rect: that made every row hundreds of pixels wide, past the
        # list's visible area, where a click no longer chose the font.
        fm = option.fontMetrics
        h = max(22, int(fm.height() * 1.55))
        name = str(index.data(Qt.ItemDataRole.DisplayRole) or "") if index is not None and index.isValid() else ""
        return QSize(min(360, fm.horizontalAdvance(name) + 48), h)

    def paint(self, painter: QPainter, option, index) -> None:
        # Never raise from a paint handler: anything unexpected draws the row the standard way.
        try:
            self._paint(painter, option, index)
        except Exception:  # noqa: BLE001
            try:
                super().paint(painter, option, index)
            except Exception:  # noqa: BLE001
                pass

    def _paint(self, painter: QPainter, option, index) -> None:
        from ui.theme import current_palette

        family = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget is not None else None
        picker = self._picker
        try:
            active = picker is not None and index.row() == picker.active_row()
        except RuntimeError:
            active = False
        pal = current_palette()
        accent = QColor(pal.accent)
        painter.save()
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)  # background, hover, selection
        r = option.rect
        if active:
            tint = QColor(accent)
            tint.setAlpha(60)
            painter.fillRect(r, tint)
            painter.fillRect(r.x(), r.y(), 3, r.height(), accent)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        role = opt.palette.ColorRole.HighlightedText if selected else opt.palette.ColorRole.Text
        painter.setPen(opt.palette.color(role))
        font, sample = self._font_for(family, option.font)
        text_rect = r.adjusted(10, 0, -(28 if active else 8), 0)
        if sample:
            sf = QFont(option.font)
            sf.setFamilies([family])
            painter.setFont(sf)
            sw = min(text_rect.width() // 3, painter.fontMetrics().horizontalAdvance(sample) + 8)
            painter.drawText(text_rect.adjusted(text_rect.width() - sw, 0, 0, 0),
                             int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), sample)
            text_rect = text_rect.adjusted(0, 0, -sw - 6, 0)
        painter.setFont(font)
        elided = painter.fontMetrics().elidedText(family, Qt.TextElideMode.ElideRight, max(10, text_rect.width()))
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), elided)
        if active:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(QColor(pal.accent_text), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                       Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            cx, cy = r.right() - 14.0, r.center().y()
            painter.drawPolyline(QPolygonF([QPointF(cx - 4.5, cy), QPointF(cx - 1.5, cy + 3.5), QPointF(cx + 4.5, cy - 3.5)]))
        painter.restore()


# ------------------------------------------------------------------------------------------- picker
class _FamilyModel(QStringListModel):
    """The family names, read-only (an editable row would start an in-place editor on a click
    instead of choosing the font)."""

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemNeverHasChildren


class FontPicker(QComboBox):
    fontPicked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last = ""
        self._pending_family: str | None = None
        self._active_key: tuple | None = None
        self._active_row = -1
        self._families_model = _FamilyModel(font_families(), self)
        self.setModel(self._families_model)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMaxVisibleItems(16)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(10)
        self.setToolTip("Font — type a few letters to find a font")
        self.setAccessibleName("Font")
        # Strong reference, parented to the box: Qt never hands us a painter it may delete.
        self._font_delegate = FontRowDelegate(self)
        self.setItemDelegate(self._font_delegate)
        view = self.view()
        if hasattr(view, "setUniformItemSizes"):
            view.setUniformItemSizes(True)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.verticalScrollBar().setSingleStep(max(12, self.fontMetrics().height()))
        view.setTextElideMode(Qt.TextElideMode.ElideRight)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        completer = QCompleter(self._families_model, self)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setMaxVisibleItems(14)
        self.setCompleter(completer)
        completer.activated[str].connect(self._pick)
        self.activated.connect(lambda i: self._pick(self.itemText(i)))
        line = self.lineEdit()
        line.setPlaceholderText("Type to search fonts")
        line.returnPressed.connect(self._commit_typed)
        line.editingFinished.connect(self._commit_typed)
        line.installEventFilter(self)  # one click on the name opens the list (typing still searches)
        self.blockSignals(True)
        self.setCurrentIndex(-1)
        self.setEditText("")
        self.blockSignals(False)

    # ------------------------------------------------------------------ events
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        # One click on the font name opens the list. While you are typing a search (the box holds
        # text other than the font in use) or have selected text, a click only places the cursor.
        try:
            if obj is self.lineEdit() and event.type() == QEvent.Type.MouseButtonRelease \
                    and event.button() == Qt.MouseButton.LeftButton:
                typed = obj.text().strip().lower()
                untouched = typed == (self._last or "").strip().lower()
                if untouched and not obj.hasSelectedText() and not self.popup_open():
                    self.showPopup()
                    return True
        except RuntimeError:  # the line edit is being destroyed
            return False
        return super().eventFilter(obj, event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        """Turning the mouse wheel over the closed box does not change the font (it used to apply a
        new font at every notch while you scrolled a panel); the panel or page scrolls instead. The
        open list scrolls as usual."""
        event.ignore()

    # ------------------------------------------------------------------ public
    def popup_open(self) -> bool:
        """True while the drop-down list or the search suggestions are shown. The box must not be
        rebuilt, refilled or deleted meanwhile."""
        try:
            view = self.view()
            if view is not None and view.isVisible():
                return True
            comp = self.completer()
            popup = comp.popup() if comp is not None else None
            return bool(popup is not None and popup.isVisible())
        except RuntimeError:
            return False

    def active_row(self) -> int:
        """List row of the font in use, or -1 when it is not an installed font (e.g. an embedded-only
        PDF font): nothing unrelated is then shown as selected.

        Cached: the list asks for it once per painted row while it scrolls. A family saved under its
        English name ("MS Mincho") is found under the localized list name ("ＭＳ 明朝") too."""
        key = (self._last, self.count())
        if self._active_key != key:
            self._active_key = key
            self._active_row = self._find_family_row(self._last or "")
        return self._active_row

    def _find_family_row(self, family: str) -> int:
        if not family:
            return -1
        row = self.findText(family, Qt.MatchFlag.MatchFixedString)
        if row >= 0:
            return row
        import unicodedata

        def norm(name: str) -> str:
            return unicodedata.normalize("NFKC", name).replace(" ", "").casefold()

        wanted = norm(family)
        names = {norm(self.itemText(i)): i for i in range(self.count())}
        if wanted in names:  # full-width / spacing differences
            return names[wanted]
        # The same font under another name: a Japanese font saved as "MS Mincho" is listed as "ＭＳ 明朝"
        # on Japanese Windows. Only names inside the font file itself count, never a look-alike
        # substitute (Helvetica is not shown as Arial).
        for other in font_family_names(family):
            row = names.get(norm(other))
            if row is not None:
                return row
        return -1

    def set_family(self, family: str) -> None:
        """Show ``family`` without emitting fontPicked and without picking a look-alike font.

        While the list is open nothing is changed (that made the open list jump and shake when the
        window refreshed its toolbar); the family is shown when the list closes."""
        if self.popup_open():
            self._pending_family = family
            return
        self._pending_family = None
        line = self.lineEdit()
        if family and family == self._last and line is not None and line.text() == family:
            return  # nothing changes — no repaint, no reselect
        self.blockSignals(True)
        try:
            if family:
                idx = self._find_family_row(family)
                if idx >= 0:
                    if idx != self.currentIndex():
                        self.setCurrentIndex(idx)
                    self._last = self.itemText(idx)
                else:  # a PDF font that is not installed: show its name, select nothing
                    self.setCurrentIndex(-1)
                    self._last = family
                if line is not None and line.text() != self._last:
                    self.setEditText(self._last)
        finally:
            self.blockSignals(False)
        self.view().viewport().update()

    def showPopup(self) -> None:  # noqa: N802
        """Open with the font in use highlighted and in view (nothing is applied). The current row is
        set before the list opens, so Qt places the list once instead of opening and then jumping."""
        row = self.active_row()
        self.blockSignals(True)
        try:
            if row >= 0 and row != self.currentIndex():
                self.setCurrentIndex(row)
        finally:
            self.blockSignals(False)
        super().showPopup()
        view = self.view()
        if row >= 0:
            index = self.model().index(row, 0)
            view.setCurrentIndex(index)
            view.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)
        else:
            view.clearSelection()
        view.viewport().update()

    def hidePopup(self) -> None:  # noqa: N802
        super().hidePopup()
        pending = self._pending_family
        if pending is not None:
            # after the list has closed completely (never inside Qt's own hide handling)
            QTimer.singleShot(0, self, lambda: self.set_family(pending) if self._pending_family == pending else None)
            return
        # the list's current row may have changed the shown name without a pick (Escape): restore it
        line = self.lineEdit()
        if line is not None and self._last and line.text() != self._last:
            self.blockSignals(True)
            self.setEditText(self._last)
            self.blockSignals(False)

    def family(self) -> str:
        return self._last

    # ---------------------------------------------------------------- internals
    def _match(self, text: str) -> int:
        text = text.strip()
        if not text:
            return -1
        exact = self.findText(text, Qt.MatchFlag.MatchFixedString)  # case-insensitive exact
        if exact >= 0:
            return exact
        low = text.lower()
        starts = [i for i in range(self.count()) if self.itemText(i).lower().startswith(low)]
        if len(starts) == 1:
            return starts[0]
        contains = [i for i in range(self.count()) if low in self.itemText(i).lower()]
        return contains[0] if len(contains) == 1 else -1

    def _commit_typed(self) -> None:
        line = self.lineEdit()
        if line is None:
            return
        typed = line.text()
        if typed.strip().lower() == (self._last or "").lower():
            return
        idx = self._match(typed)
        if idx >= 0:
            self._pick(self.itemText(idx))
        else:
            self.blockSignals(True)
            self.setEditText(self._last)
            self.blockSignals(False)

    def _pick(self, family: str) -> None:
        if not family:
            return
        idx = self.findText(family, Qt.MatchFlag.MatchFixedString)
        self.blockSignals(True)
        try:
            if idx >= 0 and idx != self.currentIndex():
                self.setCurrentIndex(idx)
            line = self.lineEdit()
            if line is not None and line.text() != family:
                self.setEditText(family)
        finally:
            self.blockSignals(False)
        self._pending_family = None  # what the user picked wins over a refresh made while the list was open
        if family != self._last:
            self._last = family
            self.fontPicked.emit(family)
        self.view().viewport().update()  # the check mark moves to the picked font
