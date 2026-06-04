class SM3:
    IV: list[int] = []  # noqa: RUF012
    for i in range(8):
        IV.append(0)
        IV[i] = (
            int(
                "7380166f4914b2b9172442d7da8a0600a96f30bc163138aae38dee4db0fb0e4e",
                16,
            )
            >> ((7 - i) * 32)
        ) & 0xFFFFFFFF

    @staticmethod
    def rotate_left(a: int, k: int) -> int:
        k %= 32
        return ((a << k) & 0xFFFFFFFF) | ((a & 0xFFFFFFFF) >> (32 - k))

    T_j: list[int] = []  # noqa: RUF012
    for i in range(16):
        T_j.append(0)
        T_j[i] = 0x79CC4519
    for i in range(16, 64):
        T_j.append(0)
        T_j[i] = 0x7A879D8A

    @staticmethod
    def FF_j(X: int, Y: int, Z: int, j: int) -> int:
        if 0 <= j < 16:
            ret = X ^ Y ^ Z
        elif 16 <= j < 64:
            ret = (X & Y) | (X & Z) | (Y & Z)
        return ret  # pyright: ignore[reportPossiblyUnboundVariable]

    @staticmethod
    def GG_j(X: int, Y: int, Z: int, j: int) -> int:
        if 0 <= j < 16:
            ret = X ^ Y ^ Z
        elif 16 <= j < 64:
            ret = (X & Y) | ((~X) & Z)
        return ret  # pyright: ignore[reportPossiblyUnboundVariable]

    @staticmethod
    def P_0(X: int) -> int:
        return X ^ (SM3.rotate_left(X, 9)) ^ (SM3.rotate_left(X, 17))

    @staticmethod
    def P_1(X: int) -> int:
        return X ^ (SM3.rotate_left(X, 15)) ^ (SM3.rotate_left(X, 23))

    @staticmethod
    def CF(V_i: list[int], B_i: list[int]) -> list[int]:
        W: list[int] = []
        for i in range(16):
            weight = 0x1000000
            data = 0
            for k in range(i * 4, (i + 1) * 4):
                data = data + B_i[k] * weight
                weight = int(weight / 0x100)
            W.append(data)

        for j in range(16, 68):
            W.append(0)
            W[j] = (
                SM3.P_1(W[j - 16] ^ W[j - 9] ^ (SM3.rotate_left(W[j - 3], 15)))
                ^ (SM3.rotate_left(W[j - 13], 7))
                ^ W[j - 6]
            )
        W_1: list[int] = []
        for j in range(64):
            W_1.append(0)
            W_1[j] = W[j] ^ W[j + 4]

        A, B, C, D, E, F, G, H = V_i
        for j in range(64):
            SS1 = SM3.rotate_left(
                ((SM3.rotate_left(A, 12)) + E + (SM3.rotate_left(SM3.T_j[j], j)))
                & 0xFFFFFFFF,
                7,
            )
            SS2 = SS1 ^ (SM3.rotate_left(A, 12))
            TT1 = (SM3.FF_j(A, B, C, j) + D + SS2 + W_1[j]) & 0xFFFFFFFF
            TT2 = (SM3.GG_j(E, F, G, j) + H + SS1 + W[j]) & 0xFFFFFFFF
            D = C
            C = SM3.rotate_left(B, 9)
            B = A
            A = TT1
            H = G
            G = SM3.rotate_left(F, 19)
            F = E
            E = SM3.P_0(TT2)

            A = A & 0xFFFFFFFF
            B = B & 0xFFFFFFFF
            C = C & 0xFFFFFFFF
            D = D & 0xFFFFFFFF
            E = E & 0xFFFFFFFF
            F = F & 0xFFFFFFFF
            G = G & 0xFFFFFFFF
            H = H & 0xFFFFFFFF

        return [
            A ^ V_i[0],
            B ^ V_i[1],
            C ^ V_i[2],
            D ^ V_i[3],
            E ^ V_i[4],
            F ^ V_i[5],
            G ^ V_i[6],
            H ^ V_i[7],
        ]

    @staticmethod
    def hash_msg(msg: list[int]) -> list[int]:
        len1 = len(msg)
        reserve1 = len1 % 64
        msg.append(0x80)
        reserve1 = reserve1 + 1
        range_end = 56
        if reserve1 > range_end:
            range_end += 64

        for i in range(reserve1, range_end):
            msg.append(0x00)

        bit_length = (len1) * 8
        bit_length_str: list[int] = [bit_length % 0x100]
        for i in range(7):
            bit_length = int(bit_length / 0x100)
            bit_length_str.append(bit_length % 0x100)
        for i in range(8):
            msg.append(bit_length_str[7 - i])

        group_count = round(len(msg) / 64)

        B: list[list[int]] = []
        for i in range(group_count):
            B.append(msg[i * 64 : (i + 1) * 64])

        V: list[list[int]] = [SM3.IV]
        for i in range(group_count):
            V.append(SM3.CF(V[i], B[i]))

        y = V[i + 1]  # pyright: ignore[reportPossiblyUnboundVariable]
        result = ""
        for i in y:
            result = f"{result}{i:08x}"
        return list(bytes.fromhex(result))

    @staticmethod
    def bytes2list(msg: bytes) -> list[int]:
        msg_bytearray = msg
        return [msg_bytearray[i] for i in range(len(msg_bytearray))]

    @staticmethod
    def sum(msg: str | bytes | list[int]) -> list[int]:
        """
        :param msg: 需要加密的字符串
        :return: 64位SM3加密结果
        """
        if isinstance(msg, list):
            return SM3.hash_msg(msg)
        return SM3.hash_msg(
            SM3.bytes2list(msg.encode() if isinstance(msg, str) else msg)
        )


if __name__ == "__main__":
    r = SM3.sum("SM3Test")
    print(r)  # noqa: T201
    print(  # noqa: T201
        r
        == [
            144,
            16,
            83,
            180,
            104,
            20,
            131,
            183,
            55,
            221,
            45,
            217,
            249,
            167,
            245,
            104,
            5,
            170,
            27,
            3,
            51,
            127,
            140,
            26,
            187,
            118,
            58,
            150,
            119,
            107,
            137,
            5,
        ]
    )
