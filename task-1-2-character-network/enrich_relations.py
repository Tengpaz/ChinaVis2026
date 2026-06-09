import argparse
import json
import os
import re
import sys
import time
import ctypes
from collections import Counter
from pathlib import Path
from typing import Dict, Tuple, Any, Optional
from urllib import request, error


def configure_utf8_output() -> None:
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetConsoleCP(65001)
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


DEFAULT_RELATION = "一般互动"

ALLOWED_RELATIONS = {
    "敌对",
    "谋略对抗",
    "合作",
    "君臣",
    "上下级",
    "亲属-父子",
    "亲属-母子",
    "亲属-夫妻",
    "亲属-兄弟姐妹",
    "师徒",
    "审判",
    "诉讼",
    "敬重/依附",
    "一般互动",
}

KNOWN_PAIR_RELATIONS: Dict[frozenset, Dict[str, object]] = {
    frozenset(["周瑜", "诸葛亮"]): {"relation": "谋略对抗", "confidence": 0.95, "evidence": "三国人物先验知识"},
    frozenset(["刘备", "关羽"]): {"relation": "君臣", "confidence": 0.90, "evidence": "三国人物先验知识"},
    frozenset(["刘备", "张飞"]): {"relation": "君臣", "confidence": 0.90, "evidence": "三国人物先验知识"},
    frozenset(["关羽", "张飞"]): {"relation": "亲属-兄弟姐妹", "confidence": 0.78, "evidence": "义结金兰近似兄弟关系"},
    frozenset(["司马懿", "司马昭"]): {"relation": "亲属-父子", "confidence": 0.96, "evidence": "历史人物先验知识"},
    frozenset(["包拯", "公孙策"]): {"relation": "合作", "confidence": 0.85, "evidence": "公案人物先验知识"},
    frozenset(["周仁全", "康氏"]): {"relation": "亲属-夫妻", "confidence": 0.96, "evidence": "剧目人物先验校正"},
    frozenset(["周仁全", "周素秋"]): {"relation": "亲属-父子", "confidence": 0.94, "evidence": "剧目人物先验校正"},
    frozenset(["康氏", "周素秋"]): {"relation": "亲属-母子", "confidence": 0.94, "evidence": "剧目人物先验校正"},
    frozenset(["艾子诚", "艾文仲"]): {"relation": "亲属-父子", "confidence": 0.95, "evidence": "剧目人物先验校正"},
    frozenset(["艾子诚", "周素秋"]): {"relation": "亲属-夫妻", "confidence": 0.94, "evidence": "剧目人物先验校正"},
}

FATHER_SON_TOKENS = ["父", "爹", "翁", "公", "太君", "老爷"]
COUPLE_TOKENS = ["夫人", "娘子", "相公", "驸马", "王妃"]
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


def is_female_marker(name: str) -> bool:
    return any(token in name for token in ["氏", "妃", "后", "妾", "妻", "妇", "娘", "婆", "姑"])


