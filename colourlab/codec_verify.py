"""Conservative identification of captured encoded bytes, never live-stream proof.

This reads codec framing, parameter-set identifiers/dimensions and coded-frame
headers. It does not decode entropy-coded pictures or establish their integrity,
delivery to a headset, decoder choice, or the identity of a running session.
Unsupported encodings and missing parameter sets deliberately remain inconclusive.
"""
from __future__ import annotations

import hashlib
from itertools import islice
from pathlib import Path
import re
import struct

CODECS = ("H.264", "HEVC", "AV1")
MAX_SAMPLE_BYTES = 16 * 1024 * 1024
_MAX_UNITS = 4096
_DUMP_HEADER = struct.Struct("<6I")
_DUMP_MAGIC = 0x31415547  # NvencTap.cpp's GAU1 constant; on disk: b"GUA1".
_START = re.compile(b"\x00\x00\x00?\x01")


class _Bits:
    def __init__(self, data):
        self.data, self.pos = data, 0

    @property
    def left(self):
        return len(self.data) * 8 - self.pos

    def u(self, count):
        if count < 0 or count > self.left:
            raise ValueError("Truncated bit header")
        result = 0
        for _ in range(count):
            result = (result << 1) | ((self.data[self.pos // 8] >> (7 - self.pos % 8)) & 1)
            self.pos += 1
        return result

    def ue(self, maximum=(1 << 31) - 1):
        zeros = 0
        while not self.u(1):
            zeros += 1
            if zeros > 31:
                raise ValueError("Unbounded Exp-Golomb header")
        value = (1 << zeros) - 1 + self.u(zeros)
        if value > maximum:
            raise ValueError("Out-of-range bit header")
        return value

    def se(self):
        v = self.ue()
        return (v + 1) // 2 if v & 1 else -(v // 2)

    def trailing(self):
        if self.left > 8 or self.u(1) != 1 or self.u(self.left) != 0:
            raise ValueError("Invalid trailing bits")


def _rbsp(data):
    """Remove and validate byte-stream emulation prevention bytes."""
    out = bytearray()
    zeros = 0
    i = 0
    while i < len(data):
        b = data[i]
        if zeros == 2:
            if b == 3:
                if i + 1 >= len(data) or data[i + 1] > 3:
                    raise ValueError("Invalid emulation-prevention byte")
                zeros = 0
                i += 1
                continue
            if b < 3:
                raise ValueError("Unescaped start-code emulation")
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
        i += 1
    return bytes(out)


def _annex_b(data):
    starts = list(islice(_START.finditer(data), _MAX_UNITS + 1))
    if len(starts) > _MAX_UNITS:
        raise ValueError("Too many Annex-B units in one sample")
    if not starts or any(data[:starts[0].start()]):
        raise ValueError("Missing Annex-B start code")
    units = []
    for i, start in enumerate(starts):
        stop = starts[i + 1].start() if i + 1 < len(starts) else len(data)
        unit = data[start.end():stop].rstrip(b"\x00")
        if not unit:
            raise ValueError("Empty Annex-B NAL unit")
        units.append(unit)
    return units


def _h264_sps(payload):
    b = _Bits(payload)
    profile = b.u(8)
    if profile not in (66, 77, 88, 100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135):
        raise ValueError("Unknown AVC profile")
    if b.u(8) & 3:
        raise ValueError("Reserved AVC constraint bits")
    level = b.u(8)
    if level == 0 or level > 62:
        raise ValueError("Invalid AVC level")
    ident = b.ue(31)
    chroma = 1
    if profile not in (66, 77, 88):
        chroma = b.ue(3)
        if chroma == 3:
            b.u(1)
        b.ue(6)
        b.ue(6)
        b.u(1)
        if b.u(1):
            for i in range(12 if chroma == 3 else 8):
                if b.u(1):
                    last = next_scale = 8
                    for _ in range(16 if i < 6 else 64):
                        if next_scale:
                            next_scale = (last + b.se() + 256) % 256
                        last = next_scale or last
    b.ue(12)  # log2_max_frame_num_minus4
    poc = b.ue(2)
    if poc == 0:
        b.ue(12)
    elif poc == 1:
        b.u(1)
        b.se()
        b.se()
        for _ in range(b.ue(255)):
            b.se()
    b.ue(16)
    b.u(1)
    width, height = 16 * (b.ue(4095) + 1), 16 * (b.ue(4095) + 1)
    frame_only = b.u(1)
    if not frame_only:
        b.u(1)
        height *= 2
    b.u(1)
    if b.u(1):
        for _ in range(4):
            b.ue(65535)
    # The VUI is not needed for identity. A present VUI must at least have
    # bytes beyond the flag; decoding its timing/color metadata is out of scope.
    if b.u(1):
        if b.left < 8 or not payload[-1]:
            raise ValueError("Truncated AVC VUI")
    else:
        b.trailing()
    return ident, {"profile_idc": profile, "coded_width": width, "coded_height": height}


def _h264(units):
    sps, pps, frames, types = {}, {}, [], []
    for unit in units:
        if unit[0] & 0x80:
            raise ValueError("AVC forbidden_zero_bit")
        kind, ref = unit[0] & 31, (unit[0] >> 5) & 3
        if kind not in (1, 5, 6, 7, 8, 9, 10, 11, 12):
            raise ValueError("Unsupported AVC NAL unit")
        if (kind in (5, 7, 8) and not ref) or (kind in (6, 9, 10, 11, 12) and ref):
            raise ValueError("Invalid AVC reference header")
        types.append(kind)
        payload = _rbsp(unit[1:])
        if not payload:
            raise ValueError("Empty AVC payload")
        if kind == 7:
            ident, details = _h264_sps(payload)
            sps[ident] = details
        elif kind == 8:
            if len(payload) < 3:
                raise ValueError("Truncated AVC PPS")
            b = _Bits(payload)
            ident, parent = b.ue(255), b.ue(31)
            b.u(2)
            if b.ue(7):
                raise ValueError("AVC slice groups unsupported")
            b.ue(31)
            b.ue(31)
            b.u(3)
            b.se()
            b.se()
            b.se()
            b.u(3)
            pps[ident] = parent
        elif kind in (1, 5):
            if len(payload) < 8:
                raise ValueError("Insufficient AVC coded slice evidence")
            b = _Bits(payload)
            b.ue(16777215)
            b.ue(9)
            frames.append(b.ue(255))
    if not sps or not pps or not frames or any(p not in sps for p in pps.values()) or any(p not in pps for p in frames):
        raise ValueError("AVC SPS/PPS and referenced coded slice required")
    return {"framing": "Annex B", "nal_types": types, "coded_slices": len(frames), **next(iter(sps.values()))}


def _hevc_profile(b, sublayers):
    b.u(2)
    b.u(1)
    profile = b.u(5)
    compatibility = b.u(32)
    if not profile and not compatibility:
        raise ValueError("Missing HEVC profile")
    b.u(48)  # constraints/source flags
    level = b.u(8)
    if not level:
        raise ValueError("Missing HEVC level")
    flags = [(b.u(1), b.u(1)) for _ in range(sublayers)]
    if sublayers:
        for _ in range(sublayers, 8):
            if b.u(2):
                raise ValueError("Reserved HEVC profile bits")
    for profile_present, level_present in flags:
        if profile_present:
            b.u(88)
        if level_present:
            b.u(8)
    return profile


def _hevc(units):
    vps, sps, pps, frames, types = set(), {}, {}, [], []
    for unit in units:
        if len(unit) < 3 or unit[0] & 0x80 or not unit[1] & 7:
            raise ValueError("Invalid HEVC NAL header")
        if ((unit[0] & 1) << 5) | (unit[1] >> 3):
            raise ValueError("Multilayer HEVC unsupported")
        kind = (unit[0] >> 1) & 63
        if kind not in (*range(10), *range(16, 22), *range(32, 41)):
            raise ValueError("Reserved HEVC NAL type")
        types.append(kind)
        payload = _rbsp(unit[2:])
        b = _Bits(payload)
        if kind == 32:
            ident = b.u(4)
            b.u(2)
            if b.u(6):
                raise ValueError("Multilayer HEVC VPS unsupported")
            layers = b.u(3)
            if layers > 6:
                raise ValueError("Invalid HEVC sublayer count")
            b.u(1)
            if b.u(16) != 65535:
                raise ValueError("Invalid HEVC VPS reserved bits")
            _hevc_profile(b, layers)
            if b.left < 8:
                raise ValueError("Truncated HEVC VPS")
            vps.add(ident)
        elif kind == 33:
            parent, layers = b.u(4), b.u(3)
            if layers > 6:
                raise ValueError("Invalid HEVC sublayer count")
            b.u(1)
            profile = _hevc_profile(b, layers)
            ident, chroma = b.ue(15), b.ue(3)
            if chroma == 3:
                b.u(1)
            width, height = b.ue(65535), b.ue(65535)
            if not width or not height:
                raise ValueError("Invalid HEVC dimensions")
            if b.u(1):
                for _ in range(4):
                    b.ue(65535)
            b.ue(8)
            b.ue(8)
            b.ue(12)
            if b.left < 8:
                raise ValueError("Truncated HEVC SPS")
            sps[ident] = (parent, {"profile_idc": profile, "coded_width": width, "coded_height": height})
        elif kind == 34:
            if len(payload) < 3:
                raise ValueError("Truncated HEVC PPS")
            ident, parent = b.ue(63), b.ue(15)
            b.u(7)
            b.ue(14)
            b.ue(14)
            b.se()
            if b.left < 3:
                raise ValueError("Truncated HEVC PPS body")
            pps[ident] = parent
        elif kind < 32:
            if len(payload) < 8:
                raise ValueError("Insufficient HEVC coded slice evidence")
            first = b.u(1)
            if 16 <= kind <= 23:
                b.u(1)
            # A first slice gives an unambiguous PPS id; later dependent
            # slices require more SPS state than this identifier maintains.
            if first:
                frames.append(b.ue(63))
    if (not vps or not sps or not pps or not frames or any(v[0] not in vps for v in sps.values())
            or any(p not in sps for p in pps.values()) or any(p not in pps for p in frames)):
        raise ValueError("HEVC VPS/SPS/PPS and referenced first coded slice required")
    return {"framing": "Annex B", "nal_types": types, "first_slices": len(frames), **next(iter(sps.values()))[1]}


def _av1_sequence(payload):
    b = _Bits(payload)
    profile, still, reduced = b.u(3), b.u(1), b.u(1)
    if profile > 2 or (reduced and not still):
        raise ValueError("Invalid AV1 sequence profile/flags")
    def level():
        value = b.u(5)
        if 23 < value < 31:
            raise ValueError("Reserved AV1 sequence level")
        return value

    if reduced:
        level()
    else:
        model = delay_bits = 0
        if b.u(1):
            if not b.u(32) or not b.u(32):
                raise ValueError("Invalid AV1 sequence timing")
            if b.u(1):
                b.ue()
            model = b.u(1)
            if model:
                delay_bits = b.u(5) + 1
                b.u(32)
                b.u(10)
        display = b.u(1)
        for _ in range(b.u(5) + 1):
            b.u(12)
            if level() > 7:
                b.u(1)
            if model and b.u(1):
                b.u(2 * delay_bits + 1)
            if display and b.u(1):
                b.u(4)
    width_bits, height_bits = b.u(4) + 1, b.u(4) + 1
    width, height = b.u(width_bits) + 1, b.u(height_bits) + 1
    if not reduced and b.u(1):
        b.u(7)
    b.u(3)
    if not reduced:
        b.u(4)
        order = b.u(1)
        if order:
            b.u(2)
        screen = 2 if b.u(1) else b.u(1)
        if screen and not b.u(1):
            b.u(1)
        if order:
            b.u(3)
    b.u(3)
    depth = 10 if b.u(1) else 8
    if profile == 2 and depth == 10 and b.u(1):
        depth = 12
    mono = 0 if profile == 1 else b.u(1)
    color = (b.u(8), b.u(8), b.u(8)) if b.u(1) else (2, 2, 2)
    if mono:
        b.u(1)
    else:
        if color != (1, 13, 0):
            b.u(1)
            sx, sy = (1, 1) if profile == 0 else (0, 0)
            if profile == 2:
                sx = b.u(1) if depth == 12 else 1
                sy = b.u(1) if depth == 12 and sx else 0
            if sx and sy:
                if b.u(2) == 3:
                    raise ValueError("Reserved AV1 chroma position")
        b.u(1)
    b.u(1)
    b.trailing()
    return {"seq_profile": profile, "bit_depth": depth, "coded_width": width,
            "coded_height": height, "reduced_still_picture_header": bool(reduced)}


def _av1(data):
    offset, types, sequence, frames, pending_header = 0, [], None, 0, False
    while offset < len(data):
        if len(types) >= _MAX_UNITS:
            raise ValueError("Too many AV1 units in one sample")
        header = data[offset]
        offset += 1
        kind = (header >> 3) & 15
        if header & 0x81 or not header & 2 or kind not in (1, 2, 3, 4, 5, 6, 7, 8, 15):
            raise ValueError("Invalid or unsupported sized AV1 OBU header")
        if header & 4:
            if offset >= len(data) or data[offset] & 7:
                raise ValueError("Truncated/reserved AV1 extension header")
            offset += 1
        size = 0
        for i in range(8):
            if offset >= len(data):
                raise ValueError("Truncated AV1 OBU length")
            byte = data[offset]
            offset += 1
            size |= (byte & 127) << (7 * i)
            if not byte & 128:
                break
        else:
            raise ValueError("Unbounded AV1 OBU length")
        if size > MAX_SAMPLE_BYTES or size > len(data) - offset:
            raise ValueError("Truncated or oversized AV1 OBU")
        payload = data[offset:offset + size]
        offset += size
        types.append(kind)
        if kind == 1:
            if sequence is not None or frames or pending_header:
                raise ValueError("Multiple/late AV1 sequence headers unsupported")
            sequence = _av1_sequence(payload)
        elif kind == 2:
            if size or pending_header:
                raise ValueError("Invalid AV1 temporal delimiter")
        elif kind in (3, 6):
            if sequence is None or len(payload) < (8 if kind == 6 else 2) or not any(payload):
                raise ValueError("AV1 sequence and substantive frame payload required")
            # show_existing_frame carries no newly coded picture evidence.
            if not sequence["reduced_still_picture_header"] and payload[0] & 128:
                raise ValueError("AV1 show_existing_frame is not coded frame evidence")
            if pending_header:
                raise ValueError("AV1 frame header without its tile group")
            pending_header = kind == 3
            frames += kind == 6
        elif kind == 4:
            if not pending_header or len(payload) < 8 or not any(payload):
                raise ValueError("AV1 tile group without substantive frame header/data")
            pending_header = False
            frames += 1
        elif kind in (7, 8):
            raise ValueError("AV1 redundant/tile-list OBUs unsupported")
    if not sequence or not frames or pending_header:
        raise ValueError("AV1 sequence header and complete sized coded-frame OBU required")
    return {"framing": "size-delimited OBUs", "obu_types": types, "coded_frames": frames, **sequence}


def identify_codec(data):
    """Return structural codec evidence or raise ValueError; no picture decoding.

    Supports Annex-B AVC/HEVC and AV1 low-overhead sized OBUs. Containers,
    length-prefixed AVC/HEVC and encrypted transport payloads are unsupported.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)) or not 0 < len(data) <= MAX_SAMPLE_BYTES:
        raise ValueError("A nonempty encoded sample of at most 16 MiB is required")
    data = bytes(data)
    matches = []
    for codec, parser in (("H.264", lambda: _h264(_annex_b(data))),
                          ("HEVC", lambda: _hevc(_annex_b(data))), ("AV1", lambda: _av1(data))):
        try:
            matches.append({"detected_codec": codec, "details": parser()})
        except ValueError:
            pass
    if len(matches) != 1:
        raise ValueError("Ambiguous sample" if matches else "No complete supported codec framing and parameter/frame evidence")
    return matches[0]


def _read_host_dump(path):
    path = Path(path)
    records, skipped, digest, consumed, count = [], 0, hashlib.sha256(), 0, 0
    if path.stat().st_size > MAX_SAMPLE_BYTES:
        raise ValueError("Host dump exceeds 16 MiB limit")
    with path.open("rb") as stream:
        while True:
            raw = stream.read(_DUMP_HEADER.size)
            if not raw:
                break
            count += 1
            if count > _MAX_UNITS:
                raise ValueError("Too many host dump records")
            consumed += len(raw)
            digest.update(raw)
            if len(raw) != _DUMP_HEADER.size:
                raise ValueError("Truncated host dump record header")
            magic, index, picture_type, frame_index, total, captured = _DUMP_HEADER.unpack(raw)
            if magic != _DUMP_MAGIC or captured > total or total == 0:
                raise ValueError("Invalid host dump record header")
            if total > MAX_SAMPLE_BYTES or captured > MAX_SAMPLE_BYTES - consumed:
                raise ValueError("Oversized host dump record")
            data = stream.read(captured)
            consumed += len(data)
            digest.update(data)
            if len(data) != captured:
                raise ValueError("Truncated host dump record payload")
            if captured != total:
                skipped += 1  # Known cap and size-only rows cannot prove identity.
                continue
            records.append({"index": index, "picture_type": picture_type, "frame_index": frame_index,
                            "total_bytes": total, "captured_bytes": captured, "data": data,
                            "sha256": hashlib.sha256(data).hexdigest()})
    if not consumed:
        raise ValueError("Empty host dump")
    for record in records:
        record["skipped_records"] = skipped
    return records, skipped, digest.hexdigest()


def read_host_dump(path):
    """Read complete NvencTap legacy AU records; skip capped/size-only rows.

    Malformed framing or a truncated file rejects the entire read. This legacy
    format contains no codec label, timestamp, process id, or session identity.
    Complete rows include data, SHA256 and original indices, never inferred time.
    """
    return _read_host_dump(path)[0]


def verify_dump(path, expected_codec):
    """Compare structural evidence in a legacy dump; never report live verified."""
    if expected_codec not in CODECS:
        raise ValueError("Unsupported expected codec")
    result = {"status": "inconclusive", "detected_codec": None, "sha256": None,
              "source": str(Path(path).resolve()), "scope": "captured sample only",
              "message": "No session identity; this cannot verify a live stream."}
    try:
        records, skipped, dump_hash = _read_host_dump(path)
        result.update(dump_sha256=dump_hash, complete_records=len(records), skipped_records=skipped)
        matches = []
        for record in records:
            try:
                matches.append((record, identify_codec(record["data"])))
            except ValueError:
                continue
        if not matches:
            result["message"] = "Inconclusive: no complete AU with supported parameter-set and coded-frame evidence. Legacy dump has no session identity."
            return result
        detected = {match["detected_codec"] for _, match in matches}
        record, match = matches[0]
        result.update(detected_codec=match["detected_codec"] if len(detected) == 1 else "mixed",
                      sha256=record["sha256"], record_index=record["index"],
                      details=match["details"], identified_records=len(matches))
        result["status"] = "sample_match" if detected == {expected_codec} else "mismatch"
        result["message"] = (f"Captured sample structurally {'matches' if result['status'] == 'sample_match' else 'does not match'} {expected_codec}. "
                             "No session identity, live-stream, delivery or decoder proof; pictures were not decoded.")
    except (OSError, ValueError, OverflowError) as exc:
        result["message"] = f"Inconclusive: {exc}. Legacy dump cannot verify a live stream."
    return result
