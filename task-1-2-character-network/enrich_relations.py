import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Tuple


DEFAULT_RELATION = "未定"

# 无方向先验关系库，可持续扩展
KNOWN_PAIR_RELATIONS: Dict[frozenset, Dict[str, object]] = {
    frozenset(["周瑜", "诸葛亮"]): {"relation": "谋略对抗", "confidence": 0.95, "evidence": "三国人物先验知识"},
    frozenset(["刘备", "关羽"]): {"relation": "君臣", "confidence": 0.9, "evidence": "三国人物先验知识"},
    frozenset(["刘备", "张飞"]): {"relation": "君臣", "confidence": 0.9, "evidence": "三国人物先验知识"},
    frozenset(["关羽", "张飞"]): {"relation": "亲属-兄弟姐妹", "confidence": 0.78, "evidence": "义结金兰近似兄弟关系"},
    frozenset(["司马懿", "司马昭"]): {"relation": "亲属-父子", "confidence": 0.96, "evidence": "历史人物先验知识"},
    frozenset(["包拯", "公孙策"]): {"relation": "合作", "confidence": 0.85, "evidence": "公案人物先验知识"},
}

FATHER_SON_TOKENS = ["父", "爹", "子", "郎", "太君", "老爷"]
COUPLE_TOKENS = ["夫人", "娘子", "相公", "驸马", "王妃", "氏"]
SIBLING_TOKENS = ["兄", "弟", "姐", "妹"]
MASTER_DISCIPLE_TOKENS = ["师", "徒", "先生", "弟子"]

MONARCH_TOKENS = ["帝", "王", "君", "主公", "陛下", "天子"]
OFFICIAL_TOKENS = ["相", "丞相", "太守", "都督", "元帅", "将军", "大人", "太尉", "尚书", "府尹"]
MILITARY_TOKENS = ["将军", "元帅", "校尉", "将", "军", "兵", "卒", "军甲", "军乙"]

JUDICIAL_TOKENS = ["包拯", "青天", "府尹", "大人", "判官", "知县", "御史"]
LITIGATION_TOKENS = ["状", "告", "冤", "案", "审", "判"]
DEPENDENCY_TOKENS = ["奴", "婢", "仆", "随从", "家丁", "老奴"]
STRATEGY_TOKENS = ["诸葛", "周瑜", "司马", "庞统", "郭嘉", "法正", "鲁肃"]


def normalize_name(name: str) -> str:
    return re.sub(r"[\s·・]", "", str(name or "")).strip()


def same_surname(name1: str, name2: str) -> bool:
    return bool(name1 and name2 and name1[0] == name2[0])


def has_any_token(name: str, tokens) -> bool:
    return any(t in name for t in tokens)


def infer_by_rules(n1: str, n2: str) -> Tuple[str, float, str]:
    # 1) 亲属
    if same_surname(n1, n2) and (has_any_token(n1, FATHER_SON_TOKENS) or has_any_token(n2, FATHER_SON_TOKENS)):
        return "亲属-父子", 0.72, "同姓+父子词"

    if same_surname(n1, n2) and (has_any_token(n1, SIBLING_TOKENS) or has_any_token(n2, SIBLING_TOKENS)):
        return "亲属-兄弟姐妹", 0.7, "同姓+兄弟姐妹词"

    if has_any_token(n1, COUPLE_TOKENS) or has_any_token(n2, COUPLE_TOKENS):
        if same_surname(n1, n2) or "氏" in n1 or "氏" in n2:
            return "亲属-夫妻", 0.68, "夫妻称谓词"

    # 2) 师徒
    if has_any_token(n1, MASTER_DISCIPLE_TOKENS) or has_any_token(n2, MASTER_DISCIPLE_TOKENS):
        return "师徒", 0.62, "师徒称谓词"

    # 3) 审判 / 诉讼（公案戏常见）
    if has_any_token(n1, JUDICIAL_TOKENS) and has_any_token(n2, LITIGATION_TOKENS):
        return "审判", 0.64, "司法角色+诉讼语义"
    if has_any_token(n2, JUDICIAL_TOKENS) and has_any_token(n1, LITIGATION_TOKENS):
        return "审判", 0.64, "司法角色+诉讼语义"

    if has_any_token(n1, LITIGATION_TOKENS) or has_any_token(n2, LITIGATION_TOKENS):
        return "诉讼", 0.58, "诉讼词弱规则"

    # 4) 君臣 / 上下级
    if (has_any_token(n1, MONARCH_TOKENS) and has_any_token(n2, OFFICIAL_TOKENS)) or (
        has_any_token(n2, MONARCH_TOKENS) and has_any_token(n1, OFFICIAL_TOKENS)
    ):
        return "君臣", 0.66, "君主词+官职词"

    if has_any_token(n1, OFFICIAL_TOKENS) or has_any_token(n2, OFFICIAL_TOKENS):
        return "上下级", 0.56, "官职词弱规则"

    if has_any_token(n1, MILITARY_TOKENS) and has_any_token(n2, MILITARY_TOKENS):
        return "合作", 0.54, "军旅同阵营弱规则"

    # 5) 敬重/依附
    if has_any_token(n1, DEPENDENCY_TOKENS) or has_any_token(n2, DEPENDENCY_TOKENS):
        return "敬重/依附", 0.6, "主仆依附词"

    # 6) 谋略人物之间优先给谋略对抗（历史戏常见）
    if has_any_token(n1, STRATEGY_TOKENS) and has_any_token(n2, STRATEGY_TOKENS):
        return "谋略对抗", 0.6, "谋士人物弱先验"

    return DEFAULT_RELATION, 0.3, "仅共现，未识别语义关系"


def infer_relation(name1: str, name2: str) -> Tuple[str, float, str]:
    n1, n2 = normalize_name(name1), normalize_name(name2)
    pair_key = frozenset([n1, n2])

    if pair_key in KNOWN_PAIR_RELATIONS:
        item = KNOWN_PAIR_RELATIONS[pair_key]
        return str(item["relation"]), float(item["confidence"]), str(item["evidence"])

    return infer_by_rules(n1, n2)


def enrich_network(input_path: Path, output_path: Path) -> None:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    stats = Counter()

    for _, play_data in data.items():
        nodes = play_data.get("nodes", [])
        links = play_data.get("links", [])
        id_to_name = {node["id"]: node["name"] for node in nodes if "id" in node and "name" in node}

        for link in links:
            source_name = id_to_name.get(link.get("source"), "")
            target_name = id_to_name.get(link.get("target"), "")

            relation, confidence, evidence = infer_relation(source_name, target_name)
            link["relation"] = relation
            link["relation_confidence"] = round(confidence, 2)
            link["relation_evidence"] = evidence
            stats[relation] += 1

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")

    print(f"已输出增强数据: {output_path}")
    print("关系类型统计:")
    for relation, count in stats.most_common():
        print(f"  - {relation}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为角色共现网络补充关系类型字段")
    parser.add_argument("--input", type=str, default="character_network_data.json", help="输入 JSON 文件")
    parser.add_argument("--output", type=str, default="character_network_data_enriched.json", help="输出 JSON 文件")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    script_dir = Path(__file__).parent
    input_path = (script_dir / args.input).resolve()
    output_path = (script_dir / args.output).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"未找到输入文件: {input_path}")

    enrich_network(input_path, output_path)


if __name__ == "__main__":
    main()
