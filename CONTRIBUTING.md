# 贡献指南

## 开发环境

```bash
pip install -e .[vision,wechat,dev]
```

## 改动后的验证门（全部通过再提 PR）

```bash
ruff check xinli tools tests channels --select E9,F63,F7,F82   # 致命错误级
python -m pytest tests/ -q                                     # 单测
python tools/scan_secrets.py --root . --tracked                # 脱敏扫描（CI 同款）
python tools/scan_secrets.py --root . --history                # 全 git 历史体检
```

CI（.github/workflows/ci.yml）跑同一组命令，push 前本地先过一遍。

## 红线

1. **任何真实个人数据不得入库**——语料、解密库、化名、地点、账号、聊天截图一律不行
   （详见 [docs/ethics.md](docs/ethics.md) 与 [AGENTS.md](AGENTS.md)）。
2. 成人模块保持**默认关闭**，改动不得改变默认值。
3. 文档声明必须与代码行为一致（默认值、平台支持、出网行为）。

## 提交约定

- 提交信息用一句话说清行为变化，风格参考 `git log`（`vX.Y.Z:` / `docs:` / `security:` 前缀）。
- 新功能请附验证方式（测试或手测步骤）。
- 行为级改动先开 issue 讨论再动手。
