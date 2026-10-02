"""
File Manager Utilities

Utilities for file and directory operations.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


class FileManager:
    """Manages file operations for dashboard"""
    
    @staticmethod
    def ensure_directory(path: Path) -> Path:
        """Ensure directory exists, create if it doesn't
        
        Args:
            path: Path to directory
            
        Returns:
            Path object
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @staticmethod
    def save_json(data: Dict, filepath: Path):
        """Save data to JSON file
        
        Args:
            data: Dictionary to save
            filepath: Path to save file
        """
        filepath = Path(filepath)
        FileManager.ensure_directory(filepath.parent)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    @staticmethod
    def load_json(filepath: Path) -> Optional[Dict]:
        """Load data from JSON file
        
        Args:
            filepath: Path to JSON file
            
        Returns:
            Dictionary or None if file doesn't exist
        """
        filepath = Path(filepath)
        
        if not filepath.exists():
            return None
        
        with open(filepath, 'r') as f:
            return json.load(f)
    
    @staticmethod
    def list_files(directory: Path, pattern: str = "*") -> List[Path]:
        """List files in directory matching pattern
        
        Args:
            directory: Directory to search
            pattern: Glob pattern
            
        Returns:
            List of Path objects
        """
        directory = Path(directory)
        
        if not directory.exists():
            return []
        
        return list(directory.glob(pattern))
    
    @staticmethod
    def get_file_size(filepath: Path) -> int:
        """Get file size in bytes
        
        Args:
            filepath: Path to file
            
        Returns:
            File size in bytes
        """
        filepath = Path(filepath)
        
        if not filepath.exists():
            return 0
        
        return filepath.stat().st_size
    
    @staticmethod
    def get_directory_size(directory: Path) -> int:
        """Get total size of directory in bytes
        
        Args:
            directory: Path to directory
            
        Returns:
            Total size in bytes
        """
        directory = Path(directory)
        
        if not directory.exists():
            return 0
        
        total = 0
        for filepath in directory.rglob('*'):
            if filepath.is_file():
                total += filepath.stat().st_size
        
        return total
    
    @staticmethod
    def copy_file(src: Path, dst: Path):
        """Copy file from source to destination
        
        Args:
            src: Source file path
            dst: Destination file path
        """
        src = Path(src)
        dst = Path(dst)
        
        FileManager.ensure_directory(dst.parent)
        shutil.copy2(src, dst)
    
    @staticmethod
    def archive_experiment(
        experiment_dir: Path,
        archive_dir: Path,
        experiment_name: Optional[str] = None
    ) -> Path:
        """Archive experiment results
        
        Args:
            experiment_dir: Path to experiment directory
            archive_dir: Path to archive directory
            experiment_name: Optional name for archive
            
        Returns:
            Path to archived file
        """
        experiment_dir = Path(experiment_dir)
        archive_dir = Path(archive_dir)
        
        FileManager.ensure_directory(archive_dir)
        
        if experiment_name is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            experiment_name = f"experiment_{timestamp}"
        
        archive_path = archive_dir / experiment_name
        shutil.make_archive(str(archive_path), 'zip', experiment_dir)
        
        return Path(f"{archive_path}.zip")
    
    @staticmethod
    def clean_old_files(directory: Path, days: int = 30):
        """Clean files older than specified days
        
        Args:
            directory: Directory to clean
            days: Age threshold in days
        """
        directory = Path(directory)
        
        if not directory.exists():
            return
        
        threshold = datetime.now().timestamp() - (days * 24 * 60 * 60)
        
        for filepath in directory.rglob('*'):
            if filepath.is_file():
                if filepath.stat().st_mtime < threshold:
                    filepath.unlink()
    
    @staticmethod
    def export_to_csv(data: List[Dict], filepath: Path):
        """Export data to CSV file
        
        Args:
            data: List of dictionaries
            filepath: Path to save CSV
        """
        import pandas as pd
        
        filepath = Path(filepath)
        FileManager.ensure_directory(filepath.parent)
        
        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)
    
    @staticmethod
    def read_log_file(filepath: Path, max_lines: int = 1000) -> List[str]:
        """Read log file and return lines
        
        Args:
            filepath: Path to log file
            max_lines: Maximum number of lines to return
            
        Returns:
            List of log lines
        """
        filepath = Path(filepath)
        
        if not filepath.exists():
            return []
        
        with open(filepath, 'r') as f:
            lines = f.readlines()
        
        return lines[-max_lines:]
