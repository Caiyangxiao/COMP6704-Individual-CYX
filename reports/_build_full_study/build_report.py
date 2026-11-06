
"""Build the Chinese study report from immutable CSV/JSON results and figures.
Optional document dependencies: python-docx==1.2.0, reportlab==4.4.9, Pillow.
Rendering checks additionally use pypdf and pypdfium2 when available.
"""
from pathlib import Path
from collections import Counter
from hashlib import sha256
from xml.sax.saxutils import escape
import csv,json,sys
from PIL import Image as PILImage
from docx import Document
from docx.shared import Cm,Inches,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Image,Spacer,PageBreak

sys.stdout.reconfigure(encoding="utf-8")
project=Path(__file__).resolve().parents[2]
result=project/"results/full_study"
analysis=result/"analysis"
figures=analysis/"figures"
output=project/"reports";build=output/"_build_full_study"
build.mkdir(parents=True,exist_ok=True)
stem="COMP6704_90次正式实验分析报告"
def readcsv(path):
 with path.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
rows=readcsv(result/"summary.csv")
groups=readcsv(analysis/"grouped_results.csv")
diagnostics=readcsv(analysis/"run_diagnostics.csv")
pairs=readcsv(analysis/"paired_comparisons.csv")
meta=json.loads((result/"metadata.json").read_text(encoding="utf-8"))
summary=json.loads((analysis/"analysis_summary.json").read_text(encoding="utf-8"))
validation=json.loads((analysis/"validation.json").read_text(encoding="utf-8"))
assert meta["completed_runs"]==summary["runs"]==len(rows)==90
assert summary["stationary_count"]==73 and summary["global_hit_count"]==26
assert (figures/"outcome_matrix.png").is_file()
methods=["GD","CG","BFGS"]
def truth(x):return x=="True" if isinstance(x,str) else bool(x)
def fmt(x,n=4):
 v=float(x)
 if v==0:return "0"
 if abs(v)<.001 or abs(v)>=10000:return f"{v:.{n-1}e}"
 return f"{v:.{n}g}"
def iv(x):return str(int(float(x)))
def stat(g,metric,scientific=False):
 if scientific:
  return fmt(g[metric+"_median"],4)+"\n["+fmt(g[metric+"_min"],3)+", "+fmt(g[metric+"_max"],3)+"]"
 return iv(g[metric+"_median"])+"\n["+iv(g[metric+"_min"])+", "+iv(g[metric+"_max"])+"]"
def grouped_table(problem):
 data=[]
 for d in [2,10,20]:
  for method in methods:
   g=next(x for x in groups if x["problem"]==problem and int(x["dimension"])==d and x["method"]==method)
   data.append([str(d),method,g["stationary_count"]+", "+g["global_hit_count"],
                iv(g["nit_median"]),stat(g,"nfev"),stat(g,"njev"),stat(g,"f_value",True)])
 return data
pages=[]
def new():pages.append([]);return pages[-1]
def p(a,s):a.append({"kind":"p","text":s})
def h(a,s,l=1):a.append({"kind":"h","text":s,"level":l})
def note(a,s):a.append({"kind":"note","text":s})
def tbl(a,headers,data,widths):a.append({"kind":"table","headers":headers,"rows":data,"widths":widths})
def fig(a,name,width=493,maxheight=430):a.append({"kind":"figure","name":name,"width":width,"maxheight":maxheight})
def caption(a,s):a.append({"kind":"caption","text":s})

