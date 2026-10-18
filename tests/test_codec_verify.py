"""Codec framing and captured-byte scope; all fixtures remain offline.

HEVC is the first complete coded picture from FFmpeg FATE's
https://fate-suite.ffmpeg.org/hevc-conformance/AMVP_A_MTK_4.bit .
AVC and AV1 are complete independently captured NvencTap AUs from the existing
2026-10-16/18 driver investigations. Fixtures retain encoded bytes, not logs or
metadata about a running device. Compressed text keeps source size manageable.
"""
import base64
import hashlib
import os
from pathlib import Path
import random
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from colourlab.codec_verify import CODECS, MAX_SAMPLE_BYTES, identify_codec, read_host_dump, verify_dump

H264 = zlib.decompress(base64.b64decode(
    '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'
))

HEVC = zlib.decompress(base64.b64decode(
    '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'
))

AV1 = zlib.decompress(base64.b64decode(
    'eNoBVwCo/xIACgwAAACOsv/f/AIZyEAyRRABCEEBBBBAQABACAEgGCATzUks7dZzQc0cBxiS5R1wdzSEichNVpgC'
    'FdjbfHq0eWDligX4Xgt5jtV6sBPPlmRiavqOWKuAILA='
))



def record(data, index=0, total=None):
    return struct.pack("<6I", 0x31415547, index, 3, index + 17,
                       len(data) if total is None else total, len(data)) + data


class CodecTests(unittest.TestCase):
    def test_independent_encoded_samples_identify_distinct_framing_and_profiles(self):
        for expected, data, dimensions in (("H.264", H264, (1024, 4096)),
                                            ("HEVC", HEVC, (416, 240)),
                                            ("AV1", AV1, (1536, 6144))):
            with self.subTest(codec=expected):
                result = identify_codec(data)
                self.assertEqual(result["detected_codec"], expected)
                self.assertEqual((result["details"]["coded_width"], result["details"]["coded_height"]), dimensions)
        self.assertEqual(CODECS, ("H.264", "HEVC", "AV1"))
        self.assertEqual(identify_codec(AV1)["details"]["bit_depth"], 10)

    def test_unsupported_containers_empty_headers_and_random_input_fail_closed(self):
        rng = random.Random(18)
        values = [b"", b"AV1", b"\0\0\0\1\x67", b"\0\0\1\x40\x01",
                  b"\x0a\x01\x00", b"\x32\x08abcdefgh", b"RIFF" + AV1, b"AV01" + AV1,
                  bytes(MAX_SAMPLE_BYTES + 1)]
        values += [rng.randbytes(rng.randrange(1, 500)) for _ in range(100)]
        for value in values:
            with self.subTest(length=len(value)), self.assertRaises(ValueError):
                identify_codec(value)

    def test_nal_forbidden_header_missing_parameter_sets_and_empty_tail_reject(self):
        for data in (H264.replace(b"\x00\x00\x00\x01\x67", b"\x00\x00\x00\x01\xe7", 1),
                     HEVC.replace(b"\x00\x00\x00\x01\x40\x01", b"\x00\x00\x00\x01\x40\x00", 1),
                     H264[:35], HEVC[:30], H264 + b"\x00\x00\x00\x01", HEVC + b"\x00\x00\x01"):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                identify_codec(data)

    def test_av1_truncation_bad_reserved_bits_lengths_and_missing_frames_reject(self):
        values = [AV1[:-1], AV1[:16], AV1[:15], AV1[:14], AV1[:2] + AV1[16:],
                  b"\x13\x00" + AV1[2:], b"\x16\x01\x00" + AV1[2:],
                  b"\x0a" + b"\xff" * 8, b"\x0a\xff\xff\xff\x7f",
                  AV1[:16] + b"\x32\x00", AV1[:16] + b"\x32\x08" + bytes(8),
                  AV1[:16] + b"\x32\x08\x80abcdefg"]
        for data in values:
            with self.subTest(data=data[:20].hex()), self.assertRaises(ValueError):
                identify_codec(data)

    def test_multiple_valid_parser_candidates_are_rejected(self):
        # Ambiguity is a defensive condition, never resolved by parser order.
        with patch("colourlab.codec_verify._av1", return_value={}), self.assertRaisesRegex(ValueError, "Ambiguous"):
            identify_codec(H264)

    def test_unit_count_is_bounded_independently_of_sample_byte_limit(self):
        for data in (b"\x12\x00" * 5000 + AV1, b"\x00\x00\x01\x09\x10" * 5000 + H264):
            with self.assertRaises(ValueError):
                identify_codec(data)


