"""Reference-based visual anomaly inspection for assembled PCBs.

No neural weights, defect-class guesses or probability claims. Coordinates and
artifacts are returned in the inspected image's coordinate system.
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import time
from pathlib import Path
import numpy as np
from PIL import Image

class AlignmentError(ValueError):
    pass

def image_url(rgb: np.ndarray, quality: int = 85) -> str:
    stream=io.BytesIO()
    Image.fromarray(rgb.astype(np.uint8)).save(stream,format='JPEG',quality=quality)
    return 'data:image/jpeg;base64,'+base64.b64encode(stream.getvalue()).decode('ascii')

class PCBAInspector:
    def __init__(self, config_path: Path):
        self.config=json.loads(config_path.read_text(encoding='utf-8'))
        self.config_sha=hashlib.sha256(config_path.read_bytes()).hexdigest()
        self.error=None
        try:
            import cv2
            self.cv=cv2
            if not hasattr(cv2,'SIFT_create'):
                raise RuntimeError('OpenCV без SIFT. Установите зависимости из requirements.txt')
        except Exception as exc:
            self.cv=None;self.error=str(exc)

    def health(self):
        return {'ready':self.cv is not None,'name':self.config['name'],
                'version':self.config['version'],'method':'reference_cv',
                'error':self.error,'default_threshold':self.config['default_threshold'],
                'requires_reference':True,'provider':'OpenCV CPU',
                'source':'https://docs.opencv.org/4.x/d1/de0/tutorial_py_feature_homography.html',
                'config_sha256':self.config_sha,
                'classes':['visual_difference','missing_component','misaligned_component','visible_damage','solder_suspect'],
                'labels_ru':['Визуальное отличие','Отсутствующий компонент','Смещённый компонент','Видимое повреждение','Подозрение на дефект пайки']}

    def _work_image(self, image):
        rgb=np.asarray(image.convert('RGB'))
        scale=min(1.,self.config['max_side']/max(image.size))
        if scale<1:
            rgb=self.cv.resize(rgb,(round(image.width*scale),round(image.height*scale)),interpolation=self.cv.INTER_AREA)
        return rgb

    def _align(self, ref, target):
        cv=self.cv
        gray_ref=cv.cvtColor(ref,cv.COLOR_RGB2GRAY)
        gray_target=cv.cvtColor(target,cv.COLOR_RGB2GRAY)
        clahe=cv.createCLAHE(clipLimit=2.,tileGridSize=(8,8))
        sift=cv.SIFT_create(nfeatures=6000)
        k1,d1=sift.detectAndCompute(clahe.apply(gray_ref),None)
        k2,d2=sift.detectAndCompute(clahe.apply(gray_target),None)
        if d1 is None or d2 is None or len(k1)<20 or len(k2)<20:
            raise AlignmentError('Недостаточно деталей для совмещения. Нужны резкие снимки одной платы сверху.')
        pairs=cv.BFMatcher(cv.NORM_L2).knnMatch(d1,d2,k=2)
        matches=[m for pair in pairs if len(pair)==2 for m,n in [pair] if m.distance<.72*n.distance]
        matches=sorted(matches,key=lambda m:m.distance)[:1200]
        if len(matches)<self.config['min_inliers']:
            raise AlignmentError('Эталон и снимок не удалось сопоставить. Проверьте модель, ревизию, ракурс и освещение.')
        src=np.float32([k1[m.queryIdx].pt for m in matches]).reshape(-1,1,2)
        dst=np.float32([k2[m.trainIdx].pt for m in matches]).reshape(-1,1,2)
        matrix,mask=cv.findHomography(src,dst,cv.RANSAC,3.,maxIters=4000,confidence=.995)
        if matrix is None or mask is None or not np.isfinite(matrix).all():
            raise AlignmentError('Не удалось рассчитать геометрию снимков.')
        inliers=mask.ravel().astype(bool);count=int(inliers.sum());ratio=count/len(matches)
        if count<self.config['min_inliers'] or ratio<self.config['min_inlier_ratio']:
            raise AlignmentError('Ненадёжное совмещение: слишком мало согласованных точек. PASS недоступен.')
        ref_area=ref.shape[0]*ref.shape[1];target_area=target.shape[0]*target.shape[1]
        c1=cv.contourArea(cv.convexHull(src[inliers]))/ref_area
        c2=cv.contourArea(cv.convexHull(dst[inliers]))/target_area
        if min(c1,c2)<self.config['min_feature_coverage']:
            raise AlignmentError('Совпадения сосредоточены на слишком маленьком участке. Переснимите всю плату.')
        h,w=ref.shape[:2];th,tw=target.shape[:2]
        corners=np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]).reshape(-1,1,2)
        projected=cv.perspectiveTransform(corners,matrix)
        polygon=projected.reshape(-1,2)
        if not np.isfinite(polygon).all() or not cv.isContourConvex(polygon.astype(np.float32)):
            raise AlignmentError('Геометрия снимков несовместима.')
        area=cv.contourArea(polygon.astype(np.float32))/target_area
        if not .2<area<5:
            raise AlignmentError('Масштаб эталона сильно отличается. Снимите плату целиком с похожего расстояния.')
        projected_points=cv.perspectiveTransform(src[inliers],matrix)
        reproj=float(np.median(np.linalg.norm(projected_points-dst[inliers],axis=2)))
        if reproj>2.5:
            raise AlignmentError('Погрешность совмещения слишком велика. PASS недоступен.')
        aligned=cv.warpPerspective(ref,matrix,(tw,th),flags=cv.INTER_LINEAR,borderMode=cv.BORDER_CONSTANT)
        valid=cv.warpPerspective(np.full((h,w),255,np.uint8),matrix,(tw,th),flags=cv.INTER_NEAREST)
        valid=cv.erode(valid,np.ones((9,9),np.uint8))>0
        return aligned,valid,{'method':'SIFT + RANSAC homography','matches':len(matches),'inliers':count,
            'inlier_ratio':round(ratio,4),'feature_coverage':round(min(c1,c2),4),
            'median_reprojection_px':round(reproj,3),'homography_work':matrix.tolist(),
            'reference_work_size':[w,h],'inspection_work_size':[tw,th]}

    def _difference(self, aligned, target, valid):
        cv=self.cv
        ref=cv.cvtColor(aligned,cv.COLOR_RGB2LAB).astype(np.float32)
        cur=cv.cvtColor(target,cv.COLOR_RGB2LAB).astype(np.float32)
        # Robust global photometric adjustment; local structural changes remain visible.
        adjusted=cur.copy()
        for channel in range(3):
            a=ref[:,:,channel][valid];b=cur[:,:,channel][valid]
            if channel==0:
                ar=np.percentile(a,[10,50,90]);br=np.percentile(b,[10,50,90])
                gain=float(np.clip((ar[2]-ar[0])/max(1.,br[2]-br[0]),.75,1.33))
                adjusted[:,:,channel]=(cur[:,:,channel]-br[1])*gain+ar[1]
            else:
                adjusted[:,:,channel]+=float(np.clip(np.median(a)-np.median(b),-12,12))
        ref=cv.GaussianBlur(ref,(3,3),.8)
        adjusted=cv.GaussianBlur(np.clip(adjusted,0,255),(3,3),.8)
        a,b=ref[:,:,0],adjusted[:,:,0]
        mu_a=cv.GaussianBlur(a,(7,7),1.5);mu_b=cv.GaussianBlur(b,(7,7),1.5)
        va=np.maximum(0,cv.GaussianBlur(a*a,(7,7),1.5)-mu_a*mu_a)
        vb=np.maximum(0,cv.GaussianBlur(b*b,(7,7),1.5)-mu_b*mu_b)
        cov=cv.GaussianBlur(a*b,(7,7),1.5)-mu_a*mu_b
        c1=(.01*255)**2;c2=(.03*255)**2
        ssim=((2*mu_a*mu_b+c1)*(2*cov+c2))/((mu_a**2+mu_b**2+c1)*(va+vb+c2))
        structure=np.clip(1-ssim,0,1)
        color=np.clip(np.linalg.norm(ref-adjusted,axis=2)/85.,0,1)
        score=np.clip(.65*structure+.35*color,0,1)
        score[~valid]=0
        return score

    def predict(self, image: Image.Image, reference: Image.Image, threshold: float, min_area: int=40, roi=None):
        if self.cv is None:raise RuntimeError(self.error or 'OpenCV не установлен')
        cv=self.cv;started=time.perf_counter();width,height=image.size
        target=self._work_image(image);ref=self._work_image(reference)
        th,tw=target.shape[:2]
        info={'scope':'visible_pcba_reference','reference_sha256':hashlib.sha256(reference.tobytes()).hexdigest(),
              'inspection_sha256':hashlib.sha256(image.tobytes()).hexdigest()}
        try:
            aligned,valid,alignment=self._align(ref,target)
        except AlignmentError as exc:
            return {'detections':[],'width':width,'height':height,'elapsed_ms':round((time.perf_counter()-started)*1000,1),
                'threshold':threshold,'min_area':min_area,'roi':roi,'model':self.health(),
                'machine_verdict':'REVIEW','analysis_blocked':True,'analysis_available':False,
                'warnings':[str(exc)],'alignment':None,'coverage':0.,'changed_fraction':None,**info}
        domain=np.ones((th,tw),np.uint8)
        if roi is not None:
            x1,y1,x2,y2=roi
            domain[:]=0
            domain[int(y1*th):max(int(y1*th)+1,int(y2*th)),int(x1*tw):max(int(x1*tw)+1,int(x2*tw))]=1
        valid=valid & domain.astype(bool)
        coverage=float(valid.sum()/max(1,domain.sum()))
        warnings=[]
        if coverage<.25:
            return {'detections':[],'width':width,'height':height,'elapsed_ms':round((time.perf_counter()-started)*1000,1),
                'threshold':threshold,'min_area':min_area,'roi':roi,'model':self.health(),
                'machine_verdict':'REVIEW','analysis_blocked':True,'analysis_available':False,
                'warnings':['Слишком мало общей области эталона и снимка.'],
                'alignment':alignment,'coverage':round(coverage,4),'changed_fraction':None,**info}
        score=self._difference(aligned,target,valid)
        mask=((score>=threshold)&valid).astype(np.uint8)*255
        mask=cv.morphologyEx(mask,cv.MORPH_OPEN,np.ones((3,3),np.uint8))
        mask=cv.morphologyEx(mask,cv.MORPH_CLOSE,np.ones((5,5),np.uint8))
        mask[~valid]=0
        changed=float(np.count_nonzero(mask)/max(1,valid.sum()))
        count,labels,stats,_=cv.connectedComponentsWithStats(mask,connectivity=8)
        detections=[]
        sx,sy=width/tw,height/th
        for idx in range(1,count):
            x,y,w,h,area=stats[idx]
            # min_area is always interpreted in inspected working-raster pixels (UI units).
            original_area=float(area*sx*sy)
            if original_area<min_area:continue
            region_score=float(np.percentile(score[labels==idx],90))
            margin=3
            box=[max(0,(x-margin)*sx),max(0,(y-margin)*sy),min(width,(x+w+margin)*sx),min(height,(y+h+margin)*sy)]
            detections.append({'id':f'a{idx}','class_id':0,'class_name':'visual_difference',
                'label':'Визуальное отличие','score':None,'anomaly_score':round(region_score,4),
                'area_px':round(original_area),'box':[round(v,2) for v in box],
                'source':'reference_comparison','status':'pending'})
        detections.sort(key=lambda d:d['anomaly_score'],reverse=True)
        blocked=False
        if len(detections)>self.config['max_regions']:
            detections=detections[:self.config['max_regions']];blocked=True
            warnings.append('Найдено слишком много областей. Часть не показана: измените условия съёмки или порог.')
        if coverage<self.config['min_coverage_for_pass']:
            blocked=True;warnings.append(f'Эталон покрывает только {coverage:.0%} области проверки. PASS заблокирован.')
        if changed>self.config['max_changed_fraction']:
            blocked=True;warnings.append('Изменилось слишком много пикселей: проверьте ревизию платы, свет и ракурс.')
        gray=cv.cvtColor(target,cv.COLOR_RGB2GRAY)
        focus=float(cv.Laplacian(gray,cv.CV_32F).var())
        if focus<25:
            blocked=True;warnings.append('Снимок выглядит размытым. Переснимите плату с фокусом на компонентах.')
        heat=cv.applyColorMap((score*255).astype(np.uint8),cv.COLORMAP_JET)
        heat=cv.cvtColor(heat,cv.COLOR_BGR2RGB)
        overlay=(target.astype(float)*.6+heat.astype(float)*.4).astype(np.uint8)
        overlay[~valid]=target[~valid]
        # Areas without reference coverage are visibly grey, not implicitly PASS.
        missing=(domain>0)&(~valid)
        overlay[missing]=(target[missing].astype(float)*.4+np.array([175,175,175])*.6).astype(np.uint8)
        aligned_full=cv.resize(aligned,(width,height),interpolation=cv.INTER_LINEAR)
        heat_full=cv.resize(overlay,(width,height),interpolation=cv.INTER_LINEAR)
        return {'detections':detections,'width':width,'height':height,
            'elapsed_ms':round((time.perf_counter()-started)*1000,1),'threshold':threshold,'min_area':min_area,
            'roi':roi,'model':self.health(),'machine_verdict':'REVIEW' if blocked else ('FAIL' if detections else 'PASS'),
            'analysis_blocked':blocked,'analysis_available':True,'warnings':warnings,'alignment':alignment,
            'coverage':round(coverage,4),'changed_fraction':round(changed,4),'focus_score':round(focus,2),
            'aligned_reference':image_url(aligned_full),'heatmap':image_url(heat_full),
            'notice':'Подсветка отличий, а не автоматический диагноз типа дефекта.',**info}
