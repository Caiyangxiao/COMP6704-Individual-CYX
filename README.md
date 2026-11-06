# COMP6704 个人作业：无约束优化 CPU 实验

姓名：Yangxiao Cai；学号：26023041r。  
**一级方向：Unconstrained Optimization（无约束优化）。**  
主题：GD、非线性 PR+ 共轭梯度和 BFGS 在非凸 Rosenbrock、Rastrigin 函数上的驻点收敛、评估成本与终点质量。

保存的 Windows 正式实验包含两个函数、2／10／20 维、每组五个配对起点、三种方法，共 **90 次求解**。
参考结果为 **73/90 驻点达标、26/90 全局目标阈值命中**；另有 47 次只满足驻点指标，17 次两项均未满足。
2026-11-05 的修订更新了报告、核验和交付工具；2026-11-06 仅进行文字润色、文件重建及文件检查，未重跑 90 次正式实验或历史的 50 项测试。原始结果、初值、配置及统计表保留。

## 1. 本轮交付与证据边界

| 本地构建产物 | 内容 |
|---|---|
| `submission/Yangxiao Cai+26023041r.pdf` | 官方 NeurIPS 2025 样式的英文报告，含参考文献不超过 10 页，小于 20 MB |
| `submission/COMP6704_reproducibility.zip` | 可运行源码、90 次原始结果、分析、测试、报告源和重建材料；与 PDF 中的同名附件逐字节相同 |
| `submission/修改说明.txt` | 本轮修改范围与主要修正 |
| `submission/COMP6704_revision_audits.zip` | 2026-11-05 修订的历史审计包，保留当时的核验、交付及打包记录 |
| `submission/polish_file_checks.json` | 2026-11-06 当前实际 PDF、附件及文件哈希检查 |

提交到Canvas的PDF内含两个附件：`COMP6704_reproducibility.zip`和`packaging_verification.json`。下载原始PDF后，可在PDF阅读器的附件面板中提取。代码、原始实验数据及复现命令均可从第一个附件获得。

解压第一个附件后，从项目根目录的 `README.md` 开始，按第 2 节安装环境并按第 3 节核验。
`packaging_verification.json` 在本次打包完成后生成，作为当前 PDF 的第二个附件，**不放入它所核验的代码 ZIP 自身**。
源码包排除 `.venv`、缓存、交付 PDF、ZIP 自身、旧版本目录和额外重跑目录。

证据按用途区分：

| 路径 | 含义与适用范围 |
|---|---|
| `results/full_study/metadata.json` | 原始 Windows 90 次求解的环境、线程、初值方式和原始源码 SHA-256 |
| `audits/history/windows_exact_reproduction_20261105.json` | 原有 Windows 到 Windows 的 90 次精确比较记录，原始字节保留；当时临时候选目录现已不存在 |
| `audits/history/packaging_before_revision_20261105.json` | 修订前的打包核验历史记录，原始字节保留；不用于证明本轮代码包 |
| `audits/final_review_20261105/`、`paper_source/review_record.json` | 此前审阅快照，保留当时的范围、源码哈希和测试数量；不能当作本轮通过记录 |
| `audits/revision_20261105/unit_tests.json`、`.log` | 2026-11-05 修订的历史单元测试结果、实际数量、测试源码哈希和日志 |
| `audits/revision_20261105/current_validation.json` | 2026-11-05 修订的历史只读数据、源码和环境核验，使用第 3 节所述格式 |
| `audits/revision_20261105/source_hash_probe.json` | 2026-11-05 修订的历史源码字节与换行等价判定记录 |
| `audits/revision_20261105/preservation_check.json` | 2026-11-05 修订的历史原始结果与受保护统计材料保留核对 |
| `audits/revision_20261105/baseline_evidence/evidence_inventory.json` | 修订前实际证据文件的存在性、来源和范围索引 |
| `paper_source/polish_record_20261106.json` | 2026-11-06 润色记录：保护检查、小修与视觉审阅，以及嵌入附件前的编译来源；收入代码 ZIP |
| `submission/packaging_verification.json` | 当前代码 ZIP 的临时解包、成员与哈希核验；外层工作文件及 PDF 第二个附件 |
| `submission/polish_file_checks.json` | 2026-11-06 最终实际 PDF、附件与文件检查；用于核对本次物理交付文件 |

