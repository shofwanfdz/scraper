"""
CSV Exporter
"""
import csv
import os
from typing import List, Dict, Any
from datetime import datetime

from loguru import logger

from config.settings import EXPORT_DIR


class CSVExporter:
    """Export scraped data to CSV format"""

    def export(
        self,
        data: List[Dict[str, Any]],
        filename: str = None,
        fields: List[str] = None,
    ) -> str:
        """
        Export data to CSV file.

        Args:
            data: List of data dictionaries
            filename: Output filename (auto-generated if None)
            fields: Specific fields to export (all if None)

        Returns:
            Path to the exported file
        """
        if not data:
            logger.warning("No data to export")
            return ""

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"export_{timestamp}.csv"

        filepath = os.path.join(str(EXPORT_DIR), filename)

        # Determine fields
        if not fields:
            fields = list(data[0].keys())

        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for row in data:
                    # Flatten nested dicts/lists for CSV
                    flat_row = {}
                    for key in fields:
                        value = row.get(key, "")
                        if isinstance(value, (list, dict)):
                            value = str(value)
                        flat_row[key] = value
                    writer.writerow(flat_row)

            logger.info(f"CSV exported: {filepath} ({len(data)} rows)")
            return filepath

        except Exception as e:
            logger.error(f"CSV export failed: {e}")
            return ""
