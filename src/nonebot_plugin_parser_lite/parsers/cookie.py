def ck2dict(cookies_str: str) -> dict[str, str]:
    """将 cookies 字符串转换为字典

    :param cookies_str: cookies 字符串

    :return: 字典
    """
    res = {}
    if not cookies_str:
        return res
    for cookie in cookies_str.split(";"):
        name, value = cookie.strip().split("=", 1)
        res[name] = value
    return res
