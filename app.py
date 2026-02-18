"""バズ投稿 蓄積分析 Streamlit ダッシュボード"""

import os
import sqlite3
import tempfile
from datetime import datetime

import pandas as pd
import streamlit as st

from analyze_posts import calculate_buzz_score
from buzz_score_v2 import calculate_buzz_score_v2
from import_csv import DB_PATH, import_file, init_db

st.set_page_config(page_title="バズ分析ダッシュボード", layout="wide")
st.title("バズ投稿 分析ダッシュボード")

init_db()


def get_conn():
    return sqlite3.connect(DB_PATH)


# ============================================================
# CSVアップロード
# ============================================================
st.header("データ追加")
uploaded = st.file_uploader(
    "CSV / Excel をアップロード（ドラッグ&ドロップ可）",
    type=["csv", "xlsx", "xls"]
)

if uploaded:
    ext = os.path.splitext(uploaded.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name
    with st.spinner("インポート中..."):
        try:
            inserted, skipped = import_file(tmp_path)
            st.success(f"新規登録: {inserted}件 / スキップ（重複）: {skipped}件")
        except Exception as e:
            st.error(f"エラー: {e}")
    os.unlink(tmp_path)
    st.rerun()

st.divider()

# ============================================================
# a) メトリクス概要
# ============================================================
st.header("現在のデータ概要")

conn = get_conn()
total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
latest_v2 = conn.execute(
    "SELECT correlation, sample_size, date FROM score_history WHERE version='v2' ORDER BY date DESC LIMIT 1"
).fetchone()
latest_v1 = conn.execute(
    "SELECT correlation FROM score_history WHERE version='v1' ORDER BY date DESC LIMIT 1"
).fetchone()
sources = conn.execute(
    "SELECT COUNT(DISTINCT source_file) FROM posts"
).fetchone()[0]
conn.close()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("総投稿数", f"{total}件")
col2.metric("ソースファイル数", f"{sources}件")
if latest_v2:
    col3.metric("v2相関係数", f"{latest_v2[0]:+.3f}")
    col4.metric("v1相関係数", f"{latest_v1[0]:+.3f}" if latest_v1 else "未計算")
    col5.metric("最終計算", latest_v2[2][:10] if latest_v2[2] else "---")
else:
    col3.metric("v2相関係数", "未計算")
    col4.metric("v1相関係数", "未計算")
    col5.metric("最終計算", "---")
    st.info("スコア履歴がありません。ターミナルで `python recalculate_score.py` を実行してください。")

st.divider()

# ============================================================
# b) 投稿一覧（スコア順ソート可能）
# ============================================================
st.header("投稿一覧")

if total > 0:
    conn = get_conn()
    df_posts = pd.read_sql(
        "SELECT id, account, text, likes, retweets, replies, impressions, date, source_file FROM posts",
        conn
    )
    conn.close()

    with st.spinner("スコアを計算中..."):
        df_posts["v2スコア"] = df_posts.apply(
            lambda r: calculate_buzz_score_v2(str(r["text"] or ""), str(r["date"] or ""))["total_score"],
            axis=1
        )

    sort_options = {
        "v2スコア（高い順）": ("v2スコア", False),
        "いいね数（多い順）":  ("likes", False),
        "投稿日時（新しい順）": ("date", False),
        "投稿日時（古い順）":  ("date", True),
    }
    sort_label = st.selectbox("並び順", list(sort_options.keys()))
    sort_col, sort_asc = sort_options[sort_label]

    df_display = df_posts[[
        "account", "text", "likes", "retweets", "replies",
        "v2スコア", "date", "source_file"
    ]].copy()
    df_display["text"] = df_display["text"].str[:80]
    df_display = df_display.rename(columns={
        "account": "アカウント",
        "text": "本文（先頭80字）",
        "likes": "いいね",
        "retweets": "RT",
        "replies": "リプライ",
        "date": "投稿日時",
        "source_file": "ソース",
    })
    df_display = df_display.sort_values(sort_col, ascending=sort_asc)

    st.dataframe(df_display, use_container_width=True, height=400, hide_index=True)
else:
    st.info("データがありません。上のアップロード機能でデータを追加してください。")

st.divider()

# ============================================================
# c) スコア精度の推移
# ============================================================
st.header("スコア精度の推移")

conn = get_conn()
df_history = pd.read_sql(
    "SELECT version, correlation, sample_size, date FROM score_history ORDER BY date DESC",
    conn
)
conn.close()

if len(df_history) > 0:
    df_history["date"] = pd.to_datetime(df_history["date"]).dt.strftime("%Y/%m/%d %H:%M")
    df_history = df_history.rename(columns={
        "version": "バージョン",
        "correlation": "相関係数",
        "sample_size": "サンプル数",
        "date": "計算日時",
    })
    st.dataframe(df_history, use_container_width=True, hide_index=True)
else:
    st.info("スコア履歴がありません。ターミナルで `python recalculate_score.py` を実行してください。")

st.divider()

# ============================================================
# d) 新規投稿スコア診断
# ============================================================
st.header("投稿スコア診断")

input_text = st.text_area("投稿テキストを入力してください", height=130, placeholder="ここに投稿文を貼り付けてください...")

if input_text.strip():
    v1_result = calculate_buzz_score(input_text)
    v2_result = calculate_buzz_score_v2(input_text)

    col1, col2, col3 = st.columns(3)
    col1.metric("v1スコア", f"{v1_result['total_score']}点")
    col2.metric("v2スコア", f"{v2_result['total_score']}点")
    col3.metric("文字数", f"{len(input_text)}字")

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("v2 要素別スコア")
        df_v2 = pd.DataFrame([
            {"要素": k, "得点": v}
            for k, v in v2_result["factors"].items()
        ])
        st.dataframe(df_v2, use_container_width=True, hide_index=True)

    with col_right:
        st.subheader("v1 要素別スコア")
        df_v1 = pd.DataFrame([
            {"要素": k, "得点": v}
            for k, v in v1_result["factors"].items()
        ])
        st.dataframe(df_v1, use_container_width=True, hide_index=True)
