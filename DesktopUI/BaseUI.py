# desktop_ui/base_ui.py
# Minimal full UI for:
# - Selecting a Location ("mapping target") from history/schedule
# - Drawing/deleting rectangle mapping (X1,Y1,X2,Y2)
# - Random colors per object (non-deterministic, not persisted)
# - Save Mapping.csv
# - Undo (single-step stack)
# - Trigger storyboard export callback
#
# Integration pattern:
# - Core/CLI prepares:
#   - plan_image_path: str
#   - history_df: pd.DataFrame with columns: Location, X1,Y1,X2,Y2,Radius(optional)
#   - schedule_df: pd.DataFrame (used only if you want to rebuild history elsewhere; UI just lists Locations)
# - Then call run_ui(plan_image_path, history_df, on_export=..., initial_mapping_path=...)

from __future__ import annotations

import sys
import random
from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPen, QBrush, QColor, QAction
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QFileDialog,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsRectItem,
    QDockWidget,
    QMessageBox,
    QLabel,
)





# -----------------------------
# Simple undo record
# -----------------------------
@dataclass
class UndoRecord:
    location: str
    prev_coords: tuple[Optional[float], Optional[float], Optional[float], Optional[float]]
    had_item: bool
    prev_rect: Optional[QRectF]


# -----------------------------
# Canvas
# -----------------------------
class PlanView(QGraphicsView):
    """
    Canvas responsibilities:
    - Render plan image + overlay rectangles
    - Capture mouse drag to draw a rectangle
    - Emit rectangle geometry back to MainWindow via callbacks
    """

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)

        # Pan + zoom friendly defaults
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFocusPolicy(Qt.StrongFocus)

        # Drawing state
        self.mode = "select"  # "draw" or "select"
        self._drag_start: Optional[QPointF] = None
        self._temp_rect_item: Optional[QGraphicsRectItem] = None

        # Callback set by MainWindow:
        #   on_rect_finalized(location: str, rect: QRectF)
        self.on_rect_finalized: Optional[Callable[[QRectF], None]] = None

    def set_mode(self, mode: str):
        self.mode = mode

        # TIP: In a real tool, you'd change cursor/icon here.
        # self.setCursor(Qt.CrossCursor if mode == "draw" else Qt.ArrowCursor)

    def wheelEvent(self, event):
        # QoL: mouse-wheel zoom
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())

        if event.button() == Qt.LeftButton and self.mode == "draw":
            self._drag_start = scene_pos

            # Create a temporary preview rect (updated on mouse move)
            if self._temp_rect_item is None:
                pen = QPen(Qt.DashLine)
                self._temp_rect_item = self.scene().addRect(QRectF(scene_pos, scene_pos), pen)
                self._temp_rect_item.setZValue(999)

            return  # don't call super to avoid drag-pan starting while drawing

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.mode == "draw" and self._drag_start is not None and self._temp_rect_item is not None:
            scene_pos = self.mapToScene(event.pos())
            rect = QRectF(self._drag_start, scene_pos).normalized()
            self._temp_rect_item.setRect(rect)
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.mode == "draw":
            if self._drag_start is not None and self._temp_rect_item is not None:
                rect = self._temp_rect_item.rect().normalized()

                # Clean up preview item
                self.scene().removeItem(self._temp_rect_item)
                self._temp_rect_item = None
                self._drag_start = None

                # Notify MainWindow
                if self.on_rect_finalized is not None:
                    self.on_rect_finalized(rect)
            return

        super().mouseReleaseEvent(event)


