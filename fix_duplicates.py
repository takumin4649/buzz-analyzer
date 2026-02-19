"""DBの重複投稿を削除するスクリプト（同一アカウント+テキスト先頭50文字）"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "data/buzz_database.db"
conn = sqlite3.connect(DB_PATH)

total_before = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
print(f"削除前: {total_before}件")

# 重複グループ確認
dups = conn.execute("""
    SELECT account, SUBSTR(text,1,50) as t50, COUNT(*) as cnt
    FROM posts
    GROUP BY account, t50
    HAVING cnt > 1
""").fetchall()
print(f"重複グループ数: {len(dups)}件")

# 重複を削除（各グループで最小IDだけ残す）
conn.execute("""
    DELETE FROM posts
    WHERE id NOT IN (
        SELECT MIN(id)
        FROM posts
        GROUP BY account, SUBSTR(text,1,50)
    )
""")
conn.commit()

total_after = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
deleted = total_before - total_after
print(f"削除後: {total_after}件")
print(f"削除件数: {deleted}件")
conn.close()
