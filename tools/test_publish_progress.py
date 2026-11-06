"""The public progress bar counts deliverable GK2 images, including new debt."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from publish_release import graphics_progress, write_graphics_bar, write_showcase


class GraphicsProgressTest(unittest.TestCase):
    def family(self, name, bundle="gk2_upcutlocal"):
        return {"bundle": bundle, "type": "Texture2D", "base": f"Assets/{name}.png"}

    def policy(self):
        return {"gk2_interface": ["Situation_0"], "excluded": {"brand": {}},
                "outside_gk2": ["original"]}

    def test_new_debt_and_local_pngs_are_not_completion(self):
        families = {n: self.family(n) for n in ["translated", "new", "brand"]}
        families["gk1"] = self.family("gk1_picture", "gk1_upcut")
        manifest = {"pictures": [{"name": n} for n in ["translated", "original"]]}
        stats = graphics_progress(families, manifest, self.policy())
        self.assertEqual(stats, {"gk2_pictures_done": 1, "gk2_pictures_total": 3,
                                 "gk2_pictures_percent": "33,3"})
        families["another"] = self.family("another")
        self.assertEqual(graphics_progress(families, manifest, self.policy())[
            "gk2_pictures_total"], 4)

    def test_unknown_shipped_interface_cannot_disappear(self):
        with self.assertRaisesRegex(ValueError, "missing from GK2 inventory"):
            graphics_progress({"brand": self.family("brand")},
                              {"pictures": [{"name": "new_interface"}]}, self.policy())

    def test_exclusion_cannot_hide_a_translation(self):
        with self.assertRaisesRegex(ValueError, "classified as excluded"):
            graphics_progress({"brand": self.family("brand")},
                              {"pictures": [{"name": "brand"}]}, self.policy())

    def test_svg_uses_exact_counts_and_ratio(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            write_graphics_bar(out, {"gk2_pictures_done": 1, "gk2_pictures_total": 4,
                                     "gk2_pictures_percent": "25,0"})
            root = ElementTree.parse(out / "graphics-progress.svg").getroot()
            ns = {"s": "http://www.w3.org/2000/svg"}
            self.assertEqual(root.find("s:title", ns).text, "Картинки GK2: 1 из 4 (25,0%)")
            self.assertEqual(root.findall("s:rect", ns)[-1].attrib["width"], "150.00")

    def test_material_debt_does_not_disappear_behind_complete_bitmaps(self):
        policy = self.policy()
        policy["material_textures"] = {"plan_model": {}, "glove_model": {}}
        families = {"brand": self.family("brand")}
        manifest = {"pictures": [{"name": "Situation_0"}]}
        stats = graphics_progress(families, manifest, policy)
        self.assertEqual((stats["gk2_pictures_done"], stats["gk2_pictures_total"]), (1, 1))
        self.assertEqual((stats["gk2_materials_done"], stats["gk2_materials_total"]), (0, 2))
        manifest["pictures"].append({"name": "plan_model", "kind": "material"})
        stats = graphics_progress(families, manifest, policy)
        self.assertEqual((stats["gk2_materials_done"], stats["gk2_materials_total"]), (1, 2))
        self.assertEqual(stats["gk2_pictures_total"], 1)

    def test_unclassified_material_cannot_be_shipped(self):
        with self.assertRaisesRegex(ValueError, "material textures missing from inventory"):
            graphics_progress({"brand": self.family("brand")},
                              {"pictures": [{"name": "unknown_model", "kind": "material"}]},
                              self.policy())

    def test_showcase_keeps_material_debt_visible(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source"
            dest = Path(folder) / "out"
            source.mkdir()
            dest.mkdir()
            (source / "README.md").write_text("{{materials_progress}}", encoding="utf-8")
            (source / "LICENSE").write_text("fixture", encoding="utf-8")
            with patch("publish_release.SHOWCASE", source):
                write_showcase(dest, {"gk2_materials_done": 1, "gk2_materials_total": 2})
            self.assertIn("**1 из 2 текстур материалов**", (dest / "README.md").read_text(encoding="utf-8"))

    def showcase(self, template, shots=()):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source"
            dest = Path(folder) / "out"
            (source / "press").mkdir(parents=True)
            dest.mkdir()
            (source / "README.md").write_text(template, encoding="utf-8")
            (source / "LICENSE").write_text("fixture", encoding="utf-8")
            for name in shots:
                (source / "press" / name).write_bytes(b"png")
            with patch("publish_release.SHOWCASE", source):
                write_showcase(dest, {})
            return (dest / "README.md").read_text(encoding="utf-8")

    def test_missing_shots_leave_no_empty_gallery_section(self):
        template = ("# T\n\n## Кадры\n\n{{video}}\n\n{{gallery:a.png|А; b.png|Б}}\n\n"
                    "## Установка\n\n1. Шаг\n\n   {{shot:c.png|В}}\n")
        text = self.showcase(template)
        self.assertNotIn("Кадры", text)
        self.assertNotIn("<table>", text)
        self.assertIn("## Установка\n\n1. Шаг", text)

    def test_gallery_keeps_existing_shots_two_per_row_with_captions(self):
        text = self.showcase("## Кадры\n\n{{gallery:\na.png|«А»;\nb.png|Б;\nc.png|В\n}}\n",
                             shots=["a.png", "c.png"])
        self.assertIn("## Кадры", text)
        self.assertIn('<img src="press/a.png" alt="«А»">', text)
        self.assertNotIn("press/b.png", text)
        self.assertEqual(text.count("<tr>"), 1)
        self.assertIn("<sub>В</sub>", text)

    def test_shot_takes_first_existing_alternative(self):
        template = "{{shot:hero.gif,hero.png|Шапка}}\n"
        self.assertIn("![Шапка](press/hero.png)", self.showcase(template, shots=["hero.png"]))
        self.assertIn("![Шапка](press/hero.gif)",
                      self.showcase(template, shots=["hero.png", "hero.gif"]))
        self.assertNotIn("press/", self.showcase(template))

    def test_named_videos_read_their_own_link_files(self):
        template = "## Игра\n\n{{video}}\n\n## Установщик\n\n{{video:installer}}\n"
        text = self.showcase(template, shots=["installer.txt"])
        self.assertNotIn("## Игра", text)
        self.assertIn("## Установщик\n\npng", text)
        self.assertNotIn("{{video", text)

    def test_section_with_subsections_is_not_empty(self):
        text = self.showcase("## Вопросы\n\n### Пустой\n\n{{video}}\n\n### Полный\n\nтекст\n")
        self.assertIn("## Вопросы", text)
        self.assertNotIn("Пустой", text)
        self.assertIn("### Полный", text)


if __name__ == "__main__":
    unittest.main()
