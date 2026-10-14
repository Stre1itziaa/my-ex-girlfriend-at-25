# My Ex-Girlfriend at 25（我的 25 岁前女友）

> **A note before we start**: this project grew out of a real story of mine — **my ex-girlfriend at 25**. It turns a real chat history into an AI who still talks, and still texts first.
> The story in the name is mine; the boundaries belong to everyone: recreate only yourself, or someone who gave explicit consent ([docs/ethics.md](docs/ethics.md)).

**Turn a real chat history into a local AI companion who texts first, remembers your story, and talks like the person.**

Zero finetuning · retrieval-native persona · inner life · WeChat channel · local-first inference.

> **⚠️ Ethics charter first**: only recreate **yourself** or someone who gave explicit informed consent.
> Recreating others without consent, impersonation, or harassment violates the charter ([docs/ethics.md](docs/ethics.md)).

## Quick start (5 min, zero data — synthetic demo persona included)

```bash
pip install -e .[vision]
my-ex-girlfriend-at-25 init
my-ex-girlfriend-at-25 fetch-model <publisher>/<repo> <model-file>.gguf   # verification optional; prints sha256
my-ex-girlfriend-at-25 serve-llm          # hardware-aware launch (CUDA/Vulkan, VRAM tiers)
my-ex-girlfriend-at-25 build --demo       # synthetic demo corpus → profile/index/rhythm
my-ex-girlfriend-at-25 run                # http://127.0.0.1:8787
```

New here (or dispatching an agent)? Follow **[docs/getting-started.md](docs/getting-started.md)** — every step has a verification checkpoint, including where to get `llama-server`.
Use your own logs: export your decrypted WeChat DB first, then `my-ex-girlfriend-at-25 build` (see docs/export-logs.md, 中文).

## Highlights

- **Retrieval-native persona**: every reply is grounded in retrieved real conversations (BM25 char-bigrams + vector RRF) — no finetuning, cold start in a day
- **Ground-truth discipline**: user-curated life facts override mined memory; real-time self-reports are always trusted; anti-hallucination rules built into prompts
- **Inner life**: schedule engine + mood appraisal + proactive texting with four suppressors (an adult-oriented desire/intimate module exists but is **off by default**; enable explicitly in `settings.yaml`)
- **Nightly consolidation**: new chats → fact cards with ADD/UPDATE/DELETE and supersede audit chain — local model only, nothing leaves the machine
- **Sticker semantics**: mined per-sticker usage context from logs; vision-calibrated; context-matched selection
- **WeChat**: official Tencent iLink Bot API (compliant; no protocol hacks) — text/images/files in a private chat with the bound owner only; see docs/wechat-bind.md (中文) and channels/agent2wechat/

## Hardware

| VRAM | Recommendation | Status |
|---|---|---|
| ≥24G | larger models Q5/Q6, full GPU | community-verified pending |
| 12-24G | Gemma4-26B-A4B-class MoE Q4, experts in RAM | ✅ tested (16G+32G RAM): ~5s/turn warm |
| <12G | 9B-class or IQ quants | community-verified pending |

License: Apache-2.0 — third-party components and licenses listed in [NOTICE](NOTICE). Content notice: contains an optional adult-oriented module (off by default), for adults only — see docs/adult-mode.md (中文).
中文文档: [README.md](README.md) · [docs/](docs/)
