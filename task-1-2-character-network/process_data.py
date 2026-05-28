import os
import re
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path
import fitz  # PyMuPDF

def pdf_to_text(pdf_path):
    """从PDF文件中提取文本"""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        print(f"错误: 无法读取PDF文件 '{pdf_path}': {e}")
        return ""

def get_character_list(text):
    """从文本中提取角色列表"""
    # 角色通常在行首，并以冒号结尾
    characters = re.findall(r'^(?<![（\(])([^\s:：(（]+)(?=:|：)', text, re.MULTILINE)
    return list(dict.fromkeys(characters))

def build_network_from_text(text):
    """从文本内容构建角色关系网络"""
    lines = text.split('\n')
    all_characters = get_character_list(text)
    if not all_characters:
        return None, None

    character_set = set(all_characters)
    co_occurrence = defaultdict(int)
    
    for line in lines:
        present_characters = [char for char in character_set if char in line]
        if len(present_characters) > 1:
            for pair in combinations(sorted(present_characters), 2):
                co_occurrence[pair] += 1

    nodes = [{"name": char, "id": i} for i, char in enumerate(all_characters)]
    char_to_id = {char["name"]: char["id"] for char in nodes}

    links = []
    for (char1, char2), weight in co_occurrence.items():
        if weight > 0:
            links.append({
                "source": char_to_id.get(char1),
                "target": char_to_id.get(char2),
                "value": weight
            })
            
    if not links:
        return None, None
        
    connected_nodes = {link["source"] for link in links} | {link["target"] for link in links}
    final_nodes = [node for node in nodes if node["id"] in connected_nodes]
    
    if not final_nodes:
        return None, None

    return final_nodes, links

def main():
    """主函数，处理所有剧本并生成最终的数据文件"""
    script_dir = Path(__file__).parent
    base_data_path = script_dir.parent / 'visualization' / 'data' / 'all' / '1-I_opera_dataset' / '赛题1-I京剧数据集' / '京剧剧本'
    
    if not base_data_path.exists():
        print(f"错误: 数据目录不存在 -> {base_data_path}")
        return

    all_networks = {}
    
    pdf_files = [f for f in os.listdir(base_data_path) if f.endswith('.pdf')]
    print(f"在目录下找到 {len(pdf_files)} 个PDF剧本文件: {base_data_path}")

    for file_name in pdf_files:
        pdf_path = base_data_path / file_name
        play_name = pdf_path.stem.split('_')[-1] # 从文件名提取剧名
        
        print(f"正在处理: {play_name} ({file_name})")
        
        # 检查是否有缓存的txt文件
        txt_path = pdf_path.with_suffix('.txt')
        if txt_path.exists():
            print("  - 找到缓存的TXT文件，直接读取。")
            with open(txt_path, 'r', encoding='utf-8') as f:
                text = f.read()
        else:
            print("  - 未找到缓存，从PDF提取文本...")
            text = pdf_to_text(pdf_path)
            if text:
                # 保存为txt文件以备后用
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(text)
                print(f"  - 文本已缓存到 {txt_path.name}")

        if not text:
            print(f"警告: 未能从 '{file_name}' 中提取到文本。")
            continue
            
        nodes, links = build_network_from_text(text)
        
        if nodes and links:
            all_networks[play_name] = {
                "nodes": nodes,
                "links": links
            }
        else:
            print(f"警告: 未能在 '{play_name}' 中提取到有效的角色关系。")

    output_path = script_dir / 'character_network_data.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_networks, f, ensure_ascii=False, indent=4)
        
    print(f"\n处理完成！所有角色关系网络数据已保存到: {output_path}")

if __name__ == '__main__':
    main()
