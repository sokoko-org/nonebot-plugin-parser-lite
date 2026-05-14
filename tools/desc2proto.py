from google.protobuf.descriptor import FieldDescriptor
import google.protobuf.descriptor_pb2 as pb2
from google.protobuf.descriptor_pb2 import (
    global___DescriptorProto,
    global___EnumDescriptorProto,
    global___FieldDescriptorProto,
)


def run_ultimate_restore(desc_path, output_proto):
    with open(desc_path, "rb") as f:
        fds = pb2.FileDescriptorSet()
        fds.ParseFromString(f.read())

    # 基础类型映射表
    TYPE_STR = {
        FieldDescriptor.TYPE_DOUBLE: "double",
        FieldDescriptor.TYPE_FLOAT: "float",
        FieldDescriptor.TYPE_INT64: "int64",
        FieldDescriptor.TYPE_UINT64: "uint64",
        FieldDescriptor.TYPE_INT32: "int32",
        FieldDescriptor.TYPE_FIXED64: "fixed64",
        FieldDescriptor.TYPE_FIXED32: "fixed32",
        FieldDescriptor.TYPE_BOOL: "bool",
        FieldDescriptor.TYPE_STRING: "string",
        FieldDescriptor.TYPE_BYTES: "bytes",
        FieldDescriptor.TYPE_UINT32: "uint32",
        FieldDescriptor.TYPE_SFIXED32: "sfixed32",
        FieldDescriptor.TYPE_SFIXED64: "sfixed64",
        FieldDescriptor.TYPE_SINT32: "sint32",
        FieldDescriptor.TYPE_SINT64: "sint64",
    }

    def get_clean_type(fld: global___FieldDescriptorProto):
        """剥离包名，获取类名"""
        if fld.type_name:
            return fld.type_name.split(".")[-1]
        return TYPE_STR.get(fld.type, "string")

    def process_enum(enum: global___EnumDescriptorProto, indent=""):
        lines = [f"{indent}enum {enum.name} {{"]
        for v in enum.value:
            lines.append(f"{indent}  {v.name} = {v.number};")
        lines.append(f"{indent}}}")
        return lines

    def process_msg(msg: global___DescriptorProto, indent=""):
        lines = [f"{indent}message {msg.name} {{"]

        # 1. 预处理：识别 MapEntry
        map_entries = {}
        for nested in msg.nested_type:
            if nested.options.map_entry:
                k_type = get_clean_type(nested.field[0])
                v_type = get_clean_type(nested.field[1])
                map_entries[nested.name] = (k_type, v_type)

        # 2. 嵌套定义：消息与枚举
        for nested in msg.nested_type:
            if not nested.options.map_entry:
                lines.extend(process_msg(nested, f"{indent}  "))
                lines.append("")
        for enum in msg.enum_type:
            lines.extend(process_enum(enum, f"{indent}  "))
            lines.append("")

        # 3. 字段处理 (包含 Oneof 分组逻辑)
        oneof_groups: dict[int, list[global___FieldDescriptorProto]] = {}

        for fld in msg.field:
            if fld.HasField("oneof_index"):
                oneof_groups.setdefault(fld.oneof_index, []).append(fld)
                continue

            f_type_name = fld.type_name.split(".")[-1] if fld.type_name else ""
            if f_type_name in map_entries:
                # 还原为 map<k, v>
                k, v = map_entries[f_type_name]
                lines.append(f"{indent}  map<{k}, {v}> {fld.name} = {fld.number};")
            else:
                # 普通字段或 Repeated 字段
                label = (
                    "repeated " if fld.label == FieldDescriptor.LABEL_REPEATED else ""
                )
                # Proto3 显式 Optional 处理 (如果 desc 记录了该特性)
                if hasattr(fld, "proto3_optional") and fld.proto3_optional:
                    label = "optional "
                lines.append(
                    f"{indent}  {label}{get_clean_type(fld)} {fld.name} = {fld.number};"
                )

        # 4. 写入 Oneof 组
        for idx, fields in oneof_groups.items():
            oneof_name = msg.oneof_decl[idx].name
            lines.append(f"{indent}  oneof {oneof_name} {{")
            for f in fields:
                lines.append(f"{indent}    {get_clean_type(f)} {f.name} = {f.number};")
            lines.append(f"{indent}  }}")

        lines.append(f"{indent}}}")
        return lines

    # --- 开始组装文档 ---
    output = [f"// Generated from {desc_path}", 'syntax = "proto3";', ""]

    for f in fds.file:
        output.append(f"// SOURCE FILE: {f.name}")

        # 顶级枚举
        for enum in f.enum_type:
            output.extend(process_enum(enum))
            output.append("")

        # 顶级消息
        for msg in f.message_type:
            output.extend(process_msg(msg))
            output.append("")

        # 顶级服务 (gRPC)
        for svc in f.service:
            output.append(f"service {svc.name} {{")
            for m in svc.method:
                in_t = m.input_type.split(".")[-1]
                out_t = m.output_type.split(".")[-1]
                c_stream = "stream " if m.client_streaming else ""
                s_stream = "stream " if m.server_streaming else ""
                output.append(
                    f"  rpc {m.name} ({c_stream}{in_t}) returns ({s_stream}{out_t});"
                )
            output.append("}\n")

    # 写入文件
    with open(output_proto, "w", encoding="utf-8") as f_out:
        f_out.write("\n".join(output))

    print(f"✅ [成功] 完整平铺协议已还原至: {output_proto}")  # noqa: T201


# --- 执行区 ---
desc = input("请输入 desc 文件名称(当前路径下): ")
# 接着用 protoc 编译这个全量 proto 即可
run_ultimate_restore(f"{desc}.desc", f"{desc}.proto")
