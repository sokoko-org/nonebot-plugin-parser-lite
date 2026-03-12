import re
import json

# 预编译正则：只用于路径提取和 ID 定位
RE_PATH = re.compile(r"0sftu[^.\-@]*")
RE_ID = re.compile(r"[0-9:;<=>?]{8,}")

# 预生成静态映射表 (O(1) 查找速度)
T1 = str.maketrans(
    "".join(chr(i) for i in range(256)), "".join(chr((i - 1) % 256) for i in range(256))
)


def get_final_stable_path_ultimate(text):
    # 1. 提取路径：因为路径必存在，直接 search
    match_path = RE_PATH.search(text)
    if not match_path:
        return text

    # 2. 翻译路径并检查末尾
    raw_path = match_path.group(0)
    decoded_path = raw_path.translate(T1)

    # 使用 endswith，代码更具可读性且性能顶尖
    if decoded_path.endswith("profile") and RE_ID.search(text, pos=match_path.end()):
        return f"{decoded_path}/author"

    return decoded_path


def decode_init_state(input_dict: dict | str):
    if isinstance(input_dict, str):
        input_dict = json.loads(input_dict)
    assert isinstance(input_dict, dict), "input_dict must be a dict after JSON parsing"
    # 字典推导式配合 items 迭代器
    return {get_final_stable_path_ultimate(k): v for k, v in input_dict.items()}