# -----------------------------
# Main Window
# -----------------------------
class MainWindow(QMainWindow):
    def __init__(
        self,
        plan_image_path: str,
        history_df: pd.DataFrame,
        initial_mapping_path: Optional[str] = None,
        on_export: Optional[Callable[[pd.DataFrame], None]] = None,
    ):
        super().__init__()
        self.setWindowTitle("Storyboard Mapper")

        # Core-owned state (UI edits in-memory; core should validate before final export)
        self.history_df = history_df
        self.initial_mapping_path = initial_mapping_path
        self.on_export = on_export

        # Graphics
        self.scene = QGraphicsScene(self)
        self.view = PlanView(self.scene, self)
        self.setCentralWidget(self.view)

        self._plan_item = None
        self._rect_items_by_location: dict[str, QGraphicsRectItem] = {}
        self._colors_by_location: dict[str, QColor] = {}

        # Undo stack (QoL)
        self._undo_stack: list[UndoRecord] = []

        # Current selection
        self.current_location: Optional[str] = None

        # Load plan
        self._load_plan(plan_image_path)

        # UI chrome
        self._build_left_dock()
        self._build_toolbar()

        # Wire canvas callback
        self.view.on_rect_finalized = self._on_rect_finalized

        # Populate list + existing rectangles
        self._load_locations_into_list()
        self._render_existing_history_rects()

        # Select first item by default
        if self.location_list.count() > 0:
            self.location_list.setCurrentRow(0)

    # ---------- UI construction ----------

    def _build_left_dock(self):
        dock = QDockWidget("Mappings", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Tip label
        self.tip_label = QLabel(
            "Flow:\n"
            "1) Select a Location\n"
            "2) Click Draw, drag a rectangle\n"
            "3) Save Mapping.csv\n"
            "4) Export Storyboard"
        )
        self.tip_label.setWordWrap(True)
        layout.addWidget(self.tip_label)

        # Location list (independent scrolling)
        self.location_list = QListWidget()
        self.location_list.currentItemChanged.connect(self._on_location_selected)
        layout.addWidget(self.location_list, stretch=1)

        # Buttons
        btn_row = QHBoxLayout()
        self.draw_btn = QPushButton("Draw")
        self.delete_btn = QPushButton("Delete")
        btn_row.addWidget(self.draw_btn)
        btn_row.addWidget(self.delete_btn)
        layout.addLayout(btn_row)

        btn_row2 = QHBoxLayout()
        self.save_btn = QPushButton("Save Mapping")
        self.undo_btn = QPushButton("Undo")
        btn_row2.addWidget(self.save_btn)
        btn_row2.addWidget(self.undo_btn)
        layout.addLayout(btn_row2)

        self.export_btn = QPushButton("Export Storyboard")
        layout.addWidget(self.export_btn)

        # Wire actions
        self.draw_btn.clicked.connect(self._set_draw_mode)
        self.delete_btn.clicked.connect(self._delete_current_mapping)
        self.save_btn.clicked.connect(self._save_mapping_csv)
        self.undo_btn.clicked.connect(self._undo_last)
        self.export_btn.clicked.connect(self._export_storyboard)

        dock.setWidget(panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _build_toolbar(self):
        # Minimal toolbar QoL
        toolbar = self.addToolBar("View")

        act_zoom_in = QAction("Zoom In", self)
        act_zoom_out = QAction("Zoom Out", self)
        act_reset = QAction("Reset", self)

        act_zoom_in.triggered.connect(lambda: self.view.scale(1.25, 1.25))
        act_zoom_out.triggered.connect(lambda: self.view.scale(0.8, 0.8))
        act_reset.triggered.connect(lambda: self.view.resetTransform())

        toolbar.addAction(act_zoom_in)
        toolbar.addAction(act_zoom_out)
        toolbar.addAction(act_reset)

    # ---------- Plan + scene ----------

    def _load_plan(self, image_path: str):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            raise ValueError(f"Failed to load image: {image_path}")

        self._plan_item = self.scene.addPixmap(pixmap)
        self._plan_item.setZValue(0)
        self.scene.setSceneRect(pixmap.rect())

        # Fit initially
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    # ---------- Location list + selection ----------

    def _load_locations_into_list(self):
        self.location_list.clear()

        # If no previous mapping existed, core should already have created history_df from schedule locations.
        # UI just lists whatever is in history_df["Location"].
        for loc in self.history_df["Location"].astype(str).tolist():
            self.location_list.addItem(QListWidgetItem(loc))

    def _on_location_selected(self, current: QListWidgetItem, _previous: QListWidgetItem):
        self.current_location = current.text() if current else None

        # TIP: On selection you can also show current coords / status
        # e.g., in status bar or a small label.

    # ---------- Drawing workflow ----------

    def _set_draw_mode(self):
        if not self.current_location:
            self._msg("Select a Location first.")
            return

        self.view.set_mode("draw")
        self.statusBar().showMessage("Draw mode: drag a rectangle on the plan.", 3000)

    def _on_rect_finalized(self, rect: QRectF):
        """
        Called after user draws a rectangle on the plan.
        Writes X1,Y1,X2,Y2 into history_df for the selected location and updates overlay.
        """
        self.view.set_mode("select")  # auto-exit draw mode for safety

        if not self.current_location:
            return

        loc = self.current_location
        x1, y1, x2, y2 = rect.left(), rect.top(), rect.right(), rect.bottom()

        # Undo snapshot
        prev = self._get_coords_for_location(loc)
        had_item = loc in self._rect_items_by_location
        prev_rect = self._rect_items_by_location[loc].rect() if had_item else None
        self._undo_stack.append(UndoRecord(loc, prev, had_item, prev_rect))

        # Update dataframe
        self._set_coords_for_location(loc, x1, y1, x2, y2)

        # Update scene item
        self._upsert_rect_item(loc, rect)

    def _upsert_rect_item(self, loc: str, rect: QRectF):
        color = self._colors_by_location.get(loc)
        if color is None:
            # Non-deterministic color (good enough for now)
            color = QColor(random.randint(40, 220), random.randint(40, 220), random.randint(40, 220), 120)
            self._colors_by_location[loc] = color

        pen = QPen(color)
        pen.setWidth(2)
        brush = QBrush(color)

        if loc in self._rect_items_by_location:
            item = self._rect_items_by_location[loc]
            item.setRect(rect)
            item.setPen(pen)
            item.setBrush(brush)
        else:
            item = self.scene.addRect(rect, pen, brush)
            item.setZValue(10)
            self._rect_items_by_location[loc] = item

    def _render_existing_history_rects(self):
        """
        If history_df already has valid coords (e.g., loaded Mapping.csv),
        draw them immediately.
        """
        for loc in self.history_df["Location"].astype(str).tolist():
            x1, y1, x2, y2 = self._get_coords_for_location(loc)

            # Minimal rule: draw only if it looks defined
            if x1 is None or y1 is None or x2 is None or y2 is None:
                continue
            if (x1, y1, x2, y2) == (0, 0, 0, 0):
                continue

            rect = QRectF(QPointF(x1, y1), QPointF(x2, y2)).normalized()
            self._upsert_rect_item(loc, rect)

    # ---------- Delete / Undo / Save / Export ----------

    def _delete_current_mapping(self):
        if not self.current_location:
            self._msg("Select a Location first.")
            return

        loc = self.current_location

        # Undo snapshot
        prev = self._get_coords_for_location(loc)
        had_item = loc in self._rect_items_by_location
        prev_rect = self._rect_items_by_location[loc].rect() if had_item else None
        self._undo_stack.append(UndoRecord(loc, prev, had_item, prev_rect))

        # Clear df
        self._set_coords_for_location(loc, 0, 0, 0, 0)

        # Remove rect item (if any)
        item = self._rect_items_by_location.pop(loc, None)
        if item is not None:
            self.scene.removeItem(item)

    def _undo_last(self):
        if not self._undo_stack:
            self.statusBar().showMessage("Nothing to undo.", 2000)
            return

        rec = self._undo_stack.pop()
        loc = rec.location
        x1, y1, x2, y2 = rec.prev_coords

        # Restore df
        if x1 is None or y1 is None or x2 is None or y2 is None:
            self._set_coords_for_location(loc, 0, 0, 0, 0)
        else:
            self._set_coords_for_location(loc, x1, y1, x2, y2)

        # Restore scene item
        if rec.had_item and rec.prev_rect is not None:
            self._upsert_rect_item(loc, rec.prev_rect)
        else:
            item = self._rect_items_by_location.pop(loc, None)
            if item is not None:
                self.scene.removeItem(item)

    def _save_mapping_csv(self):
        # Default to initial mapping path if provided; otherwise ask
        default = self.initial_mapping_path or "Mapping.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Save Mapping CSV", default, "CSV Files (*.csv)")
        if not path:
            return

        # TIP: Core should own serialization long-term.
        # For now, minimal: write df as-is.
        self.history_df.to_csv(path, index=False)
        self.statusBar().showMessage(f"Saved: {path}", 3000)

    def _export_storyboard(self):
        """
        UI calls this when user clicks Export.
        Delegates to Main via callback.
        """
        if self.on_export is None:
            self._msg("Export callback not wired.")
            return

        try:
            self.on_export(self.history_df)
        except Exception as e:
            self._msg(f"Export failed:\n{e}")



    # ---------- DataFrame helpers ----------

    def _row_index_for_location(self, loc: str) -> int:
        matches = self.history_df.index[self.history_df["Location"].astype(str) == loc].tolist()
        if not matches:
            raise ValueError(f"Location not found in history_df: {loc}")
        return matches[0]

    def _get_coords_for_location(self, loc: str) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        i = self._row_index_for_location(loc)
        row = self.history_df.loc[i]
        # Keep minimal: allow ints/floats; treat missing as None
        def val(x):
            return None if pd.isna(x) else float(x)
        return (val(row.get("X1")), val(row.get("Y1")), val(row.get("X2")), val(row.get("Y2")))

    def _set_coords_for_location(self, loc: str, x1: float, y1: float, x2: float, y2: float):
        i = self._row_index_for_location(loc)
        self.history_df.at[i, "X1"] = x1
        self.history_df.at[i, "Y1"] = y1
        self.history_df.at[i, "X2"] = x2
        self.history_df.at[i, "Y2"] = y2

    # ---------- misc ----------

    def _msg(self, text: str):
        QMessageBox.information(self, "Info", text)

    def keyPressEvent(self, event):
        # QoL: keyboard zoom
        if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.view.scale(1.25, 1.25)
        elif event.key() == Qt.Key_Minus:
            self.view.scale(0.8, 0.8)
        elif event.key() == Qt.Key_0:
            self.view.resetTransform()
        else:
            super().keyPressEvent(event)


# -----------------------------
# Entry point
# -----------------------------
def run_ui(
    plan_image_path: str,
    history_df: pd.DataFrame,
    initial_mapping_path: Optional[str] = None,
    on_export: Optional[Callable[[pd.DataFrame], None]] = None,
):
    """
    Called by your CLI/main after core validation.
    - history_df should already exist (loaded mapping OR created from schedule unique locations)
    - on_export should be a core function that renders storyboard using current mapping
    """
    app = QApplication(sys.argv)
    window = MainWindow(
        plan_image_path=plan_image_path,
        history_df=history_df,
        initial_mapping_path=initial_mapping_path,
        on_export=on_export,
    )
    window.resize(1400, 900)
    window.show()
    sys.exit(app.exec())


# Standalone UI test (optional)
if __name__ == "__main__":
    # Minimal dummy history for testing only
    dummy = pd.DataFrame({
        "Location": ["A", "B", "C"],
        "X1": [0, 0, 0],
        "Y1": [0, 0, 0],
        "X2": [0, 0, 0],
        "Y2": [0, 0, 0],
        "Radius": [0, 0, 0],
    })
    run_ui("Sample.jpg", dummy)
