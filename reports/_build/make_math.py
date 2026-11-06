
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
base=Path(__file__).parent
for name,formula in json.loads((base/"maths.json").read_text(encoding="utf-8")).items():
 fig=plt.figure(figsize=(11,1))
 fig.text(.015,.5,formula,fontsize=15,va="center",ha="left",color="#172b4d")
 p=base/(name+".png")
 fig.savefig(p,dpi=220,bbox_inches="tight",pad_inches=.08,facecolor="white")
 plt.close(fig)
 im=Image.open(p).convert("RGB")
 from PIL import ImageChops
 box=ImageChops.difference(im,Image.new("RGB",im.size,"white")).getbbox()
 if box:
  a,b,c,d=box
  im.crop((max(0,a-16),max(0,b-14),min(im.width,c+16),min(im.height,d+14))).save(p)
