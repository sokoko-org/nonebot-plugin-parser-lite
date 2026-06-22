# Video

GET `https://api.bilibili.com/x/web-interface/view`

## Params

| Name   | Description                    |
| ------ | ------------------------------ |
| `aid`  | 可选, `aid` 和 `bvid` 任选其一 |
| `bvid` | 可选, `aid` 和 `bvid` 任选其一 |

# AI总结

GET `https://api.bilibili.com/x/web-interface/view/conclusion/get`

需要 Cookie

## Params

| Name           | Description                    |
| -------------- | ------------------------------ |
| `aid`          | 可选, `aid` 和 `bvid` 任选其一 |
| `bvid`         | 可选, `aid` 和 `bvid` 任选其一 |
| `cid`          | 视频 cid                       |
| `web_location` | 固定 `333.788`                 |
| `w_rid`        | WBI签名字段                    |
| `wts`          | WBI时间戳                      |

### WBI

```js
const mixinKeyEncTab = [
  46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
  33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
  26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
  20, 34, 44, 52,
];

const getMixinKey = (orig) =>
  mixinKeyEncTab
    .map((n) => orig[n])
    .join("")
    .slice(0, 32);

function getWbiKeys() {
  pm.sendRequest(
    "https://api.bilibili.com/x/web-interface/nav",
    function (err, response) {
      const {
        data: {
          wbi_img: { img_url, sub_url },
        },
      } = response.json();
      img_key = img_url.slice(
        img_url.lastIndexOf("/") + 1,
        img_url.lastIndexOf("."),
      );
      sub_key = sub_url.slice(
        sub_url.lastIndexOf("/") + 1,
        sub_url.lastIndexOf("."),
      );
      pm.environment.set("IMG_KEY", img_key);
      pm.environment.set("SUB_KEY", sub_key);
      pm.environment.set("WBI_KEY_EXPIRE", Math.round(Date.now() / 1000) + 600);
    },
  );
}

function encWbi(params, img_key, sub_key, curr_time) {
  const mixin_key = getMixinKey(img_key + sub_key),
    chr_filter = /[!'()*]/g;

  Object.assign(params, { wts: curr_time }); // 添加 wts 字段
  // 按照 key 重排参数
  const query = Object.keys(params)
    .sort()
    .map((key) => {
      const value = params[key].toString().replace(chr_filter, "");
      return `${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
    })
    .join("&");

  const wbi_sign = CryptoJS.MD5(query + mixin_key).toString();

  return wbi_sign;
}

let img_key = pm.environment.get("IMG_KEY");
let sub_key = pm.environment.get("SUB_KEY");
let wbi_key_expire = pm.environment.get("WBI_KEY_EXPIRE");
if (
  img_key == undefined ||
  sub_key == undefined ||
  wbi_key_expire == undefined ||
  wbi_key_expire < Math.round(Date.now() / 1000)
) {
  getWbiKeys();
  img_key = pm.environment.get("IMG_KEY");
  sub_key = pm.environment.get("SUB_KEY");
}

let param = {};

pm.request.url.query.each((item) => {
  if (!item.disabled && item.value !== "") {
    param[item.key] = item.value;
  }
});

const ts = Math.round(Date.now() / 1000).toString();
const sign = encWbi(param, img_key, sub_key, ts);

console.log("Wbi Sign Applied");
pm.request.url.query.upsert({ key: "w_rid", value: sign });
pm.request.url.query.upsert({ key: "wts", value: ts });
```
