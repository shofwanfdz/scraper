"""
JSON Exporter
"""
import json
import os
from typing import List, Dict, Any
from datetime import datetime

from loguru import logger

from config.settings import EXPORT_DIR


class JSONExporter:
    """Export scraped data to JSON format"""

    def export(
        self,
        data: List[Dict[str, Any]],
        filename: str = None,
        pretty: bool = True,
    ) -> str:
        """
        Export data to JSON file.

        Args:
            data: List of data dictionaries
            filename: Output filename (auto-generated if None)
            pretty: Whether to format JSON with indentation

        Returns:
            Path to the exported file
        """
        if not data:
            logger.warning("No data to export")
            return ""

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"export_{timestamp}.json"

        filepath = os.path.join(str(EXPORT_DIR), filename)

        try:
            export_data = {
                "metadata": {
                    "exported_at": datetime.now().isoformat(),
                    "total_records": len(data),
                },
                "data": data,
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(
                    export_data,
                    f,
                    ensure_ascii=False,
                    indent=2 if pretty else None,
                    default=str,
                )

            logger.info(f"JSON exported: {filepath} ({len(data)} records)")
            return filepath

        except Exception as e:
            logger.error(f"JSON export failed: {e}")
            return ""
