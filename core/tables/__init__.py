"""Line-based table detection and editable table model."""

from core.tables.model import TableCell, TableModel
from core.tables.detect import detect_tables

__all__ = ["TableCell", "TableModel", "detect_tables"]
