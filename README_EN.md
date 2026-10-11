# xinli (心侣)

**Turn a real chat history into a local AI companion who texts first, remembers your story, and talks like the person.**

Zero finetuning · retrieval-native persona · inner life · local-first inference.

> **⚠️ Ethics charter first**: only recreate **yourself** or someone who gave explicit informed consent.
> Recreating others without consent, impersonation, or harassment violates the charter ([docs/ethics.md](docs/ethics.md)).

## Quick start (5 min, zero data — synthetic demo persona included)

```bash
pip install -e .[vision]
xinli init
xinli fetch-model <repo> <file> --sha256 <hex> --size <bytes>
xinli serve-llm          # hardware-aware launch (CUDA/Vulkan, VRAM tiers)
xinli build --demo       # synthetic demo corpus → profile/index/rhythm
xinli run                # http://127.0.0.1:8787
```

Use your own logs: export your decrypted WeChat DB, then `xinli build` (see docs/wechat-bind.md, 中文).

## Highlights

- **Retrieval-native persona**: every reply is grounded in retrieved real conversations (BM25 char-bigrams + vector RRF) — no finetuning, cold start in a day
- **Ground-truth discipline**: user-curated life facts override mined memory; real-time self-reports are always trusted; anti-hallucination rules built into prompts
- **Inner life**: schedule engine + mood appraisal + proactive texting with four suppressors (an adult-oriented desire/intimate module exists but is **off by default**; enable explicitly in `settings.yaml`)
- **Nightly consolidation**: new chats → fact cards with ADD/UPDATE/DELETE and supersede audit chain — local model only, nothing leaves the machine
- **Sticker semantics**: mined per-sticker usage context from logs; vision-calibrated; context-matched selection
- **WeChat**: official Tencent iLink Bot API (compliant; no protocol hacks) — **bridge component not yet published in this repo (planned)**; design notes in docs/wechat-bind.md (中文)

## Hardware

| VRAM | Recommendation | Status |
|---|---|---|
| ≥24G | larger models Q5/Q6, full GPU | community-verified pending |
| 12-24G | Gemma4-26B-A4B-class MoE Q4, experts in RAM | ✅ tested (16G+32G RAM): ~5s/turn warm |
| <12G | 9B-class or IQ quants | community-verified pending |

License: Apache-2.0 — third-party components and licenses listed in [NOTICE](NOTICE). Content notice: contains an optional adult-oriented module (off by default), for adults only.
中文文档: [README.md](README.md) · [docs/](docs/)
