from base64 import b64decode
from dataclasses import dataclass
import math

KUWO_SECRET_KEY: bytes = b"ylzsxkwm"
QMC_RAW_KEY_LENGTHS: tuple[int, int] = (704, 364)
QMC_V2_KEY_PREFIX: bytes = b"QQMusic EncV2,Key:"
RC4_FIRST_SEGMENT_SIZE = 128
RC4_SEGMENT_SIZE = 5120

# fmt: off
ARRAY_E = [
    31, 0, 1, 2, 3, 4, -1, -1, 3, 4, 5, 6, 7, 8, -1, -1, 7, 8, 9, 10, 11, 12, -1, -1, 11, 12, 13,
    14, 15, 16, -1, -1, 15, 16, 17, 18, 19, 20, -1, -1, 19, 20, 21, 22, 23, 24, -1, -1, 23, 24, 25,
    26, 27, 28, -1, -1, 27, 28, 29, 30, 31, 30, -1, -1
]
ARRAY_IP = [
    57, 49, 41, 33, 25, 17, 9, 1, 59, 51, 43, 35, 27, 19, 11, 3, 61, 53, 45, 37, 29, 21, 13, 5, 63,
    55, 47, 39, 31, 23, 15, 7, 56, 48, 40, 32, 24, 16, 8, 0, 58, 50, 42, 34, 26, 18, 10, 2, 60, 52,
    44, 36, 28, 20, 12, 4, 62, 54, 46, 38, 30, 22, 14, 6
]
ARRAY_IP_1 = [
    39, 7, 47, 15, 55, 23, 63, 31, 38, 6, 46, 14, 54, 22, 62, 30, 37, 5, 45, 13, 53, 21, 61, 29,
    36, 4, 44, 12, 52, 20, 60, 28, 35, 3, 43, 11, 51, 19, 59, 27, 34, 2, 42, 10, 50, 18, 58, 26,
    33, 1, 41, 9, 49, 17, 57, 25, 32, 0, 40, 8, 48, 16, 56, 24
]
ARRAY_LS = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1]
ARRAY_LS_MASK = [0, 0x100001, 0x300003]
ARRAY_P = [
    15, 6, 19, 20, 28, 11, 27, 16, 0, 14, 22, 25, 4, 17, 30, 9, 1, 7, 23, 13, 31, 26, 2, 8, 18, 12,
    29, 5, 21, 10, 3, 24
]
ARRAY_PC_1 = [
    56, 48, 40, 32, 24, 16, 8, 0, 57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2, 59,
    51, 43, 35, 62, 54, 46, 38, 30, 22, 14, 6, 61, 53, 45, 37, 29, 21, 13, 5, 60, 52, 44, 36, 28,
    20, 12, 4, 27, 19, 11, 3
]
ARRAY_PC_2 = [
    13, 16, 10, 23, 0, 4, -1, -1, 2, 27, 14, 5, 20, 9, -1, -1, 22, 18, 11, 3, 25, 7, -1, -1, 15, 6,
    26, 19, 12, 1, -1, -1, 40, 51, 30, 36, 46, 54, -1, -1, 29, 39, 50, 44, 32, 47, -1, -1, 43, 48,
    38, 55, 33, 52, -1, -1, 45, 41, 49, 35, 28, 31, -1, -1
]
MATRIX_NS_BOX = [
    [
        14, 4, 3, 15, 2, 13, 5, 3, 13, 14, 6, 9, 11, 2, 0, 5, 4, 1, 10, 12, 15, 6, 9, 10, 1, 8, 12,
        7, 8, 11, 7, 0, 0, 15, 10, 5, 14, 4, 9, 10, 7, 8, 12, 3, 13, 1, 3, 6, 15, 12, 6, 11, 2, 9,
        5, 0, 4, 2, 11, 14, 1, 7, 8, 13
    ],
    [
        15, 0, 9, 5, 6, 10, 12, 9, 8, 7, 2, 12, 3, 13, 5, 2, 1, 14, 7, 8, 11, 4, 0, 3, 14, 11, 13,
        6, 4, 1, 10, 15, 3, 13, 12, 11, 15, 3, 6, 0, 4, 10, 1, 7, 8, 4, 11, 14, 13, 8, 0, 6, 2, 15,
        9, 5, 7, 1, 10, 12, 14, 2, 5, 9
    ],
    [
        10, 13, 1, 11, 6, 8, 11, 5, 9, 4, 12, 2, 15, 3, 2, 14, 0, 6, 13, 1, 3, 15, 4, 10, 14, 9, 7,
        12, 5, 0, 8, 7, 13, 1, 2, 4, 3, 6, 12, 11, 0, 13, 5, 14, 6, 8, 15, 2, 7, 10, 8, 15, 4, 9,
        11, 5, 9, 0, 14, 3, 10, 7, 1, 12
    ],
    [
        7, 10, 1, 15, 0, 12, 11, 5, 14, 9, 8, 3, 9, 7, 4, 8, 13, 6, 2, 1, 6, 11, 12, 2, 3, 0, 5,
        14, 10, 13, 15, 4, 13, 3, 4, 9, 6, 10, 1, 12, 11, 0, 2, 5, 0, 13, 14, 2, 8, 15, 7, 4, 15,
        1, 10, 7, 5, 6, 12, 11, 3, 8, 9, 14
    ],
    [
        2, 4, 8, 15, 7, 10, 13, 6, 4, 1, 3, 12, 11, 7, 14, 0, 12, 2, 5, 9, 10, 13, 0, 3, 1, 11, 15,
        5, 6, 8, 9, 14, 14, 11, 5, 6, 4, 1, 3, 10, 2, 12, 15, 0, 13, 2, 8, 5, 11, 8, 0, 15, 7, 14,
        9, 4, 12, 7, 10, 9, 1, 13, 6, 3
    ],
    [
        12, 9, 0, 7, 9, 2, 14, 1, 10, 15, 3, 4, 6, 12, 5, 11, 1, 14, 13, 0, 2, 8, 7, 13, 15, 5, 4,
        10, 8, 3, 11, 6, 10, 4, 6, 11, 7, 9, 0, 6, 4, 2, 13, 1, 9, 15, 3, 8, 15, 3, 1, 14, 12, 5,
        11, 0, 2, 12, 14, 7, 5, 10, 8, 13
    ],
    [
        4, 1, 3, 10, 15, 12, 5, 0, 2, 11, 9, 6, 8, 7, 6, 9, 11, 4, 12, 15, 0, 3, 10, 5, 14, 13, 7,
        8, 13, 14, 1, 2, 13, 6, 14, 9, 4, 1, 2, 14, 11, 13, 5, 0, 1, 10, 8, 3, 0, 11, 3, 5, 9, 4,
        15, 2, 7, 8, 12, 15, 10, 7, 6, 12
    ],
    [
        13, 7, 10, 0, 6, 9, 5, 15, 8, 4, 3, 10, 11, 14, 12, 5, 2, 11, 9, 6, 15, 12, 0, 3, 4, 1, 14,
        13, 1, 2, 7, 8, 1, 2, 12, 15, 10, 4, 0, 3, 13, 14, 6, 9, 7, 8, 9, 6, 15, 1, 5, 12, 3, 10,
        14, 5, 8, 7, 11, 0, 4, 13, 2, 11
    ],
]
QMC_V2_DERIVE_KEY_1 = bytes(
    [
        0x33, 0x38, 0x36, 0x5A,
        0x4A, 0x59, 0x21, 0x40,
        0x23, 0x2A, 0x24, 0x25,
        0x5E, 0x26, 0x29, 0x28,
    ]
)
QMC_V2_DERIVE_KEY_2 = bytes(
    [
        0x2A, 0x2A, 0x23, 0x21,
        0x28, 0x23, 0x24, 0x25,
        0x26, 0x5E, 0x61, 0x31,
        0x63, 0x5A, 0x2C, 0x54,
    ]
)
# fmt: on


