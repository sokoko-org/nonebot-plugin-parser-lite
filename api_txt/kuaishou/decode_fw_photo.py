import re
from typing import Any

import msgspec

RE_PATH = re.compile(r"0sftu[^.\-@]*")
_FROM_CHARS = "".join(chr(i) for i in range(256))
_TO_CHARS = "".join(chr((i - 1) % 256) for i in range(256))
DECRYPT_TRANS = str.maketrans(_FROM_CHARS, _TO_CHARS)


# NOTE: 此解密不会正确解析 author 路径，因为我不需要它
def get_final_stable_path_ultimate(text: str) -> str:
    match_path = RE_PATH.search(text)
    return match_path.group(0).translate(DECRYPT_TRANS) if match_path else text


def decode_init_state(input_dict: dict[str, Any] | str | bytes) -> dict[str, Any]:
    if isinstance(input_dict, (str, bytes)):
        input_dict = msgspec.json.decode(input_dict, type=dict[str, Any])
    return {get_final_stable_path_ultimate(k): v for k, v in input_dict.items()}
