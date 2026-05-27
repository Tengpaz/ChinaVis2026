#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export compact static data for the ChinaVis Peking opera topic dashboard."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "2605_ChinaVis"
OUT = ROOT / "visualization" / "data" / "vis_data.js"

TOPIC_COLORS = [
    "#4f6f9f",
    "#a05a4f",
    "#c17c2f",
    "#7f6aa8",
    "#5b7d4d",
    "#c05f7a",
    "#3f8a8a",
    "#9a6b3a",
    "#6f7682",
]


def read_csv(name: str) -> list[dict[str, str]]:
    with (DATA_DIR / name).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def as_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_collection_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(8) if digits else text


def trim_text(text: str, limit: int = 260) -> str:
    cleaned = " ".join(str(text or "").split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "..."


def rounded(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def main() -> None:
    topics_raw = read_csv("topics.csv")
    plays_raw = read_csv("plays_index.csv")
    play_topics_raw = read_csv("play_topics.csv")
    cooccur_raw = read_csv("topic_cooccur.csv")
    snippets_raw = read_csv("topic_snippets.csv")

    topics = []
    label_by_id: dict[int, str] = {}
    keywords_by_id: dict[int, list[str]] = {}
    for row in sorted(topics_raw, key=lambda item: int(item["topic_id"])):
        topic_id = int(row["topic_id"])
        label = row["label"]
        keywords = [word for word in row.get("keywords", "").split() if word]
        label_by_id[topic_id] = label
        keywords_by_id[topic_id] = keywords
        topics.append(
            {
                "id": topic_id,
                "label": label,
                "keywords": keywords,
                "color": TOPIC_COLORS[topic_id % len(TOPIC_COLORS)],
            }
        )

    topic_ids = [topic["id"] for topic in topics]
    weights_by_play: dict[str, dict[int, float]] = defaultdict(dict)
    for row in play_topics_raw:
        weights_by_play[row["play_id"]][int(row["topic_id"])] = as_float(row["weight"])

    plays = []
    collection_acc: dict[str, dict[str, object]] = {}
    dominant_counts: dict[int, int] = defaultdict(int)
    total_weights: dict[int, float] = defaultdict(float)
    active_topic_counts = []

    for row in plays_raw:
        play_id = row["play_id"]
        collection_id = normalize_collection_id(row["collection_id"])
        weights = {topic_id: weights_by_play[play_id].get(topic_id, 0.0) for topic_id in topic_ids}
        total = sum(weights.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"{play_id} topic weights sum to {total:.6f}, expected 1.0")

        ranked = sorted(weights.items(), key=lambda item: item[1], reverse=True)
        primary_topic_id = ranked[0][0]
        combo_parts = [label_by_id[topic_id] for topic_id, weight in ranked if weight >= 0.1]
        active_count = sum(1 for weight in weights.values() if weight > 0)
        active_topic_counts.append(active_count)
        dominant_counts[primary_topic_id] += 1
        for topic_id, weight in weights.items():
            total_weights[topic_id] += weight

        plays.append(
            {
                "id": play_id,
                "title": row["title"],
                "collectionId": collection_id,
                "collectionName": row["collection_name"],
                "weights": {str(topic_id): rounded(weight) for topic_id, weight in weights.items()},
                "primaryTopicId": primary_topic_id,
                "comboLabel": " + ".join(combo_parts) if combo_parts else label_by_id[primary_topic_id],
                "activeTopicCount": active_count,
            }
        )

        bucket = collection_acc.setdefault(
            collection_id,
            {
                "id": collection_id,
                "name": row["collection_name"],
                "playCount": 0,
                "sums": defaultdict(float),
            },
        )
        bucket["playCount"] = int(bucket["playCount"]) + 1
        for topic_id, weight in weights.items():
            bucket["sums"][topic_id] += weight

    collections = []
    for collection_id, bucket in sorted(collection_acc.items()):
        play_count = int(bucket["playCount"])
        means = {topic_id: float(bucket["sums"][topic_id]) / play_count for topic_id in topic_ids}
        dominant_topic_id = max(means, key=means.get)
        collections.append(
            {
                "id": collection_id,
                "name": bucket["name"],
                "playCount": play_count,
                "meanWeights": {str(topic_id): rounded(means[topic_id]) for topic_id in topic_ids},
                "dominantTopicId": dominant_topic_id,
            }
        )

    max_cooccur = max(as_float(row["cooccur_weight"]) for row in cooccur_raw)
    cooccurrences = []
    for row in cooccur_raw:
        weight = as_float(row["cooccur_weight"])
        cooccurrences.append(
            {
                "source": int(row["topic_i"]),
                "target": int(row["topic_j"]),
                "weight": rounded(weight),
                "normalizedWeight": rounded(weight / max_cooccur if max_cooccur else 0.0),
            }
        )
    cooccurrences.sort(key=lambda item: item["weight"], reverse=True)

    play_lookup = {play["id"]: play for play in plays}
    snippets = []
    for row in snippets_raw:
        topic_id = int(row["topic_id"])
        play = play_lookup.get(row["play_id"], {})
        snippets.append(
            {
                "playId": row["play_id"],
                "title": play.get("title", row["play_id"]),
                "topicId": topic_id,
                "label": label_by_id[topic_id],
                "score": rounded(as_float(row["score"]), 3),
                "snippetShort": trim_text(row["snippet"]),
            }
        )

    strongest_topic_id = max(total_weights, key=total_weights.get)
    strongest_pair = cooccurrences[0]
    data = {
        "meta": {
            "source": "2605_ChinaVis",
            "playCount": len(plays),
            "collectionCount": len(collections),
            "topicCount": len(topics),
            "cooccurrenceCount": len(cooccurrences),
            "snippetCount": len(snippets),
            "averageActiveTopics": rounded(sum(active_topic_counts) / len(active_topic_counts), 2),
            "strongestTopicId": strongest_topic_id,
            "strongestTopicLabel": label_by_id[strongest_topic_id],
            "strongestPairLabel": f"{label_by_id[strongest_pair['source']]} - {label_by_id[strongest_pair['target']]}",
            "llmAgreement": 0.84,
        },
        "topics": topics,
        "plays": plays,
        "collections": collections,
        "cooccurrences": cooccurrences,
        "snippets": snippets,
        "topicTotals": {str(topic_id): rounded(total_weights[topic_id]) for topic_id in topic_ids},
        "dominantTopicCounts": {str(topic_id): dominant_counts[topic_id] for topic_id in topic_ids},
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    js = "window.CHINAVIS_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    OUT.write_text(js, encoding="utf-8")
    print(f"Wrote {OUT}")
    print(
        f"plays={len(plays)} collections={len(collections)} topics={len(topics)} "
        f"cooccurrences={len(cooccurrences)} snippets={len(snippets)}"
    )


if __name__ == "__main__":
    main()
