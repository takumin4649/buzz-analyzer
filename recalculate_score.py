"""postsテーブル全データでスコアを再計算し、score_historyに記録する"""

import os
import sqlite3
from datetime import datetime

import pandas as pd

from analyze_posts import calculate_buzz_score
from buzz_score_v2 import calculate_buzz_score_v2
from import_csv import DB_PATH, init_db

OUTPUT_FILE = "output/score_evolution.md"


def recalculate():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT id, text, likes, date FROM posts", conn)
    conn.close()

    if len(df) == 0:
        print("DBにデータがありません。先に import_csv.py を実行してください。")
        return

    n = len(df)
    print(f"対象: {n}件")

    v1_scores, v2_scores, likes_list = [], [], []
    for _, row in df.iterrows():
        text = str(row["text"] or "")
        date_str = str(row["date"] or "")
        likes = int(row["likes"] or 0)
        v1_scores.append(calculate_buzz_score(text)["total_score"])
        v2_scores.append(calculate_buzz_score_v2(text, date_str)["total_score"])
        likes_list.append(likes)

    df_sc = pd.DataFrame({"likes": likes_list, "v1": v1_scores, "v2": v2_scores})
    corr_v1 = float(df_sc["likes"].corr(df_sc["v1"]))
    corr_v2 = float(df_sc["likes"].corr(df_sc["v2"]))

    now = datetime.now().isoformat()
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    # score_history に記録
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO score_history (version, correlation, sample_size, date, notes) VALUES (?,?,?,?,?)",
        ("v1", corr_v1, n, now, "自動再計算")
    )
    conn.execute(
        "INSERT INTO score_history (version, correlation, sample_size, date, notes) VALUES (?,?,?,?,?)",
        ("v2", corr_v2, n, now, "自動再計算")
    )
    conn.commit()

    history = pd.read_sql(
        "SELECT version, correlation, sample_size, date FROM score_history ORDER BY date DESC",
        conn
    )
    conn.close()

    print(f"\n相関係数:")
    print(f"  v1: {corr_v1:+.3f}")
    print(f"  v2: {corr_v2:+.3f}")

    _append_evolution_report(history, corr_v1, corr_v2, n, today)
    print(f"\n履歴を追記しました: {OUTPUT_FILE}")


def _append_evolution_report(history, corr_v1, corr_v2, n, today):
    """score_evolution.md に最新エントリを追記する"""
    new_entry = (
        f"## {today}  サンプル数: {n}件\n\n"
        f"| バージョン | 相関係数 |\n"
        f"|-----------|----------|\n"
        f"| v1        | {corr_v1:+.3f}    |\n"
        f"| v2        | {corr_v2:+.3f}    |\n\n"
    )

    header = "# スコア精度の推移\n\n"
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing = f.read()
        # ヘッダー直後に新エントリを挿入
        if existing.startswith(header):
            content = header + new_entry + existing[len(header):]
        else:
            content = header + new_entry + existing
    else:
        content = header + new_entry

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    recalculate()
