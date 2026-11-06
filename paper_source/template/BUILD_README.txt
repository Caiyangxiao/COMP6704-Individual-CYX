COMP6704 论文模板与已填充 LaTeX 稿

1. 官方来源
https://media.neurips.cc/Conferences/NeurIPS2025/Styles.zip
neurips_2025.sty、neurips_2025.tex、neurips_2025.pdf 和官方 ZIP 保留原始字节。
模板版本 2025/05/01。来源与 SHA-256 见 template_provenance.json。

2. 课程适配
report.tex 是本作业的完整英文论文，使用官方样式及 preprint/nonatbib 选项。
仅在主文档覆盖首页会议信息为课程说明；作者实名、学号、10页以内和20MB以下按课程要求处理。
不表示本作业已向 NeurIPS 投稿或被录用。Word 是同内容的可编辑课程适配稿，官方不提供 Word 模板。

3. 直接编译现有论文
安装 Tectonic 或含 XeLaTeX 的 TeX Live/MiKTeX。首次使用可能下载字体与宏包。
从本目录执行：
  tectonic --keep-logs report.tex
或连续执行两遍：
  xelatex -interaction=nonstopmode -halt-on-error report.tex
原生公式和参考文献均包含在 report.tex 中。两张图通过 ../assets/ 读取，解压时保留目录结构。
该流程只需要模板包，不需要 Python 或90次实验原始数据，输出 report.pdf 尚未添加复现ZIP附件。

4. 从结构化正文生成并构建正式附件版 PDF
使用完整 COMP6704_reproducibility.zip；根 README 说明生成、编译、打包与附件嵌入顺序。
generate_latex.py 以 content.json、equations.json、图像和未改官方样式生成 report.tex。
build_final_report.py --latex-pdf 会核查编译PDF的来源指纹，避免使用旧正文或旧图。
若编辑了结构化正文，须重新生成 LaTeX、编译、打包，再构建正式PDF。
若直接编辑 report.tex，请自行审阅与Word/结构化正文的一致性；再次运行生成器会覆盖直接编辑。

5. 验收
正式报告不超过10页，含参考文献；PDF小于20MB，嵌入附件计入大小。
独立模板ZIP不含实验数据；完整代码ZIP包含数据、日志、审计脚本、README与模板。