a=new()
a.append({"kind":"title","text":"COMP6704 个人作业\n90 次正式实验分析报告"})
a.append({"kind":"banner","text":"Unconstrained Optimization（无约束优化）\n非凸测试函数上的 GD、非线性 CG 与 BFGS"})
p(a,"姓名：Yangxiao Cai　　学号：26023041r\n实验日期：2026 年 11 月 5 日　　文件性质：正式实验结果与分析材料")
h(a,"1　实验范围与总体结果")
p(a,"按完善版 CPU 方案完成 Rosenbrock、Rastrigin 两函数 × 2／10／20 三种维度 × 每设置 5 个共享初始点 × 三种方法，共 90 次求解、30 组初值配对。协议、起点和终止阈值保持固定；所有未达标运行均纳入统计。")
p(a,"计算环境为本机 Windows CPU，Python 3.12.8、NumPy 1.26.4、SciPy 1.13.1；float64，顺序运行，BLAS／OpenMP 线程环境限为 1。梯度二范数阈值 10^-6，目标阈值 |f−f*|≤10^-6，接受更新上限 5000。")
data=[]
for problem in ["rosenbrock","rastrigin"]:
 for method in methods:
  rr=[r for r in rows if r["problem"]==problem and r["method"]==method]
  data.append([problem.title(),method,"15",str(sum(truth(r["stationary"]) for r in rr)),
               str(sum(truth(r["global_hit"]) for r in rr)),
               str(sum(not truth(r["stationary"]) for r in rr))])
tbl(a,["函数","方法","次数","驻点达标","全局目标命中","未达驻点"],data,[.23,.14,.10,.17,.20,.16])
p(a,"总体 73/90 达到驻点阈值，26/90 命中已知全局目标；另有 47 次达到驻点阈值但未命中全局目标。未达标的 17 次分为 15 次 Rosenbrock-GD 达到迭代上限，以及 2 次 Rastrigin 20 维 BFGS 精度损失终止。本批原始 solver_success 与驻点标签恰好一致，分析仍保留两种判定。")
note(a,"所有目标值、梯度和计数均来自实际保存的 90 次运行。分组统计以五个起点为单位；命中比例只描述这五个固定初值，不解释为算法总体成功概率。")

a=new()
h(a,"2　Rosenbrock：效率、维度与终点质量")
p(a,"下表每组 n=5。S、G 分别为驻点达标和全局目标命中次数（各自分母为 5）；计数与目标值为中位数 [最小值, 最大值]，包括未达标运行。迭代列只列中位数，完整范围见 grouped_results.csv。")
tbl(a,["d","方法","S, G\n(各/5)","迭代","nfev\n中位 [范围]","njev\n中位 [范围]","最终 f\n中位 [范围]"],grouped_table("rosenbrock"),[.05,.08,.10,.09,.19,.19,.30])
h(a,"2.1　GD 是预算耗尽，不能称为线搜索失败",2)
p(a,"15 次 GD 均接受了 5000 次更新，梯度仍高于阈值。2／10／20 维最终梯度中位数分别为 5.312×10^-3、4.303×10^-2、1.261×10^-1；函数调用中位数约 4.93 万、5.31 万、5.33 万。")
p(a,"接受步长中位数分别为 1/512、1/1024、1/1024；每次接受更新的函数试探次数中位数为 10、11、11。轨迹与小步长、狭谷中的缓慢进展一致；没有消融实验，不能把差异完全归因于方向或每轮重置步长。")
h(a,"2.2　BFGS 降低评估成本，同时存在非全局终点",2)
p(a,"10／20 维 BFGS 的 nfev 中位数为 114／175，CG 为 434／709；两种方法全部达到驻点阈值，但全局目标命中分别为 BFGS 12/15、CG 14/15。BFGS 有三个、CG 有一个非全局近驻点，故较少评估不能直接解释为综合质量更好。")
p(a,"中位数可能掩盖少数局部极小终点：10 维 BFGS 的最终 f 中位数约 3.08×10^-17，但最大值约 3.98658。因此必须同时看范围、命中数与逐初值表。")

