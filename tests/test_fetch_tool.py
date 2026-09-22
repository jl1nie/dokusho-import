"""tools/fetch_bookmeter.py の統合テスト。

読書メーターのURL構造だけ真似したローカルサーバを立てて、実際に
HTTPで取得させる。外部には出ない。
"""

import http.server
import importlib.util
import io
import re
import socketserver
import threading
import unittest
import zipfile
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse

FIXTURES = Path(__file__).parent / "fixtures"
TOOL = Path(__file__).parent.parent / "tools" / "fetch_bookmeter.py"

_spec = importlib.util.spec_from_file_location("fetch_bookmeter", TOOL)
fetch_bookmeter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch_bookmeter)

REQUESTS: list[str] = []


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        REQUESTS.append(self.path)
        parsed = urlparse(self.path)
        name = None
        if re.fullmatch(r"/users/\d+/books/read", parsed.path):
            page = parse_qs(parsed.query).get("page", ["1"])[0]
            name = f"read_page_{page}.html"
        elif re.fullmatch(r"/users/\d+", parsed.path):
            name = "user.html"
        else:
            m = re.fullmatch(r"/books/(\d+)", parsed.path)
            if m:
                name = f"book_{m.group(1)}.html"

        path = FIXTURES / name if name else None
        if path is not None and path.exists():
            body = path.read_bytes()
        elif name and name.startswith("read_page_"):
            # 存在しないページ番号は本0件のHTMLを返す（実サイトの挙動に寄せる）
            body = b"<html><body><ul></ul></body></html>"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TestFetchTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        REQUESTS.clear()

    def run_tool(self, *extra):
        argv = [
            "621778",
            "--base", self.base,
            "--interval", "0",
            "--workdir", str(self.root / "work"),
            "--out", str(self.root / "out.zip"),
            *extra,
        ]
        with redirect_stderr(io.StringIO()) as err:
            code = fetch_bookmeter.main(argv)
        return code, err.getvalue()

    def test_fetches_each_book_once(self):
        # 一覧では1冊につきリンクが2本出るが、取得は1冊1回であること
        code, _ = self.run_tool()
        self.assertEqual(code, 0)
        book_requests = [p for p in REQUESTS if p.startswith("/books/")]
        self.assertEqual(len(book_requests), len(set(book_requests)))
        self.assertEqual(len(book_requests), 4)

    def test_total_request_count(self):
        # プロフィール1 + 一覧2ページ + 本4冊
        self.run_tool()
        self.assertEqual(len(REQUESTS), 7)

    def test_stops_when_page_has_no_new_books(self):
        self.run_tool()
        self.assertNotIn("/users/621778/books/read?page=3", REQUESTS)

    def test_zip_contains_all_pages_and_manifest(self):
        self.run_tool()
        with zipfile.ZipFile(self.root / "out.zip") as archive:
            names = set(archive.namelist())
        self.assertIn("manifest.json", names)
        self.assertIn("user.html", names)
        self.assertIn("read_page_1.html", names)
        for book_id in ("13558368", "22001", "33002", "44003"):
            self.assertIn(f"book_{book_id}.html", names)

    def test_manifest_records_book_count(self):
        import json

        self.run_tool()
        with zipfile.ZipFile(self.root / "out.zip") as archive:
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["book_count"], 4)
        self.assertEqual(manifest["user_id"], "621778")

    def test_rerun_makes_no_requests(self):
        self.run_tool()
        REQUESTS.clear()
        code, _ = self.run_tool()
        self.assertEqual(code, 0)
        self.assertEqual(REQUESTS, [])

    def test_resumes_only_missing_file(self):
        self.run_tool()
        (self.root / "work" / "book_22001.html").unlink()
        REQUESTS.clear()
        self.run_tool()
        self.assertEqual(REQUESTS, ["/books/22001"])

    def test_limit_applies_to_unique_books(self):
        self.run_tool("--limit", "2")
        book_requests = [p for p in REQUESTS if p.startswith("/books/")]
        self.assertEqual(len(book_requests), 2)

    def test_saved_html_matches_served_html(self):
        self.run_tool()
        saved = (self.root / "work" / "book_13558368.html").read_text(encoding="utf-8")
        self.assertEqual(saved, (FIXTURES / "book_13558368.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
