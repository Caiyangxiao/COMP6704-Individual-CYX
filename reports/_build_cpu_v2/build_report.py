
from pathlib import Path
import json, subprocess, sys, re
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Image, Spacer, PageBreak
from docx import Document
from docx.shared import Cm, Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from PIL import Image as PILImage
from pypdf import PdfReader
import pypdfium2 as pdfium
sys.stdout.reconfigure(encoding="utf-8")

root=Path(r"C:\Users\25244\Desktop\Codex\COMP6704\Individual Assignment")
out=root/"reports"; build=out/"_build_cpu_v2"
build.mkdir(parents=True,exist_ok=True)
stem="COMP6704_CPU版选题方案说明报告_完善版"
maths={
"general":r"$\min_{x\in\mathbb{R}^{d}} f(x),\qquad g_k=\nabla f(x_k)$",
"rosen":r"$f_R(x)=\sum_{i=1}^{d-1}\left[100(x_{i+1}-x_i^2)^2+(1-x_i)^2\right],\quad f_R^\star=0$",
"rosen_hess":r"$\nabla^2 f_R(0,1)=\begin{pmatrix}-398&0\\0&200\end{pmatrix},\qquad \nabla f_R(0,1)=\begin{pmatrix}-2\\200\end{pmatrix}$",
"rastr":r"$f_A(x)=10d+\sum_{i=1}^{d}\left[x_i^2-10\cos(2\pi x_i)\right],\quad f_A^\star=0$",
"rastr_der":r"$[\nabla f_A(x)]_i=2x_i+20\pi\sin(2\pi x_i),\quad [\nabla^2 f_A(x)]_{ii}=2+40\pi^2\cos(2\pi x_i)$",
"gd":r"$p_k=-g_k,\qquad x_{k+1}=x_k+\alpha_k p_k$",
"armijo":r"$f(x_k-\alpha_k g_k)\leq f(x_k)-c_1\alpha_k\|g_k\|_2^2$",
"gd_lower":r"$\alpha_k\geq\min\left\{1,\frac{2\tau(1-c_1)}{L}\right\}>0,\qquad \sum_{k=0}^{\infty}\|g_k\|_2^2<\infty$",
"cg":r"$p_0=-g_0,\quad \beta_k^{\mathrm{PR+}}=\max\left\{0,\frac{g_k^\top(g_k-g_{k-1})}{g_{k-1}^\top g_{k-1}}\right\},\quad p_k=-g_k+\beta_k^{\mathrm{PR+}}p_{k-1}$",
"bfgs_defs":r"$p_k=-H_k g_k,\quad s_k=x_{k+1}-x_k,\quad y_k=g_{k+1}-g_k,\quad \rho_k=(y_k^\top s_k)^{-1}$",
"bfgs":r"$H_{k+1}=(I-\rho_k s_k y_k^\top)H_k(I-\rho_k y_k s_k^\top)+\rho_k s_k s_k^\top$",
"wolfe":r"$f(x_{k+1})\leq f(x_k)+c_1\alpha_k g_k^\top p_k,\qquad |g_{k+1}^\top p_k|\leq c_2|g_k^\top p_k|$",
"curvature":r"$s_k^\top y_k=\alpha_k(g_{k+1}-g_k)^\top p_k\geq\alpha_k(1-c_2)(-g_k^\top p_k)>0$",
}
(build/"maths.json").write_text(json.dumps(maths,ensure_ascii=False,indent=2),encoding="utf-8")
make_math=r'''
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
'''
# Matplotlib's internal mathtext does not support pmatrix; use bmatrix-free notation.
maths["rosen_hess"]=r"$\nabla^2 f_R(0,1)=\mathrm{diag}(-398,\,200),\qquad \nabla f_R(0,1)=(-2,\,200)^\top$"
(build/"maths.json").write_text(json.dumps(maths,ensure_ascii=False,indent=2),encoding="utf-8")
(build/"make_math.py").write_text(make_math,encoding="utf-8")
subprocess.run([r"C:\Users\25244\AppData\Local\Programs\Python\Python312\python.exe",str(build/"make_math.py")],check=True)

pages=[]
def new(): pages.append([]);return pages[-1]
def p(a,s):a.append({"kind":"p","text":s})
def h(a,s,l=1):a.append({"kind":"h","text":s,"level":l})
def note(a,s):a.append({"kind":"note","text":s})
def tbl(a,headers,rows,widths):a.append({"kind":"table","headers":headers,"rows":rows,"widths":widths})
def eq(a,key):a.append({"kind":"formula","key":key})

