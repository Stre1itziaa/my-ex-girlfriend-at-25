# -*- coding: utf-8 -*-
"""配置加载: settings.yaml(系统) + persona.yaml(人格) 的唯一入口。

约定:
  - 所有模块经此读取配置, 代码里零字面量 (硬编码=CI 扫描会拦的债务)
  - example 文件入库, 实际文件 (settings.yaml/persona.yaml) 在 .gitignore
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    raw: dict = field(default_factory=dict)

    # --- llm ---
    @property
    def backend(self) -> str:
        return self.raw.get("llm", {}).get("backend", "local")

    @property
    def local_base(self) -> str:
        return self.raw.get("llm", {}).get("local", {}).get("base", "http://127.0.0.1:8081/v1")

    @property
    def local_model(self) -> str:
        return self.raw.get("llm", {}).get("local", {}).get("model", "")

    # --- ui ---
    @property
    def ui_host(self) -> str:
        return self.raw.get("ui", {}).get("host", "127.0.0.1")

    @property
    def ui_port(self) -> int:
        return self.raw.get("ui", {}).get("port", 8787)

    # --- 通用 ---
    def section(self, key: str) -> dict:
        return self.raw.get(key, {})

    def __getitem__(self, key):
        return self.raw[key]


@dataclass
class Persona:
    raw: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.raw.get("name", "她")

    @property
    def life(self) -> dict:
        return self.raw.get("life", {})

    @property
    def style(self) -> dict:
        return self.raw.get("style", {})

    def location_templates(self) -> dict:
        return self.raw.get("location_templates",
                            {"workday": ["公司上班"], "weekend": ["家里"]})

    def __getitem__(self, key):
        return self.raw[key]


def _load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"{path.name} 不存在 —— 请先 `cp {path.parent.name}/{path.stem}.example.yaml {path.name}` 并按注释填写")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_settings(base: Path = None) -> Settings:
    b = Path(base) if base else (Path(os.environ.get("MY_EX_GIRLFRIEND_AT_25_BASE", BASE)))
    return Settings(_load(b / "config" / "settings.yaml"))


def load_persona(base: Path = None) -> Persona:
    b = Path(base) if base else (Path(os.environ.get("MY_EX_GIRLFRIEND_AT_25_BASE", BASE)))
    return Persona(_load(b / "config" / "persona.yaml"))
