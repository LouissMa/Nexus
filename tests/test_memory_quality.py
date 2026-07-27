from __future__ import annotations

from datetime import UTC, datetime

from nexus.memory_lifecycle import (
    build_compression_plan,
    normalize_memory,
    score_importance,
)


NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)


def test_chinese_importance_language_is_detected_inside_sentences() -> None:
    ordinary = score_importance("今天阅读一章教材", ["学习"])
    significant = score_importance(
        "重要目标：明天是考试截止日期，必须完成申请",
        ["考试", "目标"],
    )

    assert significant > ordinary


def test_compression_summary_is_bounded_while_sources_remain_referenced() -> None:
    memories = [
        normalize_memory(
            {
                "id": f"m{index}",
                "text": f"Research note {index}: " + ("detail " * 100),
                "tags": ["research"],
                "created_at": "2025-01-01T00:00:00+00:00",
                "importance": 0.2,
            },
            now=NOW,
        )
        for index in range(20)
    ]

    plan = build_compression_plan(
        memories,
        older_than_days=90,
        max_importance=0.4,
        now=NOW,
    )[0]

    assert len(plan.source_ids) == 20
    assert len(plan.summary_text) < 1600
    assert "12 more items" in plan.summary_text