a=new()
a.append({"kind":"title","text":"COMP6704 个人作业\nCPU 版选题方案说明报告"})
a.append({"kind":"banner","text":"一级方向：Unconstrained Optimization（无约束优化）"})
a.append({"kind":"subtitle","text":"具体主题：非凸测试函数上的经典算法比较\nGD、非线性共轭梯度与 BFGS"})
p(a,"英文题目：Comparing Gradient Descent, Nonlinear Conjugate Gradient, and BFGS on Nonconvex Test Functions")
p(a,"姓名：Yangxiao Cai　　学号：26023041r\n课程：Advanced Topics in Optimization　　学期：Fall 2026\n修订日期：2026 年 11 月 5 日")
note(a,"报告性质：选题与实施方案。正式实验尚未开展；本文不报告算法排名、已取得的收敛曲线或实际运行耗时。")
h(a,"1　方向归属、研究动机与完成范围")
p(a,"本项目属于 Unconstrained Optimization 大方向下的“非凸无约束数值优化与算法基准比较”。研究变量为实向量，不设边界、等式或不等式约束。初始点从有限区间产生，仅用于规定起点分布，不限制后续迭代。")
p(a,"小组项目选择 Convex Optimization。个人项目以非凸曲率、局部驻点和初值敏感性为研究对象，实验与分析独立完成。两者的区别体现在问题性质和研究内容；“无约束”本身并不排除凸问题，因此本报告同时明确非凸这一分支。")
tbl(a,["研究问题","拟提供的证据"],[
["RQ1：何种实现下降更有效率？","目标差距与迭代数、累计函数／梯度评估次数的关系。"],
["RQ2：维度与初值有何影响？","2、10、20 维，各组合共享 5 个初始点的配对结果。"],
["RQ3：终止是否意味着全局目标命中？","分别检查求解器状态、梯度范数和已知全局目标差距。"]],[.43,.57])
p(a,"固定范围为 Rosenbrock 与 Rastrigin 两个函数、GD／非线性 CG／BFGS 三种方法，共 90 次 CPU 求解。研究贡献定位为可解释、可复现的受控比较；理论推导、近期文献与失败分析用于支撑研究深度。")

a=new()
h(a,"2　文献基础与近期研究")
p(a,"文献综述围绕“下降方向—线搜索—曲率更新—非凸收敛边界”组织。Nocedal 与 Wright 的教材提供线搜索、非线性共轭梯度和拟牛顿法的基础框架。[1] 本方案进一步纳入以下两篇近期原始研究，而非仅依赖软件文档。")
h(a,"2.1　近期文献及其与本项目的关系",2)
tbl(a,["文献","已核实的主要内容","本项目如何使用"],[
["Jin、Jiang、Mokhtari\nNeurIPS 2024 [2]","分析 BFGS 配合 Armijo–Wolfe 线搜索的非渐近收敛性质；主要保证依赖强凸性与梯度等正则条件。","用来说明线搜索和问题假设影响收敛保证；这些结论不能直接套用于本项目的非凸函数。"],
["Mannel\nJOTA 2025 [3]","研究改进的 L-BFGS／BB 方法，通过谨慎选择更新对建立非凸问题的驻点类保证；局部线性收敛还需相应条件。","用来讨论普通拟牛顿法在非凸问题上的理论边界，以及曲率保障为何值得研究。"]],[.23,.40,.37])
p(a,"两篇论文均作为综述和理论对照，不增加本项目的算法数量。Mannel 研究的是经过修改的 L-BFGS，不能将其保证写成 SciPy 普通 BFGS 的保证；Jin 等的强凸情形也不改变本项目属于非凸无约束优化的定位。")
h(a,"2.2　从文献形成的分析主线",2)
p(a,"首先区分“充分下降”与“到达驻点”：函数值下降并不自动给出梯度趋零，还需步长下界及问题正则性。其次区分“驻点收敛”与“找到全局最优”：非凸文献中的 global convergence 常指从一般初值建立驻点类性质，不能直接翻译为全局最优保证。")
p(a,"实验将据此解释：Rosenbrock 的弯曲狭谷为何使单纯负梯度方向进展缓慢；曲率信息是否减少评估；Rastrigin 中较小梯度为何可能对应非全局局部极小值。所有具体比较结论留待实际结果决定。")
h(a,"2.3　资料使用与实现边界",2)
p(a,"算法原理与收敛背景参考教材和研究论文；接口参数及具体保障检查 SciPy 文档与对应版本源码。[4–7] 测试函数出处与性质另行注明。[7–8] 最终报告拟补充与所用 CG 变体、拟牛顿更新相对应的经典文献，保持“理论依据—具体实现—实验解释”一致。")
note(a,"本方案已补入近期研究的初步比较。正式报告仍需结合全文阅读、课程讲义与实际实验，形成连贯的相关工作讨论；参考文献列表本身不代替综述。")

