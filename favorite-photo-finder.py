#!/usr/bin/env python3
"""
Favorite Photo Finder (reines Python-XMP/XML)
Findet JPGs mit Sternen im XMP-Bereich und kopiert Favoriten ins Zielverzeichnis.
"""

import os
import sys
import shutil
import argparse
import logging
import re
from pathlib import Path
from datetime import datetime
from xml.etree import ElementTree

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

SUPPORTED_FORMATS = ['.jpg', '.jpeg']

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

NAMESPACES = {
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "msp": "http://ns.microsoft.com/photo/1.0/",
    "dc": "http://purl.org/dc/elements/1.1/"
}

def extract_xmp(file_path):
    """Extrahiere XMP-XML-Block aus JPEG-Binary."""
    with open(file_path, "rb") as f:
        data = f.read()
        m = re.search(b"<x:xmpmeta[\s\S]+?</x:xmpmeta>", data)
        if not m:
            return None
        xml_str = m.group(0).decode("utf-8", errors="ignore")
        return xml_str
    return None

def get_xmp_rating(xmp_str):
    """Liest Sternebewertung aus XMP-XML (Adobe/Windows)."""
    if not xmp_str:
        return 0
    try:
        # Register Namespaces
        for prefix, ns in NAMESPACES.items():
            ElementTree.register_namespace(prefix, ns)
        xml = ElementTree.fromstring(xmp_str)
        for desc in xml.findall(".//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description"):
            # 1. xmp:Rating (Adobe 0-5)
            rating = desc.attrib.get(f"{{{NAMESPACES['xmp']}}}Rating")
            if rating:
                return int(rating)
            # 2. MicrosoftPhoto:Rating (1/25/50/75/99 →1-5 Sterne)
            ms_rating = desc.attrib.get(f"{{{NAMESPACES['msp']}}}Rating")
            if ms_rating:
                val = int(ms_rating)
                if val <= 1: return 1
                elif val <= 25: return 2
                elif val <= 50: return 3
                elif val <= 75: return 4
                else: return 5
        # Not found
        return 0
    except Exception as e:
        logger.debug(f"XMP parse error: {e}")
        return 0

def get_xmp_keywords(xmp_str):
    """Extrahiere Stichwörter (dc:subject, xmp:Keywords) aus XMP."""
    keywords = set()
    if not xmp_str:
        return keywords
    try:
        xml = ElementTree.fromstring(xmp_str)
        # dc:subject als Bag
        for bag in xml.findall(".//{http://purl.org/dc/elements/1.1/}subject"):
            for li in bag.findall(".//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li"):
                keywords.add(li.text.strip().upper())
        # Oder xmp:Keywords direkt
        for desc in xml.findall(".//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description"):
            kw = desc.attrib.get(f"{{{NAMESPACES['xmp']}}}Keywords")
            if kw:
                for sep in [';', ',', '|']:
                    if sep in kw:
                        keywords.update(k.strip().upper() for k in kw.split(sep))
                        break
                else:
                    keywords.add(kw.strip().upper())
        return keywords
    except Exception as e:
        logger.debug(f"XMP keyword error: {e}")
        return keywords

def get_exif_date(file_path):
    """Lese das Dateimodifizierungsdatum (Proxy für EXIF DateTimeOriginal)."""
    try:
        return datetime.fromtimestamp(os.path.getmtime(file_path))
    except Exception:
        return None

def matches_criteria(filepath, rating=None, keywords=None, year=None, month=None):
    xmp_str = extract_xmp(filepath)
    stars = get_xmp_rating(xmp_str)
    kws = get_xmp_keywords(xmp_str)
    dt = get_exif_date(filepath)
    # Sterne prüfen
    if rating is not None and stars < rating:
        return False
    # Keywords prüfen
    if keywords:
        if not any(kw.upper() in kws for kw in keywords):
            return False
    # Datum prüfen
    if (year or month) and dt:
        if year and dt.year != year:
            return False
        if month and dt.month != month:
            return False
    return True

def main():
    parser = argparse.ArgumentParser(
        description="Find JPGs with XMP star rating (pure Python/XML)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("source", help="Source directory with photos")
    parser.add_argument("destination", help="Destination directory for matches")
    parser.add_argument("-k", "--keyword", action="append", help="Filter keyword")
    parser.add_argument("-r", "--rating", type=int, choices=[1,2,3,4,5], help="Minimum stars")
    parser.add_argument("-y", "--year", type=int)
    parser.add_argument("-m", "--month", type=int, choices=range(1,13))
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Show matches, do not copy")
    args = parser.parse_args()

    src_dir = Path(args.source)
    if not src_dir.is_dir():
        print("Source directory does not exist!")
        sys.exit(1)

    files = []
    if args.recursive:
        for root, dirs, fnames in os.walk(src_dir):
            for f in fnames:
                fp = Path(root) / f
                if fp.suffix.lower() in SUPPORTED_FORMATS:
                    files.append(str(fp))
    else:
        for fp in src_dir.iterdir():
            if fp.is_file() and fp.suffix.lower() in SUPPORTED_FORMATS:
                files.append(str(fp))

    matches = []
    for fp in tqdm(files, desc="Scanning", unit="file") if tqdm else files:
        xmp_str = extract_xmp(fp)
        stars = get_xmp_rating(xmp_str)
        kws = get_xmp_keywords(xmp_str)
        dt = get_exif_date(fp)
        logger.info(f"{Path(fp).name}: Sterne={stars}, Keywords={kws}, Datum={dt}")
        if matches_criteria(fp, rating=args.rating, keywords=args.keyword, year=args.year, month=args.month):
            matches.append(fp)

    print(f"\nGefundene Favoriten (Kopie in '{args.destination}'): {len(matches)}")
    if not args.dry_run:
        Path(args.destination).mkdir(parents=True, exist_ok=True)
        for fp in matches:
            src_file = Path(fp)
            dest_file = Path(args.destination) / src_file.name
            if dest_file.exists():
                counter = 1
                stem = dest_file.stem
                suffix = dest_file.suffix
                while dest_file.exists():
                    dest_file = Path(args.destination) / f"{stem}_{counter}{suffix}"
                    counter += 1
            shutil.copy2(fp, dest_file)
        print(f"{len(matches)} Dateien kopiert!")

if __name__ == "__main__":
    main()
