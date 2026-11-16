# Everwood Classic fork: minimal in-memory BLP2 decoder for the model browser preview (numpy only, no bpy,
# no temp files). Supports what 1.12 / 3.3.5 data uses: palettized (encoding 1, alpha depth 0/1/4/8),
# DXT1/3/5 (encoding 2, alpha type 0/1/7) and raw BGRA (encoding 3). Picks the smallest mip level that is
# still >= `min_size` on its longest side, so previews decode fast.
# Returns an (H, W, 4) uint8 RGBA array, row 0 = top of the image (BLP order).

import struct
import numpy as np


class BLPError(Exception):
    pass


def _rgb565(c):
    r = ((c >> 11) & 31).astype(np.uint16) * 255 // 31
    g = ((c >> 5) & 63).astype(np.uint16) * 255 // 63
    b = (c & 31).astype(np.uint16) * 255 // 31
    return np.stack([r, g, b], axis=-1).astype(np.int32)


def _dxt_colors(blocks, dxt1):
    """blocks: (N, 8) uint8 colour part -> (N, 16, 4) RGBA (alpha 255, or 0 for DXT1 transparent)."""
    c0 = blocks[:, 0].astype(np.uint16) | (blocks[:, 1].astype(np.uint16) << 8)
    c1 = blocks[:, 2].astype(np.uint16) | (blocks[:, 3].astype(np.uint16) << 8)
    p0, p1 = _rgb565(c0), _rgb565(c1)
    four = (c0 > c1) | (not dxt1)
    four = four[:, None]
    p2 = np.where(four, (2 * p0 + p1) // 3, (p0 + p1) // 2)
    p3 = np.where(four, (p0 + 2 * p1) // 3, 0)
    pal = np.stack([p0, p1, p2, p3], axis=1)                         # (N, 4, 3)
    alpha = np.full((len(blocks), 4), 255, np.int32)
    if dxt1:
        alpha[:, 3] = np.where(four[:, 0], 255, 0)
    bits = blocks[:, 4:8].astype(np.uint32)
    bits = bits[:, 0] | (bits[:, 1] << 8) | (bits[:, 2] << 16) | (bits[:, 3] << 24)
    idx = (bits[:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3   # (N, 16)
    rgb = np.take_along_axis(pal, idx[:, :, None].astype(np.int64).repeat(3, 2), axis=1)
    a = np.take_along_axis(alpha, idx.astype(np.int64), axis=1)
    return np.concatenate([rgb, a[:, :, None]], axis=2)


def _dxt3_alpha(blocks):
    a = blocks[:, :8]
    lo, hi = a & 15, a >> 4
    return (np.stack([lo, hi], axis=2).reshape(len(blocks), 16).astype(np.int32) * 17)


def _dxt5_alpha(blocks):
    a0 = blocks[:, 0].astype(np.int32)
    a1 = blocks[:, 1].astype(np.int32)
    pal = np.zeros((len(blocks), 8), np.int32)
    pal[:, 0], pal[:, 1] = a0, a1
    eight = (a0 > a1)
    for i in range(1, 7):
        pal[:, i + 1] = np.where(eight, ((7 - i) * a0 + i * a1) // 7, 0)
    for i in range(1, 5):
        pal[:, i + 1] = np.where(eight, pal[:, i + 1], ((5 - i) * a0 + i * a1) // 5)
    pal[:, 6] = np.where(eight, pal[:, 6], 0)
    pal[:, 7] = np.where(eight, pal[:, 7], 255)
    bits = np.zeros(len(blocks), np.uint64)
    for i in range(6):
        bits |= blocks[:, 2 + i].astype(np.uint64) << np.uint64(8 * i)
    idx = (bits[:, None] >> (np.uint64(3) * np.arange(16, dtype=np.uint64))) & np.uint64(7)
    return np.take_along_axis(pal, idx.astype(np.int64), axis=1)


def _blocks_to_image(px, w, h):
    """px: (N, 16, 4) per 4x4 block -> (h, w, 4)."""
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    img = px.reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return img[:h, :w]


def decode(data, min_size=128):
    if len(data) < 148 or data[:4] != b'BLP2':
        raise BLPError("not a BLP2 file")
    _type, enc, alpha_depth, alpha_type, _mips = struct.unpack_from('<IBBBB', data, 4)
    w, h = struct.unpack_from('<II', data, 12)
    offs = struct.unpack_from('<16I', data, 20)
    sizes = struct.unpack_from('<16I', data, 84)

    level = 0
    while level + 1 < 16 and offs[level + 1] and sizes[level + 1] and max(w >> (level + 1), h >> (level + 1)) >= min_size:
        level += 1
    mw, mh = max(1, w >> level), max(1, h >> level)
    o, n = offs[level], sizes[level]
    raw = np.frombuffer(data, np.uint8, n, o)

    if enc == 1:                                                     # palettized
        pal = np.frombuffer(data, np.uint8, 1024, 148).reshape(256, 4)          # BGRA
        idx = raw[:mw * mh]
        rgb = pal[idx][:, [2, 1, 0]].astype(np.uint8)
        if alpha_depth == 8:
            a = raw[mw * mh:mw * mh * 2]
        elif alpha_depth == 4:
            a4 = raw[mw * mh:mw * mh + (mw * mh + 1) // 2]
            a = np.stack([a4 & 15, a4 >> 4], 1).reshape(-1)[:mw * mh] * 17
        elif alpha_depth == 1:
            a1 = raw[mw * mh:mw * mh + (mw * mh + 7) // 8]
            a = np.unpackbits(a1, bitorder='little')[:mw * mh] * 255
        else:
            a = np.full(mw * mh, 255, np.uint8)
        if len(a) < mw * mh:
            a = np.full(mw * mh, 255, np.uint8)
        return np.concatenate([rgb, a.reshape(-1, 1).astype(np.uint8)], 1).reshape(mh, mw, 4)

    if enc == 2:                                                     # DXT
        nblocks = max(1, (mw + 3) // 4) * max(1, (mh + 3) // 4)
        if alpha_type == 0 or alpha_depth <= 1:                     # DXT1
            blocks = raw[:nblocks * 8].reshape(nblocks, 8)
            px = _dxt_colors(blocks, True)
            if alpha_depth == 0:
                px[:, :, 3] = 255
        else:
            blocks = raw[:nblocks * 16].reshape(nblocks, 16)
            px = _dxt_colors(blocks[:, 8:], False)
            px[:, :, 3] = _dxt5_alpha(blocks) if alpha_type == 7 else _dxt3_alpha(blocks)
        return _blocks_to_image(px, mw, mh).astype(np.uint8)

    if enc == 3:                                                     # raw BGRA
        img = raw[:mw * mh * 4].reshape(mh, mw, 4)
        return img[:, :, [2, 1, 0, 3]].copy()

    raise BLPError("unsupported BLP encoding %d" % enc)