a=new()
h(a,"3　数学问题与非凸性分析")
eq(a,"general")
p(a,"统一研究 f:R^d→R 的无约束最小化。两函数均光滑、下有界，并有已知全局最小值，便于同时观察梯度达标与目标值接近全局最小值的差别。")
h(a,"3.1　Rosenbrock 函数：狭谷与耦合",2)
eq(a,"rosen")
p(a,"各项为平方和，因此 f_R≥0；当且仅当 x=(1,…,1) 时取到全局最小值 0。邻接变量之间存在耦合；二维最优点附近的弯曲狭谷适合观察负梯度震荡、方向更新和曲率近似的作用。[7]")
eq(a,"rosen_hess")
p(a,"上述二维点的 Hessian 同时有负、正特征值，证明目标非凸；该点梯度不为零，因此不把它称为鞍点。较高维时也可通过固定其他坐标并考察相应负曲率方向说明非凸。Hessian 仅用于理论解释，不作为求解器输入。")
h(a,"3.2　Rastrigin 函数：多局部极小值",2)
eq(a,"rastr")
eq(a,"rastr_der")
p(a,"Hessian 的非对角项为零。当某个坐标为 1/2 时，对应方向曲率为 2−40π²<0，故目标非凸；该负曲率例点也不必是驻点。将目标写成各项 x_i²+10[1−cos(2πx_i)] 之和，可知唯一全局最小点为 x=0，最小值为 0。[8]")
p(a,"Rastrigin 的多峰结构用于揭示局部算法与全局目标之间的差别。高维随机初值下，全局目标命中数可能均为零；这仍是有效现象，应结合梯度、目标值与评估次数解释，不临时挑选更有利的起点。")
h(a,"3.3　解析梯度与数值核对",2)
p(a,"Rosenbrock 使用 SciPy 的 rosen、rosen_der；Rastrigin 自行实现上述函数与梯度。正式实验前在多个非驻点用中心有限差分核对解析梯度，记录步长与相对误差。误差标准、版本和公式在运行前确认。")

a=new()
h(a,"4　GD 与非线性共轭梯度")
h(a,"4.1　GD 与 Armijo 回溯：实现与下降保证",2)
eq(a,"gd")
eq(a,"armijo")
p(a,"自行实现 GD。每轮从 α=1 开始，不满足 Armijo 时令 α←0.5α；固定 c1=10^-4。最多允许 50 次回溯，α<10^-12 或出现非有限值时记录失败；仅接受有限且满足条件的更新。若浮点计算使新点完全等于旧点，则记录数值停滞，不自动视为收敛。")
p(a,"Armijo 直接给出接受点的充分下降。若梯度在相关区域为 L-Lipschitz，则 α≤2(1−c1)/L 足以满足条件。在理想精确算术、目标下有界、梯度局部 Lipschitz、初始子水平集紧，且回溯可充分继续的条件下，固定回溯比例 τ=0.5 可得正的步长下界：")
eq(a,"gd_lower")
p(a,"因此理想无限迭代情形下梯度范数趋零，但不必证明整个点序列收敛到唯一点。[1] 本项目设有最大迭代数与步长下限；达到这些限制时，必须按实际梯度判断，不将理论背景当作已完成收敛的证据。")
h(a,"4.2　非线性 CG：PR+ 及充分下降检查",2)
eq(a,"cg")
p(a,"此处 CG 是非线性共轭梯度，区别于线性方程组 CG 和 Newton-CG。采用 scipy.optimize.minimize(method='CG')，提供解析梯度。公式中的 β 为 PR+：把 Polak–Ribière 系数截断为非负，k≥1。β=0 时方向退化为负梯度。")
p(a,"PR+ 截断本身不能保证每一步充分下降。已核对的 SciPy 1.13.1 实现，在接受线搜索步长时另检查下一方向的充分下降条件（σ=0.01），或接受已达到梯度阈值的点。[4,6] 这与“每次失败就显式重启”并非同一实现，不混写。")
p(a,"CG 设置 c1=10^-4、c2=0.4，使用库的 Wolfe 线搜索及内部保障。与 GD 的回溯策略不同，实验比较对象是这些明确配置的算法实现；迭代次数差异不能全部归因于搜索方向。")

