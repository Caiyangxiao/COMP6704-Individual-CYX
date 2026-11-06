# 历史核验记录（2026-11-05）

这里保存已存在记录的原字节副本，不代表本轮重新执行了90次求解。

- windows_exact_reproduction_20261105.json：历史 Windows 环境90次逐运行、逐轨迹精确比较记录；原来源为 submission/reproduction_verification.json。
- packaging_before_revision_20261105.json：修订前 ZIP（SHA-256：813dbbca5315ea8c692bf318b3b45b5c9c7383c4f3912b1ae9544c7c4573ee2e）的打包记录。它不是数值重跑记录，也不是新 ZIP 的打包记录。
- capture_provenance_20261105.json：来源路径、SHA-256、适用范围及保留条件。

历史复现候选的临时路径当前不存在，不能对其不可用的原始候选文件再次核查。已核对历史存档与修订前存档：186份原始实验文件、7份原求解源码及历史5份测试源码保持原字节一致。历史28项测试记录不覆盖当前新增的两份测试文件。参考结果为S=73、G=26，含80,605个轨迹事件。

定向查找未找到可核验的 Linux S=72/G=26 运行文件，故不声称该结果或跨平台逐位一致。历史日志的[72/90]是进度计数。

新的 submission/packaging_verification.json 应保留在它核验的代码 ZIP 之外，并可作为 PDF 独立附件；本目录的旧打包记录仅用于历史来源说明。
