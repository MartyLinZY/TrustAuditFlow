# TrustFlowAudit IEEE Paper

本目录用于撰写“面向数据流通的 BLoP 轻量化升级：可信委员会驱动的区块链分布式数据校验方法”小论文草稿。

## 文件结构

- `main.tex`：IEEE 双栏主文件。
- `references.bib`：参考文献条目，后续需要继续核对卷期页码。
- `sections/`：分章节正文。
- `build/`：编译输出目录。

## 当前写作范围

已完成：

- 摘要与关键词
- 引言
- 相关工作
- 问题定义与设计目标
- 系统模型
- TrustFlowAudit 方法
- 安全性与开销讨论
- 局限与未来工作
- 结论

暂未撰写：

- 实验部分正文
- 实验结果表格
- 消融实验
- 与 baseline 的定量对比

## 编译

优先使用 XeLaTeX：

```bash
cd paper/TrustFlowAudit_IEEE_Paper
latexmk -xelatex -bibtex -interaction=nonstopmode -output-directory=build main.tex
```

如果本机没有 `latexmk`，可使用 Codex LaTeX 编译工具或手动执行：

```bash
xelatex -output-directory=build main.tex
bibtex build/main
xelatex -output-directory=build main.tex
xelatex -output-directory=build main.tex
```
