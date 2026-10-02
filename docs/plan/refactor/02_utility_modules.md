# Phase 2: ユーティリティモジュールの整理

## 🎯 目的

既存の `utils.py` を機能別に分割し、再利用可能なユーティリティモジュールを作成します。

## ⏱️ 推定時間: 3-4時間

## 📋 前提条件

- [x] Phase 0, 1 が完了している
- [x] `src/utils/` ディレクトリが存在

## 🔧 実行手順

### Step 1: ファイル操作ユーティリティ

```python
# src/utils/file_utils.py を作成

"""File operation utilities."""

import os
import re
from typing import List, Tuple, Dict
from pathlib import Path


def natural_sort_key(s: str) -> List:
    """
    Natural sorting key for strings containing numbers.
    
    Args:
        s: String to create sort key for
        
    Returns:
        List of integers and strings for natural sorting
        
    Example:
        >>> sorted(['file1.txt', 'file10.txt', 'file2.txt'], key=natural_sort_key)
        ['file1.txt', 'file2.txt', 'file10.txt']
    """
    return [int(text) if text.isdigit() else text.lower() 
            for text in re.split('([0-9]+)', s)]


def get_all_files(directory: str, extension: str = None) -> List[str]:
    """
    Recursively get all files in directory.
    
    Args:
        directory: Root directory to search
        extension: Optional file extension filter (e.g., '.json')
        
    Returns:
        List of file paths
    """
    result = []
    for folder, _, files in os.walk(directory):
        for f in files:
            if extension is None or f.endswith(extension):
                result.append(os.path.join(folder, f))
    return result


def ensure_directory(path: str) -> None:
    """
    Ensure directory exists, create if it doesn't.
    
    Args:
        path: Directory path to ensure
    """
    Path(path).mkdir(parents=True, exist_ok=True)
```

詳細な実装は `docs/plan/02_utility_modules.md` に記載されています。

---

**所要時間**: 3-4時間  
**難易度**: ⭐⭐ (Medium)