a=new()
h(a,"3　Rastrigin：驻点速度与目标质量分离")
p(a,"统计口径与上一页相同，每组 n=5；所有 45 次均未命中全局目标。GD、CG 各 15 次驻点达标，BFGS 为 13/15。")
tbl(a,["d","方法","S, G\n(各/5)","迭代","nfev\n中位 [范围]","njev\n中位 [范围]","最终 f\n中位 [范围]"],grouped_table("rastrigin"),[.05,.08,.10,.09,.19,.19,.30])
h(a,"3.1　最快达到某个驻点，不等于得到最低目标值",2)
p(a,"二维第 1 个共享初值中，GD 用 36 次更新／313 次函数评估到达 f≈0.994959；CG 为 9／24、f≈4.974790；BFGS 为 7／10、f≈7.959662。三者均驻点达标，但 GD 的终点目标值最低。二维五组配对中，GD 有四组得到比另外两法更低的目标值。")
h(a,"3.2　维度与初值改变相对表现",2)
p(a,"CG 在三个维度的 nfev 中位数均为 19；BFGS 为 12、39、86。二维 BFGS 的评估较少，高维 CG 的调用成本较低；这属于所测配置下的观察，不是普遍排名。目标值上，10 维 CG／BFGS 中位数约 27.86，GD 约 35.82；20 维 GD 的第 2 个起点到达 f≈126.36，另外两法约 63.68／62.68。")
p(a,"不同方向及线搜索路径可进入不同局部吸引域，解释了同一起点下终点质量的差别。Rastrigin 目标是各坐标贡献之和，随维度增加的原始总目标值也受加和项数量影响，不能单独据此判定收敛质量退化。")
note(a,"本批未命中全局目标不代表这些方法对所有初值均不可能命中。实验保留全部五个起点，未在观察结果后补选更有利起点或放宽阈值。")

a=new()
h(a,"4　Rosenbrock 全部初值收敛曲线")
fig(a,"rosenbrock_convergence_all_starts.png",493,430)
caption(a,"图 1：行对应 d=2、10、20；列依次为目标差距—更新数、目标差距—nfev、梯度范数—更新数。每条细线是一条实际运行，圆圈／叉分别表示驻点达标／未达标；曲线止于原始终止事件。")
p(a,"蓝色 GD 曲线在预算结束时仍未穿过梯度阈值；目标下降并不意味着有限预算内已满足驻点精度。橙色 CG 和绿色 BFGS 在较少更新与评估后达到阈值，高维时两者的评估成本差异更加明显。")
p(a,"10／20 维部分目标差距曲线停在约 3.99，但对应梯度曲线已经达到阈值。这些运行没有数值失败，而是达到非全局近驻点，不能与 GD 的预算耗尽混为一类。")
p(a,"横轴用保留零点的 symlog，纵轴为对数，显示下限为 10^-16；原始数值保留。终止之后没有延长曲线或作末值填充。完整矢量图另存为同名 PDF，便于放大检查。")

a=new()
h(a,"5　Rastrigin 全部初值收敛曲线")
fig(a,"rastrigin_convergence_all_starts.png",493,430)
caption(a,"图 2：维度和指标顺序与图 1 一致，保留五个起点、三种算法和两次精度损失终止。")
p(a,"多数梯度曲线在局部阶段明显下降，而目标差距在远高于零的位置形成平台。这是“驻点达标”与“全局目标命中”分离的直接证据，不能把平台目标值当成梯度收敛失败。")
p(a,"20 维 BFGS 的两个叉形终点未达到梯度阈值；其中第 4 个初值仅略高于阈值。即使表格或图形显示舍入为 1.00×10^-6，仍按保存的完整精度判定未达标。")
p(a,"最终目标值的平台高度在初值之间、方法之间均有差异。较陡的梯度下降曲线本身不足以说明某方法在目标质量上更好，也不能直接推断严格的线性或超线性收敛阶。")

a=new()
h(a,"6　评估成本与终点质量的维度比较")
fig(a,"rosenbrock_cost_quality_by_dimension.png",444,290)
caption(a,"图 3：Rosenbrock 的 nfev、njev、最终差距和梯度。线为五起点中位数，须线为最小—最大范围，散点保留各次运行。")
fig(a,"rastrigin_cost_quality_by_dimension.png",444,290)
caption(a,"图 4：Rastrigin，口径同图 3。未驻点达标的 BFGS 运行仍纳入中位数与范围。")
p(a,"调用数分别报告，不把一次函数调用和一次梯度调用等价相加。Rosenbrock-GD 尚未达到同等精度，因此不能把其成本与成功运行的比值称为“同精度加速倍数”。")

a=new()
h(a,"7　失败原因与非全局驻点诊断")
h(a,"7.1　两例 Rastrigin 20 维 BFGS 精度损失",2)
fail=[r for r in diagnostics if r["problem"]=="rastrigin" and not truth(r["stationary"])]
tbl(a,["起点","最终梯度范数","阈值倍数","nit","总 nf / ng","终止额外 nf / ng"],[
 ["#"+r["start_id"],f"{float(r['gradient_norm']):.9e}",f"{float(r['gradient_over_threshold']):.9f}",
 iv(next(x for x in rows if x["run_id"]==r["run_id"])["nit"]),
 next(x for x in rows if x["run_id"]==r["run_id"])["nfev"]+" / "+next(x for x in rows if x["run_id"]==r["run_id"])["njev"],
 r["terminal_extra_nfev"]+" / "+r["terminal_extra_njev"]] for r in fail],
 [.09,.25,.18,.08,.18,.22])
p(a,"两者原始状态均为 SciPy status=2，消息为 Desired error not necessarily achieved due to precision loss。第 3 个初值在最后一次接受更新后，又消耗 58 次函数和 46 次梯度评估，却没有新接受点；这些开销已记录在 terminal 事件中。")
p(a,"第 4 个初值的梯度只比阈值高约 0.02346%，末次接受更新的目标变化在保存精度下为零，且终止前没有额外评估。它与数值判据分辨率限制相容，但日志不足以唯一确定内部终止机制；保留“未达标”，不通过舍入或事后放宽阈值改算成功。")
h(a,"7.2　Rosenbrock 的四个非全局近驻点",2)
local=[r for r in diagnostics if r["problem"]=="rosenbrock" and truth(r["stationary"]) and not truth(r["global_hit"])]
tbl(a,["维度／起点／方法","f","梯度范数","Hessian 最小特征值"],[
 [r["dimension"]+"维 #"+r["start_id"]+" "+r["method"],fmt(r["f_value"],8),fmt(r["gradient_norm"],5),fmt(r["hessian_min_eigenvalue"],8)] for r in local],[.31,.23,.23,.23])
p(a,"对保存终点离线计算的 Hessian 均数值正定，最小特征值约 0.499–0.501；结合小梯度，支持终点位于非全局局部极小附近，而非仅凭梯度把鞍点称为极小点。该诊断不构成对浮点终点的精确数学证明，且不计入原求解器调用预算。")
h(a,"7.3　机制解释的范围",2)
p(a,"GD 的 15 次预算耗尽、BFGS 的两次精度损失以及成功驻点的非全局目标值，是三类不同现象。当前数据支持对它们分别解释；不支持将全部未命中全局目标的运行统称为“不收敛”，也不支持声称某算法对一般非凸问题具有全局最优保证。")

a=new()
h(a,"8　逐初值结果矩阵、完整性与限制")
fig(a,"outcome_matrix.png",493,220)
caption(a,"图 5：每行是一个函数／维度，每列是方法与初值编号。G=驻点且全局目标命中，L=驻点但非全局，I=迭代上限，P=精度损失／线搜索类终止。")
tbl(a,["核验项目","实际结果"],[
 ["求解与配对","90 条汇总、90 个单次 JSON、90 份轨迹；30 组共享初值，组合完整。"],
 ["逐步记录","80,605 条事件＝80,425 个接受更新＋180 个初始／终止事件。"],
 ["计数与梯度","原始 SciPy 计数、包装器计数和终止轨迹一致；12/12 项梯度预检查通过。"],
 ["来源与协议","原求解源码及 SciPy 源码摘要匹配；配置、起点和线程环境均保存。"],
 ["计算用时","求解器计时累加 "+f"{summary['summed_solver_seconds']:.2f}"+" 秒；不含离线诊断、CSV 写出与绘图。"]
 ],[.23,.77])
p(a,"每组仅五个起点、两个标准函数和三个小维度，命中次数不作总体概率或强统计显著性推断。图中的维度趋势不能验证渐近复杂度；毫秒级墙钟差异只作辅助。GD、CG 与 BFGS 的线搜索实现不同，比较对象是本方案的具体配置。")
p(a,"同一终点质量下的条件比较也应标明子集：仅看 CG、BFGS 同时命中全局目标的 Rosenbrock 配对，2／10／20 维分别有 5／3／4 组，CG/BFGS 的 nfev 比值中位数约 1.24／2.97／3.91。这不是全部样本的无条件排名。")
p(a,"复现入口：run_experiments.py --config configs/full_study.json；汇总与绘图入口：analyze_results.py --results results/full_study --plot；完整核验：validate_study.py --results results/full_study。实际命令见 README。所有原始失败记录保留。")

a=new()
h(a,"附图　全部五个二维起点的配对轨迹")
fig(a,"rosenbrock_trajectories_all_starts.png",493,300)
caption(a,"图 6：Rosenbrock。每个面板共享一个初始点，各方法独立求解；星号为已知全局最小点，叉表示终止时未驻点达标。")
fig(a,"rastrigin_trajectories_all_starts.png",493,300)
caption(a,"图 7：Rastrigin。不同路径可进入不同局部吸引域；实际轨迹可离开初始化区间，因为本项目没有施加边界约束。")
p(a,"完整精度统计：analysis/grouped_results.csv；逐初值比较：initial_point_comparison.csv；失败与曲率证据：run_diagnostics.csv；图表均另附独立 PDF，便于引用和放大。")

build.joinpath("report_content.json").write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding="utf-8")
textlines=[]
for i,page in enumerate(pages,1):
 textlines.append(f"第 {i} 页")
 for b in page:
  if "text" in b:textlines.append(b["text"])
  elif b["kind"]=="table":
   textlines.append(" | ".join(b["headers"]).replace("\n"," "))
   textlines.extend(" | ".join(row).replace("\n"," ") for row in b["rows"])
  elif b["kind"]=="figure":textlines.append("[图表] "+b["name"])
 textlines.append("")
(analysis/"analysis_zh.txt").write_text("\n".join(textlines),encoding="utf-8")

pdfmetrics.registerFont(TTFont("Song",r"C:\Windows\Fonts\simsun.ttc",subfontIndex=0))
pdfmetrics.registerFont(TTFont("Hei",r"C:\Windows\Fonts\simhei.ttf"))
pdfmetrics.registerFontFamily("Song",normal="Song",bold="Hei",italic="Song",boldItalic="Hei")
W,H=A4;usable=W-100
styles={
 "p":ParagraphStyle("p",fontName="Song",fontSize=9.7,leading=14.8,spaceAfter=7,wordWrap="CJK",textColor=colors.HexColor("#243247")),
 "h":ParagraphStyle("h",fontName="Hei",fontSize=15,leading=20,spaceAfter=9,spaceBefore=5,textColor=colors.HexColor("#17365A"),keepWithNext=True),
 "h2":ParagraphStyle("h2",fontName="Hei",fontSize=11.1,leading=15.5,spaceAfter=6,spaceBefore=5,textColor=colors.HexColor("#24577E"),keepWithNext=True),
 "title":ParagraphStyle("title",fontName="Hei",fontSize=24,leading=32,spaceAfter=13,textColor=colors.HexColor("#17365A")),
 "banner":ParagraphStyle("banner",fontName="Hei",fontSize=14,leading=21,spaceAfter=13,backColor=colors.HexColor("#E4EFF7"),borderPadding=8,textColor=colors.HexColor("#17365A")),
 "note":ParagraphStyle("note",fontName="Song",fontSize=9.1,leading=14.1,spaceAfter=9,wordWrap="CJK",backColor=colors.HexColor("#EFF4F8"),borderPadding=7),
 "caption":ParagraphStyle("caption",fontName="Song",fontSize=8.6,leading=12.7,spaceAfter=8,wordWrap="CJK",textColor=colors.HexColor("#4C637A")),
 "cell":ParagraphStyle("cell",fontName="Song",fontSize=8.3,leading=12,wordWrap="CJK"),
 "th":ParagraphStyle("th",fontName="Hei",fontSize=8.6,leading=12.3,wordWrap="CJK",textColor=colors.white),
}
def st(s):return escape(s).replace("\n","<br/>")
story=[]
for i,page in enumerate(pages):
 if i:story.append(PageBreak())
 for b in page:
  k=b["kind"]
  if k in ["p","h","title","banner","note","caption"]:
   style=styles["h2" if k=="h" and b.get("level")==2 else k]
   story.append(Paragraph(st(b["text"]),style))
  elif k=="figure":
   path=figures/b["name"];im=PILImage.open(path)
   width=min(usable,b["width"]);height=width*im.height/im.width
   if height>b["maxheight"]:width*=b["maxheight"]/height;height=b["maxheight"]
   story.extend([Image(str(path),width=width,height=height,hAlign="CENTER"),Spacer(1,5)])
  elif k=="table":
   data=[[Paragraph(st(s),styles["th"]) for s in b["headers"]]]
   data += [[Paragraph(st(s),styles["cell"]) for s in row] for row in b["rows"]]
   t=Table(data,colWidths=[usable*w for w in b["widths"]],repeatRows=1,hAlign="LEFT")
   t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#24577E")),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F2F6F9"),colors.white]),
    ("GRID",(0,0),(-1,-1),.35,colors.HexColor("#D4DFE8")),("VALIGN",(0,0),(-1,-1),"TOP"),
    ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
    ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5)]))
   story.extend([t,Spacer(1,8)])
def footer(c,d):
 c.saveState();c.setStrokeColor(colors.HexColor("#D5DFE8"));c.line(50,43,W-50,43)
 c.setFont("Song",8);c.setFillColor(colors.HexColor("#62758A"))
 c.drawString(50,30,"COMP6704 · Unconstrained Optimization · 90 次正式实验")
 c.drawRightString(W-50,30,str(d.page));c.restoreState()
pdfpath=output/(stem+".pdf")
SimpleDocTemplate(str(pdfpath),pagesize=A4,leftMargin=50,rightMargin=50,topMargin=43,bottomMargin=55,
 title="COMP6704 90次正式实验分析报告",author="Yangxiao Cai").build(story,onFirstPage=footer,onLaterPages=footer)

doc=Document();sec=doc.sections[0]
sec.page_width=Cm(21);sec.page_height=Cm(29.7)
sec.top_margin=Cm(1.5);sec.bottom_margin=Cm(1.65);sec.left_margin=Cm(1.75);sec.right_margin=Cm(1.75)
def fstyle(s,size,name="宋体",bold=False):
 s.font.name="Times New Roman";s.font.size=Pt(size);s.font.bold=bold
 s._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"),name)
fstyle(doc.styles["Normal"],9.7)
doc.styles["Normal"].paragraph_format.line_spacing=1.1
doc.styles["Normal"].paragraph_format.space_after=Pt(5)
for name,size in [("Title",24),("Heading 1",15),("Heading 2",11.1)]:
 fstyle(doc.styles[name],size,"黑体",True)
 doc.styles[name].font.color.rgb=RGBColor.from_string("17365A")
 doc.styles[name].paragraph_format.space_before=Pt(5);doc.styles[name].paragraph_format.space_after=Pt(7)
fp=sec.footer.paragraphs[0];fp.alignment=WD_ALIGN_PARAGRAPH.RIGHT
rr=fp.add_run("COMP6704 · Unconstrained Optimization · 正式实验　|　");rr.font.size=Pt(8)
field=OxmlElement("w:fldSimple");field.set(qn("w:instr"),"PAGE");fp._p.append(field)
for i,page in enumerate(pages):
 if i:doc.add_page_break()
 for b in page:
  k=b["kind"]
  if k=="h":doc.add_heading(b["text"],level=b.get("level",1))
  elif k in ["p","title","banner","note","caption"]:
   pp=doc.add_paragraph(b["text"],style="Title" if k=="title" else "Normal")
   if k=="banner":
    for rr in pp.runs:rr.font.size=Pt(14);rr.font.bold=True;rr.font.color.rgb=RGBColor.from_string("17365A")
   if k in ["caption","note"]:
    for rr in pp.runs:rr.font.size=Pt(8.6 if k=="caption" else 9.1)
   if k in ["banner","note"]:
    shade=OxmlElement("w:shd");shade.set(qn("w:fill"),"E4EFF7" if k=="banner" else "EFF4F8");pp._p.get_or_add_pPr().append(shade)
  elif k=="figure":
   path=figures/b["name"];im=PILImage.open(path)
   width=min(usable,b["width"]);height=width*im.height/im.width
   if height>b["maxheight"]:width*=b["maxheight"]/height
   pp=doc.add_paragraph();pp.alignment=WD_ALIGN_PARAGRAPH.CENTER
   pic=pp.add_run().add_picture(str(path),width=Inches(width/72))
   pic._inline.docPr.set("descr",b["name"])
   pp.paragraph_format.space_after=Pt(3)
  elif k=="table":
   t=doc.add_table(rows=1,cols=len(b["headers"]));t.style="Table Grid";t.autofit=False
   for j,s in enumerate(b["headers"]):t.rows[0].cells[j].text=s
   for row in b["rows"]:
    for cell,s in zip(t.add_row().cells,row):cell.text=s
   for ri,row in enumerate(t.rows):
    pr=row._tr.get_or_add_trPr();pr.append(OxmlElement("w:cantSplit"))
    if ri==0:pr.append(OxmlElement("w:tblHeader"))
    for ci,cell in enumerate(row.cells):
     cell.width=Cm(17.5*b["widths"][ci])
     shade=OxmlElement("w:shd");shade.set(qn("w:fill"),"24577E" if ri==0 else ("F2F6F9" if ri%2 else "FFFFFF"));cell._tc.get_or_add_tcPr().append(shade)
     for pp in cell.paragraphs:
      pp.paragraph_format.space_before=Pt(2);pp.paragraph_format.space_after=Pt(2);pp.paragraph_format.line_spacing=1.01
      for rr in pp.runs:
       rr.font.size=Pt(8.3)
       if ri==0:rr.font.bold=True;rr.font.color.rgb=RGBColor(255,255,255)
   pp=doc.add_paragraph();pp.paragraph_format.line_spacing=Pt(3);pp.paragraph_format.space_after=Pt(0)
doc.core_properties.title=stem
doc.core_properties.author="Yangxiao Cai"
doc.core_properties.subject="Unconstrained Optimization — full 90-run CPU study"
docxpath=output/(stem+".docx");doc.save(docxpath)

inputs=[result/"summary.csv",analysis/"grouped_results.csv",analysis/"run_diagnostics.csv",analysis/"validation.json"]
inputs += sorted(figures.glob("*.png"))
manifest={"input_sha256":{str(x.relative_to(project)).replace("\\","/"):sha256(x.read_bytes()).hexdigest() for x in inputs},
 "generator_sha256":sha256(Path(__file__).read_bytes()).hexdigest(),"planned_pages":len(pages),
 "pdf_bytes":pdfpath.stat().st_size,"docx_bytes":docxpath.stat().st_size}
try:
 from pypdf import PdfReader
 r=PdfReader(pdfpath)
 manifest["pdf_pages"]=len(r.pages)
 manifest["page_text_lengths"]=[len(x.extract_text()) for x in r.pages]
 manifest["docx_tables"]=len(doc.tables);manifest["docx_figures"]=len(doc.inline_shapes)
 (build/"pdf_text.txt").write_text("\n\n".join(x.extract_text() for x in r.pages),encoding="utf-8")
 import pypdfium2 as pdfium
 pd=pdfium.PdfDocument(str(pdfpath))
 for i in range(len(pd)):pd[i].render(scale=1.2).to_pil().save(build/f"page_{i+1}.png")
except ImportError:pass
(build/"report_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(manifest,ensure_ascii=False,indent=2))
print(docxpath);print(pdfpath)