a=new()
h(a,"5　BFGS、曲率条件与复杂度修正")
h(a,"5.1　逆 Hessian 近似与更新",2)
eq(a,"bfgs_defs")
eq(a,"bfgs")
p(a,"使用 scipy.optimize.minimize(method='BFGS')，H0=I，提供解析梯度，不显式计算真实 Hessian。CG 与 BFGS 的库实现均如实注明来源；自行实现范围是 GD、函数、记录与比较流程。[5–6]")
h(a,"5.2　Wolfe 条件为何与 BFGS 有关",2)
eq(a,"wolfe")
p(a,"在下降方向 g_k^T p_k<0、α_k>0、0<c1<c2<1 下，强 Wolfe 的曲率条件推出：")
eq(a,"curvature")
p(a,"因此，精确算术下从正定 H0 出发，标准 BFGS 更新可保持逆 Hessian 近似正定，并产生下降方向。[1] 这不是一般非凸问题的全局最优保证；有限精度及具体实现中的保护也须单独记录。CG／BFGS 统一取 c2=0.4，注明 BFGS 的该值不同于 SciPy 默认 0.9。[4–5]")
h(a,"5.3　理论高效实现与实际库实现分开报告",2)
tbl(a,["实现／方法","方向和更新时间","优化器状态空间"],[
["GD","O(d)","O(d)"],
["非线性 CG","O(d)","O(d)"],
["标准高效 BFGS","利用低秩结构，可实现 O(d²)","O(d²)"],
["SciPy 1.13.1 BFGS","方向 O(d²)；已核源码的更新含通用稠密乘法，按常规计算为 O(d³)","O(d²)"]],[.29,.47,.24])
p(a,"SciPy 1.13.1 的更新含 A1·H·A2 的稠密乘法；不再承诺控制库内部“避免通用矩阵乘法”。[6] 若正式使用其他版本，须重新核查源码，按实际版本更新结论。")
p(a,"表中不含函数／梯度评估及日志。两测试函数的每次函数或解析梯度评估均为 O(d)，总调用成本还取决于线搜索；保存 K 个 d 维接受点另需 O(Kd) 空间与总复制时间。小维度计时不足以单独验证渐近复杂度。")

a=new()
h(a,"6　主实验协议：90 次配对 CPU 求解")
tbl(a,["项目","冻结前拟采用的设置"],[
["函数与维度","Rosenbrock、Rastrigin；d∈{2,10,20}。"],
["初始点","每个函数／维度组合生成 5 个，保存后由三种方法逐点共享。"],
["生成规则","种子 20261105；Rosenbrock 各坐标 Uniform[-2,2]，Rastrigin 各坐标 Uniform[-3,3]。"],
["运行总量","2 个函数 × 3 种维度 × 5 个初值 × 3 种方法 = 90 次；试跑另计。"],
["精度与环境","float64；同一电脑、环境、线程设置；顺序运行。"],
["公共停止目标","梯度二范数≤10^-6；最多 5000 个接受更新；保留失败和非有限值。"],
["SciPy 参数","jac=解析梯度，norm=2，gtol=10^-6，maxiter=5000；BFGS xrtol=0，H0=I。"],
["线搜索","GD：Armijo，α0=1，τ=0.5；CG／BFGS：c1=10^-4、c2=0.4。"],
["全局目标阈值","求解后独立判断 |f(x)−f*|≤10^-6；两函数 f*=0。"]],[.25,.75])
p(a,"先在二维小例子上核对梯度、更新、日志和终止规则，再冻结全部参数与起点。五个起点用于初值敏感性观察；固定初值后的方法是确定性的，不称为五个随机训练种子。")
h(a,"6.1　三类结果标签分别统计",2)
tbl(a,["标签","判断方式"],[
["求解器状态","原始 success／status／message；GD 保存对应的自定义状态。"],
["公共驻点指标达标","离线重算后，结果有限且梯度二范数≤10^-6。"],
["已知全局目标阈值命中","结果有限且 |f(x)−f*|≤10^-6；表述为数值阈值命中，不证明精确全局最优。"]],[.30,.70])
p(a,"公共标签用于横向比较，原始状态用于解释终止原因。迭代上限、线搜索失败、数值停滞均保留，不只汇总成功案例。若出现明显不合理的负目标差距，先核查实现或数值问题，不据此记为全局目标命中。")
h(a,"6.2　预算与解释边界",2)
p(a,"相同最大迭代数不是相同计算预算，因此同时报告函数与梯度评估次数，不默认一次函数调用等价于一次梯度调用。主要结论限定于这两个函数、所测维度、初值分布与实现；不声称普遍算法排名。")