历史 Windows 比较和 2026-11-05 测试记录原样保留，不表示 2026-11-06 重新执行或完成跨平台验证。
本次文字／版面与文件检查分别见润色记录和外层 `polish_file_checks.json`；各记录以其日期和范围为准。
源码 ZIP 的 `archive_manifest.json` 记录成员大小和 SHA-256。

## 2. 安装与解释器

将代码 ZIP 解压到新目录，进入包含本 README、`configs/`、`cpu_optimization/` 的项目根目录。
所有命令均从这里执行。正式参考环境为 Python **3.12.8**、NumPy **1.26.4**、SciPy **1.13.1**、Matplotlib **3.10.0**。
`requirements-lock.txt` 保存原环境依赖；`requirements.txt` 固定三个主要数值／绘图依赖。

Windows PowerShell：

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

Linux／macOS，使用已安装的 Python 3.12.8：

```bash
python3.12 --version
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
```

以下 `python` 均指该虚拟环境的解释器；未激活环境时，Windows 使用
`.\.venv\Scripts\python.exe`，Linux／macOS 使用 `.venv/bin/python`。
WSL 调用现有 Windows 环境可使用 `.venv/Scripts/python.exe`。
如锁定依赖无法安装，可改用 `requirements.txt` 并保留实际环境记录；版本差异须在核验结果中体现。
原机器的绝对路径仅作来源记录，不是运行依赖。

固定 NumPy／SciPy 版本不能保证不同操作系统、Python 构建、处理器或数值库具有相同浮点路径。
微小算术差异可能改变线搜索、评估次数及严格 `1e-6` 阈值附近的终止分类；本项目未隔离其具体平台成因。
环境版本匹配、已保存数据完整与新环境重新求解一致，是不同证据。

## 3. 单元测试与只读核验

```bash
python run_tests_audit.py --output audits/local_check/unit_tests.json
python validate_study.py --results results/full_study --output audits/local_check/current_validation.json
```

测试数量以 `unit_tests.json` 中的 **`tests_run`** 为准，同时检查 `passed`、`failures`、`errors`、`skipped` 和同名 `.log`。
测试覆盖梯度、Armijo、预算与失败状态、计数、配对初值、结果保护，以及原始哈希和换行等价判断。
单元测试的临时小型夹具不属于新增正式实验。

`validate_study.py` 不调用求解器，不写入参考结果目录。
默认输出为 `audits/current_validation.json`；显式指定 `audits/local_check/` 可避免覆盖交付的审计证据。
核验器拒绝把输出放入 `results/` 或受保护源码树。新报告的 `schema_version=2`：

| 核验域 | 主要内容 | 通过条件 |
|---|---|---|
| `data_internal_integrity` | 90 条汇总、单次 JSON、轨迹、完整组合、30 组配对起点、12 项梯度检查、`nit`／累计计数、GD 更新及 Armijo、终点诊断和独立标签 | 该域 `passed=true`，无数据错误 |
| `source_integrity` | 元数据已记录的项目源码及安装环境的 SciPy `_optimize.py`，保留原始 SHA-256 比较并核对换行等价证明 | 每个记录符合原始字节或得到严格换行等价证明；缺文件或真实内容差异均失败 |
| `environment_match` | Python 补丁版本、NumPy、SciPy 与历史版本匹配；另记录系统、构建、CPU、线程上下文 | 必需版本匹配；上下文差异单列，不解释为已复现求解路径或计时 |

