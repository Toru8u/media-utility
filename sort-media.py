"""
Media File Sorter - Improved Version

Sorts media files (JPG, JPEG, PNG, MOV, MP4) into subdirectories based on metadata timestamps.
Creates directories in YYYY-MM-DD format and renames files with timestamp prefixes.

Usage: python sort-media-improved.py <src_dir> [dest_dir] [--dry-run]
"""

import sys
import os
import glob
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List

# Try to import required libraries with helpful error messages
try:
    from PIL import Image
except ImportError:
    print("Error: Pillow library not found. Install with: pip install Pillow")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    print("Warning: tqdm not found. Progress bar disabled. Install with: pip install tqdm")
    tqdm = None

# Constants
EXIF_TAG_DATETIME = 306  # DateTime image was changed
EXIF_TAG_DATETIME_ORIGINAL = 36867  # DateTime original image was taken
EXIF_TAG_DATETIME_DIGITIZED = 36868  # DateTime image was digitized

MIN_VALID_YEAR = 1970
MAX_VALID_YEAR = datetime.now().year + 1

SUPPORTED_IMAGE_FORMATS = ['jpg', 'jpeg', 'png']
SUPPORTED_VIDEO_FORMATS = ['mov', 'mp4']

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('media_sorter.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MediaSorter:
    """Main class for sorting media files by metadata timestamps."""
    
    def __init__(self, src_dir: str, dest_dir: str, dry_run: bool = False):
        self.src_dir = src_dir
        self.dest_dir = dest_dir
        self.dry_run = dry_run
        self.stats = {
            'processed': 0,
            'failed': 0,
            'skipped': 0,
            'moved': 0
        }
        
    def case_insensitive_glob(self, pattern: str) -> List[str]:
        """Perform case-insensitive file globbing."""
        def either(c):
            return f'[{c.lower()}{c.upper()}]' if c.isalpha() else c
        return glob.glob(''.join(map(either, pattern)))
    
    def validate_date(self, date_obj: datetime) -> bool:
        """Validate that date is within reasonable bounds."""
        if date_obj is None:
            return False
        return MIN_VALID_YEAR <= date_obj.year <= MAX_VALID_YEAR
    
    def get_image_timestamps(self, filename: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract timestamp from image EXIF data.
        Returns: (short_date, long_datetime) as ('YYYY-MM-DD', 'YYYY-MM-DD_HH-MM-SS')
        """
        try:
            with Image.open(filename) as img:
                # Use modern getexif() instead of deprecated _getexif()
                exif_data = img.getexif()
                
                if not exif_data:
                    logger.warning(f"No EXIF data found in {Path(filename).name}")
                    return None, None
                
                # Try multiple EXIF tags in priority order
                timestamp_str = None
                for tag in [EXIF_TAG_DATETIME_ORIGINAL, EXIF_TAG_DATETIME, EXIF_TAG_DATETIME_DIGITIZED]:
                    timestamp_str = exif_data.get(tag)
                    if timestamp_str:
                        break
                
                if not timestamp_str:
                    logger.warning(f"No timestamp tags found in {Path(filename).name}")
                    return None, None
                
                # Parse timestamp
                try:
                    dt = datetime.strptime(timestamp_str, '%Y:%m:%d %H:%M:%S')
                except ValueError:
                    logger.error(f"Invalid timestamp format in {Path(filename).name}: {timestamp_str}")
                    return None, None
                
                if not self.validate_date(dt):
                    logger.warning(f"Invalid date in {Path(filename).name}: {dt.year}")
                    return None, None
                
                short_date = dt.strftime('%Y-%m-%d')
                long_datetime = dt.strftime('%Y-%m-%d_%H-%M-%S')
                
                return short_date, long_datetime
                
        except Exception as e:
            logger.error(f"Error reading EXIF from {Path(filename).name}: {e}")
            return None, None
    
    def get_video_timestamps(self, filename: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract timestamp from video metadata (MOV/MP4).
        Returns: (short_date, long_datetime) as ('YYYY-MM-DD', 'YYYY-MM-DD_HH-MM-SS')
        """
        import struct
        
        ATOM_HEADER_SIZE = 8
        EPOCH_ADJUSTER = 2082844800  # Unix to QuickTime epoch difference
        
        try:
            with open(filename, 'rb') as f:
                # Search for moov atom
                while True:
                    atom_header = f.read(ATOM_HEADER_SIZE)
                    if not atom_header or len(atom_header) < ATOM_HEADER_SIZE:
                        logger.warning(f"No moov atom found in {Path(filename).name}")
                        return None, None
                    
                    if atom_header[4:8] == b'moov':
                        break
                    else:
                        atom_size = struct.unpack('>I', atom_header[0:4])[0]
                        f.seek(atom_size - 8, 1)
                
                # Found moov, look for mvhd
                atom_header = f.read(ATOM_HEADER_SIZE)
                if atom_header[4:8] == b'cmov':
                    logger.error(f"Compressed moov atom not supported in {Path(filename).name}")
                    return None, None
                elif atom_header[4:8] != b'mvhd':
                    logger.error(f"Expected mvhd header in {Path(filename).name}")
                    return None, None
                
                # Read timestamps
                f.seek(4, 1)
                creation_time = struct.unpack('>I', f.read(4))[0] - EPOCH_ADJUSTER
                dt = datetime.fromtimestamp(creation_time)
                
                if not self.validate_date(dt):
                    logger.warning(f"Invalid date in {Path(filename).name}: {dt.year}")
                    return None, None
                
                short_date = dt.strftime('%Y-%m-%d')
                long_datetime = dt.strftime('%Y-%m-%d_%H-%M-%S')
                
                return short_date, long_datetime
                
        except Exception as e:
            logger.error(f"Error reading video metadata from {Path(filename).name}: {e}")
            return None, None
    
    def get_file_creation_fallback(self, filename: str) -> Tuple[Optional[str], Optional[str]]:
        """Fallback: use file creation/modification time."""
        try:
            stat = os.stat(filename)
            # Use the earlier of creation or modification time
            timestamp = min(stat.st_ctime, stat.st_mtime)
            dt = datetime.fromtimestamp(timestamp)
            
            short_date = dt.strftime('%Y-%m-%d')
            long_datetime = dt.strftime('%Y-%m-%d_%H-%M-%S')
            
            logger.info(f"Using file timestamp as fallback for {Path(filename).name}")
            return short_date, long_datetime
        except Exception as e:
            logger.error(f"Error getting file timestamp for {Path(filename).name}: {e}")
            return None, None
    
    def generate_unique_filename(self, dest_dir: str, base_name: str, extension: str) -> str:
        """Generate unique filename by adding suffix if needed."""
        target_path = os.path.join(dest_dir, f"{base_name}.{extension}")
        
        if not os.path.exists(target_path):
            return f"{base_name}.{extension}"
        
        # File exists, add counter
        counter = 1
        while True:
            new_name = f"{base_name}_{counter:03d}.{extension}"
            target_path = os.path.join(dest_dir, new_name)
            if not os.path.exists(target_path):
                logger.info(f"Filename collision detected, using {new_name}")
                return new_name
            counter += 1
            if counter > 999:
                raise RuntimeError(f"Too many filename collisions for {base_name}")
    
    def check_disk_space(self, file_path: str) -> bool:
        """Check if there's enough disk space for the operation."""
        try:
            file_size = os.path.getsize(file_path)
            stat = shutil.disk_usage(self.dest_dir)
            
            # Require at least 100MB free or 2x file size, whichever is larger
            required_space = max(file_size * 2, 100 * 1024 * 1024)
            
            if stat.free < required_space:
                logger.error(f"Insufficient disk space. Free: {stat.free / (1024**3):.2f} GB")
                return False
            return True
        except Exception as e:
            logger.error(f"Error checking disk space: {e}")
            return False
    
    def process_file(self, file_path: str, file_type: str) -> bool:
        """
        Process a single file: extract metadata, create directory, move file.
        Returns True if successful, False otherwise.
        """
        try:
            file_name = Path(file_path).name
            extension = Path(file_path).suffix[1:].lower()  # Remove dot and lowercase
            
            # Get timestamps based on file type
            if file_type == 'image':
                short_date, long_datetime = self.get_image_timestamps(file_path)
            elif file_type == 'video':
                short_date, long_datetime = self.get_video_timestamps(file_path)
            else:
                logger.error(f"Unknown file type: {file_type}")
                return False
            
            # Fallback to file creation time if metadata extraction failed
            if short_date is None or long_datetime is None:
                logger.info(f"Trying fallback method for {file_name}")
                short_date, long_datetime = self.get_file_creation_fallback(file_path)
            
            if short_date is None or long_datetime is None:
                logger.error(f"Could not determine timestamp for {file_name}, skipping")
                self.stats['skipped'] += 1
                return False
            
            # Create target directory
            target_dir = os.path.join(self.dest_dir, short_date)
            
            if not self.dry_run and not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
                logger.info(f"Created directory: {short_date}")
            
            # Generate unique filename
            original_stem = Path(file_path).stem
            new_base_name = f"{long_datetime}_{original_stem}"
            new_file_name = self.generate_unique_filename(target_dir, new_base_name, extension)
            
            target_path = os.path.join(target_dir, new_file_name)
            
            # Check disk space
            if not self.dry_run and not self.check_disk_space(file_path):
                logger.error(f"Skipping {file_name} due to insufficient disk space")
                self.stats['skipped'] += 1
                return False
            
            # Move file
            if self.dry_run:
                logger.info(f"[DRY RUN] Would move: {file_name} -> {short_date}/{new_file_name}")
            else:
                shutil.move(file_path, target_path)
                logger.info(f"Moved: {file_name} -> {short_date}/{new_file_name}")
            
            self.stats['moved'] += 1
            self.stats['processed'] += 1
            return True
            
        except Exception as e:
            logger.error(f"Error processing {Path(file_path).name}: {e}")
            self.stats['failed'] += 1
            return False
    
    def process_files_by_type(self, extensions: List[str], file_type: str):
        """Process all files of given extensions."""
        all_files = []
        for ext in extensions:
            pattern = os.path.join(self.src_dir, f"*.{ext}")
            files = self.case_insensitive_glob(pattern)
            all_files.extend(files)
        
        if not all_files:
            logger.info(f"No {file_type} files found with extensions: {extensions}")
            return
        
        logger.info(f"Found {len(all_files)} {file_type} file(s) to process")
        
        # Use tqdm if available
        if tqdm:
            iterator = tqdm(all_files, desc=f"Processing {file_type}s", unit="file")
        else:
            iterator = all_files
        
        for file_path in iterator:
            self.process_file(file_path, file_type)
    
    def run(self):
        """Main execution method."""
        logger.info("=" * 60)
        logger.info("Media Sorter - Starting")
        logger.info(f"Source directory: {self.src_dir}")
        logger.info(f"Destination directory: {self.dest_dir}")
        logger.info(f"Dry run mode: {self.dry_run}")
        logger.info("=" * 60)
        
        # Process images
        self.process_files_by_type(SUPPORTED_IMAGE_FORMATS, 'image')
        
        # Process videos
        self.process_files_by_type(SUPPORTED_VIDEO_FORMATS, 'video')
        
        # Print statistics
        logger.info("=" * 60)
        logger.info("Processing complete - Summary:")
        logger.info(f"  Total processed: {self.stats['processed']}")
        logger.info(f"  Successfully moved: {self.stats['moved']}")
        logger.info(f"  Skipped: {self.stats['skipped']}")
        logger.info(f"  Failed: {self.stats['failed']}")
        logger.info("=" * 60)


def main():
    """Main entry point."""
    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python sort-media-improved.py <src_dir> [dest_dir] [--dry-run]")
        print("\nOptions:")
        print("  src_dir     Source directory containing media files")
        print("  dest_dir    Destination directory (optional, defaults to src_dir)")
        print("  --dry-run   Simulate operations without making changes")
        sys.exit(0)
    
    src_dir = sys.argv[1]
    dry_run = '--dry-run' in sys.argv
    
    # Remove --dry-run from argv for dest_dir detection
    args = [arg for arg in sys.argv[1:] if arg != '--dry-run']
    
    if len(args) >= 2:
        dest_dir = args[1]
    else:
        dest_dir = src_dir
    
    # Validate directories
    if not os.path.isdir(src_dir):
        print(f"Error: Source directory does not exist: {src_dir}")
        sys.exit(1)
    
    if not os.path.isdir(dest_dir):
        print(f"Error: Destination directory does not exist: {dest_dir}")
        sys.exit(1)
    
    # Check write permissions
    if not dry_run and not os.access(dest_dir, os.W_OK):
        print(f"Error: No write permission for destination directory: {dest_dir}")
        sys.exit(1)
    
    # Create sorter and run
    sorter = MediaSorter(src_dir, dest_dir, dry_run)
    sorter.run()


if __name__ == "__main__":
    main()