class QmcError(Exception):
    pass


def simple_make_key(salt: int, length: int) -> bytes:
    key = bytearray(length)
    UINT64_MAX = 18446744073709551615
    for index in range(length):
        val = abs(math.tan(float(salt) + float(index) * 0.1)) * 100.0
        val_u64 = UINT64_MAX if val >= UINT64_MAX or math.isnan(val) else int(val)
        key[index] = val_u64 & 0xFF
    return bytes(key)


def tea_decrypt_block(block: bytes, key: bytes | bytearray) -> bytes:
    if len(block) < 8:
        raise QmcError("invalid tea block")
    v0 = int.from_bytes(block[:4], "big")
    v1 = int.from_bytes(block[4:8], "big")
    if len(key) < 16:
        raise QmcError("invalid tea key")
    k0 = int.from_bytes(key[:4], "big")
    k1 = int.from_bytes(key[4:8], "big")
    k2 = int.from_bytes(key[8:12], "big")
    k3 = int.from_bytes(key[12:16], "big")
    delta = 0x9E37_79B9
    sum_value = (delta * 16) & 0xFFFFFFFF
    for _ in range(16):
        part_v1_1 = ((v0 << 4) + k2) & 0xFFFFFFFF
        part_v1_2 = (v0 + sum_value) & 0xFFFFFFFF
        part_v1_3 = ((v0 >> 5) + k3) & 0xFFFFFFFF
        v1 = (v1 - (part_v1_1 ^ part_v1_2 ^ part_v1_3)) & 0xFFFFFFFF

        part_v0_1 = ((v1 << 4) + k0) & 0xFFFFFFFF
        part_v0_2 = (v1 + sum_value) & 0xFFFFFFFF
        part_v0_3 = ((v1 >> 5) + k1) & 0xFFFFFFFF
        v0 = (v0 - (part_v0_1 ^ part_v0_2 ^ part_v0_3)) & 0xFFFFFFFF

        sum_value = (sum_value - delta) & 0xFFFFFFFF

    return v0.to_bytes(4, "big") + v1.to_bytes(4, "big")


