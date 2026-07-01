# 图文

GET `https://bbs-api.miyoushe.com/post/wapi/getPostFull?post_id={TOPIC_ID}`

需要 Referer `https://www.miyoushe.com/`

请求头有个`DS`，但是不带这个请求也给数据

```js
import md5 from "md5";

export const getDS = () => {
  const salt = "ZSHlXeQUBis52qD1kEgKt5lUYed4b7Bb";
  const lettersAndNumbers =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

  const i = Math.floor(Date.now() / 1000);
  let r = "";
  for (let i; i < 6; i++) {
    r +=
      lettersAndNumbers[Math.floor(Math.random() * lettersAndNumbers.length)];
  }
  const c = md5(`salt=${salt}&t=${i}&r=${r}`);
  return `${i},${r},${c}`;
};
```

# 表情列表

GET `https://bbs-api-static.miyoushe.com/misc/api/emoticon_set`

不需要请求头

这个文件非常大，使用优化脚本优化后粘贴到 `sticker.py` 即可

# 评论

GET ` https://bbs-api.miyoushe.com/post/wapi/getPostReplies?is_hot=true&post_id={TOPIC_ID}&size={COUNT}`

请求头同上

## 评论表情

> 这里只写官方表情，自定义表情就是图片直接插就行

形如 `_(丽都漫步-苍角)` `_(妮可 哈哈)` `_(雅珂达-哈哈)` `_(爱可菲-嘲笑)` `_(阿君得意)`

正则如下

```python
MIHOUSE_EMOJI_PATTERN = re.compile(r"_\((?P<name>[^)]+)\)")
```

~~然后拿到名称走贴纸CDN请求~~, CDN装不了这么多，本地组合得了
