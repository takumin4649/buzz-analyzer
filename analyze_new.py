"""新規追加データだけを対象に差分分析を行う"""

import sqlite3
from datetime import datetime

import pandas as pd

from analyze_posts import calculate_buzz_score, classify_category, classify_opening_pattern
from buzz_score_v2 import calculate_buzz_score_v2
from import_csv import DB_PATH, init_db

OUTPUT_DIR = "output"


def _score_row(row):
    text = str(row["text"] or "")
    date_str = str(row["date"] or "")
    return calculate_buzz_score_v2(text, date_str)["total_score"]


def analyze_new_posts():
    """最新インポートバッチを「新規」として差分分析する"""
    init_db()
    conn = sqlite3.connect(DB_PATH)

    # 最新 added_at を取得
    latest = conn.execute("SELECT MAX(added_at) FROM posts").fetchone()[0]
    if not latest:
        print("DBにデータがありません。先に import_csv.py を実行してください。")
        conn.close()
        return

    # 同一インポート操作（60秒以内）を「新規バッチ」と判定
    df_new = pd.read_sql("""
        SELECT * FROM posts
        WHERE added_at >= datetime(?, '-60 seconds')
        ORDER BY likes DESC
    """, conn, params=(latest,))

    df_all = pd.read_sql("SELECT * FROM posts", conn)
    conn.close()

    if len(df_new) == 0:
        print("新規追加データがありません。")
        return

    df_prev = df_all[~df_all["id"].isin(df_new["id"])].copy()

    print(f"新規追加: {len(df_new)}件 / 既存合計: {len(df_all)}件 / 比較対象: {len(df_prev)}件")
    print()

    # スコア計算
    df_new = df_new.copy()
    df_new["v2_score"] = df_new.apply(_score_row, axis=1)
    df_new["category"] = df_new["text"].apply(classify_category)

    lines = _build_report(df_new, df_prev, latest)
    report = "\n".join(lines)

    today = datetime.now().strftime("%Y%m%d_%H%M")
    output_file = f"{OUTPUT_DIR}/analyze_new_{today}.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report)

    print(report)
    print(f"\nレポート保存: {output_file}")


def _build_report(df_new, df_prev, latest):
    lines = []
    now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    lines.append(f"# 差分分析レポート")
    lines.append(f"**分析日時:** {now_str}")
    lines.append(f"**新規バッチ:** {latest[:19]}")
    lines.append(f"**新規件数:** {len(df_new)}件  |  **既存件数:** {len(df_prev)}件")
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- スコア比較 ---
    lines.append("## スコア比較")
    lines.append("")

    new_avg = df_new["v2_score"].mean()
    new_max = df_new["v2_score"].max()
    new_min = df_new["v2_score"].min()

    if len(df_prev) > 0:
        df_prev = df_prev.copy()
        df_prev["v2_score"] = df_prev.apply(_score_row, axis=1)
        prev_avg = df_prev["v2_score"].mean()
        diff = new_avg - prev_avg
        lines.append(f"| 指標 | 新規 | 既存 | 差分 |")
        lines.append(f"|------|------|------|------|")
        lines.append(f"| v2平均スコア | {new_avg:.1f} | {prev_avg:.1f} | {diff:+.1f} |")
        lines.append(f"| 最高スコア   | {new_max:.0f} | {df_prev['v2_score'].max():.0f} | — |")
        lines.append(f"| 最低スコア   | {new_min:.0f} | {df_prev['v2_score'].min():.0f} | — |")
    else:
        lines.append(f"| 指標 | 新規 |")
        lines.append(f"|------|------|")
        lines.append(f"| v2平均スコア | {new_avg:.1f} |")
        lines.append(f"| 最高スコア   | {new_max:.0f} |")
        lines.append(f"| 最低スコア   | {new_min:.0f} |")
    lines.append("")

    # --- カテゴリ分布 ---
    lines.append("## カテゴリ分布（新規）")
    lines.append("")
    lines.append("| カテゴリ | 件数 | 割合 |")
    lines.append("|---------|------|------|")
    cat_counts = df_new["category"].value_counts()
    for cat, cnt in cat_counts.items():
        pct = cnt / len(df_new) * 100
        lines.append(f"| {cat} | {cnt} | {pct:.0f}% |")
    lines.append("")

    # --- TOP10 ---
    lines.append("## 新規投稿 TOP10（いいね順）")
    lines.append("")
    lines.append("| 順位 | v2 | いいね | アカウント | 本文（先頭） |")
    lines.append("|------|-----|--------|-----------|------------|")
    top10 = df_new.nlargest(10, "likes")
    for i, (_, row) in enumerate(top10.iterrows(), 1):
        text = str(row["text"])[:60].replace("\n", " ")
        lines.append(f"| {i} | {row['v2_score']:.0f} | {row['likes']} | @{row['account']} | {text}... |")
    lines.append("")

    # --- 改善余地の大きい投稿（高いいね & 低スコア） ---
    undervalued = df_new[(df_new["likes"] >= df_new["likes"].quantile(0.5)) &
                         (df_new["v2_score"] < df_new["v2_score"].quantile(0.5))]
    if len(undervalued) > 0:
        lines.append("## スコア未反映のバズ投稿（高いいね & 低v2スコア）")
        lines.append("")
        lines.append("| v2 | いいね | 本文（先頭） |")
        lines.append("|-----|--------|------------|")
        for _, row in undervalued.nlargest(5, "likes").iterrows():
            text = str(row["text"])[:60].replace("\n", " ")
            lines.append(f"| {row['v2_score']:.0f} | {row['likes']} | {text}... |")
        lines.append("")

    return lines


if __name__ == "__main__":
    analyze_new_posts()