def xor_8_bytes(left: bytes | bytearray, right: bytes | bytearray) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right, strict=True))


def decrypt_tencent_tea(input_buffer: bytes, key: bytes | bytearray) -> bytes:
    SALT_LEN = 2
    ZERO_LEN = 7
    if len(input_buffer) % 8 != 0:
        raise QmcError("inBuf size not a multiple of the block size")
    if len(input_buffer) < 16:
        raise QmcError("inBuf size too small")
    # 初始块解密
    decrypted_block = bytearray(tea_decrypt_block(input_buffer[:8], key))
    pad_len = decrypted_block[0] & 0x7
    output_len = len(input_buffer) - 1 - pad_len - SALT_LEN - ZERO_LEN
    if output_len < 0:
        raise QmcError("invalid TEA padding length")
    output = bytearray(output_len)
    iv_prev = bytearray(8)
    iv_cur = bytearray(input_buffer[:8])
    input_pos = 8
    dest_idx = 1 + pad_len

    def decrypt_next_block():
        nonlocal decrypted_block, iv_prev, iv_cur, input_pos, dest_idx

        iv_prev[:] = iv_cur
        if input_pos + 8 > len(input_buffer):
            raise QmcError("unexpected end of tea buffer")
        next_block = input_buffer[input_pos : input_pos + 8]
        iv_cur[:] = next_block
        xored = xor_8_bytes(decrypted_block, iv_cur)
        decrypted_block[:] = tea_decrypt_block(xored, key)
        input_pos += 8
        dest_idx = 0

    salt_index = 1
    while salt_index <= SALT_LEN:
        if dest_idx < 8:
            dest_idx += 1
            salt_index += 1
        else:
            decrypt_next_block()

    output_pos = 0
    while output_pos < output_len:
        if dest_idx < 8:
            output[output_pos] = decrypted_block[dest_idx] ^ iv_prev[dest_idx]
            dest_idx += 1
            output_pos += 1
        else:
            decrypt_next_block()

    zero_index = 1
    while zero_index <= ZERO_LEN:
        if dest_idx < 8:
            if decrypted_block[dest_idx] != iv_prev[dest_idx]:
                raise QmcError("zero check failed")
            dest_idx += 1
            zero_index += 1
        else:
            decrypt_next_block()
    return bytes(output)


def derive_key_v1(raw_key_decoded: bytes) -> bytes:
    if len(raw_key_decoded) < 16:
        raise QmcError("key length is too short")
    simple_key = simple_make_key(106, 8)
    tea_key_buf = bytearray(16)
    for index in range(8):
        tea_key_buf[index << 1] = simple_key[index]
        tea_key_buf[(index << 1) + 1] = raw_key_decoded[index]
    tea_key = bytes(tea_key_buf)
    decrypted = decrypt_tencent_tea(raw_key_decoded[8:], tea_key)
    return raw_key_decoded[:8] + decrypted


def derive_key_v2(raw_key: bytes) -> bytes:
    try:
        buffer = decrypt_tencent_tea(raw_key, QMC_V2_DERIVE_KEY_1)
        buffer = decrypt_tencent_tea(buffer, QMC_V2_DERIVE_KEY_2)
    except QmcError as e:
        raise QmcError(f"TEA decryption chain failed in v2: {e}") from e

    try:
        return b64decode(buffer)
    except Exception as e:
        raise QmcError(f"Base64 decode failed for derived v2 key: {e}") from e


def derive_qmc_key(raw_key: bytes) -> bytes:
    decoded = b64decode(raw_key)
    if decoded.startswith(QMC_V2_KEY_PREFIX):
        decoded = derive_key_v2(decoded[len(QMC_V2_KEY_PREFIX) :])
    return derive_key_v1(decoded)


