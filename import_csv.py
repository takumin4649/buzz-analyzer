"""CSVやExcelをpostsテーブルにインポートするスクリプト"""

import os
import sqlite3
import sys
from datetime import datetime

import pandas as pd

from analyze_posts import GIVEAWAY_KEYWORDS

DB_PATH = "data/buzz_database.db"


def init_db():
    """DBとテーブルを初期化する（存在しない場合のみ作成）"""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            account     TEXT,
            text        TEXT,
            likes       INTEGER DEFAULT 0,
            retweets    INTEGER DEFAULT 0,
            replies     INTEGER DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            date        TEXT,
            source_file TEXT,
            added_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS score_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            version     TEXT,
            correlation REAL,
            sample_size INTEGER,
            date        TEXT,
            notes       TEXT
        );

        CREATE TABLE IF NOT EXISTS score_weights (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT,
            feature TEXT,
            weight  REAL
        );
    """)
    conn.commit()
    conn.close()


def _to_int(val):
    """数値変換（失敗時は0）"""
    try:
        v = pd.to_numeric(val, errors="coerce")
        return int(v) if pd.notna(v) else 0
    except Exception:
        return 0


def normalize_df(df, source_file):
    """DataFrameのカラムをpostsテーブルのスキーマに正規化する"""
    cols = df.columns.tolist()

    # カラム名マッピング（Excel形式 / TwExport CSV形式 / 英語列名）
    col_map = {}
    for c in ["本文", "テキスト", "text"]:
        if c in cols:
            col_map["text"] = c
            break
    for c in ["ユーザー名", "@", "account"]:
        if c in cols:
            col_map["account"] = c
            break
    for c in ["いいね数", "likes"]:
        if c in cols:
            col_map["likes"] = c
            break
    for c in ["リポスト数", "RT数", "retweets"]:
        if c in cols:
            col_map["retweets"] = c
            break
    for c in ["リプライ数", "replies"]:
        if c in cols:
            col_map["replies"] = c
            break
    for c in ["imp", "impressions"]:
        if c in cols:
            col_map["impressions"] = c
            break
    for c in ["投稿日時", "date"]:
        if c in cols:
            col_map["date"] = c
            break

    if "text" not in col_map:
        raise ValueError(f"テキストカラムが見つかりません。列名: {cols}")

    rows = []
    for _, row in df.iterrows():
        text = str(row.get(col_map["text"], "") or "").strip()
        if not text or text == "nan":
            continue
        rows.append({
            "account":     str(row.get(col_map.get("account", ""), "") or ""),
            "text":        text,
            "likes":       _to_int(row.get(col_map.get("likes", ""), 0)),
            "retweets":    _to_int(row.get(col_map.get("retweets", ""), 0)),
            "replies":     _to_int(row.get(col_map.get("replies", ""), 0)),
            "impressions": _to_int(row.get(col_map.get("impressions", ""), 0)),
            "date":        str(row.get(col_map.get("date", ""), "") or ""),
            "source_file": source_file,
            "added_at":    datetime.now().isoformat(),
        })
    return rows


def _is_giveaway(text):
    """プレゼント企画・業者系投稿かどうか判定"""
    for kw in GIVEAWAY_KEYWORDS:
        if kw in text:
            return True
    return False


def import_file(filepath):
    """CSV or Excel をDBにインポートする。(inserted, skipped) を返す"""
    init_db()

    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(filepath)
    elif ext == ".csv":
        df = None
        for enc in ["utf-8-sig", "utf-8", "cp932"]:
            try:
                df = pd.read_csv(filepath, encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        if df is None:
            raise ValueError("CSVのエンコーディングが判定できませんでした")
    else:
        raise ValueError(f"未対応のファイル形式: {ext}")

    print(f"読み込み完了: {len(df)}件")

    source_file = os.path.basename(filepath)
    rows = normalize_df(df, source_file)

    # プレゼント企画フィルター
    before_filter = len(rows)
    rows = [r for r in rows if not _is_giveaway(r["text"])]
    filtered_out = before_filter - len(rows)
    if filtered_out > 0:
        print(f"プレゼント企画・業者系を除外: {filtered_out}件")

    # DBへ挿入（重複チェック: 同一text + 同一account）
    conn = sqlite3.connect(DB_PATH)
    inserted = 0
    skipped = 0
    for row in rows:
        exists = conn.execute(
            "SELECT id FROM posts WHERE text = ? AND account = ?",
            (row["text"], row["account"])
        ).fetchone()
        if exists:
            skipped += 1
            continue
        conn.execute("""
            INSERT INTO posts
                (account, text, likes, retweets, replies, impressions, date, source_file, added_at)
            VALUES
                (:account, :text, :likes, :retweets, :replies, :impressions, :date, :source_file, :added_at)
        """, row)
        inserted += 1
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    conn.close()

    print(f"新規登録: {inserted}件 / スキップ（重複）: {skipped}件")
    print(f"DB合計: {total}件")
    return inserted, skipped


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法: python import_csv.py <ファイルパス>")
        print("例:      python import_csv.py output/filtered_buzz_posts_20260218.xlsx")
        sys.exit(1)
    import_file(sys.argv[1])