def infer_by_rules(n1: str, n2: str, weight: int = 1) -> Tuple[str, float, str]:
    if same_surname(n1, n2) and (has_any_token(n1, FATHER_SON_TOKENS) or has_any_token(n2, FATHER_SON_TOKENS)):
        if is_female_marker(n1) or is_female_marker(n2):
            return "亲属-母子", 0.70, "同姓+直系亲属词+女性标记"
        return "亲属-父子", 0.72, "同姓+父子词"

    if same_surname(n1, n2) and (has_any_token(n1, SIBLING_TOKENS) or has_any_token(n2, SIBLING_TOKENS)):
        return "亲属-兄弟姐妹", 0.70, "同姓+兄弟姐妹词"

    # “氏”只说明女性/已婚身份，不能直接把她与所有共现人物都判成夫妻
    if has_any_token(n1, COUPLE_TOKENS) or has_any_token(n2, COUPLE_TOKENS):
        return "亲属-夫妻", 0.72, "明确婚姻称谓词"

    if ("氏" in n1 and same_surname(n2, n1.replace("氏", ""))) or ("氏" in n2 and same_surname(n1, n2.replace("氏", ""))):
        return "亲属-夫妻", 0.70, "姓氏女性称谓+同姓推断"

    if has_any_token(n1, MASTER_DISCIPLE_TOKENS) or has_any_token(n2, MASTER_DISCIPLE_TOKENS):
        return "师徒", 0.62, "师徒称谓词"

    if has_any_token(n1, JUDICIAL_TOKENS) and has_any_token(n2, LITIGATION_TOKENS):
        return "审判", 0.64, "司法角色+诉讼语义"
    if has_any_token(n2, JUDICIAL_TOKENS) and has_any_token(n1, LITIGATION_TOKENS):
        return "审判", 0.64, "司法角色+诉讼语义"

    if has_any_token(n1, LITIGATION_TOKENS) or has_any_token(n2, LITIGATION_TOKENS):
        return "诉讼", 0.58, "诉讼词弱规则"

    if (has_any_token(n1, MONARCH_TOKENS) and has_any_token(n2, OFFICIAL_TOKENS)) or (
        has_any_token(n2, MONARCH_TOKENS) and has_any_token(n1, OFFICIAL_TOKENS)
    ):
        return "君臣", 0.66, "君主词+官职词"

    if has_any_token(n1, OFFICIAL_TOKENS) or has_any_token(n2, OFFICIAL_TOKENS):
        return "上下级", 0.56, "官职词弱规则"

    if has_any_token(n1, DEPENDENCY_TOKENS) or has_any_token(n2, DEPENDENCY_TOKENS):
        return "敬重/依附", 0.60, "主仆依附词"

    if has_any_token(n1, STRATEGY_TOKENS) and has_any_token(n2, STRATEGY_TOKENS):
        return "谋略对抗", 0.60, "谋士人物弱先验"

    if has_any_token(n1, MILITARY_TOKENS) and has_any_token(n2, MILITARY_TOKENS):
        if weight >= 5:
            return "合作", 0.57, "军旅同阵营+高强度"
        return "上下级", 0.52, "军旅同阵营+低强度"

    if weight >= 8:
        return "合作", 0.56, "高频共现近似合作"
    if weight >= 3:
        return "一般互动", 0.50, "中频共现"
    return "一般互动", 0.45, "低频共现"


def infer_relation(name1: str, name2: str, weight: int = 1) -> Tuple[str, float, str]:
    n1, n2 = normalize_name(name1), normalize_name(name2)
    pair_key = frozenset([n1, n2])

    if pair_key in KNOWN_PAIR_RELATIONS:
        item = KNOWN_PAIR_RELATIONS[pair_key]
        return str(item["relation"]), float(item["confidence"]), str(item["evidence"])

    return infer_by_rules(n1, n2, weight)


def sanitize_relation(relation: str, confidence: float, evidence: str) -> Tuple[str, float, str]:
    rel = relation if relation in ALLOWED_RELATIONS else DEFAULT_RELATION
    conf = min(max(float(confidence), 0.0), 1.0)
    evd = evidence or "规则回退"
    return rel, conf, evd


def build_llm_prompt(name1: str, name2: str, weight: int, play_name: str) -> str:
    labels = "、".join(sorted(ALLOWED_RELATIONS))
    return (
        "你是京剧人物关系标注助手。请在给定标签中选择最合适的一项，不要创造新标签。\n"
        f"标签集合：{labels}\n"
        f"剧目：{play_name}\n"
        f"人物A：{name1}\n"
        f"人物B：{name2}\n"
        f"共现强度(value)：{weight}\n"
        "请只返回JSON对象，格式为："
        '{"relation":"标签之一","confidence":0到1,"reason":"不超过25字"}'
    )


def call_llm(
    api_base: str,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float = 0.0,
    timeout_sec: int = 45,
    max_retries: int = 2,
) -> Optional[Dict[str, Any]]:
    url = api_base.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": "你是严谨的信息抽取助手。"},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    for i in range(max_retries + 1):
        try:
            req = request.Request(url, data=data, headers=headers, method="POST")
            with request.urlopen(req, timeout=timeout_sec) as resp:
                raw = resp.read().decode("utf-8")
            obj = json.loads(raw)
            content = obj["choices"][0]["message"]["content"]
            return json.loads(content)
        except (error.URLError, error.HTTPError, TimeoutError, KeyError, json.JSONDecodeError):
            if i == max_retries:
                return None
            time.sleep(1.2 * (i + 1))
    return None


