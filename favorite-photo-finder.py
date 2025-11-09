#!/usr/bin/env python3
"""
Favorite Photo Finder

Finds photos with specific EXIF tags/ratings and copies them to a target directory.
Useful for creating yearly photo books/calendars from marked photos.

Supports:
- EXIF Keywords (e.g., "FAVORITE", "CALENDAR", "BEST")
- EXIF Ratings (1-5 stars)
- Custom date ranges

Usage:
    python favorite-photo-finder.py <source_dir> <dest_dir> [options]
    
Examples:
    # Find all photos with keyword "FAVORITE"
    python favorite-photo-finder.py ~/Photos ~/Favorites --keyword FAVORITE
    
    # Find all 5-star rated photos
    python favorite-photo-finder.py ~/Photos ~/Best --rating 5
    
    # Find favorites from 2024
    python favorite-photo-finder.py ~/Photos ~/Calendar2024 --keyword FAVORITE --year 2024
"""

import os
import sys
import shutil
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Set

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
except ImportError:
    print("Error: Pillow library required. Install with: pip install Pillow")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    print("Warning: tqdm not found. Progress bar disabled. Install with: pip install tqdm")
    tqdm = None

# Constants
SUPPORTED_FORMATS = ['.jpg', '.jpeg', '.png', '.heic', '.heif']

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('favorite_finder.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PhotoMetadata:
    """Extract and analyze photo metadata."""
    
    def __init__(self, file_path: str):
        self.path = file_path
        self.file_path = Path(file_path)
        self._exif = None
        self._keywords = None
        self._rating = None
        self._date = None
        
    @property
    def exif(self) -> dict:
        """Get all EXIF data."""
        if self._exif is None:
            try:
                with Image.open(self.path) as img:
                    exif_data = img.getexif()
                    if exif_data:
                        self._exif = {
                            TAGS.get(tag, tag): value
                            for tag, value in exif_data.items()
                        }
                    else:
                        self._exif = {}
            except Exception as e:
                logger.debug(f"Could not read EXIF from {self.file_path.name}: {e}")
                self._exif = {}
        return self._exif
    
    @property
    def keywords(self) -> Set[str]:
        """Get EXIF keywords as set (case-insensitive)."""
        if self._keywords is None:
            keywords = set()
            exif = self.exif
            
            # Check various possible keyword fields
            for field in ['Keywords', 'XPKeywords', 'Subject', 'TagsList']:
                if field in exif:
                    value = exif[field]
                    if isinstance(value, str):
                        # Split by common separators
                        for sep in [';', ',', '|']:
                            if sep in value:
                                keywords.update(k.strip().upper() for k in value.split(sep))
                                break
                        else:
                            keywords.add(value.strip().upper())
                    elif isinstance(value, (list, tuple)):
                        keywords.update(str(k).strip().upper() for k in value)
            
            self._keywords = keywords
        return self._keywords
    
    @property
    def rating(self) -> Optional[int]:
        """Get EXIF rating (0-5 stars)."""
        if self._rating is None:
            exif = self.exif
            
            # Check various rating fields
            for field in ['Rating', 'RatingPercent']:
                if field in exif:
                    try:
                        rating = int(exif[field])
                        # Normalize to 0-5
                        if field == 'RatingPercent':
                            rating = rating // 20
                        self._rating = max(0, min(5, rating))
                        return self._rating
                    except (ValueError, TypeError):
                        pass
            
            self._rating = 0
        return self._rating
    
    @property
    def date_taken(self) -> Optional[datetime]:
        """Get date photo was taken."""
        if self._date is None:
            exif = self.exif
            
            # Try multiple date fields
            for field in ['DateTimeOriginal', 'DateTime', 'DateTimeDigitized']:
                if field in exif:
                    try:
                        date_str = exif[field]
                        self._date = datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
                        return self._date
                    except (ValueError, TypeError):
                        pass
            
            # Fallback to file modification time
            try:
                self._date = datetime.fromtimestamp(os.path.getmtime(self.path))
            except:
                self._date = None
        
        return self._date
    
    def matches_criteria(self, keywords: Optional[List[str]] = None, 
                        rating: Optional[int] = None,
                        year: Optional[int] = None,
                        month: Optional[int] = None) -> bool:
        """Check if photo matches search criteria."""
        
        # Check keywords
        if keywords:
            photo_keywords = self.keywords
            if not any(kw.upper() in photo_keywords for kw in keywords):
                return False
        
        # Check rating
        if rating is not None:
            if self.rating < rating:
                return False
        
        # Check date
        if year or month:
            date = self.date_taken
            if not date:
                return False
            if year and date.year != year:
                return False
            if month and date.month != month:
                return False
        
        return True


class FavoritePhotoFinder:
    """Main class for finding and copying favorite photos."""
    
    def __init__(self, src_dir: str, dest_dir: str, args):
        self.src_dir = Path(src_dir)
        self.dest_dir = Path(dest_dir)
        self.args = args
        self.stats = {
            'scanned': 0,
            'matched': 0,
            'copied': 0,
            'errors': 0
        }
        
    def scan_directory(self) -> List[str]:
        """Scan directory for image files."""
        logger.info(f"Scanning directory: {self.src_dir}")
        
        image_files = []
        
        if self.args.recursive:
            for root, dirs, files in os.walk(self.src_dir):
                for file in files:
                    file_path = Path(root) / file
                    if file_path.suffix.lower() in SUPPORTED_FORMATS:
                        image_files.append(str(file_path))
        else:
            for file in self.src_dir.iterdir():
                if file.is_file() and file.suffix.lower() in SUPPORTED_FORMATS:
                    image_files.append(str(file))
        
        logger.info(f"Found {len(image_files)} image files")
        return image_files
    
    def find_favorites(self, image_files: List[str]) -> List[str]:
        """Find images matching criteria."""
        logger.info("Searching for favorite photos...")
        
        matched = []
        
        iterator = tqdm(image_files, desc="Analyzing photos", unit="file") if tqdm else image_files
        
        for file_path in iterator:
            self.stats['scanned'] += 1
            
            try:
                photo = PhotoMetadata(file_path)
                
                if photo.matches_criteria(
                    keywords=self.args.keywords,
                    rating=self.args.rating,
                    year=self.args.year,
                    month=self.args.month
                ):
                    matched.append(file_path)
                    self.stats['matched'] += 1
                    logger.debug(f"Match: {Path(file_path).name}")
                    
            except Exception as e:
                logger.error(f"Error analyzing {Path(file_path).name}: {e}")
                self.stats['errors'] += 1
        
        logger.info(f"Found {len(matched)} matching photos")
        return matched
    
    def copy_photos(self, photo_paths: List[str]):
        """Copy matched photos to destination."""
        if not photo_paths:
            logger.info("No photos to copy")
            return
        
        # Create destination directory
        if not self.args.dry_run:
            self.dest_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Copying {len(photo_paths)} photos to {self.dest_dir}")
        
        # Organize by date if requested
        if self.args.organize_by_date:
            self._copy_organized(photo_paths)
        else:
            self._copy_flat(photo_paths)
    
    def _copy_flat(self, photo_paths: List[str]):
        """Copy photos to flat directory."""
        iterator = tqdm(photo_paths, desc="Copying photos", unit="file") if tqdm else photo_paths
        
        for src_path in iterator:
            try:
                src_file = Path(src_path)
                dest_file = self.dest_dir / src_file.name
                
                # Handle name collisions
                if dest_file.exists():
                    counter = 1
                    stem = dest_file.stem
                    suffix = dest_file.suffix
                    while dest_file.exists():
                        dest_file = self.dest_dir / f"{stem}_{counter}{suffix}"
                        counter += 1
                
                if self.args.dry_run:
                    logger.info(f"[DRY RUN] Would copy: {src_file.name} -> {dest_file}")
                else:
                    shutil.copy2(src_path, dest_file)
                    logger.debug(f"Copied: {src_file.name}")
                
                self.stats['copied'] += 1
                
            except Exception as e:
                logger.error(f"Error copying {Path(src_path).name}: {e}")
                self.stats['errors'] += 1
    
    def _copy_organized(self, photo_paths: List[str]):
        """Copy photos organized by date (YYYY-MM-DD folders)."""
        iterator = tqdm(photo_paths, desc="Copying photos", unit="file") if tqdm else photo_paths
        
        for src_path in iterator:
            try:
                photo = PhotoMetadata(src_path)
                date = photo.date_taken
                
                if date:
                    date_folder = self.dest_dir / date.strftime('%Y-%m-%d')
                else:
                    date_folder = self.dest_dir / "no_date"
                
                if not self.args.dry_run:
                    date_folder.mkdir(parents=True, exist_ok=True)
                
                src_file = Path(src_path)
                dest_file = date_folder / src_file.name
                
                # Handle name collisions
                if dest_file.exists():
                    counter = 1
                    stem = dest_file.stem
                    suffix = dest_file.suffix
                    while dest_file.exists():
                        dest_file = date_folder / f"{stem}_{counter}{suffix}"
                        counter += 1
                
                if self.args.dry_run:
                    logger.info(f"[DRY RUN] Would copy: {src_file.name} -> {dest_file}")
                else:
                    shutil.copy2(src_path, dest_file)
                    logger.debug(f"Copied: {src_file.name}")
                
                self.stats['copied'] += 1
                
            except Exception as e:
                logger.error(f"Error copying {Path(src_path).name}: {e}")
                self.stats['errors'] += 1
    
    def print_summary(self):
        """Print final summary."""
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Photos scanned:       {self.stats['scanned']}")
        print(f"Photos matched:       {self.stats['matched']}")
        print(f"Photos copied:        {self.stats['copied']}")
        print(f"Errors:               {self.stats['errors']}")
        print("=" * 80)
    
    def run(self):
        """Main execution method."""
        logger.info("="*60)
        logger.info("Favorite Photo Finder - Starting")
        logger.info(f"Source: {self.src_dir}")
        logger.info(f"Destination: {self.dest_dir}")
        logger.info(f"Criteria: Keywords={self.args.keywords}, Rating>={self.args.rating}, Year={self.args.year}")
        logger.info(f"Dry run: {self.args.dry_run}")
        logger.info("="*60)
        
        # Scan for images
        image_files = self.scan_directory()
        
        if not image_files:
            logger.info("No image files found!")
            return
        
        # Find favorites
        matched_photos = self.find_favorites(image_files)
        
        # Copy photos
        self.copy_photos(matched_photos)
        
        # Summary
        self.print_summary()


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Find and copy favorite/rated photos',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Find photos with keyword "FAVORITE"
  %(prog)s ~/Photos ~/Favorites --keyword FAVORITE
  
  # Find 5-star photos from 2024
  %(prog)s ~/Photos ~/Calendar2024 --rating 5 --year 2024
  
  # Multiple keywords
  %(prog)s ~/Photos ~/Best --keyword FAVORITE --keyword CALENDAR --keyword BEST
  
  # Organize by date
  %(prog)s ~/Photos ~/Sorted --rating 4 --organize-by-date
        """
    )
    
    parser.add_argument('source', help='Source directory with photos')
    parser.add_argument('destination', help='Destination directory for matched photos')
    
    # Search criteria
    parser.add_argument('-k', '--keyword', dest='keywords', action='append',
                       help='EXIF keyword to search for (can be used multiple times)')
    parser.add_argument('-r', '--rating', type=int, choices=[1,2,3,4,5],
                       help='Minimum EXIF rating (1-5 stars)')
    parser.add_argument('-y', '--year', type=int,
                       help='Filter by year (e.g., 2024)')
    parser.add_argument('-m', '--month', type=int, choices=range(1,13),
                       help='Filter by month (1-12)')
    
    # Options
    parser.add_argument('--recursive', action='store_true',
                       help='Search subdirectories recursively')
    parser.add_argument('--organize-by-date', action='store_true',
                       help='Organize copied photos into YYYY-MM-DD folders')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without copying')
    
    args = parser.parse_args()
    
    # Validation
    if not os.path.isdir(args.source):
        parser.error(f"Source directory does not exist: {args.source}")
    
    if not args.keywords and args.rating is None:
        parser.error("Must specify at least --keyword or --rating")
    
    return args


def main():
    """Main entry point."""
    args = parse_arguments()
    
    try:
        finder = FavoritePhotoFinder(args.source, args.destination, args)
        finder.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