@dataclass
class MapCipher:
    key: bytes
    size: int = 0

    def __post_init__(self):
        if not self.key:
            raise QmcError("qmc map cipher key cannot be empty")
        self.size = len(self.key)

    @staticmethod
    def rotate(value: int, bits: int) -> int:
        rotate = (bits + 4) % 8
        left = (value << rotate) & 0xFF
        right = value >> rotate
        return left | right

    def get_mask(self, offset: int) -> int:
        normalized_offset = offset % 0x7FFF if offset > 0x7FFF else offset
        index = ((normalized_offset * normalized_offset) + 71214) % self.size
        return self.rotate(self.key[index], index & 0x7)

    def decrypt(self, buffer: bytearray, offset: int) -> None:
        # 原地异或解密
        for i in range(len(buffer)):
            buffer[i] ^= self.get_mask(offset + i)


@dataclass
class Rc4Cipher:
    key: bytes
    size: int = 0
    box_state: bytearray = None  # pyright: ignore[reportAssignmentType]
    hash: int = 0

    def __post_init__(self) -> None:
        if not self.key:
            raise QmcError("qmc rc4 cipher key cannot be empty")
        self.size = len(self.key)
        self.box_state = bytearray((i & 0xFF) for i in range(self.size))
        j = 0
        for i in range(self.size):
            j = (j + self.box_state[i] + self.key[i % self.size]) % self.size
            self.box_state[i], self.box_state[j] = self.box_state[j], self.box_state[i]
        self.hash = self.get_hash_base(self.key)

    @staticmethod
    def get_hash_base(key: bytes) -> int:
        result = 1
        for v in key:
            if v == 0:
                continue
            next_hash = (result * v) & 0xFFFFFFFF
            if next_hash == 0 or next_hash <= result:
                break
            result = next_hash
        return result

    def get_segment_skip(self, segment_id: int) -> int:
        seed = self.key[segment_id % self.size]
        if seed == 0:
            return 0
        index = int((float(self.hash) / float((segment_id + 1) * seed)) * 100.0)
        return index % self.size

    def decrypt_first_segment(
        self, buffer: bytearray | memoryview, offset: int
    ) -> None:
        for idx in range(len(buffer)):
            buffer[idx] ^= self.key[self.get_segment_skip(offset + idx)]

    def decrypt_segment(self, buffer: bytearray | memoryview, offset: int) -> None:
        box_state = bytearray(self.box_state)
        j = 0
        k = 0
        skip_length = (offset % RC4_SEGMENT_SIZE) + self.get_segment_skip(
            offset // RC4_SEGMENT_SIZE
        )
        block_len = len(buffer)
        for index in range(skip_length + block_len):
            j = (j + 1) % self.size
            k = (box_state[j] + k) % self.size
            box_state[j], box_state[k] = box_state[k], box_state[j]

            if index >= skip_length:
                out_idx = index - skip_length
                xor_index = (box_state[j] + box_state[k]) % self.size
                buffer[out_idx] ^= box_state[xor_index]

    def decrypt(self, buffer: bytearray | memoryview, offset: int) -> None:
        to_process = len(buffer)
        processed = 0
        if offset < RC4_FIRST_SEGMENT_SIZE:
            block_size = min(to_process, RC4_FIRST_SEGMENT_SIZE - offset)
            self.decrypt_first_segment(
                memoryview(buffer)[processed : processed + block_size], offset
            )
            offset += block_size
            to_process -= block_size
            processed += block_size
            if to_process == 0:
                return

        if offset % RC4_SEGMENT_SIZE != 0:
            block_size = min(to_process, RC4_SEGMENT_SIZE - offset % RC4_SEGMENT_SIZE)
            self.decrypt_segment(
                memoryview(buffer)[processed : processed + block_size], offset
            )
            offset += block_size
            to_process -= block_size
            processed += block_size
            if to_process == 0:
                return

        while to_process > RC4_SEGMENT_SIZE:
            self.decrypt_segment(
                memoryview(buffer)[processed : processed + RC4_SEGMENT_SIZE], offset
            )
            offset += RC4_SEGMENT_SIZE
            to_process -= RC4_SEGMENT_SIZE
            processed += RC4_SEGMENT_SIZE
        if to_process > 0:
            self.decrypt_segment(memoryview(buffer)[processed:], offset)


class QmcCipher:
    def __init__(self, key: bytes):
        if not key:
            raise QmcError("QMC key cannot be empty")
        self._cipher = Rc4Cipher(key) if len(key) > 300 else MapCipher(key)

    def decrypt(self, buffer: bytearray | memoryview, offset: int) -> None:
        self._cipher.decrypt(buffer, offset)  # pyright: ignore[reportArgumentType]
