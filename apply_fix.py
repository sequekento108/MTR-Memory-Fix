import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

TARGETS = {
    "org/mtr/model/StoredVertexData.class": ["write"],
    "org/mtr/model/ObjModelLoader.class": ["writeVertex"],
}

WHITE_SOURCE = "Color.WHITE"


def read_cp(data, pos):
    count = struct.unpack(">H", data[pos:pos + 2])[0]
    pos += 2
    entries = {}
    i = 1
    while i < count:
        tag = data[pos]
        pos += 1
        if tag == 1:
            ln = struct.unpack(">H", data[pos:pos + 2])[0]
            entries[i] = (tag, data[pos + 2:pos + 2 + ln])
            pos += 2 + ln
        elif tag in (7, 8, 16, 19, 20):
            entries[i] = (tag, data[pos:pos + 2])
            pos += 2
        elif tag in (9, 10, 11, 12, 17, 18):
            entries[i] = (tag, data[pos:pos + 4])
            pos += 4
        elif tag == 15:
            entries[i] = (tag, data[pos:pos + 3])
            pos += 3
        elif tag in (3, 4):
            entries[i] = (tag, data[pos:pos + 4])
            pos += 4
        elif tag in (5, 6):
            entries[i] = (tag, data[pos:pos + 8])
            pos += 8
            i += 2
            continue
        else:
            raise Exception("unknown CP tag %d at index %d" % (tag, i))
        i += 1
    return count, entries, pos


def utf8(entries, idx):
    tag, raw = entries[idx]
    assert tag == 1
    return raw.decode("utf-8")


def color_refs(entries):
    color_class = next(idx for idx, (t, r) in entries.items() if t == 7 and utf8(entries, struct.unpack(">H", r[:2])[0]) == "java/awt/Color")

    def is_white_init(r):
        if struct.unpack(">H", r[:2])[0] != color_class:
            return False
        _, nraw = entries[struct.unpack(">H", r[2:4])[0]]
        nm = struct.unpack(">H", nraw[:2])[0]
        ds = struct.unpack(">H", nraw[2:4])[0]
        return utf8(entries, nm) == "<init>" and utf8(entries, ds) == "(IIII)V"

    color_init = next(idx for idx, (t, r) in entries.items() if t == 10 and is_white_init(r))
    return color_class, color_init


def ensure_white_fieldref(data):
    count, entries, cp_end = read_cp(data, 8)
    color_class, _ = color_refs(entries)
    for idx, (tag, raw) in entries.items():
        if tag == 9:
            cls = struct.unpack(">H", raw[:2])[0]
            nat = struct.unpack(">H", raw[2:4])[0]
            _, nraw = entries[nat]
            nm = struct.unpack(">H", nraw[:2])[0]
            if cls == color_class and utf8(entries, nm) == "WHITE":
                return data, idx, False
    desc_idx = next(idx for idx, (t, r) in entries.items() if t == 1 and r.decode() == "Ljava/awt/Color;")
    new_cp = bytearray()
    white_utf = count
    count += 1
    new_cp.extend(b"\x01" + struct.pack(">H", len(b"WHITE")) + b"WHITE")
    nat_idx = count
    count += 1
    new_cp.extend(b"\x0c" + struct.pack(">HH", white_utf, desc_idx))
    field_idx = count
    count += 1
    new_cp.extend(b"\x09" + struct.pack(">HH", color_class, nat_idx))
    cp_start = 8 + 2
    data = data[:8] + struct.pack(">H", count) + data[cp_start:cp_end] + bytes(new_cp) + data[cp_end:]
    return data, field_idx, True


def patch_methods(data, method_names):
    data, white_field_idx, _ = ensure_white_fieldref(data)
    _, entries, pos = read_cp(data, 8)
    names = {idx: raw.decode("utf-8") for idx, (tag, raw) in entries.items() if tag == 1}
    color_class, color_init = color_refs(entries)
    pat = bytes([0xBB, (color_class >> 8) & 0xFF, color_class & 0xFF, 0x59]) + bytes([0x11, 0, 0xFF]) * 4 + bytes([0xB7, (color_init >> 8) & 0xFF, color_init & 0xFF])
    rep = bytes([0xB2, (white_field_idx >> 8) & 0xFF, white_field_idx & 0xFF]) + bytes(16)
    assert len(rep) == len(pat)

    def u16():
        nonlocal pos
        v = struct.unpack(">H", data[pos:pos + 2])[0]
        pos += 2
        return v

    u16()
    u16()
    u16()
    for _ in range(u16()):
        pos += 2
    for _ in range(u16()):
        pos += 6
        for _ in range(u16()):
            pos += 2
            ln = struct.unpack(">I", data[pos:pos + 4])[0]
            pos += 4 + ln
    total = 0
    for _ in range(u16()):
        pos += 2
        name_idx = u16()
        u16()
        mname = names.get(name_idx, "?")
        for _ in range(u16()):
            an = u16()
            alen = struct.unpack(">I", data[pos:pos + 4])[0]
            pos += 4
            if names.get(an) == "Code" and mname in method_names:
                code_len = struct.unpack(">I", data[pos + 4:pos + 8])[0]
                code_off = pos + 8
                code = bytes(data[code_off:code_off + code_len])
                n = code.count(pat)
                if n == 0:
                    white_pat = bytes([0xB2, (white_field_idx >> 8) & 0xFF, white_field_idx & 0xFF])
                    assert white_pat in code, "method %s: neither white-Color allocation nor existing patch found" % mname
                    print("  %s: already patched, skipping" % mname)
                else:
                    ep = code_off + code_len
                    assert struct.unpack(">H", data[ep:ep + 2])[0] == 0, "unexpected exception table in %s" % mname
                    data[code_off:code_off + code_len] = code.replace(pat, rep)
                    total += n
                    print("  %s: replaced %d white-Color allocation(s)" % (mname, n))
            pos += alen
    return data, total


def patch_class(raw, method_names):
    data, total = patch_methods(bytearray(raw), method_names)
    return bytes(data), total


def main():
    src = sys.argv[1]
    if len(sys.argv) > 2:
        dst = sys.argv[2]
    elif src.endswith(".jar"):
        dst = src[:-4] + "-patched.jar"
    else:
        dst = src + "-patched"
    with zipfile.ZipFile(src) as zin:
        classes = {path: zin.read(path) for path in TARGETS}
    patched = {}
    for path, methods in TARGETS.items():
        print("%s:" % path)
        patched[path], n = patch_class(classes[path], methods)
        print("  total replaced: %d" % n)
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(tmp + "/org/mtr/model", exist_ok=True)
        for path, data in patched.items():
            with open(tmp + "/" + path, "wb") as f:
                f.write(data)
        shutil.copy(src, tmp + "/out.jar")
        for path in patched:
            subprocess.run(["zip", "-q", tmp + "/out.jar", path], cwd=tmp, check=True)
        shutil.move(tmp + "/out.jar", dst)
    print("wrote %s" % dst)


if __name__ == "__main__":
    main()
