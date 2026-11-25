"""Generate a physically scaled A4 calibration target, all lengths in mm."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

OUT = Path(__file__).resolve().parents[1] / 'output' / 'pdf'
OUT.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(TTFont('CN', 'C:/Windows/Fonts/msyh.ttc'))
c = canvas.Canvas(str(OUT / 'K230_A4_calibration_map.pdf'), pagesize=(210*mm, 297*mm))
c.setTitle('K230 A4 160mm calibration map')
def text(x, y, value, size=9, center=False):
    c.setFont('CN', size)
    (c.drawCentredString if center else c.drawString)(x*mm, y*mm, value)
def line(x1,y1,x2,y2):
    c.line(x1*mm,y1*mm,x2*mm,y2*mm)
text(105,282,'K230 机械臂视觉标定坐标图',17,True)
text(105,273,'A4 纵向 · 100% 实际大小 · 单位：毫米',10,True)
text(105,265,'禁止“适合页面 / 缩放打印”；先用尺子核对下方 100 mm 校验线',9,True)
ox,oy=25,85
for i in range(0,161,10):
    c.setStrokeGray(.72 if i%20==0 else .88)
    c.setLineWidth(.45 if i%20==0 else .25)
    line(ox+i,oy,ox+i,oy+160)
    line(ox,oy+i,ox+160,oy+i)
    if 0<i<160 and i%20==0:
        c.setFillGray(.25)
        text(ox+i,oy-5,str(i),7,True)
        text(ox-8,oy+i-1,str(i),7,True)
c.setFillGray(0);c.setStrokeGray(0);c.setLineWidth(.8)
c.rect(ox*mm,oy*mm,160*mm,160*mm)
for name,x,y,ly in [('A',0,0,-13),('B',160,0,-13),('C',160,160,7),('D',0,160,7)]:
    px,py=ox+x,oy+y
    c.setFillGray(1);c.circle(px*mm,py*mm,3.5*mm,fill=1,stroke=0)
    c.setFillGray(0);c.circle(px*mm,py*mm,2*mm,fill=1,stroke=0)
    c.setLineWidth(.6)
    line(px-5,py,px+5,py);line(px,py-5,px,py+5)
    text(px,py+ly,f'{name} ({x}, {y})',8,True)
for name,x,y in [('E',80,80),('F',40,120),('G',120,40)]:
    px,py=ox+x,oy+y
    c.setFillGray(1);c.circle(px*mm,py*mm,3*mm,fill=1,stroke=0)
    c.setFillGray(0);c.setLineWidth(.7)
    c.circle(px*mm,py*mm,2*mm,fill=0,stroke=1)
    line(px-4,py,px+4,py);line(px,py-4,px,py+4)
    text(px,py+6,f'{name} ({x}, {y})',8,True)
text(105,65,'A → B 为 +X；A → D 为 +Y；每小格 10 × 10 mm',9,True)
c.setLineWidth(1)
line(55,54,155,54);line(55,51,55,57);line(155,51,155,57)
text(105,58,'打印校验：两端刻线中心间距必须为 100 mm',9,True)
text(18,43,'用途：A/B/C/D 拟合平面映射；E/F/G 独立检查误差。',9)
text(18,36,'测木块顶面：整张纸平整固定在离桌面 30 mm 的水平硬板上。',9)
text(18,29,'纸面实际高度含纸和硬板厚度；请用尺子量准。',9)
text(18,22,'保持相机、机械臂观察姿态及坐标图不动，所有标记须完整可见。',9)
text(18,15,'此为图纸局部坐标；需再测量其相对底座的位置与方向，才能用于抓取。',8)
c.showPage();c.save()
print(OUT / 'K230_A4_calibration_map.pdf')