def enrich_network(
    input_path: Path,
    output_path: Path,
    use_llm: bool,
    llm_min_weight: int,
    llm_min_rule_conf: float,
    api_base: str,
    api_key: str,
    model: str,
    cache_path: Path,
) -> None:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    stats = Counter()

    cache: Dict[str, Dict[str, Any]] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    for play_name, play_data in data.items():
        nodes = play_data.get("nodes", [])
        links = play_data.get("links", [])
        id_to_name = {node["id"]: node["name"] for node in nodes if "id" in node and "name" in node}

        for link in links:
            source_name = id_to_name.get(link.get("source"), "")
            target_name = id_to_name.get(link.get("target"), "")
            weight = int(link.get("value", 1) or 1)

            relation, confidence, evidence = infer_relation(source_name, target_name, weight)
            relation_source = "rule"
            needs_review = False

            try_llm = use_llm and weight >= llm_min_weight and confidence < llm_min_rule_conf
            if try_llm:
                key = f"{play_name}||{normalize_name(source_name)}||{normalize_name(target_name)}||{weight}"
                llm_obj = cache.get(key)

                if llm_obj is None:
                    prompt = build_llm_prompt(source_name, target_name, weight, play_name)
                    llm_obj = call_llm(api_base, api_key, model, prompt)
                    if llm_obj:
                        cache[key] = llm_obj

                if llm_obj and isinstance(llm_obj, dict):
                    llm_relation = str(llm_obj.get("relation", "")).strip()
                    llm_conf = float(llm_obj.get("confidence", 0.0) or 0.0)
                    llm_reason = str(llm_obj.get("reason", "LLM判定")).strip() or "LLM判定"

                    llm_relation, llm_conf, llm_reason = sanitize_relation(llm_relation, llm_conf, llm_reason)
                    if llm_conf >= confidence:
                        relation, confidence, evidence = llm_relation, llm_conf, f"LLM:{llm_reason}"
                        relation_source = "llm"
                    else:
                        needs_review = True

            relation, confidence, evidence = sanitize_relation(relation, confidence, evidence)
            link["relation"] = relation
            link["relation_confidence"] = round(confidence, 2)
            link["relation_evidence"] = evidence
            link["relation_source"] = relation_source
            link["needs_review"] = needs_review
            stats[relation] += 1

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已输出增强数据: {output_path}")
    print(f"已输出缓存: {cache_path}")
    print("关系类型统计:")
    for relation, count in stats.most_common():
        print(f"  - {relation}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为角色共现网络补充关系类型字段（支持LLM）")
    parser.add_argument("--input", type=str, default="character_network_data.json", help="输入 JSON 文件")
    parser.add_argument("--output", type=str, default="character_network_data_enriched.json", help="输出 JSON 文件")
    parser.add_argument("--use-llm", action="store_true", help="启用 LLM 关系判定")
    parser.add_argument("--llm-min-weight", type=int, default=3, help="仅对 value>=该阈值的边调用LLM")
    parser.add_argument("--llm-min-rule-conf", type=float, default=0.65, help="仅对规则置信度低于该值的边调用LLM")
    parser.add_argument("--api-base", type=str, default="https://api.openai.com/v1", help="OpenAI兼容接口 base URL")
    parser.add_argument("--api-key", type=str, default="", help="API Key（可留空，优先读环境变量 OPENAI_API_KEY）")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="模型名")
    parser.add_argument("--cache", type=str, default="relation_llm_cache.json", help="LLM缓存文件")
    return parser.parse_args()


def main() -> None:
    configure_utf8_output()
    args = parse_args()
    script_dir = Path(__file__).parent

    input_arg = Path(args.input)
    output_arg = Path(args.output)
    cache_arg = Path(args.cache)

    input_path = input_arg.resolve() if input_arg.is_absolute() else (script_dir / input_arg).resolve()
    output_path = output_arg.resolve() if output_arg.is_absolute() else (script_dir / output_arg).resolve()
    cache_path = cache_arg.resolve() if cache_arg.is_absolute() else (script_dir / cache_arg).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"未找到输入文件: {input_path}")

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY", "")
    if args.use_llm and not api_key:
        raise ValueError("已启用 --use-llm，但未提供 --api-key 且环境变量 OPENAI_API_KEY 为空")

    enrich_network(
        input_path=input_path,
        output_path=output_path,
        use_llm=args.use_llm,
        llm_min_weight=args.llm_min_weight,
        llm_min_rule_conf=args.llm_min_rule_conf,
        api_base=args.api_base,
        api_key=api_key,
        model=args.model,
        cache_path=cache_path,
    )


if __name__ == "__main__":
    main()
