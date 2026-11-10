"""Execute the local Node OAuth regression under the existing Python CI.

Offline only: no OAuth exchange, environment writes, or network requests.
"""
import base64
import hashlib
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class R2NodeAndCspCI(unittest.TestCase):
    def test_node_handoff_regression(self):
        result = subprocess.run(
            ["node", "--test", "tests/test_oauth_handoff_r2.cjs", "tests/test_oauth_handoff_r2_nonfinite_clock.cjs"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        self.assertEqual(result.returncode, 0, (result.stdout + "\n" + result.stderr)[-7000:])

    def test_html_embeds_identical_core_and_exact_csp_hash(self):
        core = (ROOT / "readiness/oauth-handoff-local-r2.cjs").read_text(encoding="utf-8")
        html = (ROOT / "readiness/oauth-handoff-local-r2.html").read_text(encoding="utf-8")
        self.assertEqual(html.count(core), 1)
        scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
        self.assertEqual(len(scripts), 1)
        expected = base64.b64encode(hashlib.sha256(scripts[0].encode("utf-8")).digest()).decode("ascii")
        self.assertIn("script-src &#x27;sha256-" + expected + "&#x27;", html)
        self.assertEqual(html.count("script-src &#x27;sha256-"), 1)
        self.assertIn("connect-src &#x27;none&#x27;", html)


if __name__ == "__main__":
    unittest.main()
