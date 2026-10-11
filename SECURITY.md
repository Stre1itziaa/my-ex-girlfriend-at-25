# Security Policy / 安全策略

## 报告漏洞

本项目的威胁模型特殊：它处理**极私密的数据**（你的聊天记录、情感记忆）。发现以下问题请**私下报告**（不要开公开 issue）：

- 真人数据/凭据泄漏路径（扫描器绕过、意外入库）
- 本地服务未授权访问（WebUI/llama-server 被远程利用）
- 提示注入导致的记忆污染或行为劫持

联系方式：请使用 GitHub 的**私有漏洞报告**（仓库页 → Security → Report a vulnerability），
该通道仅维护者可见，不会暴露你的身份。请勿开公开 issue 描述漏洞细节。

## 已知设计边界（非漏洞但须知）

- WebUI 与 llama-server 默认只绑 127.0.0.1、无鉴权——**不要**手动改成 0.0.0.0 暴露到局域网；也不要把仓库目录通过 GitHub 网页拖拽上传（网页上传不走 .gitignore，会把 memory/data/state 运行时数据一并带上去）
- journal/facts 是明文 JSONL——磁盘加密（BitLocker 等）由用户自行决定
- LLM 后端默认 local（不出网）；手动切到 glm 云后端即意味着对话内容出域