class HostDumpTests(unittest.TestCase):
    def setUp(self):
        root = Path(os.environ.get("COLOURLAB_OUTPUT_ROOT", Path(__file__).resolve().parents[2] / "builds" / "SteamVRColourLab")).resolve()
        temporary_root = root / "build" / "codec-test-temp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / "gxr_au_dump.bin"

    def test_complete_au_bytes_hash_and_original_indices_are_preserved(self):
        self.path.write_bytes(record(AV1, 7))
        rows = read_host_dump(self.path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["data"], AV1)
        self.assertEqual(rows[0]["index"], 7)
        self.assertEqual(rows[0]["frame_index"], 24)
        self.assertEqual(rows[0]["sha256"], hashlib.sha256(AV1).hexdigest())
        self.assertEqual(rows[0]["skipped_records"], 0)

    def test_known_cap_and_size_only_records_cannot_supply_codec_evidence(self):
        self.path.write_bytes(record(AV1) + record(AV1[:10], 1, len(AV1)) + record(b"", 2, 999))
        rows = read_host_dump(self.path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["skipped_records"], 2)
        result = verify_dump(self.path, "AV1")
        self.assertEqual(result["status"], "sample_match")
        self.assertEqual(result["skipped_records"], 2)
        self.assertEqual(result["scope"], "captured sample only")
        self.assertIn("No session identity", result["message"])
        self.assertNotIn("verified", result["status"])
        self.path.write_bytes(record(AV1[:10], 0, len(AV1)) + record(b"", 1, 999))
        self.assertEqual(read_host_dump(self.path), [])
        self.assertEqual(verify_dump(self.path, "AV1")["status"], "inconclusive")

    def test_truncated_bad_magic_impossible_size_and_empty_files_reject_all(self):
        for data in (b"", b"GUA1", record(AV1)[:-1], record(AV1) + b"GUA1",
                     b"GAU1" + record(AV1)[4:], struct.pack("<6I", 0x31415547, 0, 0, 0, 1, 2) + b"ab",
                     struct.pack("<6I", 0x31415547, 0, 0, 0, 0xffffffff, 0),
                     struct.pack("<6I", 0x31415547, 0, 0, 0, 0, 0)):
            with self.subTest(length=len(data)):
                self.path.write_bytes(data)
                with self.assertRaises(ValueError):
                    read_host_dump(self.path)
                self.assertEqual(verify_dump(self.path, "AV1")["status"], "inconclusive")

    def test_large_file_rejected_before_opening_payload(self):
        self.path.write_bytes(record(AV1))
        with patch("colourlab.codec_verify.Path.stat") as stat:
            stat.return_value.st_size = MAX_SAMPLE_BYTES + 1
            with self.assertRaisesRegex(ValueError, "exceeds"):
                read_host_dump(self.path)

    def test_expected_codec_does_not_influence_detected_codec(self):
        self.path.write_bytes(record(AV1))
        result = verify_dump(self.path, "HEVC")
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["detected_codec"], "AV1")
        self.assertEqual(result["sha256"], hashlib.sha256(AV1).hexdigest())
        self.assertEqual(result["dump_sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(result["source"], str(self.path.resolve()))
        with self.assertRaises(ValueError):
            verify_dump(self.path, "automatic")

    def test_conflicting_complete_records_are_mismatch(self):
        self.path.write_bytes(record(AV1) + record(H264, 1))
        result = verify_dump(self.path, "AV1")
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["detected_codec"], "mixed")

    def test_missing_file_and_raw_bytes_cannot_claim_live_verification(self):
        self.assertEqual(verify_dump(self.path, "AV1")["status"], "inconclusive")
        self.path.write_bytes(AV1)
        self.assertEqual(verify_dump(self.path, "AV1")["status"], "inconclusive")
