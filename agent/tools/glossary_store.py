"""GlossaryStore — 术语表持久化存储

按领域分类组织术语表，存储为 JSON 文件（Translation/glossaries/{domain}.json）。
支持加载、保存、备份、合并、查询和更新操作。

存储格式:
{
  "domain": "nlp",
  "entries": [
    {"english": "Transformer", "chinese": "Transformer", "keep_english": true, ...},
    ...
  ],
  "updated_at": "2024-01-01T00:00:00"
}

Requirements: 3.4, 7.3, 7.5
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

import aiofiles

from agent.models import GlossaryEntry

logger = logging.getLogger(__name__)

# glossary_store.py 位于 test/agent/tools/
# parents: [0]=tools [1]=agent [2]=test
PROJECT_ROOT = Path(__file__).resolve().parents[2]
GLOSSARY_DIR = PROJECT_ROOT / "Translation" / "glossaries"


class GlossaryStore:
    """术语表持久化存储

    管理 Translation/glossaries/ 目录下按领域命名的 JSON 术语表文件。
    提供 CRUD 操作和备份机制。

    Attributes:
        glossary_dir: 术语表存储目录，默认为 Translation/glossaries/
    """

    _lock = asyncio.Lock()

    def __init__(self, glossary_dir: Path | None = None) -> None:
        """初始化 GlossaryStore

        Args:
            glossary_dir: 自定义术语表存储目录（主要用于测试）。
                         默认使用 Translation/glossaries/。
        """
        self.glossary_dir = glossary_dir or GLOSSARY_DIR

    def _domain_path(self, domain: str) -> Path:
        """获取指定领域的术语表文件路径"""
        return self.glossary_dir / f"{domain}.json"

    async def load(self, domain: str) -> list[GlossaryEntry]:
        """加载指定领域的术语表

        Args:
            domain: 领域名称（如 "nlp"、"cv"）

        Returns:
            术语条目列表。如果文件不存在或解析失败，返回空列表。
        """
        path = self._domain_path(domain)
        if not path.exists():
            logger.debug(f"术语表文件不存在: {path}")
            return []

        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
            data = json.loads(content)
            entries = [
                GlossaryEntry.from_dict(item)
                for item in data.get("entries", [])
            ]
            logger.info(f"📖 已加载术语表 [{domain}]: {len(entries)} 条")
            return entries
        except (json.JSONDecodeError, IOError, KeyError) as exc:
            logger.warning(f"加载术语表失败 [{domain}]: {exc}")
            return []

    async def save(self, domain: str, entries: list[GlossaryEntry]) -> None:
        """保存术语表到文件

        将术语条目列表序列化为 JSON 并写入
        Translation/glossaries/{domain}.json。

        Args:
            domain: 领域名称
            entries: 术语条目列表
        """
        async with self._lock:
            self.glossary_dir.mkdir(parents=True, exist_ok=True)
            path = self._domain_path(domain)

            data = {
                "domain": domain,
                "entries": [entry.to_dict() for entry in entries],
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }

            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))

            logger.info(f"💾 已保存术语表 [{domain}]: {len(entries)} 条")

    async def backup(self, domain: str) -> Path | None:
        """创建术语表备份

        将当前术语表文件复制为 {domain}.{timestamp}.bak.json。
        如果原文件不存在则跳过。

        Args:
            domain: 领域名称

        Returns:
            备份文件路径，如果原文件不存在则返回 None。
        """
        path = self._domain_path(domain)
        if not path.exists():
            logger.debug(f"无需备份，术语表文件不存在: {path}")
            return None

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_name = f"{domain}.{timestamp}.bak.json"
        backup_path = self.glossary_dir / backup_name

        shutil.copy2(str(path), str(backup_path))
        logger.info(f"📋 已创建术语表备份: {backup_name}")
        return backup_path

    async def merge(
        self, domain: str, new_entries: list[GlossaryEntry]
    ) -> list[dict]:
        """合并新术语到已有术语表

        合并规则：
        - 已有术语的翻译保持不变（优先使用已有翻译）
        - 新术语被添加到术语表中
        - 同一英文术语有不同中文翻译时，记录为冲突

        Args:
            domain: 领域名称
            new_entries: 新提取的术语条目列表

        Returns:
            冲突列表，每个冲突为 dict:
            {"english": str, "existing": str, "incoming": str}
        """
        existing = await self.load(domain)

        # 构建已有术语的索引（英文小写 -> GlossaryEntry）
        existing_map: dict[str, GlossaryEntry] = {
            entry.english.lower(): entry for entry in existing
        }

        conflicts: list[dict] = []

        for new_entry in new_entries:
            key = new_entry.english.lower()
            if key in existing_map:
                old = existing_map[key]
                # 检测冲突：同一英文术语的不同中文翻译
                if old.chinese != new_entry.chinese:
                    conflicts.append(
                        {
                            "english": new_entry.english,
                            "existing": old.chinese,
                            "incoming": new_entry.chinese,
                        }
                    )
                # 已有术语保持不变（不覆盖）
            else:
                # 新术语：添加到术语表
                new_entry.domain = domain
                new_entry.updated_at = datetime.now().isoformat(timespec="seconds")
                existing_map[key] = new_entry

        # 备份并保存合并后的术语表
        await self.backup(domain)
        merged = list(existing_map.values())
        await self.save(domain, merged)

        if conflicts:
            logger.warning(
                f"⚠️ 术语合并冲突 [{domain}]: {len(conflicts)} 个"
            )
        logger.info(
            f"🔀 术语合并完成 [{domain}]: 合并后 {len(merged)} 条"
        )
        return conflicts

    async def query(
        self, term: str, domain: str = ""
    ) -> list[GlossaryEntry]:
        """查询术语（支持模糊匹配）

        在指定领域（或所有领域）中搜索包含查询词的术语。
        匹配规则：英文或中文字段包含查询词（大小写不敏感）。

        Args:
            term: 查询词
            domain: 限定搜索的领域。空字符串表示搜索所有领域。

        Returns:
            匹配的术语条目列表
        """
        term_lower = term.lower()
        results: list[GlossaryEntry] = []

        if domain:
            domains = [domain]
        else:
            # 搜索所有领域
            domains = self._list_domains()

        for d in domains:
            entries = await self.load(d)
            for entry in entries:
                if (
                    term_lower in entry.english.lower()
                    or term_lower in entry.chinese.lower()
                ):
                    results.append(entry)

        logger.debug(
            f"🔍 术语查询 '{term}' (domain={domain or 'all'}): "
            f"找到 {len(results)} 条"
        )
        return results

    async def update_entry(
        self,
        domain: str,
        english: str,
        chinese: str,
        source: str = "user_edit",
    ) -> None:
        """更新或新增单个术语条目

        如果术语已存在则更新其中文翻译和来源；
        如果不存在则新增条目。更新前会创建备份。

        Args:
            domain: 领域名称
            english: 英文术语
            chinese: 中文翻译
            source: 来源标识（默认 "user_edit"）
        """
        entries = await self.load(domain)

        # 查找已有条目
        found = False
        for entry in entries:
            if entry.english.lower() == english.lower():
                entry.chinese = chinese
                entry.source = source
                entry.updated_at = datetime.now().isoformat(timespec="seconds")
                found = True
                break

        if not found:
            entries.append(
                GlossaryEntry(
                    english=english,
                    chinese=chinese,
                    domain=domain,
                    source=source,
                    updated_at=datetime.now().isoformat(timespec="seconds"),
                )
            )

        # 备份并保存
        await self.backup(domain)
        await self.save(domain, entries)

        action = "更新" if found else "新增"
        logger.info(f"✏️ 术语{action} [{domain}]: {english} → {chinese}")

    def _list_domains(self) -> list[str]:
        """列出所有已有的领域名称

        Returns:
            领域名称列表（从文件名推断）
        """
        if not self.glossary_dir.exists():
            return []
        return [
            p.stem
            for p in self.glossary_dir.glob("*.json")
            if not p.stem.endswith(".bak")
            and ".bak." not in p.name
        ]
