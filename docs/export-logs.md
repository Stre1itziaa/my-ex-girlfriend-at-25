# 喂她你自己的聊天记录（真数据路径）

> ⚠️ **先读数据红线**：解密后的聊天库是**极敏感个人数据**——只存本机、绝不提交进任何仓库
> （`wechat_data/` 已在 .gitignore）、用完可删。继续即表示你已读并同意 [ethics.md](ethics.md)：
> 只处理**你自己的**对话，或**获得明确知情同意**的人的对话。

## 原理

本项目管线的输入是一个**已解密**的微信 SQLite 库；本项目**不提供、不分发任何解密工具**。
请自行使用社区开源方案（如 PyWxDump 一类）完成解密，并自行评估其合规与风险——
解密通常依赖特定微信版本与登录密钥，属于你对自己设备的操作。

## 第 1 步：拿到解密库

用社区工具解密后，你会得到一个或多个 `.db` 文件。记住它的**完整文件名**（如 `MSG0.db`）。

## 第 2 步：安装导出依赖 + 填配置

```bash
pip install -e .[wechat]        # zstandard: 微信 WCDB 压缩消息需要
```

新建 `config/target.yaml`（此文件在 .gitignore 里，不会入库）：

```yaml
target:
  wxid: <填对方的wxid>          # 对方的微信 wxid（在解密库 Name2Id 表里能查到）
  name: 备注名                   # 仅用于文档展示（编年史标题等），可填代称
  source_db: MSG0.db            # 解密库文件名
```

然后把解密库放到：

```
wechat_data/decrypted/MSG0.db
```

## 第 3 步：导出 → 建库

```bash
python -m my_ex_girlfriend_at_25.pipeline.s1_export   # 解密库 → data/corpus/raw.jsonl（只写不改的真相源）
my-ex-girlfriend-at-25 build                          # s2清洗 → … → s8b 打标，全管线
```

**✅ 验证**：s1 末行输出消息数/时间跨度/类型分布；`my-ex-girlfriend-at-25 doctor` 检索索引 ✓。

## 第 4 步：告诉 TA 记忆的边界（推荐）

如果语料截止在过去某天，在 `config/persona.yaml` 里加一行，让她知道之后的记忆是空白：

```yaml
memory_cutoff: 2026-09-30   # 你语料的截止日期
```

然后 `my-ex-girlfriend-at-25 run`。此后新产生的对话会在每夜固化循环里变成长期记忆（需本地模型在跑）。

## 输入契约（给高级用户/agent）

s1 导出器对解密库的假定（微信 v4 库结构）：

- 会话表：`Msg_ + md5(wxid)`；联系人表 `Name2Id`（rowid ↔ user_name）
- 消息列：`local_id, local_type, real_sender_id, create_time, message_content, WCDB_CT_message_content`
- `WCDB_CT_message_content != 0` 时内容为 zstd 压缩字节（自动解压）
- `local_type & 0xFFFFFFFF` 为基础类型码（1 文字 / 3 图 / 34 语音 / 47 表情 / …）
- schema 变了？改 [../my_ex_girlfriend_at_25/pipeline/s1_export.py](../my_ex_girlfriend_at_25/pipeline/s1_export.py) 即可——真相源格式见其 docstring

## 再次提醒

- 解密库与 `data/corpus/` 导出件**一个字节都不要提交**（CI 的 `tools/scan_secrets.py --history` 会拦）
- 处理他人对话务必持有其明确同意；纪念逝者场景请符合其生前意愿与当地法律