顶层 `passed` 是三个域全部通过的合取，顶层 `errors` 带域名前缀。
系统／CPU／线程上下文不同不会被当作原始数据损坏，但应审阅 `platform_context`。
只读核验通过不表示完成了新的 90 次求解，也不证明墙钟时间一致。
`results/full_study/analysis/validation.json` 若存在，是保留的旧版记录，不能替代本轮输出。

源码核验首先比较当前原始字节与历史可信 SHA-256，保留 `raw_comparison`。
若不一致，仅尝试由当前字节重建统一 LF 或 CRLF；只有某个重建结果的 SHA-256
**恰好等于历史原始摘要**，才记为 `eol_equivalent`。
这不是忽略所有哈希差异，也不改写预期摘要：BOM、空白、末尾换行和代码内容仍受检查；
原始字节不匹配且包含孤立 CR 时不接受换行回退。SciPy 源码与必需版本错误仍会使相应域失败。

## 4. 保存数据与离线分析

| 路径（相对 `results/full_study/`） | 内容 |
|---|---|
| `summary.csv`、`runs/`、`traces/` | 90 次汇总、单次 JSON 与逐事件 CSV |
| `initial_points.json` | 30 组实际起点，三种方法共享 |
| `gradient_checks.json` | 12 项非驻点中心差分检查 |
| `config_resolved.json`、`metadata.json` | 冻结协议、历史环境、来源及完成状态 |
| `analysis/grouped_results.csv` | 18 组统计，五起点中位数与范围，包含失败样本 |
| `analysis/initial_point_comparison.csv`、`paired_comparisons.csv` | 配对终点及成本比较 |
| `analysis/run_diagnostics.csv` | 全部终点、末步与离线曲率诊断 |
| `analysis/nonstationary_runs.csv`、`analysis/stationary_non_global_runs.csv` | 17 次未达驻点阈值及 47 次驻点达标但未命中全局目标的案例 |
| `analysis/analysis_summary.json` | 完整精度汇总 |
| `analysis/analysis_provenance.json`、绘图目录中的元数据 | 后续分析／图表的源码、输入和显示参数来源 |

正式数据有 **80,605 条事件、80,425 个接受更新**。
图示对数下限只用于显示；曲线在实际终止处截止，不用末值延长，不删除失败轨迹。
离线 Hessian 与其他诊断不计入求解预算。

如需重新生成统计和全量图，先复制到新的工作目录，避免写入交付参考树：

```bash
python -c "import shutil; shutil.copytree('results/full_study', 'work/offline_rebuild')"
python analyze_results.py --results work/offline_rebuild --plot
python make_paper_figures.py --results work/offline_rebuild --output work/offline_rebuild/analysis/paper_figures
```

`copytree` 拒绝覆盖已存在的目标目录；再次执行请另选目录。
这些命令只对保存数据做分析与绘图，不运行求解器。

## 5. 可选：在新目录重新求解

以下是读者可执行的复现步骤，**本轮修订未执行这些正式求解命令**：

```bash
python run_experiments.py --config configs/full_study.json --output results/full_study_repeat01 --threads 1
python validate_study.py --results results/full_study_repeat01 --output audits/local_check/repeated_validation.json
python paper_source/verify_reproduction.py --reference results/full_study --candidate results/full_study_repeat01 --output audits/local_check/reproduction_comparison.json
```

运行器拒绝覆盖非空输出目录；已存在时换新名称。二维试跑可改用 `configs/demo_2d.json`
并选择另一新目录，共两个函数、各一个二维起点、三种方法，六次求解。
严格比较器按 `run_id` 比较已保存的数值结果与轨迹，排除耗时和时间戳。
新环境只有在实际运行并完成比较后，才有相应复现证据；不预设逐位一致。
`--threads 1` 在导入 NumPy 前设置该进程的 BLAS／OpenMP 线程变量，不改系统设置；方法顺序执行。

## 6. 固定协议、日志与成本解释