a=new()
h(a,"7　逐步记录、计时与结果展示")
h(a,"7.1　修正：同时保存轨迹和累计评估次数",2)
p(a,"函数和梯度分别使用带计数的包装器；包含线搜索试探在内的实际调用均计入。CG／BFGS 用返回的 nfev、njev 与包装器总数交叉核对。只保存最终计数不能恢复逐步评估成本，因此每个轨迹事件需保存以下信息：")
tbl(a,["字段","内容"],[
["身份与事件","函数、维度、初值编号、方法、event_type∈{initial,accepted,terminal}。"],
["逐步状态","接受更新编号 k、x.copy()、累计 nfev／njev；可同时存相对求解起点的时间戳。"],
["初始记录","求解前记录 x0 和零计数，图示目标值离线补算；求解器正常的初值评估仍计数。"],
["接受点记录","callback 仅复制坐标并读取现有计数，不额外评价函数或梯度。"],
["终止记录","追加最终计数及坐标；失败线搜索可能增加计数但没有新接受点，此记录不增加 nit。"]],[.24,.76])
p(a,"求解结束后，用不计数的 raw_fun／raw_grad 离线计算每个事件的目标值、梯度和公共标签。计时和包装器统计在此之前结束；补值不污染求解预算。失败终止事件允许与上一接受点坐标相同，但累计评估次数更大。")
h(a,"7.2　计时边界与输出图表",2)
p(a,"用 time.perf_counter 从求解器开始到返回计时，包含正常初始化、试探评估和统一轨迹记录开销；不含导入、安装、离线分析、绘图或写文件。固定并记录线程与电源设置，不并发运行。小问题墙钟噪声较大，耗时作为辅助证据。")
tbl(a,["图表","展示要求"],[
["二维等高线与轨迹","两函数各一张，使用预先固定的第 1 个起点；坐标范围覆盖实际轨迹。"],
["目标差距与梯度曲线","同时提供对迭代数和累计 nfev 的比较；njev 另列。对数显示下限明确，原始值保留。"],
["分组汇总表","按函数／维度／方法报告 5 个起点的中位数、范围、驻点达标数、全局目标命中数。"],
["成本与失败分析","函数／梯度调用次数、辅助耗时、各类终止原因及代表性失败轨迹。"]],[.29,.71])
p(a,"五个起点仅提供有限敏感性证据；二维轨迹和代表案例不替代全部运行汇总。高维全局命中数若均为零，结合目标值、驻点指标和评估成本分析。")

a=new()
h(a,"8　实施条件、进度与课程交付")
p(a,"本机 i7-13700HX、约 16 GB 内存足以承担本方案的 2–20 维求解。统一使用 CPU；BFGS 最大矩阵为 20×20。Python、NumPy、SciPy、Matplotlib 即可完成。已核查的本机 SciPy 1.13.1 可作为实现参照；正式运行锁定实际版本，变更版本时重新核查参数、源码与复杂度。")
p(a,"按每天 1–2 小时安排，预计人工投入 18–26 小时：阅读与理论 4–6 小时，实现与核对 5–7 小时，实验和分析 3–4 小时，报告与复现 6–9 小时。自动求解耗时另由试跑测定。新增工作主要用于文献、推导和记录完整性，不扩大主实验。")
tbl(a,["日期（2026）","完成标志"],[
["11/5–11/9","完成近期文献初读、函数性质与三方法推导，确认环境和二维试跑。"],
["11/10–11/14","完成 GD、梯度核对、统一日志和公共判定，冻结 90 次实验配置。"],
["11/15–11/18","执行主实验，核对计数和失败记录，生成全量汇总及图表。"],
["11/19–11/26","完成理论与结果解释、相关工作、报告和 README；复查复现命令。"],
["11/27–11/28","检查 PDF、引用、姓名学号与代码链接，提前提交 Canvas。"],
["11/29","截止日缓冲；23:59 前提交，以 Canvas 显示时间为准。"]],[.25,.75])
h(a,"8.1　最终报告与可复现交付",2)
p(a,"最终报告整份 PDF 控制在 10 页以内、文件小于 20 MB，开头注明姓名和学号，按姓名+学号命名并提交 Canvas。NeurIPS 2025 模板及大规模真实数据为鼓励项。[9] 本方案采用标准合成测试问题路线。")
tbl(a,["评分项","对应交付"],[
["文献综述 20%","经典框架、两篇近期研究及其假设与适用边界。"],
["建模 20%","无约束变量空间、函数、非凸性与研究动机。"],
["算法 20%","GD 实现、CG／BFGS 公式、线搜索、库来源与复杂度。"],
["实验分析 30%","轨迹、目标差距、驻点、初值与维度、评估次数及失败解释。"],
["复现 10%","版本、配置、初值、逐步日志、结果 CSV、脚本和 README。"]],[.28,.72])
p(a,"代码结构保持简洁：实验脚本、绘图脚本、配置、初始点、逐步及汇总结果、README。若需缩减规模，在正式运行前决定将 20 维转为扩展，保留两函数、三方法及 2／10 维，共 60 次。")

