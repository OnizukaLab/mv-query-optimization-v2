# 結果のjsonファイルからcsvファイルを生成

import json 
import csv
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

class CSVExporter:

    inpput_file: