# 合成フィクスチャ（注意）

ここのHTMLは**読書メーターの実物ではなく、手で書いた合成データ**です。
「/books/数字 へのリンク」「amazon.co.jp/dp/10文字」という構造だけに
依存したパーサであることを検証するためのものです。

実際のHTML構造に対する検証は別途必要です。手順:

1. ブラウザで `https://bookmeter.com/users/<自分のID>/books/read?page=1` を
   「ページを保存」し、`read_page_1.html` として置く
2. 本ページを `book_<book_id>.html` として置く
3. `python3 -m dokusho_import.cli --html-dir <そのディレクトリ> --out /tmp/out.csv`