a=new()
h(a,"参考文献与实现资料")
refs=[
("[1] Nocedal, J., & Wright, S. J. (2006). Numerical Optimization (2nd ed.). Springer. 重点章节：线搜索、共轭梯度与拟牛顿方法。","https://link.springer.com/book/10.1007/978-0-387-40065-5"),
("[2] Jin, Q., Jiang, R., & Mokhtari, A. (2024). Non-asymptotic Global Convergence Analysis of BFGS with the Armijo-Wolfe Line Search. Advances in Neural Information Processing Systems 37. arXiv:2404.16731（作者稿修订于 2025-01-08）。","https://arxiv.org/abs/2404.16731"),
("[3] Mannel, F. (2025). A Globalization of L-BFGS and the Barzilai–Borwein Method for Nonconvex Unconstrained Optimization. Journal of Optimization Theory and Applications, 204, Article 47. DOI:10.1007/s10957-024-02565-5。","https://link.springer.com/article/10.1007/s10957-024-02565-5"),
("[4] SciPy. minimize(method='CG'). SciPy 1.13.1 Manual. 非线性 CG、线搜索参数与终止规则。","https://docs.scipy.org/doc/scipy-1.13.1/reference/optimize.minimize-cg.html"),
("[5] SciPy. minimize(method='BFGS'). SciPy 1.13.1 Manual. BFGS、初始逆 Hessian、线搜索参数与终止规则。","https://docs.scipy.org/doc/scipy-1.13.1/reference/optimize.minimize-bfgs.html"),
("[6] SciPy developers. scipy/optimize/_optimize.py, tag v1.13.1. 核查 _minimize_cg 的 PR+ 与充分下降检查，以及 _minimize_bfgs 的矩阵更新。","https://github.com/scipy/scipy/blob/v1.13.1/scipy/optimize/_optimize.py"),
("[7] SciPy. Optimization tutorial. SciPy 1.13.1 Manual. Rosenbrock 函数、解析梯度和求解接口。","https://docs.scipy.org/doc/scipy-1.13.1/tutorial/optimize.html"),
("[8] Surjanovic, S., & Bingham, D. Virtual Library of Simulation Experiments: Test Functions and Datasets — Rastrigin Function. Simon Fraser University. 测试函数说明。","https://www.sfu.ca/~ssurjano/rastr.html"),
("[9] COMP6704: Advanced Topics in Optimization. Individual Assignment. PolyU Fall 2026. 用户提供的课程要求，第 1–3 页。",None),
]
for s,u in refs:a.append({"kind":"ref","text":s,"url":u})
p(a,"网页与版本资料核对日期：2026 年 11 月 5 日。公式推导、曲率判断和实验安排由本方案明确给出；最终报告应结合实际阅读、代码和运行结果修订。")
h(a,"本次完善重点",2)
p(a,"明确一级方向及非凸分支；补充 2024／2025 年近期文献；增加非凸性、Armijo、PR+ 和 BFGS 曲率分析；区分标准高效 BFGS 与实际库实现复杂度；逐步记录累计评估次数和终止事件，保持主实验 90 次。")
(build/"report_content.json").write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding="utf-8")

pdfmetrics.registerFont(TTFont("Song",r"C:\Windows\Fonts\simsun.ttc",subfontIndex=0))
pdfmetrics.registerFont(TTFont("Hei",r"C:\Windows\Fonts\simhei.ttf"))
pdfmetrics.registerFontFamily("Song",normal="Song",bold="Hei",italic="Song",boldItalic="Hei")
W,H=A4; usable=W-102
styles={
"p":ParagraphStyle("p",fontName="Song",fontSize=9.8,leading=15.0,spaceAfter=6,wordWrap="CJK",textColor=colors.HexColor("#243247")),
"h":ParagraphStyle("h",fontName="Hei",fontSize=15,leading=20,spaceAfter=9,spaceBefore=5,textColor=colors.HexColor("#17365A"),keepWithNext=True),
"h2":ParagraphStyle("h2",fontName="Hei",fontSize=11.2,leading=16,spaceAfter=6,spaceBefore=5,textColor=colors.HexColor("#24577E"),keepWithNext=True),
"title":ParagraphStyle("title",fontName="Hei",fontSize=24,leading=32,spaceAfter=13,textColor=colors.HexColor("#17365A")),
"subtitle":ParagraphStyle("subtitle",fontName="Hei",fontSize=15,leading=22,spaceAfter=10,textColor=colors.HexColor("#24577E")),
"banner":ParagraphStyle("banner",fontName="Hei",fontSize=14.2,leading=20,spaceAfter=15,backColor=colors.HexColor("#E4EFF7"),borderPadding=8,textColor=colors.HexColor("#17365A")),
"note":ParagraphStyle("note",fontName="Song",fontSize=9.1,leading=14.2,spaceAfter=9,wordWrap="CJK",backColor=colors.HexColor("#EFF4F8"),borderPadding=7),
"cell":ParagraphStyle("cell",fontName="Song",fontSize=9.05,leading=13.3,wordWrap="CJK"),
"th":ParagraphStyle("th",fontName="Hei",fontSize=9.3,leading=13.5,wordWrap="CJK",textColor=colors.white),
"ref":ParagraphStyle("ref",fontName="Song",fontSize=9,leading=13.4,spaceAfter=9,wordWrap="CJK"),
}
def txt(s):return escape(s).replace("\n","<br/>")
story=[]
for ix,page in enumerate(pages):
 if ix:story.append(PageBreak())
 for b in page:
  k=b["kind"]
  if k in ["p","h","title","subtitle","banner","note","ref"]:
   sty=styles["h2" if k=="h" and b.get("level")==2 else k]
   s=txt(b["text"])
   if k=="ref" and b.get("url"):s+=' <link href="'+escape(b["url"],{'"':"&quot;"})+'" color="#1F5C99">[原文链接]</link>'
   story.append(Paragraph(s,sty))
  elif k=="formula":
   fn=build/(b["key"]+".png");im=PILImage.open(fn)
   # Use a consistent target height for ordinary equations, then fit long lines.
   width=min(usable,im.width/230*72)
   height=im.height/im.width*width
   story.extend([Image(str(fn),width=width,height=height,hAlign="CENTER"),Spacer(1,6)])
  elif k=="table":
   data=[[Paragraph(txt(s),styles["th"]) for s in b["headers"]]]
   data += [[Paragraph(txt(s),styles["cell"]) for s in row] for row in b["rows"]]
   t=Table(data,colWidths=[w*usable for w in b["widths"]],repeatRows=1,hAlign="LEFT")
   t.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#24577E")),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F2F6F9"),colors.white]),
    ("GRID",(0,0),(-1,-1),.35,colors.HexColor("#D4DFE8")),
    ("VALIGN",(0,0),(-1,-1),"TOP"),
    ("TOPPADDING",(0,0),(-1,-1),5.5),("BOTTOMPADDING",(0,0),(-1,-1),5.5),
    ("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7)
   ]))
   story += [t,Spacer(1,8)]
