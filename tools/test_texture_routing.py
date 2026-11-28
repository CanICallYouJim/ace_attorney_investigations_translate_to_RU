"""Protect existing Addressables lookups when registering translated textures."""
import base64
import json
import struct
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from picture_layer import TextureCatalog
from plates import table_rows


class SituationTableTests(unittest.TestCase):
    def test_uses_shared_key_for_plain_guid_and_keeps_named_sprite(self):
        def asset(path_id, tree):
            return SimpleNamespace(path_id=path_id, type=SimpleNamespace(name="MonoBehaviour"),
                                   read_typetree=lambda: tree)

        table = asset(3, {
            "m_SharedData": {"m_FileID": 1, "m_PathID": 4},
            "m_TableData": [
                {"m_Id": 1, "m_Localized": "guid[Situation_0_ger]"},
                {"m_Id": 2, "m_Localized": "8a1ce869b7cb4c64abacb62f7c1485a5"},
                {"m_Id": 9, "m_Localized": "other"},
            ],
        })
        shared = asset(4, {
            "m_TableCollectionName": "Image Table",
            "m_Entries": [{"m_Id": 1, "m_Key": "Situation_0"},
                          {"m_Id": 2, "m_Key": "Situation_6"},
                          {"m_Id": 9, "m_Key": "Situation_5"}],
        })
        with (patch("plates.untouched", return_value=Path("shared")),
              patch("plates.UnityPy.load", side_effect=[
                  SimpleNamespace(objects=[table]), SimpleNamespace(objects=[shared])])):
            result = table_rows(Path("german"), {"Situation_0_ger", "Situation_6_ger"})
        self.assertEqual(result, {1: "guid[Situation_0_ger]", 2: "8a1ce869b7cb4c64abacb62f7c1485a5"})


class TextureCatalogTests(unittest.TestCase):
    def test_new_texture_keeps_source_provider_and_dependencies(self):
        source = "Assets/GK2/Example/CutObj_eng.png"
        target = source.replace("_eng", "_ger")
        source_entry = (0, 2, 0, 234, -1, 0, 5)
        # Two game asset families use different lookup conventions.
        for suffix in ("", ".png"):
            with self.subTest(suffix=suffix):
                existing_key = b"gk2/example/CutObj_eng" + suffix.encode("ascii")
                data = {
                    "m_InternalIds": [source],
                    "m_KeyDataString": base64.b64encode(
                        struct.pack("<iBi", 1, 0, len(existing_key)) + existing_key
                    ).decode(),
                    "m_BucketDataString": base64.b64encode(struct.pack("<4i", 1, 4, 1, 0)).decode(),
                    "m_EntryDataString": base64.b64encode(struct.pack("<8i", 1, *source_entry)).decode(),
                    "m_ExtraDataString": "AA==",
                }
                catalog = TextureCatalog(json.dumps(data).encode())
                link = {"source": source, "key": target}
                catalog.register([link])
                result = json.loads(catalog.encode())
                self.assertEqual(result["m_InternalIds"], [source, target])
                self.assertEqual(result["m_ExtraDataString"], data["m_ExtraDataString"])
                keys = base64.b64decode(result["m_KeyDataString"])
                buckets = base64.b64decode(result["m_BucketDataString"])
                count, first_offset, first_size, first_id, offset, size, entry_id = struct.unpack("<7i", buckets)
                self.assertEqual((count, first_offset, first_size, first_id, size, entry_id),
                                 (2, 4, 1, 0, 1, 1))
                self.assertEqual(keys[9:offset], existing_key)
                self.assertEqual(keys[offset + 5:], existing_key.replace(b"_eng", b"_ger"))
                table = base64.b64decode(result["m_EntryDataString"])
                self.assertEqual(list(struct.iter_unpack("<7i", table[4:])),
                                 [source_entry, (1, 2, 0, 234, -1, 1, 5)])
                again = TextureCatalog(catalog.encode())
                again.register([link])
                self.assertEqual(again.changed, 0)


if __name__ == "__main__":
    unittest.main()
