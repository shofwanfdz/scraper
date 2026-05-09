"""
Excel Exporter
"""
import os
from typing import List, Dict, Any
from datetime import datetime

from loguru import logger

from config.settings import EXPORT_DIR


class ExcelExporter:
    """Export scraped data to Excel format"""

    def export(
        self,
        data: List[Dict[str, Any]],
        filename: str = None,
        sheet_name: str = "Scraped Data",
    ) -> str:
        """
        Export data to Excel file.

        Args:
            data: List of data dictionaries
            filename: Output filename (auto-generated if None)
            sheet_name: Name of the Excel sheet

        Returns:
            Path to the exported file
        """
        if not data:
            logger.warning("No data to export")
            return ""

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"export_{timestamp}.xlsx"

        filepath = os.path.join(str(EXPORT_DIR), filename)

        try:
            import pandas as pd

            # Flatten nested structures
            flat_data = []
            for row in data:
                flat_row = {}
                for key, value in row.items():
                    if isinstance(value, (list, dict)):
                        flat_row[key] = str(value)
                    else:
                        flat_row[key] = value
                flat_data.append(flat_row)

            df = pd.DataFrame(flat_data)
            df.to_excel(filepath, sheet_name=sheet_name, index=False, engine="openpyxl")

            logger.info(f"Excel exported: {filepath} ({len(data)} rows)")
            return filepath

        except ImportError:
            logger.error("pandas/openpyxl not installed. Run: pip install pandas openpyxl")
            return ""
        except Exception as e:
            logger.error(f"Excel export failed: {e}")
            return ""
