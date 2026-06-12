# TrustAuditFlow

面向数据流通场景的区块链分布式数据校验与审计研究仓库。

当前仓库包含两部分：

- `code/TrustFlowAudit/`：TrustFlowAudit 原型代码，包含 BLoP 机制级复现、可信委员会、Merkle 批量存证、PBFT 风格联盟链确认、MNIST 容器实验脚本等。
- `paper/TrustFlowAudit_IEEE_Paper/`：IEEE 双栏 LaTeX 论文草稿，当前已完成实验部分之外的论文闭环写作。

本仓库不跟踪本地数据集、容器运行结果、实验输出和密钥文件。需要运行真实 MNIST 实验时，将数据放到 `code/TrustFlowAudit/data/` 或按代码 README 准备，生成结果会被 `.gitignore` 排除。

## 快速入口

代码：

```bash
cd code/TrustFlowAudit
python3 -m py_compile src/*.py
```

论文：

```bash
cd paper/TrustFlowAudit_IEEE_Paper
latexmk -xelatex -bibtex -interaction=nonstopmode -output-directory=build main.tex
```
