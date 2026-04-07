from __future__ import annotations

import glob
import sys
from pathlib import Path


def import_pymupdf():
    try:
        import pymupdf as fitz

        return fitz
    except ModuleNotFoundError:
        project_dir = Path(__file__).resolve().parents[1]
        for env_name in (".venv", "env"):
            pattern = project_dir / env_name / "lib" / "python*" / "site-packages"
            for site_packages in sorted(glob.glob(str(pattern))):
                if site_packages not in sys.path:
                    sys.path.insert(0, site_packages)
                try:
                    import pymupdf as fitz

                    return fitz
                except ModuleNotFoundError:
                    continue
        raise
