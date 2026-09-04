from pathlib import Path
import unittest
from xml.etree import ElementTree
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DOCX = (
    ROOT
    / "docs/working-paper/A_Share_Factor_Specification_Effects_Stage1_Manuscript.docx"
)
RESULT_TABLES = (
    ROOT
    / "studies/pit_factor_bias_decomposition_v2/prespecified_results_tables.md"
)
WORDPROCESSINGML = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORDPROCESSINGML}


def w_name(local_name: str) -> str:
    return f"{{{WORDPROCESSINGML}}}{local_name}"


class Stage1ManuscriptArtifactTest(unittest.TestCase):
    def test_prespecified_results_supplement_has_complete_rows(self) -> None:
        text = RESULT_TABLES.read_text(encoding="utf-8")

        self.assertNotIn(r"\n|", text)
        self.assertEqual(text.count("\n| PRIMARY |"), 1)
        self.assertEqual(text.count("\n| SECONDARY |"), 28)
        self.assertEqual(text.count("\n| CELL |"), 72)
        self.assertEqual(text.count("`C_publication_isolation_momentum_60d`"), 1)
        self.assertEqual(text.count("`C_publication_isolation_low_vol_20d`"), 1)

    def test_docx_contains_result_shell_and_uses_plain_black_heading_system(self) -> None:
        """Catch omission of the fixed result shell or return of decorative headings."""

        with ZipFile(DOCX) as archive:
            document = ElementTree.fromstring(archive.read("word/document.xml"))
            styles = ElementTree.fromstring(archive.read("word/styles.xml"))

        text = "\n".join(
            node.text or "" for node in document.findall(".//w:t", NS)
        )
        self.assertIn("Pre-specified historical result shell", text)
        self.assertIn("Not yet estimated", text)

        title = next(
            paragraph
            for paragraph in document.findall(".//w:body/w:p", NS)
            if (
                paragraph.find("./w:pPr/w:pStyle", NS) is not None
                and paragraph.find("./w:pPr/w:pStyle", NS).get(w_name("val"))
                == "Title"
            )
        )
        self.assertIsNone(title.find("./w:pPr/w:pBdr", NS))

        for style_id in ("Title", "Subtitle", "Heading1", "Heading2", "Heading3"):
            style = next(
                node
                for node in styles.findall("./w:style", NS)
                if node.get(w_name("styleId")) == style_id
            )
            color = style.find("./w:rPr/w:color", NS)
            self.assertIsNotNone(color)
            self.assertEqual(color.get(w_name("val")).upper(), "000000")


if __name__ == "__main__":
    unittest.main()