| 项目 | 固定设置 |
|---|---|
| 函数／维度 | Rosenbrock、Rastrigin；2、10、20 维 |
| 初值 | 每组五点；基础种子 `20261105`；`PCG64 / SeedSequence([seed, objective_index, dimension])` |
| 初值分布 | Rosenbrock 每坐标 `Uniform[-2,2]`；Rastrigin 每坐标 `Uniform[-3,3]`；仅用于生成起点，不约束后续迭代 |
| 停止 | float64；梯度二范数 `<=1e-6`；最多 5000 个接受更新 |
| 独立全局目标标签 | 有限结果且 `abs(f_final-f_star)<=1e-6`；两函数 `f_star=0` |

- **GD：** 自写 Armijo 回溯，`alpha0=1, c1=1e-4, tau=0.5`，最小步长 `1e-12`。
  初次试探后最多缩步 50 次，至多 51 次试探，也可能先达到最小步长。失败步不更新坐标；非有限值和浮点停滞明确记录。
- **CG：** SciPy 1.13.1 非线性 PR+ CG，解析梯度，`norm=2, gtol=1e-6, c1=1e-4, c2=0.4`。
  PR+ 之外还有下一方向的充分下降保障；具体行为以该版本源码为准。
- **BFGS：** SciPy 1.13.1 普通全内存 BFGS，解析梯度、单位初始逆 Hessian，
  `norm=2, gtol=1e-6, c1=1e-4, c2=0.4, xrtol=0`；覆盖库默认的 `c2=0.9`。

Rosenbrock 使用 SciPy `rosen/rosen_der`。Rastrigin 使用数学等价的稳定形式
`sum(x_i**2 + 20*sin(pi*x_i)**2)`，梯度为 `2*x_i + 20*pi*sin(2*pi*x_i)`。
中心差分检查采用 `h_i=1e-6*max(1,abs(x_i))`、分量 `atol=rtol=1e-5`，不进入求解预算。
解析推导和独立检查未提供梯度实现错误的证据；有限检查不能排除所有数值问题。

所有实际求解函数／梯度调用都经过计数器，包括拒绝试探和失败的终止搜索。
SciPy 缓存避免的原始调用不虚增；包装器计数须与库返回的 `nfev/njev` 一致。

| 事件 | 含义 |
|---|---|
| `initial` | `iteration=nfev=njev=0`；图示诊断离线补算，求解器自身初值评估仍正常计数 |
| `accepted` | 一次接受更新，复制坐标与已有累计计数；回调不额外评估函数／梯度 |
| `terminal` | 最终坐标及全部计数，不增加 `nit`；失败试探可能增计数而不改变坐标 |

计时包含求解初始化、试探、更新和统一事件记录，不含导入、离线诊断、绘图及文件写入。
独立保留原始 `solver_success/solver_status/solver_message`、公共 `stationary` 和 `global_hit`。
原 Windows 批次中 `solver_success` 与 `stationary` 恰好均为 73 次，但两者含义不同。
15 次 Rosenbrock-GD 用尽更新预算；两次 Rastrigin 20 维 BFGS 精度损失终止，均未达公共梯度阈值。
小梯度不保证全局最优；命中目标阈值也不是精确最优性的数学证书。

GD／CG 的方向与状态成本为 `O(d)`。标准高效 BFGS 的方向和低秩更新为 `O(d²)`；
**本次 SciPy 1.13.1** 使用通用稠密乘积 `A1 @ H @ A2` 更新，按常规稠密算术为 `O(d³)`，状态和方向仍为 `O(d²)`。
这些成本不含线搜索评估与日志；两模型每次函数／梯度评估为 `O(d)`，保存 K 个 d 维点另需 `O(Kd)` 空间与复制工作。
相同迭代上限不等于相同计算预算，小维度计时也不足以验证渐近阶或给出普遍最快方法排名。

## 7. 官方样式报告的重建与打包

数值实验不需要文档依赖。重建报告需安装：

```bash
python -m pip install -r requirements-report.txt
```

