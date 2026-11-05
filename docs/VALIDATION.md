# Release-2.1环境设施与脚手架检查记录 · 2026-11-05

本次检查对象是“引导成员自行研究、编码和评估”的任务工作本。没有运行研究实验，没有验证尚未实现的算法，没有生成数据、统计结论或图表。

## 已检查
- notebook共有29个单元，13个代码单元；格式、Python语法、稳定cell ID、共享/M1–M5/收尾分区正确。
- M1有4个、M2有5个、M3有5个、M4有6个、M5有3个待实现函数/方法，共23个。所有成员研究接口只有说明和NotImplementedError，无隐藏实现、参考本导入或自动执行调用。
- 在真实Jupyter内核从docs子目录顺序加载全部单元成功：第0节正确定位仓库，检查环境，创建三个模式分区和本次run的六个子目录，打印路径和版本表。仅写入outputs/development/local_setup/config/environment.json；没有研究数据、统计或图。源notebook仍无输出、无执行计数。
- scripts/test_setup.py的8项测试通过：重复初始化保持文件、JSON/CSV拒绝覆盖与非法JSON、路径边界、formal目录防复用、环境变化要求新run、仓库外显式根路径、缺依赖时调用当前Python安装并提示重启、只检查模式不安装。测试全部在临时仓库运行；依赖安装分支使用模拟调用，没有在测试中实际下载或更换包。
- README、任务说明、输入输出契约、成员记录与进度板同步；中文模板已修复，内部链接可解析。
- 上一版一键运行脚本、面向完整实现的测试和旧demo产物已移除。保留清输出、结构检查和环境/路径测试脚本；研究实现仍待成员完成。
- 正式登记仍为空，没有伪造成员签名或已完成状态。

当前代码SHA256：cf578b2b16dd45d9ce210cd3121ce5114b55b8b488dffb059282e2ef8c5c0f7a。

## 可重复的结构检查
    python scripts/validate_release.py
    python scripts/validate_release.py --expect-scaffold
    python scripts/test_setup.py

第二条用于验证成员研究模块仍只留接口，允许第0节已实现公共设施；成员开始实现后无需继续满足该选项。第三条只测试环境与路径代码。普通检查报告剩余占位函数，不把“没有占位符”视作正确性证据。

## 修改前版本保留
reference/ARIN7101_Context_Bandit_Release_v1_Complete_Reference.ipynb保留修改前45个单元的完整release内容；从修改前保存的notebook快照恢复并核对源代码哈希，与原run的manifest一致。
- 修改前代码SHA256：4d45227ef5862159a6d2a6ea5cc88ddccf25dc325b5d1bfaac9a3e74eb5dcd77。
- 保留文件SHA256：11dd498f4ed939c081e0bef9ab80d9353b5755ec6ed2c66fccdd37acdea64df1。
- 原始completed notebook的哈希也保持不变，详见reference/README。

## 不在本次检查范围
数据生成、策略、后验更新、回放、统计、归档校验和制图尚未实现，必须由成员自行研究、编码、设计测试并交叉复核。旧版全流程demo通过不适用于当前脚手架；不得据此宣称当前项目代码、实验或个人任务已完成。未测试浏览器界面或完成最终汇报。
