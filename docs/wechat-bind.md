# 微信通道绑定（腾讯官方 iLink Bot API）

> 本项目**只支持官方合规通道**。协议号/hook 类方案有封号风险，且违反微信条款——不在本项目范围内。

## 原理

桥接组件 [`channels/agent2wechat/`](../channels/agent2wechat/) 通过腾讯官方 iLink Bot API（ClawBot 通道）把"她"接到你的微信私聊：
机器人以独立身份存在（显示为"微信ClawBot"），只能与**扫码绑定的主人**私聊，架构上不可能打扰第三方。
桥接是独立实现（Node 守护进程 + 文件队列），框架无关，完整说明见其 [README](../channels/agent2wechat/README.md)。

Python 侧适配器 `channels/bridge_io.py` 由 `xinli run` 自动加载：轮询 inbox、**连发聚合**（追等两轮把快速连发聚齐再回）、图片送本地视觉模型、表情包标记转真实附件。

## 绑定步骤

1. 启动桥接守护进程（Node 18+，无第三方 npm 依赖）：
   ```bash
   cd channels/agent2wechat && node bridge.mjs run
   ```
2. 扫码绑定（另开终端；二维码过期自动刷新，最多 3 张）：
   ```bash
   node bridge.mjs login
   ```
   （二维码信息在 `login/qr.json`，如需验证码写入 `login/verify.txt`；绑定成功后凭据写入 `state.json`，**勿外传，已在 .gitignore**）
3. 重启 `xinli run` —— 之后她主动发消息会双投递：本地 WebUI + 你的微信；你从微信发来的文字/图片也会进入她的对话。

## PAUSED 冷却闸

在 `channels/agent2wechat/` 下创建 `PAUSED` 空文件即可冻结微信收发：消息只留在 inbox 不回复，删除该文件后统一处理。适合不想让她打扰你的时段。

## 约束（实测）

- 机器人**不能凭空开对话**：先由你给它发一句任意消息打开窗口，窗口内它的主动消息才能直达微信
- 窗口过期后退化为"只回不发"+本地 WebUI 兜底；重新发一句即可再开
- 你发的表情包/图片会以文件形式到达 `media-in/`，大脑当前只处理文本和图片

## 已知限制

- iLink 协议的消息类型只有 文本/图片/语音/文件/视频——**没有表情(emoji)类型**，
  动图表情到微信会被降级为静态图（协议限制，细节见腾讯官方仓库 openclaw-weixin 的 `docs/protocol.md`）