def footer(c,d):
 c.saveState();c.setStrokeColor(colors.HexColor("#D5DFE8"));c.line(51,43,W-51,43)
 c.setFont("Song",8);c.setFillColor(colors.HexColor("#62758A"))
 c.drawString(51,30,"COMP6704 · Unconstrained Optimization · CPU 选题方案")
 c.drawRightString(W-51,30,str(d.page));c.restoreState()
pdfpath=out/(stem+".pdf")
SimpleDocTemplate(str(pdfpath),pagesize=A4,leftMargin=51,rightMargin=51,topMargin=45,bottomMargin=56,
 title="COMP6704 CPU版选题方案 — Unconstrained Optimization",author="Yangxiao Cai").build(story,onFirstPage=footer,onLaterPages=footer)

doc=Document();sec=doc.sections[0]
sec.page_width=Cm(21);sec.page_height=Cm(29.7)
sec.top_margin=Cm(1.55);sec.bottom_margin=Cm(1.65);sec.left_margin=Cm(1.8);sec.right_margin=Cm(1.8)
sec.footer_distance=Cm(.65)
def fontstyle(s,size,name="宋体",bold=False):
 s.font.name="Times New Roman";s.font.size=Pt(size);s.font.bold=bold
 s._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"),name)
normal=doc.styles["Normal"];fontstyle(normal,9.8)
normal.paragraph_format.line_spacing=1.1
normal.paragraph_format.space_after=Pt(5)
for nm,sz in [("Title",24),("Subtitle",14.5),("Heading 1",15),("Heading 2",11.2)]:
 fontstyle(doc.styles[nm],sz,"黑体",True)
 doc.styles[nm].font.color.rgb=RGBColor.from_string("17365A")
 doc.styles[nm].paragraph_format.space_before=Pt(5);doc.styles[nm].paragraph_format.space_after=Pt(7)
 doc.styles[nm].paragraph_format.keep_with_next=True
fp=sec.footer.paragraphs[0];fp.alignment=WD_ALIGN_PARAGRAPH.RIGHT
r=fp.add_run("COMP6704 · Unconstrained Optimization · CPU 方案　|　");r.font.size=Pt(8)
fld=OxmlElement("w:fldSimple");fld.set(qn("w:instr"),"PAGE");fp._p.append(fld)
def link(par,label,url):
 rel=par.part.relate_to(url,RT.HYPERLINK,is_external=True)
 el=OxmlElement("w:hyperlink");el.set(qn("r:id"),rel)
 rr=OxmlElement("w:r");rp=OxmlElement("w:rPr")
 color=OxmlElement("w:color");color.set(qn("w:val"),"1F5C99");rp.append(color)
 rr.append(rp);tt=OxmlElement("w:t");tt.text=label;rr.append(tt);el.append(rr);par._p.append(el)
