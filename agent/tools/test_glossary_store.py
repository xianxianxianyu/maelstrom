"""GlossaryStore 单元测试

覆盖: load/save round-trip, backup creation, merge with conflicts,
query with fuzzy match, update_entry (新增 + 更新)

使用 tmp_path fixture 隔离测试，不写入真实 Translation/ 目录。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio

from agent.models import GlossaryEntry
from agent.tools.glossary_store import GlossaryStore


@pytest_asyncio.fixture
async def store(tmp_path: Path) -> GlossaryStore:
    """创建使用临时目录的 GlossaryStore"""
    return GlossaryStore(glossary_dir=tmp_path)


def _make_entry(
    english: str = "attention",
    chinese: str = "注意力",
    keep_english: bool = False,
    domain: str = "nlp",
    source: str = "paper.pdf",
) -> GlossaryEntry:
    """辅助函数：创建测试用 GlossaryEntry"""
    return GlossaryEntry(
        english=english,
        chinese=chinese,
        keep_english=keep_english,
        domain=domain,
        source=source,
        updated_at="2024-01-01T00:00:00",
    )


# ── load / save round-trip ──


@pytest.mark.asyncio
async def test_save_and_load_round_trip(store: GlossaryStore) -> None:
    """保存后加载应得到等价的术语列表"""
    entries = [
        _make_entry("Transformer", "Transformer", keep_english=True),
        _make_entry("attention mechanism", "注意力机制"),
        _make_entry("embedding", "嵌入"),
    ]

    await store.save("nlp", entries)
    loaded = await store.load("nlp")

    assert len(loaded) == len(entries)
    for orig, got in zip(entries, loaded):
        assert got.english == orig.english
        assert got.chinese == orig.chinese
        assert got.keep_english == orig.keep_english
        assert got.domain == orig.domain
        assert got.source == orig.source


@pytest.mark.asyncio
async def test_load_nonexistent_domain_returns_empty(store: GlossaryStore) -> None:
    """加载不存在的领域应返回空列表"""
    result = await store.load("nonexistent")
    assert result == []


@pytest.mark.asyncio
async def test_load_corrupted_file_returns_empty(store: GlossaryStore) -> None:
    """加载损坏的 JSON 文件应返回空列表而非抛异常"""
    path = store.glossary_dir / "bad.json"
    store.glossary_dir.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json {{{", encoding="utf-8")

    result = await store.load("bad")
    assert result == []


@pytest.mark.asyncio
async def test_save_creates_directory(tmp_path: Path) -> None:
    """保存时应自动创建不存在的目录"""
    nested = tmp_path / "deep" / "nested" / "glossaries"
    store = GlossaryStore(glossary_dir=nested)

    await store.save("test", [_make_entry()])
    assert nested.exists()
    assert (nested / "test.json").exists()


@pytest.mark.asyncio
async def test_save_json_format(store: GlossaryStore) -> None:
    """保存的 JSON 应包含 domain、entries 和 updated_at 字段"""
    await store.save("nlp", [_make_entry()])

    path = store.glossary_dir / "nlp.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["domain"] == "nlp"
    assert isinstance(data["entries"], list)
    assert len(data["entries"]) == 1
    assert "updated_at" in data
    assert data["entries"][0]["english"] == "attention"


# ── backup ──


@pytest.mark.asyncio
async def test_backup_creates_timestamped_file(store: GlossaryStore) -> None:
    """备份应创建带时间戳的 .bak.json 文件"""
    await store.save("nlp", [_make_entry()])

    backup_path = await store.backup("nlp")

    assert backup_path is not None
    assert backup_path.exists()
    assert ".bak.json" in backup_path.name
    assert backup_path.name.startswith("nlp.")

    # 备份内容应与原文件一致
    original = json.loads((store.glossary_dir / "nlp.json").read_text(encoding="utf-8"))
    backup_data = json.loads(backup_path.read_text(encoding="utf-8"))
    assert original == backup_data


@pytest.mark.asyncio
async def test_backup_nonexistent_returns_none(store: GlossaryStore) -> None:
    """备份不存在的文件应返回 None"""
    result = await store.backup("nonexistent")
    assert result is None


# ── merge ──


@pytest.mark.asyncio
async def test_merge_adds_new_entries(store: GlossaryStore) -> None:
    """合并应添加新术语"""
    existing = [_make_entry("attention", "注意力")]
    await store.save("nlp", existing)

    new_entries = [_make_entry("embedding", "嵌入")]
    conflicts = await store.merge("nlp", new_entries)

    assert conflicts == []
    loaded = await store.load("nlp")
    assert len(loaded) == 2
    english_terms = {e.english for e in loaded}
    assert "attention" in english_terms
    assert "embedding" in english_terms


@pytest.mark.asyncio
async def test_merge_preserves_existing_translations(store: GlossaryStore) -> None:
    """合并时已有术语的翻译应保持不变"""
    existing = [_make_entry("attention", "注意力")]
    await store.save("nlp", existing)

    # 尝试用不同翻译合并同一术语
    new_entries = [_make_entry("attention", "关注度")]
    conflicts = await store.merge("nlp", new_entries)

    # 应有冲突
    assert len(conflicts) == 1
    assert conflicts[0]["english"] == "attention"
    assert conflicts[0]["existing"] == "注意力"
    assert conflicts[0]["incoming"] == "关注度"

    # 已有翻译应保持不变
    loaded = await store.load("nlp")
    attention_entries = [e for e in loaded if e.english == "attention"]
    assert len(attention_entries) == 1
    assert attention_entries[0].chinese == "注意力"


@pytest.mark.asyncio
async def test_merge_no_conflict_same_translation(store: GlossaryStore) -> None:
    """合并时相同翻译不应产生冲突"""
    existing = [_make_entry("attention", "注意力")]
    await store.save("nlp", existing)

    new_entries = [_make_entry("attention", "注意力")]
    conflicts = await store.merge("nlp", new_entries)

    assert conflicts == []


@pytest.mark.asyncio
async def test_merge_creates_backup(store: GlossaryStore) -> None:
    """合并操作应创建备份文件"""
    await store.save("nlp", [_make_entry()])

    await store.merge("nlp", [_make_entry("embedding", "嵌入")])

    bak_files = list(store.glossary_dir.glob("nlp.*.bak.json"))
    assert len(bak_files) >= 1


@pytest.mark.asyncio
async def test_merge_case_insensitive(store: GlossaryStore) -> None:
    """合并时英文术语匹配应大小写不敏感"""
    existing = [_make_entry("Transformer", "变换器")]
    await store.save("nlp", existing)

    new_entries = [_make_entry("transformer", "转换器")]
    conflicts = await store.merge("nlp", new_entries)

    assert len(conflicts) == 1
    assert conflicts[0]["existing"] == "变换器"
    assert conflicts[0]["incoming"] == "转换器"


@pytest.mark.asyncio
async def test_merge_into_empty_domain(store: GlossaryStore) -> None:
    """合并到空领域应直接添加所有术语"""
    new_entries = [
        _make_entry("attention", "注意力"),
        _make_entry("embedding", "嵌入"),
    ]
    conflicts = await store.merge("nlp", new_entries)

    assert conflicts == []
    loaded = await store.load("nlp")
    assert len(loaded) == 2


# ── query ──


@pytest.mark.asyncio
async def test_query_exact_match(store: GlossaryStore) -> None:
    """精确匹配应返回对应术语"""
    entries = [
        _make_entry("attention mechanism", "注意力机制"),
        _make_entry("embedding", "嵌入"),
    ]
    await store.save("nlp", entries)

    results = await store.query("attention mechanism", domain="nlp")
    assert len(results) == 1
    assert results[0].english == "attention mechanism"


@pytest.mark.asyncio
async def test_query_fuzzy_substring_match(store: GlossaryStore) -> None:
    """子串匹配应返回包含查询词的术语"""
    entries = [
        _make_entry("attention mechanism", "注意力机制"),
        _make_entry("self-attention", "自注意力"),
        _make_entry("embedding", "嵌入"),
    ]
    await store.save("nlp", entries)

    results = await store.query("attention", domain="nlp")
    assert len(results) == 2
    english_terms = {r.english for r in results}
    assert "attention mechanism" in english_terms
    assert "self-attention" in english_terms


@pytest.mark.asyncio
async def test_query_chinese_match(store: GlossaryStore) -> None:
    """查询中文应匹配中文翻译字段"""
    entries = [
        _make_entry("attention", "注意力机制"),
        _make_entry("embedding", "嵌入"),
    ]
    await store.save("nlp", entries)

    results = await store.query("注意力", domain="nlp")
    assert len(results) == 1
    assert results[0].english == "attention"


@pytest.mark.asyncio
async def test_query_case_insensitive(store: GlossaryStore) -> None:
    """查询应大小写不敏感"""
    entries = [_make_entry("Transformer", "变换器")]
    await store.save("nlp", entries)

    results = await store.query("transformer", domain="nlp")
    assert len(results) == 1
    assert results[0].english == "Transformer"


@pytest.mark.asyncio
async def test_query_across_all_domains(store: GlossaryStore) -> None:
    """不指定领域时应搜索所有领域"""
    await store.save("nlp", [_make_entry("attention", "注意力", domain="nlp")])
    await store.save("cv", [_make_entry("convolution", "卷积", domain="cv")])

    # 搜索所有领域
    results = await store.query("attention")
    assert len(results) == 1
    assert results[0].english == "attention"

    # 搜索另一个术语
    results = await store.query("convolution")
    assert len(results) == 1
    assert results[0].english == "convolution"


@pytest.mark.asyncio
async def test_query_no_match_returns_empty(store: GlossaryStore) -> None:
    """无匹配时应返回空列表"""
    await store.save("nlp", [_make_entry("attention", "注意力")])

    results = await store.query("nonexistent", domain="nlp")
    assert results == []


# ── update_entry ──


@pytest.mark.asyncio
async def test_update_entry_modifies_existing(store: GlossaryStore) -> None:
    """更新已有术语应修改其翻译"""
    entries = [_make_entry("attention", "注意力")]
    await store.save("nlp", entries)

    await store.update_entry("nlp", "attention", "注意力机制", source="user_edit")

    loaded = await store.load("nlp")
    assert len(loaded) == 1
    assert loaded[0].chinese == "注意力机制"
    assert loaded[0].source == "user_edit"


@pytest.mark.asyncio
async def test_update_entry_adds_new(store: GlossaryStore) -> None:
    """更新不存在的术语应新增条目"""
    await store.save("nlp", [_make_entry("attention", "注意力")])

    await store.update_entry("nlp", "embedding", "嵌入", source="paper.pdf")

    loaded = await store.load("nlp")
    assert len(loaded) == 2
    embedding = [e for e in loaded if e.english == "embedding"]
    assert len(embedding) == 1
    assert embedding[0].chinese == "嵌入"
    assert embedding[0].domain == "nlp"


@pytest.mark.asyncio
async def test_update_entry_creates_backup(store: GlossaryStore) -> None:
    """更新操作应创建备份"""
    await store.save("nlp", [_make_entry("attention", "注意力")])

    await store.update_entry("nlp", "attention", "注意力机制")

    bak_files = list(store.glossary_dir.glob("nlp.*.bak.json"))
    assert len(bak_files) >= 1


@pytest.mark.asyncio
async def test_update_entry_case_insensitive(store: GlossaryStore) -> None:
    """更新时英文术语匹配应大小写不敏感"""
    await store.save("nlp", [_make_entry("Transformer", "变换器")])

    await store.update_entry("nlp", "transformer", "转换器")

    loaded = await store.load("nlp")
    assert len(loaded) == 1
    # 原始大小写保留，翻译已更新
    assert loaded[0].english == "Transformer"
    assert loaded[0].chinese == "转换器"


@pytest.mark.asyncio
async def test_update_entry_to_empty_domain(store: GlossaryStore) -> None:
    """更新到空领域应创建文件并添加条目"""
    await store.update_entry("new_domain", "attention", "注意力")

    loaded = await store.load("new_domain")
    assert len(loaded) == 1
    assert loaded[0].english == "attention"
    assert loaded[0].chinese == "注意力"


# ── _list_domains ──


@pytest.mark.asyncio
async def test_list_domains(store: GlossaryStore) -> None:
    """_list_domains 应返回所有领域名称，排除备份文件"""
    await store.save("nlp", [_make_entry()])
    await store.save("cv", [_make_entry("convolution", "卷积")])
    await store.backup("nlp")  # 创建备份文件

    domains = store._list_domains()
    assert "nlp" in domains
    assert "cv" in domains
    # 备份文件不应出现在领域列表中
    for d in domains:
        assert "bak" not in d
