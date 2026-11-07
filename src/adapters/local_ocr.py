"""Local OCR using MaaFramework and bundled PaddleOCR models. No network calls."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'vendor'))
from maa.controller import CustomController
from maa.resource import Resource
from maa.tasker import Tasker
from maa.pipeline import JOCR,JTemplateMatch

class ReadOnlyController(CustomController):
    def connect(self): return True
    def request_uuid(self): return 'local-ocr-read-only'
    def screencap(self): return self.image
    def deny(self,*args): return False
    start_app=stop_app=click=swipe=touch_down=touch_move=touch_up=click_key=input_text=key_down=key_up=deny

class LocalOCR:
    def __init__(self):
        self.resource=Resource()
        self.resource.post_image(ROOT/'resources/local/image').wait()
        if not self.resource.post_ocr_model(ROOT/'resources/local/ocr').wait().succeeded:
            raise RuntimeError('本地OCR模型加载失败')
        self.controller=ReadOnlyController()
        self.controller.post_connection().wait()
        self.tasker=Tasker()
        self.tasker.bind(self.resource,self.controller)

    def read(self,image,only_rec=False):
        self.controller.image=image
        job=self.tasker.post_recognition('OCR',JOCR(threshold=.65,only_rec=only_rec),image).wait()
        detail=job.get()
        if not detail: raise RuntimeError('OCR识别失败')
        results=[]
        for node in detail.nodes:
            if node.recognition:
                for item in node.recognition.all_results:
                    if item.score>=.65:
                        results.append({'text':item.text,'box':list(item.box),'score':float(item.score)})
        return results

    def match(self,image,name,threshold=.86):
        files=[p.name for p in (ROOT/'resources/local/image').glob(name+'_*.png')]
        if not files:return []
        self.controller.image=image
        results=[]
        for file in files:
            job=self.tasker.post_recognition('TemplateMatch',JTemplateMatch(template=[file],threshold=[threshold]),image).wait()
            detail=job.get()
            if detail:
                for node in detail.nodes:
                    if node.recognition:
                        for item in node.recognition.filtered_results:
                            box=list(item.box)
                            if not any(abs(box[0]-r['box'][0])<25 and abs(box[1]-r['box'][1])<25 for r in results):
                                results.append({'box':box,'score':item.score,'template':name})
        return results
