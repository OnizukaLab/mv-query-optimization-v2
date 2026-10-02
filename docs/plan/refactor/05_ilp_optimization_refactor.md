# Phase 5: ILP最適化モジュールの統合

## 🎯 目的

5つのILPアルゴリズムを共通基底クラスで統合し、コードの重複を削減します。

## ⏱️ 推定時間: 7-10時間

## 📋 実行手順概要

### Step 1: 基底クラスの実装

```python
# src/optimization/base.py

from abc import ABC, abstractmethod
from typing import List, Tuple
import gurobipy as gp

class BaseILPOptimizer(ABC):
    """Base class for ILP optimization algorithms."""
    
    def __init__(self, query_manager, config):
        self.qm = query_manager
        self.config = config
        
    @abstractmethod
    def initialize(self, **kwargs) -> List[int]:
        """Initialize solution (algorithm-specific)."""
        pass
        
    def build_ilp_model(self, **kwargs):
        """Build ILP model (common)."""
        pass
        
    def solve(self) -> Tuple:
        """Solve ILP model (common)."""
        pass
```

### Step 2: 各アルゴリズムの実装

- `src/optimization/normal.py`
- `src/optimization/bigsubs.py`
- `src/optimization/utility_capacity.py`
- `src/optimization/utility.py`
- `src/optimization/frequency.py`

### Step 3: Factory パターン

```python
# src/optimization/factory.py

class OptimizerFactory:
    """Factory for creating optimizer instances."""
    
    @classmethod
    def create(cls, algorithm: str, **kwargs):
        """Create optimizer instance."""
        pass
```

---

**所要時間**: 7-10時間  
**難易度**: ⭐⭐⭐⭐ (Very Hard)
