
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageChops
base=Path(__file__).parent
for key,formula in json.loads((base/"maths.json").read_text(encoding="utf-8")).items():
 fig=plt.figure(figsize=(15,1.5))
 fig.text(.01,.5,formula,fontsize=16,va="center",color="#17365A")
 p=base/(key+".png")
 fig.savefig(p,dpi=230,bbox_inches="tight",pad_inches=.1,facecolor="white")
 plt.close(fig)
 im=Image.open(p).convert("RGB")
 box=ImageChops.difference(im,Image.new("RGB",im.size,"white")).getbbox()
 if box:
  l,t,r,b=box
  im.crop((max(0,l-16),max(0,t-12),min(im.width,r+16),min(im.height,b+12))).save(p)
