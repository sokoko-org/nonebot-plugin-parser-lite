from typing import Literal

from .sign import douyinSign

SignType = Literal["a_bogus", "x_bogus"]


def get_signature(
    url: str,
    sign_type: SignType = "a_bogus",
    user_agent: str | None = None,
) -> str:
    """获取签名参数"""
    if sign_type == "x_bogus":
        return douyinSign.XB(url, user_agent)
    # 默认 a_bogus
    return douyinSign.AB(url, user_agent)


def get_sign_param_name(sign_type: SignType = "a_bogus") -> str:
    """获取签名参数名称"""
    return "X-Bogus" if sign_type == "x_bogus" else "a_bogus"


def build_signed_url(
    url: str,
    sign_type: SignType = "a_bogus",
    user_agent: str | None = None,
) -> str:
    """构建带签名的 URL"""
    signature = get_signature(url, sign_type, user_agent)
    param_name = get_sign_param_name(sign_type)
    return f"{url}&{param_name}={signature}"


# 如何使用
#
# 1. 在 api.py 中调用函数获取对应的 url
# 2. 在此文件中调用 build_signed_url 签名 url
# 3. 请求 url
