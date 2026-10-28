"""The public progress bar counts deliverable GK2 images, including new debt."""
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

from publish_release import graphics_progress, write_graphics_bar


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


if __name__ == "__main__":
    unittest.main()
