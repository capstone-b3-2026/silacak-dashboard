"""Menjalankan tes logika rute frontend (Node) dari rangkaian tes Python. Dilewati bila Node/frontend tidak ada."""
import os
import shutil
import subprocess
import unittest

JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend", "src", "utils", "routeGeo.test.mjs")


class RouteJs(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node") and os.path.exists(JS), "Node atau folder frontend tidak tersedia")
    def test_route_geo(self):
        r = subprocess.run(["node", JS], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