另安装 XeLaTeX（TeX Live／MiKTeX）或 Tectonic，并使引擎命令可用；引擎程序不随包分发，首次编译可能下载宏包。
`paper_source/template/neurips_2025.sty` 保持官方原样，主文档覆盖课程说明。
PDF 使用 US Letter、5.5 × 9 英寸正文区、10 pt／11 pt 正文；验收以实际编译结果为准。

正文修改入口为 `paper_source/create_content.py`，生成 `content.json`；公式源为 `equations.json`。
生成正文时，脚本要求已有的 `audits/revision_20261105/unit_tests.json` 为通过记录，
且其中 `test_sources` 哈希与当前测试一致，再读取实际测试数量；缺失或过期记录会停止生成。
第 3 节本地检查另写 `audits/local_check/`，不会悄悄替换交付审计。

以 Tectonic 为例，从项目根目录执行：

```bash
python paper_source/create_content.py
python paper_source/generate_latex.py
python -c "from pathlib import Path; Path('submission/_latex').mkdir(parents=True, exist_ok=True)"
tectonic --keep-logs --outdir submission/_latex paper_source/template/report.tex
python paper_source/package_reproducibility.py --dry-run
python paper_source/package_reproducibility.py --verification-output submission/packaging_verification.json
python paper_source/package_reproducibility.py --verify-only --verification-output submission/packaging_verification.json
python paper_source/build_final_report.py --latex-pdf submission/_latex/report.pdf --packaging-report submission/packaging_verification.json
```

LaTeX 生成器核对保存数据来源；最终构建器核对编译 PDF 的源码指纹、页数、大小、归档全部成员与当前项目的字节一致性，以及附件字节。
先完成正文、README 和预打包审计，再打包，再嵌入代码 ZIP 与本次打包记录，避免自包含依赖。
打包工具保留入包文件原始字节，并按历史原始摘要逐字节核对七份原求解源码。
若只读核验认定为换行等价、但打包要求的原始字节不符，应保留差异并恢复可信原始字节，不能改写预期哈希。
本次包的核验记录不进入代码包自身。
2026-11-05 的修订审计包保留原样；2026-11-06 的实际文件检查另见 `submission/polish_file_checks.json`。

仅检查版面时使用独立预览目录：

```bash
python paper_source/build_final_report.py --no-attachment --latex-pdf submission/_latex/report.pdf
```

预览写入 `submission/_preview/`，不会覆盖正式交付。最终 PDF 的嵌入附件计入 20 MB 限制。
上述分析、核验、文档构建和打包步骤均不重新运行求解器。

## 8. 主要入口

| 路径 | 职责 |
|---|---|
| `cpu_optimization/objectives.py`、`cpu_optimization/solvers.py`、`cpu_optimization/experiment.py` | 目标与梯度、算法／计数、配对初值与原始输出 |
| `cpu_optimization/analysis.py` 及绘图模块 | 保存数据的统计、终止诊断和图表 |
| `run_experiments.py` | 新目录求解入口 |
| `run_tests_audit.py`、`tests/` | 单元测试及持久审计 |
| `validate_study.py`、`provenance_integrity.py` | 三域只读核验与严格源码／换行证明 |
| `analyze_results.py`、`plot_results.py`、`make_paper_figures.py` | 离线分析与绘图 |
| `configs/`、`requirements*.txt` | 固定协议与依赖 |
| `results/full_study/`、`audits/`、`paper_source/` | 原始结果、分范围证据、报告源 |

理论与近期研究见英文报告。实现依据包括 SciPy 1.13.1 的
[CG 文档](https://docs.scipy.org/doc/scipy-1.13.1/reference/optimize.minimize-cg.html)、
[BFGS 文档](https://docs.scipy.org/doc/scipy-1.13.1/reference/optimize.minimize-bfgs.html)及
[对应源码](https://github.com/scipy/scipy/blob/v1.13.1/scipy/optimize/_optimize.py)。
