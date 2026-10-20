import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mdreader  # noqa: E402


def ids(text):
    return [hid for _level, _title, hid in mdreader.render(text)[1]]


class RenderTest(unittest.TestCase):
    def test_gfm_extensions(self):
        body, _ = mdreader.render("| a |\n|---|\n| 1 |\n\n- [x] done\n\n~~gone~~ https://example.com\n\nx[^1]\n\n[^1]: n\n")
        for fragment in ("<table>", 'type="checkbox"', "<del>gone</del>",
                         '<a href="https://example.com">', 'class="footnotes"'):
            self.assertIn(fragment, body)

    def test_code_is_highlighted(self):
        body, _ = mdreader.render('```python\nx = "<a>"\n```\n')
        self.assertIn('<div class="highlight">', body)
        self.assertIn("&lt;a&gt;", body)

    def test_unknown_language_left_alone(self):
        body, _ = mdreader.render("```nosuchlang\nx\n```\n")
        self.assertIn('<code class="language-nosuchlang">', body)

    def test_alerts(self):
        body, _ = mdreader.render("> [!WARNING]\n> Careful.\n")
        self.assertIn('class="alert alert-warning"', body)
        self.assertIn('<p class="alert-title">Warning</p><p>Careful.</p>', body)

    def test_dangerous_tags_filtered(self):
        body, _ = mdreader.render("<script>alert(1)</script>\n\n<details><summary>s</summary>b</details>\n")
        self.assertNotIn("<script>", body)
        self.assertIn("<details>", body)

    def test_toc_and_ids(self):
        _, toc = mdreader.render("# Hello *World*\n\n## Second\n")
        self.assertEqual(toc, [(1, "Hello World", "hello-world"), (2, "Second", "second")])

    def test_ids_are_unique(self):
        self.assertEqual(ids("# Foo\n# Foo\n# Foo 1\n"), ["foo", "foo-1", "foo-1-1"])
        self.assertEqual(ids('<h2 id="setup">Raw</h2>\n\n## Setup\n'), ["setup", "setup-1"])
        self.assertEqual(ids("# fn-1\n\nx[^1]\n\n[^1]: n\n"), ["fn-1-1"])

    def test_front_matter(self):
        body, toc = mdreader.render("---\ntitle: X\n---\n# Real\n")
        self.assertIn('class="front-matter"', body)
        self.assertEqual([t for _l, t, _i in toc], ["Real"])

    def test_leading_rule_is_not_front_matter(self):
        body, toc = mdreader.render("---\n\n# Intro\ntext\n\nSection\n---\nmore\n")
        self.assertNotIn("front-matter", body)
        self.assertEqual([t for _l, t, _i in toc], ["Intro", "Section"])


if __name__ == "__main__":
    unittest.main()
