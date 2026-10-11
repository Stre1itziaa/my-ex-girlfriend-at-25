# 微信通道绑定（腾讯官方 iLink Bot API）

> **⚠️ 通道组件尚未随库发布（规划中）**：本文档是设计说明与前瞻教程，`channels/wechat/` 的桥接代码
> 会在后续版本随库发布。当前版本请使用本地 WebUI（`xinli run`）。
>
> 本项目**只支持官方合规通道**。协议号/hook 类方案有封号风险，且违反微信条款——不在本项目范围内。

## 原理

腾讯 [openclaw-weixin](https://github.com/Tencent/openclaw-weixin) 提供官方 Bot API（iLink）：
机器人以独立身份存在（显示为"微信ClawBot"），只能与**扫码绑定的主人**私聊，架构上不可能打扰第三方。
本仓库的桥接（`channels/wechat/`，随通道组件发布）将是该协议的独立实现：Node 守护进程 + 文件队列（inbox/outbox）。

## 绑定步骤

1. `xinli init` 已创建 `channels/wechat/` 目录
2. 启动桥接守护进程：
   ```bash
   cd channels/wechat && node bridge.mjs run
   ```
   （首次会生成二维码 `login/qr.png`，用你的微信扫码并确认绑定）
3. 绑定成功后凭据写入 `channels/wechat/state.json`（**勿外传，已在 .gitignore**）
4. 重启 `xinli run` —— 之后她主动发消息会双投递：本地 WebUI + 你的微信

## 约束（实测）

- 机器人**不能凭空开对话**：先由你给它发一句任意消息打开窗口，窗口内它的主动消息才能直达微信
- 窗口过期后退化为"只回不发"+本地 WebUI 兜底；重新发一句即可再开
- 你发的表情包/图片会以文件形式到达 `media-in/`，大脑当前只处理文本

## 已知限制

- iLink 协议的消息类型只有 文本/图片/语音/文件/视频——**没有表情(emoji)类型**，
  动图表情到微信会被降级为静态图（协议限制，见上游 docs/protocol.md）
