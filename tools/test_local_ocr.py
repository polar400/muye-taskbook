import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
sys.path.insert(0,str(ROOT))
from adapters.local_ocr import LocalOCR
from PIL import Image
import numpy as np
img=np.array(Image.open(ROOT/'verification/direct-native-click-after.png').convert('RGB'))[:,:,::-1].copy()
import json
print(json.dumps(LocalOCR().read(img),ensure_ascii=False))
