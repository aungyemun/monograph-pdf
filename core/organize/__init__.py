"""PDF page organization: insert/delete/reorder/rotate/crop, merge, and split."""

from core.organize.merge import MergeJob, MergeSource, combine_to_pdf
from core.organize.page_ops import (
    PageRange,
    PageSizeInfo,
    copy_pages_between,
    crop_page,
    delete_pages,
    duplicate_pages,
    extract_pages,
    insert_blank_page,
    insert_pdf_pages,
    inspect_page_sizes,
    move_page,
    parse_page_ranges,
    replace_page,
    reorder_pages,
    rotate_pages,
    warning_for_signatures,
)
from core.organize.split import SplitMode, SplitPlan, plan_split, run_split
from core.organize.temputil import cleanup_abandoned_temps, organize_temp_dir

__all__ = [
    "MergeJob",
    "MergeSource",
    "PageRange",
    "PageSizeInfo",
    "SplitMode",
    "SplitPlan",
    "cleanup_abandoned_temps",
    "combine_to_pdf",
    "copy_pages_between",
    "crop_page",
    "delete_pages",
    "duplicate_pages",
    "extract_pages",
    "insert_blank_page",
    "insert_pdf_pages",
    "inspect_page_sizes",
    "move_page",
    "organize_temp_dir",
    "parse_page_ranges",
    "plan_split",
    "replace_page",
    "reorder_pages",
    "rotate_pages",
    "run_split",
    "warning_for_signatures",
]
