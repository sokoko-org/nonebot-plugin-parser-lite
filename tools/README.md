# Protobuf 相关

## proto文件合并导入到desc文件

在项目的根目录下执行，统一使用当前目录作为搜索起点

```shell
protoc -I . --include_imports --descriptor_set_out=all.desc ./path/to/your/main.proto
```

## desc文件转proto

```shell
py desc2proto.py
```
