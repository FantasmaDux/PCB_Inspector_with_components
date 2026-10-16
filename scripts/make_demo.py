"""Create clearly synthetic PCBA fixtures, not photographs or measured defects."""
from pathlib import Path
import hashlib
import json
import random
from PIL import Image, ImageDraw, ImageEnhance

ROOT=Path(__file__).resolve().parent.parent

def component(draw,box,index):
    x,y,w,h=box
    for offset in range(7,w-4,9):
        draw.rectangle((x+offset,y-5,x+offset+4,y+3),fill='#bdc4b5')
        draw.rectangle((x+offset,y+h-3,x+offset+4,y+h+5),fill='#bdc4b5')
    draw.rounded_rectangle((x,y,x+w,y+h),radius=3,fill='#252a2d',outline='#777f79',width=2)
    draw.text((x+6,y+7),f'IC {index:02d}',fill='#c6cabe')
    draw.line((x+6,y+h-8,x+w-8,y+h-8),fill='#434e4c',width=2)
    draw.ellipse((x+5,y+3,x+9,y+7),fill='#b5bbb1')

def board(seed=42):
    rng=random.Random(seed);image=Image.new('RGB',(900,620),'#184d39');d=ImageDraw.Draw(image)
    d.rounded_rectangle((18,18,882,602),radius=16,fill='#206744',outline='#d2c086',width=3)
    for _ in range(80):
        x1,y1=rng.randint(35,860),rng.randint(40,580);x2,y2=rng.randint(35,860),rng.randint(40,580)
        d.line([(x1,y1),(x2,y1),(x2,y2)],fill=rng.choice(['#799b5b','#6d9150','#457b48']),width=rng.choice([1,2,3]))
        d.ellipse((x2-3,y2-3,x2+3,y2+3),fill='#c0bb7e')
    boxes=[]
    for row in range(4):
        for col in range(6):
            idx=row*6+col+1;x=55+col*136+rng.randint(-7,7);y=70+row*130+rng.randint(-6,6)
            box=(x,y,70+rng.randint(0,12),40+rng.randint(0,10));boxes.append(box)
            d.text((x,y-21),f'U{idx:02d} {rng.randint(100,999)}',fill='#e1e7c4')
            component(d,box,idx)
            for j in range(3):
                rx=x+j*23;d.rectangle((rx,y+62,rx+14,y+69),fill='#bab08c');d.rectangle((rx+3,y+61,rx+11,y+70),fill='#594d3a')
    for x,y in [(35,35),(865,35),(35,585),(865,585)]:d.ellipse((x-8,y-8,x+8,y+8),fill='#c3af72');d.ellipse((x-4,y-4,x+4,y+4),fill='#283f31')
    d.text((290,568),'SYNTHETIC PCBA DEMO - NOT A REAL PCB PHOTO',fill='#d1debb')
    return image,boxes

def main():
    folder=ROOT/'samples';folder.mkdir(exist_ok=True)
    golden,boxes=board();golden.save(folder/'demo_reference.png')
    ImageEnhance.Brightness(golden).enhance(1.04).save(folder/'demo_normal.png')
    missing=golden.copy();d=ImageDraw.Draw(missing);x,y,w,h=boxes[8]
    d.rectangle((x-6,y-7,x+w+6,y+h+7),fill='#206744')
    for offset in range(7,w-4,9):
        d.rectangle((x+offset,y-5,x+offset+4,y+3),fill='#c6c8a2');d.rectangle((x+offset,y+h-3,x+offset+4,y+h+5),fill='#c6c8a2')
    missing.save(folder/'demo_missing.png')
    displaced=golden.copy();d=ImageDraw.Draw(displaced);x,y,w,h=boxes[15];d.rectangle((x-6,y-7,x+w+6,y+h+7),fill='#206744');component(d,(x+18,y+13,w,h),16)
    displaced.rotate(1.5,resample=Image.Resampling.BICUBIC,fillcolor='#184d39').save(folder/'demo_displaced.png')
    wrong,_=board(87);wrong.save(folder/'demo_wrong_reference.png')
    entries=[]
    for name,label in [('normal','Без внесённых изменений'),('missing','Удалён условный компонент'),('displaced','Смещён компонент и повёрнут снимок')]:
        filename=f'demo_{name}.png'
        entries.append({'file':filename,'reference':'demo_reference.png','label':label,'variant':'SYNTHETIC-PCBA rev.1','synthetic':True,'description':'Синтетическая иллюстрация собранной платы. Это демонстрационный сценарий, а не фотография или оценка качества на реальных платах.','sha256':hashlib.sha256((folder/filename).read_bytes()).hexdigest()})
    (folder/'manifest.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Created synthetic PCBA pairs')

if __name__=='__main__':main()
