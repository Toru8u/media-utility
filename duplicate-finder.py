#!/usr/bin/env python3
"""
Image Duplicate Finder

Finds and removes duplicate images in a directory tree.
Supports exact duplicates (hash-based) and similar images (perceptual hash).

Usage: 
    python duplicate-finder.py <directory> [options]
    
Examples:
    python duplicate-finder.py /path/to/photos --dry-run
    python duplicate-finder.py /path/to/photos --similar --interactive
    python duplicate-finder.py /path/to/photos --auto --keep-largest
"""

import os
import sys
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import argparse

# Try to import required libraries
try:
    from PIL import Image
except ImportError:
    print("Error: Pillow library required. Install with: pip install Pillow")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    print("Warning: tqdm not found. Progress bar disabled. Install with: pip install tqdm")
    tqdm = None

try:
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False
    print("Note: imagehash not found. --similar mode disabled. Install with: pip install imagehash")

# Constants
SUPPORTED_FORMATS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
DEFAULT_SIMILARITY_THRESHOLD = 95

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('duplicate_finder.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ImageFile:
    """Represents an image file with its metadata."""
    
    def __init__(self, path: str):
        self.path = path
        self.file_path = Path(path)
        self.size = os.path.getsize(path)
        self.mtime = os.path.getmtime(path)
        self._hash = None
        self._perceptual_hash = None
        self._dimensions = None
        
    @property
    def hash(self) -> str:
        """Calculate MD5 hash of file content."""
        if self._hash is None:
            hasher = hashlib.md5()
            with open(self.path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
            self._hash = hasher.hexdigest()
        return self._hash
    
    @property
    def perceptual_hash(self) -> Optional[str]:
        """Calculate perceptual hash for similarity detection."""
        if not IMAGEHASH_AVAILABLE:
            return None
            
        if self._perceptual_hash is None:
            try:
                with Image.open(self.path) as img:
                    self._perceptual_hash = str(imagehash.average_hash(img))
            except Exception as e:
                logger.warning(f"Could not calculate perceptual hash for {self.file_path.name}: {e}")
                self._perceptual_hash = ""
        return self._perceptual_hash
    
    @property
    def dimensions(self) -> Tuple[int, int]:
        """Get image dimensions (width, height)."""
        if self._dimensions is None:
            try:
                with Image.open(self.path) as img:
                    self._dimensions = img.size
            except Exception as e:
                logger.warning(f"Could not get dimensions for {self.file_path.name}: {e}")
                self._dimensions = (0, 0)
        return self._dimensions
    
    @property
    def pixels(self) -> int:
        """Total number of pixels."""
        w, h = self.dimensions
        return w * h
    
    @property
    def path_depth(self) -> int:
        """Directory depth from root."""
        return len(self.file_path.parts)
    
    def __repr__(self):
        return f"ImageFile({self.file_path.name}, {self.size} bytes)"


class DuplicateFinder:
    """Main class for finding and managing duplicate images."""
    
    def __init__(self, root_dir: str, args):
        self.root_dir = Path(root_dir)
        self.args = args
        self.all_images: List[ImageFile] = []
        self.duplicates: Dict[str, List[ImageFile]] = defaultdict(list)
        self.similar_groups: List[List[ImageFile]] = []
        self.stats = {
            'total_files': 0,
            'total_size': 0,
            'duplicate_files': 0,
            'duplicate_size': 0,
            'deleted_files': 0,
            'deleted_size': 0,
            'errors': 0
        }
        
    def scan_directory(self) -> List[ImageFile]:
        """Scan directory for image files."""
        logger.info(f"Scanning directory: {self.root_dir}")
        
        image_files = []
        exclude_dirs = set(self.args.exclude_dirs.split(',')) if self.args.exclude_dirs else set()
        
        for root, dirs, files in os.walk(self.root_dir):
            # Remove excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                file_path = Path(root) / file
                
                # Check extension
                if file_path.suffix.lower() not in SUPPORTED_FORMATS:
                    continue
                
                # Check minimum size
                try:
                    size = os.path.getsize(file_path)
                    if size < self.args.min_size * 1024:  # Convert KB to bytes
                        continue
                    
                    image_files.append(ImageFile(str(file_path)))
                    self.stats['total_files'] += 1
                    self.stats['total_size'] += size
                    
                except Exception as e:
                    logger.error(f"Error accessing {file_path}: {e}")
                    self.stats['errors'] += 1
        
        logger.info(f"Found {len(image_files)} image files")
        return image_files
    
    def find_exact_duplicates(self, images: List[ImageFile]):
        """Find exact duplicates using MD5 hash."""
        logger.info("Finding exact duplicates...")
        
        hash_map = defaultdict(list)
        
        iterator = tqdm(images, desc="Computing hashes", unit="file") if tqdm else images
        
        for img in iterator:
            try:
                file_hash = img.hash
                hash_map[file_hash].append(img)
            except Exception as e:
                logger.error(f"Error hashing {img.path}: {e}")
                self.stats['errors'] += 1
        
        # Filter to only groups with duplicates
        self.duplicates = {h: imgs for h, imgs in hash_map.items() if len(imgs) > 1}
        
        # Calculate stats
        for imgs in self.duplicates.values():
            for img in imgs[1:]:  # All except the one we keep
                self.stats['duplicate_files'] += 1
                self.stats['duplicate_size'] += img.size
        
        logger.info(f"Found {len(self.duplicates)} groups of exact duplicates")
        logger.info(f"Total duplicate files: {self.stats['duplicate_files']}")
        logger.info(f"Total duplicate size: {self.stats['duplicate_size'] / (1024**2):.2f} MB")
    
    def find_similar_images(self, images: List[ImageFile]):
        """Find similar images using perceptual hashing."""
        if not IMAGEHASH_AVAILABLE:
            logger.error("imagehash library not available. Cannot find similar images.")
            return
        
        logger.info("Finding similar images...")
        
        # Calculate perceptual hashes
        hash_map = {}
        iterator = tqdm(images, desc="Computing perceptual hashes", unit="file") if tqdm else images
        
        for img in iterator:
            try:
                phash = img.perceptual_hash
                if phash:
                    hash_map[img] = imagehash.hex_to_hash(phash)
            except Exception as e:
                logger.error(f"Error calculating perceptual hash for {img.path}: {e}")
                self.stats['errors'] += 1
        
        # Find similar groups
        processed = set()
        threshold = (100 - self.args.similarity) / 100 * 64  # Convert percentage to hash distance
        
        logger.info("Comparing images for similarity...")
        for img1 in hash_map:
            if img1 in processed:
                continue
            
            group = [img1]
            processed.add(img1)
            
            for img2 in hash_map:
                if img2 in processed:
                    continue
                
                # Calculate hash distance
                distance = hash_map[img1] - hash_map[img2]
                
                if distance <= threshold:
                    group.append(img2)
                    processed.add(img2)
            
            if len(group) > 1:
                self.similar_groups.append(group)
        
        logger.info(f"Found {len(self.similar_groups)} groups of similar images")
    
    def select_file_to_keep(self, group: List[ImageFile]) -> ImageFile:
        """Select which file to keep based on strategy."""
        strategy = self.args.keep
        
        if strategy == 'largest':
            return max(group, key=lambda x: x.size)
        elif strategy == 'highest-res':
            return max(group, key=lambda x: x.pixels)
        elif strategy == 'oldest':
            return min(group, key=lambda x: x.mtime)
        elif strategy == 'newest':
            return max(group, key=lambda x: x.mtime)
        elif strategy == 'shortest-path':
            return min(group, key=lambda x: x.path_depth)
        else:
            # Default: largest file
            return max(group, key=lambda x: x.size)
    
    def display_duplicate_group(self, group: List[ImageFile], group_num: int, is_similar: bool = False):
        """Display information about a duplicate group."""
        print("\n" + "=" * 80)
        print(f"{'Similar' if is_similar else 'Duplicate'} Group #{group_num}")
        print("=" * 80)
        
        for idx, img in enumerate(group, 1):
            size_mb = img.size / (1024**2)
            width, height = img.dimensions
            date = datetime.fromtimestamp(img.mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            print(f"\n[{idx}] {img.file_path}")
            print(f"    Size: {size_mb:.2f} MB | Resolution: {width}x{height} | Date: {date}")
            print(f"    Path depth: {img.path_depth} | Pixels: {img.pixels:,}")
    
    def process_duplicates_interactive(self):
        """Process duplicates with user interaction."""
        total_groups = len(self.duplicates) + len(self.similar_groups)
        
        if total_groups == 0:
            logger.info("No duplicates found!")
            return
        
        print(f"\n{'='*80}")
        print(f"Found {total_groups} duplicate/similar groups")
        print(f"{'='*80}\n")
        
        group_num = 1
        
        # Process exact duplicates
        for file_hash, group in self.duplicates.items():
            self.display_duplicate_group(group, group_num, is_similar=False)
            
            suggested = self.select_file_to_keep(group)
            suggested_idx = group.index(suggested) + 1
            
            print(f"\n💡 Suggested to keep: [{suggested_idx}] (Strategy: {self.args.keep})")
            
            while True:
                choice = input(f"\nKeep which file? [1-{len(group)}], 's' to skip, 'q' to quit: ").strip().lower()
                
                if choice == 'q':
                    logger.info("User quit. Exiting...")
                    return
                elif choice == 's':
                    logger.info("Skipped group")
                    break
                elif choice.isdigit() and 1 <= int(choice) <= len(group):
                    keep_idx = int(choice) - 1
                    to_delete = [img for i, img in enumerate(group) if i != keep_idx]
                    
                    self.delete_files(to_delete)
                    break
                else:
                    print("Invalid choice. Try again.")
            
            group_num += 1
        
        # Process similar images
        for group in self.similar_groups:
            self.display_duplicate_group(group, group_num, is_similar=True)
            
            suggested = self.select_file_to_keep(group)
            suggested_idx = group.index(suggested) + 1
            
            print(f"\n💡 Suggested to keep: [{suggested_idx}] (Strategy: {self.args.keep})")
            
            while True:
                choice = input(f"\nKeep which file? [1-{len(group)}], 's' to skip, 'q' to quit: ").strip().lower()
                
                if choice == 'q':
                    logger.info("User quit. Exiting...")
                    return
                elif choice == 's':
                    logger.info("Skipped group")
                    break
                elif choice.isdigit() and 1 <= int(choice) <= len(group):
                    keep_idx = int(choice) - 1
                    to_delete = [img for i, img in enumerate(group) if i != keep_idx]
                    
                    self.delete_files(to_delete)
                    break
                else:
                    print("Invalid choice. Try again.")
            
            group_num += 1
    
    def process_duplicates_auto(self):
        """Process duplicates automatically based on keep strategy."""
        total_groups = len(self.duplicates) + len(self.similar_groups)
        
        if total_groups == 0:
            logger.info("No duplicates found!")
            return
        
        logger.info(f"Processing {total_groups} duplicate groups automatically...")
        
        all_to_delete = []
        
        # Process exact duplicates
        for file_hash, group in self.duplicates.items():
            keep = self.select_file_to_keep(group)
            to_delete = [img for img in group if img != keep]
            all_to_delete.extend(to_delete)
            
            logger.info(f"Group: Keeping {keep.file_path.name}, deleting {len(to_delete)} files")
        
        # Process similar images
        for group in self.similar_groups:
            keep = self.select_file_to_keep(group)
            to_delete = [img for img in group if img != keep]
            all_to_delete.extend(to_delete)
            
            logger.info(f"Similar group: Keeping {keep.file_path.name}, deleting {len(to_delete)} files")
        
        if all_to_delete:
            print(f"\n⚠️  About to delete {len(all_to_delete)} files")
            print(f"💾 Total space to free: {sum(img.size for img in all_to_delete) / (1024**2):.2f} MB")
            
            if not self.args.yes:
                confirm = input("\nProceed with deletion? [y/N]: ").strip().lower()
                if confirm != 'y':
                    logger.info("Deletion cancelled by user")
                    return
            
            self.delete_files(all_to_delete)
    
    def delete_files(self, files: List[ImageFile]):
        """Delete specified files."""
        for img in files:
            try:
                if not self.args.dry_run:
                    os.remove(img.path)
                    logger.info(f"Deleted: {img.path}")
                else:
                    logger.info(f"[DRY RUN] Would delete: {img.path}")
                
                self.stats['deleted_files'] += 1
                self.stats['deleted_size'] += img.size
            except Exception as e:
                logger.error(f"Error deleting {img.path}: {e}")
                self.stats['errors'] += 1
    
    def print_summary(self):
        """Print final summary."""
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total files scanned:      {self.stats['total_files']}")
        print(f"Total size scanned:       {self.stats['total_size'] / (1024**2):.2f} MB")
        print(f"Duplicate files found:    {self.stats['duplicate_files']}")
        print(f"Duplicate size found:     {self.stats['duplicate_size'] / (1024**2):.2f} MB")
        print(f"Files deleted:            {self.stats['deleted_files']}")
        print(f"Space freed:              {self.stats['deleted_size'] / (1024**2):.2f} MB")
        print(f"Errors encountered:       {self.stats['errors']}")
        print("=" * 80)
    
    def run(self):
        """Main execution method."""
        logger.info("="*60)
        logger.info("Duplicate Image Finder - Starting")
        logger.info(f"Directory: {self.root_dir}")
        logger.info(f"Mode: {'Interactive' if self.args.interactive else 'Automatic'}")
        logger.info(f"Dry run: {self.args.dry_run}")
        logger.info(f"Keep strategy: {self.args.keep}")
        logger.info("="*60)
        
        # Scan directory
        self.all_images = self.scan_directory()
        
        if not self.all_images:
            logger.info("No image files found!")
            return
        
        # Find exact duplicates
        self.find_exact_duplicates(self.all_images)
        
        # Find similar images if requested
        if self.args.similar:
            self.find_similar_images(self.all_images)
        
        # Process duplicates
        if self.args.interactive:
            self.process_duplicates_interactive()
        else:
            self.process_duplicates_auto()
        
        # Print summary
        self.print_summary()


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Find and remove duplicate images',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/photos --dry-run
  %(prog)s /path/to/photos --similar --interactive
  %(prog)s /path/to/photos --auto --keep-largest --yes
  %(prog)s /path/to/photos --min-size 100 --exclude-dirs "Backup,Archive"
        """
    )
    
    parser.add_argument('directory', help='Directory to scan for duplicates')
    
    # Detection options
    parser.add_argument('--similar', action='store_true',
                       help='Also find similar (not just exact) duplicates')
    parser.add_argument('--similarity', type=int, default=95,
                       help='Similarity threshold for similar images (0-100, default: 95)')
    
    # Processing mode
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--interactive', action='store_true',
                           help='Interactive mode: manually select which files to keep')
    mode_group.add_argument('--auto', action='store_true', default=True,
                           help='Automatic mode: use keep strategy (default)')
    
    # Keep strategy
    parser.add_argument('--keep', choices=['largest', 'highest-res', 'oldest', 'newest', 'shortest-path'],
                       default='largest',
                       help='Which file to keep in each duplicate group (default: largest)')
    
    # Filters
    parser.add_argument('--min-size', type=int, default=0,
                       help='Minimum file size in KB (default: 0)')
    parser.add_argument('--exclude-dirs', type=str,
                       help='Comma-separated list of directory names to exclude')
    
    # Safety options
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be deleted without actually deleting')
    parser.add_argument('--yes', '-y', action='store_true',
                       help='Skip confirmation prompt in auto mode')
    
    args = parser.parse_args()
    
    # Validation
    if args.similar and not IMAGEHASH_AVAILABLE:
        parser.error("--similar requires imagehash library. Install with: pip install imagehash")
    
    if not os.path.isdir(args.directory):
        parser.error(f"Directory does not exist: {args.directory}")
    
    return args


def main():
    """Main entry point."""
    args = parse_arguments()
    
    try:
        finder = DuplicateFinder(args.directory, args)
        finder.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