for ix,page in enumerate(pages):
 if ix:doc.add_page_break()
 for b in page:
  k=b["kind"]
  if k=="h":doc.add_heading(b["text"],level=b.get("level",1))
  elif k in ("p","title","subtitle","banner","note","ref"):
   pp=doc.add_paragraph(b["text"],style={"title":"Title","subtitle":"Subtitle"}.get(k,"Normal"))
   if k=="banner":
    for r in pp.runs:r.font.size=Pt(14);r.font.bold=True;r.font.color.rgb=RGBColor.from_string("17365A")
    pp.paragraph_format.space_after=Pt(12)
   if k in ("banner","note"):
    pr=pp._p.get_or_add_pPr();sh=OxmlElement("w:shd");sh.set(qn("w:fill"),"E4EFF7" if k=="banner" else "EFF4F8");pr.append(sh)
   if k in ("note","ref"):
    for r in pp.runs:r.font.size=Pt(9)
   if k=="ref" and b.get("url"):link(pp," [原文链接]",b["url"])
  elif k=="formula":
   pp=doc.add_paragraph();pp.alignment=WD_ALIGN_PARAGRAPH.CENTER
   fn=build/(b["key"]+".png");im=PILImage.open(fn)
   shape=pp.add_run().add_picture(str(fn),width=Inches(min(6.7,im.width/230)))
   shape._inline.docPr.set("descr",maths[b["key"]])
   pp.paragraph_format.space_after=Pt(4)
  elif k=="table":
   t=doc.add_table(rows=1,cols=len(b["headers"]));t.style="Table Grid";t.autofit=False
   for j,s in enumerate(b["headers"]):t.rows[0].cells[j].text=s
   for row in b["rows"]:
    for c,s in zip(t.add_row().cells,row):c.text=s
   for ri,row in enumerate(t.rows):
    pr=row._tr.get_or_add_trPr();cant=OxmlElement("w:cantSplit");pr.append(cant)
    if ri==0:
     repeat=OxmlElement("w:tblHeader");pr.append(repeat)
    for ci,c in enumerate(row.cells):
     c.width=Cm(17.4*b["widths"][ci])
     shade=OxmlElement("w:shd");shade.set(qn("w:fill"),"24577E" if ri==0 else ("F2F6F9" if ri%2 else "FFFFFF"));c._tc.get_or_add_tcPr().append(shade)
     for pp in c.paragraphs:
      pp.paragraph_format.space_before=Pt(2);pp.paragraph_format.space_after=Pt(3);pp.paragraph_format.line_spacing=1.02
      for r in pp.runs:
       r.font.size=Pt(9)
       if ri==0:r.font.bold=True;r.font.color.rgb=RGBColor(255,255,255)
   spacer=doc.add_paragraph();spacer.paragraph_format.space_after=Pt(0)
   spacer.paragraph_format.space_before=Pt(0);spacer.paragraph_format.line_spacing=Pt(3)
doc.core_properties.title="COMP6704 CPU版选题方案说明报告（完善版）"
doc.core_properties.subject="Unconstrained Optimization — 非凸无约束优化算法比较"
doc.core_properties.author="Yangxiao Cai"
doc.core_properties.keywords="COMP6704, Unconstrained Optimization, CPU, GD, CG, BFGS"
docxpath=out/(stem+".docx");doc.save(docxpath)
r=PdfReader(pdfpath);texts=[p.extract_text() for p in r.pages]
expected_tables=sum(b["kind"]=="table" for page in pages for b in page)
expected_formula=sum(b["kind"]=="formula" for page in pages for b in page)
checks={"pages":len(r.pages),"planned_pages":len(pages),"pdf_bytes":pdfpath.stat().st_size,"docx_bytes":docxpath.stat().st_size,
 "tables":len(doc.tables),"formulas":len(doc.inline_shapes),"expected_tables":expected_tables,"expected_formulas":expected_formula,
 "page_text_lengths":[len(s) for s in texts],
 "first_page_has_direction":"Unconstrained Optimization" in texts[0],
 "has_recent_references":"2024" in texts[1] and "2025" in texts[1],
 "has_counter_protocol":"terminal" in "\n".join(texts),
 "has_complexity_correction":"O(d³)" in "\n".join(texts),
 "links":sum(len(p.get("/Annots",[])) for p in r.pages)}
(build/"pdf_text.txt").write_text("\n\n".join(f"PAGE {i+1}\n{s}" for i,s in enumerate(texts)),encoding="utf-8")
(build/"verification.json").write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding="utf-8")
pd=pdfium.PdfDocument(str(pdfpath))
for i in range(len(pd)):pd[i].render(scale=1.25).to_pil().save(build/f"page_{i+1}.png")
print(json.dumps(checks,ensure_ascii=False,indent=2))
print(docxpath);print(pdfpath)

