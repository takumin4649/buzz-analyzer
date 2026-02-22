"""バズ投稿 蓄積分析 Streamlit ダッシュボード"""

import os
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from algorithm_analysis import (
    analyze_discussion_algorithm_value,
    analyze_dwell_potential,
    analyze_early_engagement_potential,
    analyze_link_impact,
    analyze_thread_potential,
    analyze_tone,
    analyze_tone_distribution,
    calculate_algorithm_score,
    predict_early_engagement,
)
from analyze_posts import calculate_buzz_score
from buzz_score_v2 import calculate_buzz_score_v2
from import_csv import DB_PATH, import_file, init_db
from reader_psychology import analyze_reader_psychology

st.set_page_config(page_title="バズ分析ダッシュボード", layout="wide")
st.title("バズ投稿 分析ダッシュボード")

init_db()


def get_conn():
    return sqlite3.connect(DB_PATH)


def get_account_list():
    """posts + account_followers の全アカウントをABC順（大文字小文字無視）で返す"""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT DISTINCT account FROM posts WHERE account != ''
        UNION
        SELECT account FROM account_followers WHERE account != ''
        """
    ).fetchall()
    conn.close()
    return sorted([r[0] for r in rows], key=str.lower)


def account_filter_ui(label="アカウント名でフィルター（部分一致）",
                      placeholder="例: Mr_boten",
                      key_prefix="acct"):
    """テキストフィルター + ドロップダウンのUI部品。選択されたアカウント名を返す"""
    account_list = get_account_list()
    filter_val = st.text_input(label, placeholder=placeholder, key=f"{key_prefix}_filter")
    if filter_val:
        filtered = [a for a in account_list if filter_val.lower() in a.lower()]
        if not filtered:
            st.caption("一致するアカウントがありません。全件表示中。")
            filtered = account_list
    else:
        filtered = account_list
    selected = st.selectbox("アカウントを選択", filtered, key=f"{key_prefix}_select")
    return selected


def to_naive_datetime(series):
    """タイムゾーン付き・なし混在をtz-naiveに統一する"""
    result = pd.to_datetime(series, errors="coerce", utc=True)
    if hasattr(result, "dt"):
        return result.dt.tz_convert(None)
    return result


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
            inserted, skipped_rows = import_file(tmp_path)
            skipped = len(skipped_rows)
            if inserted > 0:
                st.success(f"新規登録: {inserted}件 / スキップ（重複）: {skipped}件")
            else:
                st.info(f"新規登録: 0件（全{skipped}件は既にDB済み）")

            if skipped > 0:
                with st.expander(f"スキップされた重複投稿を確認（{skipped}件）"):
                    df_skip = pd.DataFrame(skipped_rows)[["account", "text", "likes", "date"]]
                    df_skip["text"] = df_skip["text"].str[:60]
                    df_skip = df_skip.rename(columns={
                        "account": "アカウント", "text": "本文（先頭60字）",
                        "likes": "いいね", "date": "投稿日時"
                    })
                    st.dataframe(df_skip, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"エラー: {e}")
    os.unlink(tmp_path)
    st.rerun()

st.divider()

# ============================================================
# メトリクス概要
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
sources = conn.execute("SELECT COUNT(DISTINCT source_file) FROM posts").fetchone()[0]
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
# タブ切り替え
# ============================================================
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
    "投稿一覧", "アカウント別分析", "ソースファイル別", "投稿パターン分析",
    "スコア診断", "スコア精度推移", "重複管理", "投稿作成",
    "読者心理分析", "Xアルゴリズム分析",
])

# ============================================================
# TAB1: 投稿一覧
# ============================================================
with tab1:
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

        # フィルター
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            account_filter = st.text_input("アカウント名で絞り込み（部分一致）", "")
        with col_f2:
            keyword_filter = st.text_input("テキスト内キーワード検索", "")
        with col_f3:
            source_options = ["すべて"] + sorted(df_posts["source_file"].dropna().unique().tolist())
            source_filter = st.selectbox("ソースファイルで絞り込み", source_options)

        df_filtered = df_posts.copy()
        if account_filter:
            df_filtered = df_filtered[df_filtered["account"].str.contains(account_filter, case=False, na=False)]
        if keyword_filter:
            df_filtered = df_filtered[df_filtered["text"].str.contains(keyword_filter, case=False, na=False)]
        if source_filter != "すべて":
            df_filtered = df_filtered[df_filtered["source_file"] == source_filter]

        st.caption(f"表示件数: {len(df_filtered)}件 / 全{total}件")

        sort_options = {
            "v2スコア（高い順）":        ("v2スコア", False),
            "いいね数（多い順）":         ("likes", False),
            "インプレッション（高い順）": ("impressions", False),
            "投稿日時（新しい順）":       ("date", False),
            "投稿日時（古い順）":         ("date", True),
        }
        sort_label = st.selectbox("並び順", list(sort_options.keys()))
        sort_col, sort_asc = sort_options[sort_label]

        df_display = df_filtered[[
            "account", "text", "likes", "retweets", "replies", "impressions",
            "v2スコア", "date", "source_file"
        ]].copy()
        df_display["text"] = df_display["text"].str[:80]
        df_display = df_display.rename(columns={
            "account":     "アカウント",
            "text":        "本文（先頭80字）",
            "likes":       "いいね",
            "retweets":    "RT",
            "replies":     "リプライ",
            "impressions": "インプレッション",
            "date":        "投稿日時",
            "source_file": "ソースファイル",
        })
        df_display = df_display.sort_values(sort_col, ascending=sort_asc)
        st.dataframe(df_display, use_container_width=True, height=500, hide_index=True)
    else:
        st.info("データがありません。上のアップロード機能でデータを追加してください。")

# ============================================================
# TAB2: アカウント別分析
# ============================================================
with tab2:
    st.header("アカウント別分析")

    if total > 0:
        conn = get_conn()
        df_acc = pd.read_sql(
            """
            SELECT
                p.account,
                COUNT(*) as 投稿数,
                ROUND(AVG(p.likes), 1) as 平均いいね,
                ROUND(AVG(p.retweets), 1) as 平均RT,
                ROUND(AVG(p.replies), 1) as 平均リプライ,
                ROUND(AVG(p.impressions), 0) as 平均インプレッション,
                MAX(p.likes) as 最大いいね,
                COALESCE(af.followers, 0) as フォロワー数
            FROM posts p
            LEFT JOIN account_followers af ON p.account = af.account
            WHERE p.account != ''
            GROUP BY p.account
            ORDER BY 平均いいね DESC
            """,
            conn
        )
        # エンゲージメント率（フォロワー登録済みのみ）
        mask = df_acc["フォロワー数"] > 0
        df_acc["エンゲージメント率(%)"] = None
        df_acc.loc[mask, "エンゲージメント率(%)"] = (
            df_acc.loc[mask, "平均いいね"] / df_acc.loc[mask, "フォロワー数"] * 100
        ).round(2)
        conn.close()

        st.subheader("アカウント比較表")
        st.dataframe(df_acc, use_container_width=True, hide_index=True)

        st.subheader("平均いいね TOP10")
        st.bar_chart(df_acc.head(10).set_index("account")["平均いいね"])

        st.subheader("投稿数 TOP10")
        st.bar_chart(df_acc.sort_values("投稿数", ascending=False).head(10).set_index("account")["投稿数"])

        # エンゲージメント率（フォロワー登録済みアカウントのみ）
        df_eng = df_acc[df_acc["フォロワー数"] > 0].copy()
        if not df_eng.empty:
            st.subheader("エンゲージメント率（いいね÷フォロワー数）")
            st.bar_chart(df_eng.set_index("account")["エンゲージメント率(%)"])

        st.divider()

        # ============================================================
        # フォロワー数登録
        # ============================================================
        st.subheader("フォロワー数登録")

        conn = get_conn()
        df_followers = pd.read_sql(
            "SELECT account, followers, updated_at FROM account_followers ORDER BY followers DESC",
            conn
        )
        conn.close()

        # 全アカウント一覧（posts + account_followers、ABC順）
        account_list = get_account_list()

        # テキストフィルター → ドロップダウンに反映
        fw_filter = st.text_input(
            "アカウント名でフィルター（部分一致）",
            key="fw_filter",
            placeholder="例: Mr_boten"
        )
        if fw_filter:
            filtered_accounts = [a for a in account_list if fw_filter.lower() in a.lower()]
            if not filtered_accounts:
                st.caption("一致するアカウントがありません。全件表示中。")
                filtered_accounts = account_list
        else:
            filtered_accounts = account_list

        col_fw1, col_fw2, col_fw3 = st.columns([2, 1, 1])
        with col_fw1:
            fw_account = st.selectbox("アカウントを選択", filtered_accounts, key="fw_account")
        with col_fw2:
            existing = df_followers[df_followers["account"] == fw_account]["followers"].values
            default_val = int(existing[0]) if len(existing) > 0 else 0
            fw_count = st.number_input("フォロワー数", min_value=0, value=default_val, step=100, key="fw_count")
        with col_fw3:
            st.write("")
            st.write("")
            if st.button("登録", key="fw_register"):
                conn = get_conn()
                now = datetime.now().isoformat()
                conn.execute(
                    "INSERT OR REPLACE INTO account_followers (account, followers, updated_at) VALUES (?,?,?)",
                    (fw_account, fw_count, now)
                )
                conn.execute(
                    "UPDATE posts SET follower_count=? WHERE account=?",
                    (fw_count, fw_account)
                )
                conn.commit()
                conn.close()
                st.success(f"{fw_account}: {fw_count:,}人を登録しました")
                st.rerun()

        # 全アカウント フォロワー一覧（登録済み・未登録を全件表示）
        st.markdown("**全アカウント フォロワー一覧**")
        df_all_acc = pd.DataFrame({"account": account_list})
        df_all_merged = df_all_acc.merge(
            df_followers[["account", "followers", "updated_at"]],
            on="account", how="left"
        )
        df_all_merged["フォロワー数"] = df_all_merged["followers"].apply(
            lambda x: f"{int(x):,}人" if pd.notna(x) and x > 0 else "未登録"
        )
        df_all_merged["更新日時"] = df_all_merged["updated_at"].fillna("").str[:10]
        # 登録済み件数のサマリー
        registered_cnt = df_all_merged["followers"].notna().sum()
        st.caption(f"登録済み: {registered_cnt}件 / 全{len(account_list)}アカウント")
        st.dataframe(
            df_all_merged[["account", "フォロワー数", "更新日時"]].rename(
                columns={"account": "アカウント"}
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()

        # ============================================================
        # フォロワー帯別分析
        # ============================================================
        st.subheader("フォロワー帯別分析")

        conn = get_conn()
        df_fw_band = pd.read_sql(
            """
            SELECT
                p.account,
                p.likes,
                p.retweets,
                COALESCE(af.followers, 0) as followers
            FROM posts p
            LEFT JOIN account_followers af ON p.account = af.account
            WHERE af.followers IS NOT NULL AND af.followers > 0
            """,
            conn
        )
        conn.close()

        if not df_fw_band.empty:
            bins = [0, 500, 1000, 5000, 999999999]
            labels = ["500以下", "500-1000", "1000-5000", "5000以上"]
            df_fw_band["フォロワー帯"] = pd.cut(
                df_fw_band["followers"], bins=bins, labels=labels, right=True
            )
            # 1回のagg()で全項目を集計（二重groupbyによる長さ不一致を回避）
            band_avg = df_fw_band.groupby("フォロワー帯", observed=True).agg(
                アカウント数=("account", "nunique"),
                投稿数=("likes", "count"),
                いいね合計=("likes", "sum"),
                平均いいね=("likes", "mean"),
                平均RT=("retweets", "mean"),
                平均フォロワー数=("followers", "mean"),
            ).round(1).reset_index()

            # エンゲージメント率 = (いいね合計 / (平均フォロワー数 × 投稿数)) × 100
            # ゼロ除算・NaN対応
            band_avg["エンゲージメント率(%)"] = band_avg.apply(
                lambda r: round(r["いいね合計"] / (r["平均フォロワー数"] * r["投稿数"]) * 100, 2)
                if r["平均フォロワー数"] > 0 and r["投稿数"] > 0 else None,
                axis=1,
            )

            st.dataframe(
                band_avg.drop(columns=["いいね合計"]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("フォロワー数を登録するとフォロワー帯別分析が表示されます。")
    else:
        st.info("データがありません。")

# ============================================================
# TAB3: ソースファイル別
# ============================================================
with tab3:
    st.header("ソースファイル別分析")

    if total > 0:
        conn = get_conn()
        df_src = pd.read_sql(
            """
            SELECT
                source_file,
                COUNT(*) as 投稿数,
                ROUND(AVG(likes), 1) as 平均いいね,
                ROUND(AVG(retweets), 1) as 平均RT,
                ROUND(AVG(impressions), 0) as 平均インプレッション,
                MAX(likes) as 最大いいね,
                MIN(date) as 最古投稿日,
                MAX(date) as 最新投稿日,
                COUNT(DISTINCT account) as アカウント数
            FROM posts
            GROUP BY source_file
            ORDER BY 投稿数 DESC
            """,
            conn
        )
        conn.close()

        st.subheader("ファイル別サマリー")
        st.dataframe(df_src, use_container_width=True, hide_index=True)

        st.subheader("ファイル別 投稿数")
        st.bar_chart(df_src.set_index("source_file")["投稿数"])

        st.subheader("ファイル別 平均いいね")
        st.bar_chart(df_src.set_index("source_file")["平均いいね"])

        # ファイルを選んで投稿を表示
        st.subheader("ファイル内の投稿を確認")
        selected_src = st.selectbox(
            "ソースファイルを選択",
            df_src["source_file"].tolist(),
            key="src_select"
        )
        if selected_src:
            conn = get_conn()
            df_src_posts = pd.read_sql(
                "SELECT account, text, likes, retweets, impressions, date FROM posts WHERE source_file=? ORDER BY likes DESC",
                conn, params=(selected_src,)
            )
            conn.close()
            df_src_posts["text"] = df_src_posts["text"].str[:70]
            df_src_posts = df_src_posts.rename(columns={
                "account": "アカウント", "text": "本文（先頭70字）",
                "likes": "いいね", "retweets": "RT",
                "impressions": "インプレッション", "date": "投稿日時"
            })
            st.caption(f"{selected_src}: {len(df_src_posts)}件")
            st.dataframe(df_src_posts, use_container_width=True, height=400, hide_index=True)
    else:
        st.info("データがありません。")

# ============================================================
# TAB4: 投稿パターン分析
# ============================================================
with tab4:
    st.header("投稿パターン分析")

    if total > 0:
        conn = get_conn()
        df_all = pd.read_sql("SELECT text, likes, retweets, date FROM posts", conn)
        conn.close()

        df_all["char_count"] = df_all["text"].str.len()
        df_all["date_parsed"] = to_naive_datetime(df_all["date"])
        df_all["hour"] = df_all["date_parsed"].dt.hour
        df_all["weekday"] = df_all["date_parsed"].dt.dayofweek

        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("時間帯別 平均いいね数")
            df_hour = df_all.dropna(subset=["hour"]).copy()
            if len(df_hour) > 0:
                # 0〜23の全時間帯を用意してreindexで強制昇順
                hour_avg = df_hour.groupby("hour")["likes"].mean().round(1)
                hour_avg = hour_avg.reindex(range(24), fill_value=0).reset_index()
                hour_avg.columns = ["時間帯_num", "平均いいね"]
                hour_avg["時間帯"] = hour_avg["時間帯_num"].astype(str) + "時"
                fig = px.bar(hour_avg, x="時間帯", y="平均いいね",
                             category_orders={"時間帯": hour_avg["時間帯"].tolist()})
                fig.update_xaxes(tickangle=0)
                fig.update_layout(margin=dict(t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("日時データがありません。")

        with col_b:
            st.subheader("曜日別 平均いいね数")
            df_wd = df_all.dropna(subset=["weekday"]).copy()
            if len(df_wd) > 0:
                wd_names = ["月", "火", "水", "木", "金", "土", "日"]
                df_wd["曜日"] = df_wd["weekday"].apply(lambda x: wd_names[int(x)])
                wd_avg = df_wd.groupby("曜日")["likes"].mean().round(1).reindex(wd_names, fill_value=0).reset_index()
                wd_avg.columns = ["曜日", "平均いいね"]
                fig = px.bar(wd_avg, x="曜日", y="平均いいね",
                             category_orders={"曜日": wd_names})
                fig.update_xaxes(tickangle=0)
                fig.update_layout(margin=dict(t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("日時データがありません。")

        st.subheader("文字数帯別 平均いいね数")
        bins = [0, 50, 100, 140, 200, 280, 1000]
        labels = ["〜50字", "51-100字", "101-140字", "141-200字", "201-280字", "281字〜"]
        df_all["文字数帯"] = pd.cut(df_all["char_count"], bins=bins, labels=labels, right=True)
        char_avg = df_all.groupby("文字数帯", observed=True)["likes"].agg(["mean", "count"]).round(1).reset_index()
        char_avg.columns = ["文字数帯", "平均いいね", "投稿数"]
        st.dataframe(char_avg, use_container_width=True, hide_index=True)
        fig = px.bar(char_avg, x="文字数帯", y="平均いいね",
                     category_orders={"文字数帯": labels})
        fig.update_xaxes(tickangle=0)
        fig.update_layout(margin=dict(t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("データがありません。")

# ============================================================
# TAB5: スコア診断
# ============================================================
with tab5:
    st.header("投稿スコア診断")

    input_text = st.text_area(
        "投稿テキストを入力してください",
        height=130,
        placeholder="ここに投稿文を貼り付けてください..."
    )

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
            st.dataframe(
                pd.DataFrame([{"要素": k, "得点": v} for k, v in v2_result["factors"].items()]),
                use_container_width=True, hide_index=True
            )
        with col_right:
            st.subheader("v1 要素別スコア")
            st.dataframe(
                pd.DataFrame([{"要素": k, "得点": v} for k, v in v1_result["factors"].items()]),
                use_container_width=True, hide_index=True
            )

        st.subheader("改善アドバイス")
        advice = []
        text_len = len(input_text)
        if text_len < 80:
            advice.append("文字数が少なめです。80〜140字が最もエンゲージメントが高い傾向があります。")
        elif text_len > 280:
            advice.append("文字数が多めです。280字以内に収めると読まれやすくなります。")
        if "！" not in input_text and "!" not in input_text:
            advice.append("感情を強調する「！」を追加すると反応が上がる場合があります。")
        if not any(kw in input_text for kw in ["正直", "実は", "ド素人", "告白", "本当のこと"]):
            advice.append("「正直」「実は」「ド素人」など自己開示フレーズを入れるとバズりやすくなります。")
        if not any(kw in input_text for kw in ["？", "?", "どう思", "あなた"]):
            advice.append("疑問形や読者への問いかけを入れるとリプライが増えます。")
        if v2_result["total_score"] >= 70:
            advice.append("スコアが高いです。このまま投稿してみましょう。")
        elif v2_result["total_score"] >= 50:
            advice.append("スコアは中程度です。上記のアドバイスを参考に磨いてみてください。")
        else:
            advice.append("スコアが低めです。拓巳の方程式（等身大の告白×具体的体験）を意識してみましょう。")
        for a in advice:
            st.write(f"- {a}")

        st.subheader("この投稿に近いバズ投稿 TOP3")
        if total > 0:
            conn = get_conn()
            df_buzz = pd.read_sql(
                "SELECT account, text, likes, retweets FROM posts ORDER BY likes DESC LIMIT 200",
                conn
            )
            conn.close()
            words = set(input_text.replace("。", " ").replace("、", " ").split())
            df_buzz["類似度"] = df_buzz["text"].apply(
                lambda t: len(words & set(str(t).replace("。", " ").replace("、", " ").split()))
            )
            top3 = df_buzz.sort_values(["類似度", "likes"], ascending=[False, False]).head(3)
            for i, (_, row) in enumerate(top3.iterrows(), 1):
                with st.expander(f"#{i} いいね{row['likes']}件 / {row['account']}"):
                    st.write(row["text"])

# ============================================================
# TAB6: スコア精度推移
# ============================================================
with tab6:
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
            "version": "バージョン", "correlation": "相関係数",
            "sample_size": "サンプル数", "date": "計算日時",
        })
        st.dataframe(df_history, use_container_width=True, hide_index=True)
    else:
        st.info("スコア履歴がありません。ターミナルで `python recalculate_score.py` を実行してください。")

# ============================================================
# TAB7: 重複管理
# ============================================================
with tab7:
    st.header("重複管理")
    st.caption("判定基準: 同一アカウント + 同一テキスト全文")

    conn = get_conn()
    dup_groups = conn.execute("""
        SELECT
            account,
            text,
            COUNT(*) as cnt,
            MIN(id) as keep_id,
            MAX(likes) as max_likes
        FROM posts
        GROUP BY account, text
        HAVING cnt > 1
        ORDER BY cnt DESC
    """).fetchall()
    dup_total = sum(r[2] - 1 for r in dup_groups)
    conn.close()

    if dup_groups:
        st.warning(f"重複グループ: {len(dup_groups)}件 / 削除可能な重複投稿: {dup_total}件")

        col_btn1, col_btn2 = st.columns([1, 3])
        with col_btn1:
            if st.button(f"全重複を一括削除（{dup_total}件削除）", type="primary"):
                conn = get_conn()
                before = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
                conn.execute("""
                    DELETE FROM posts
                    WHERE id NOT IN (
                        SELECT MIN(id) FROM posts GROUP BY account, text
                    )
                """)
                conn.commit()
                after = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
                conn.close()
                st.success(f"削除完了: {before - after}件削除 / 残り{after}件")
                st.rerun()

        st.divider()
        st.subheader("重複グループ一覧")

        for i, (account, text, cnt, keep_id, max_likes) in enumerate(dup_groups):
            label = f"[{cnt}件重複] {account} / 「{text[:40]}...」 / いいね最大{max_likes}"
            with st.expander(label):
                conn = get_conn()
                group_rows = conn.execute(
                    "SELECT id, account, text, likes, date, source_file FROM posts "
                    "WHERE account=? AND text=? ORDER BY id ASC",
                    (account, text)
                ).fetchall()
                conn.close()

                df_group = pd.DataFrame(
                    group_rows, columns=["ID", "アカウント", "本文", "いいね", "投稿日時", "ソースファイル"]
                )
                df_group["本文"] = df_group["本文"].str[:60]
                df_group["残す"] = df_group["ID"] == keep_id
                st.dataframe(df_group, use_container_width=True, hide_index=True)

                if st.button(f"このグループの重複を削除（{cnt - 1}件削除、ID:{keep_id}を残す）", key=f"del_{i}"):
                    conn = get_conn()
                    conn.execute(
                        "DELETE FROM posts WHERE account=? AND text=? AND id != ?",
                        (account, text, keep_id)
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"{cnt - 1}件削除しました")
                    st.rerun()
    else:
        st.success("重複投稿はありません。")

# ============================================================
# TAB8: 投稿作成
# ============================================================
with tab8:
    st.header("投稿作成")

    # DBからバズ投稿TOP取得（共通利用）
    conn = get_conn()
    top_posts = pd.read_sql(
        "SELECT text, likes, account FROM posts WHERE likes > 0 ORDER BY likes DESC LIMIT 20",
        conn
    )
    conn.close()

    # ============================================================
    # 1. テンプレート一覧
    # ============================================================
    st.subheader("1. 投稿テンプレート")

    TEMPLATES = [
        {
            "name": "拓巳型（自己開示型）",
            "structure": "自己開示 → 具体的体験 → 気づき → 余韻",
            "description": "「正直に言う」「実は」系の告白から入り、具体的な体験を語り、静かな気づきで締める。CTAなし。",
            "skeleton": (
                "正直に言う。[自己開示：恥ずかしいこと・弱点・失敗]\n\n"
                "[具体的な体験・数字・エピソード]\n\n"
                "それで気づいたのは、[シンプルな気づき]。\n\n"
                "[余韻のある一文で締め。問いかけでも可]"
            ),
            "keywords": ["正直", "実は", "ド素人", "告白", "恥ずかしい"],
        },
        {
            "name": "リスク警告型",
            "structure": "事実提示 → 驚き → 対処法",
            "description": "「知らないと損する」「○○してる人は注意」系。具体的な数字で驚かせて、対処法を提示。",
            "skeleton": (
                "[意外な事実・統計・体験]\n\n"
                "これ、実は[驚きのポイント]。\n\n"
                "対処法は[具体的なアクション]だけ。\n\n"
                "[一言で締め]"
            ),
            "keywords": ["注意", "知らないと", "損", "実は", "危ない"],
        },
        {
            "name": "プロンプト/ツール紹介型",
            "structure": "失敗 → 改善 → 具体例",
            "description": "「こう使ったら失敗した」→「こう変えたら上手くいった」→ 具体的なプロンプト/手順を提示。",
            "skeleton": (
                "[最初にやった失敗・よくある間違い]\n\n"
                "でも[改善したこと]をしたら全然違った。\n\n"
                "具体的には：\n[箇条書きで手順・プロンプト例]\n\n"
                "[再現性ある締め・「試してみて」でも可]"
            ),
            "keywords": ["プロンプト", "Claude", "ChatGPT", "試した", "変えた"],
        },
    ]

    # DBからテンプレート別の例示投稿を取得
    def find_template_examples(keywords, df, n=2):
        if df.empty:
            return []
        mask = df["text"].apply(
            lambda t: any(kw in str(t) for kw in keywords)
        )
        matched = df[mask].head(n)
        return matched[["text", "likes", "account"]].to_dict("records")

    for tmpl in TEMPLATES:
        with st.expander(f"**{tmpl['name']}** ─ {tmpl['structure']}"):
            col_l, col_r = st.columns([1, 1])
            with col_l:
                st.markdown(f"**構造説明**\n\n{tmpl['description']}")
                st.code(tmpl["skeleton"], language=None)
            with col_r:
                examples = find_template_examples(tmpl["keywords"], top_posts)
                if examples:
                    st.markdown("**DB内の類似バズ投稿（いいね順）**")
                    for ex in examples:
                        st.info(f"いいね {ex['likes']}件 / {ex['account']}\n\n{ex['text'][:120]}{'...' if len(ex['text'])>120 else ''}")
                else:
                    st.caption("該当する例がDBにありません")

    st.divider()

    # ============================================================
    # 2. バズ要素チェックリスト
    # ============================================================
    st.subheader("2. バズ要素チェックリスト")

    draft = st.text_area(
        "下書きを貼り付けてください",
        height=150,
        placeholder="ここに投稿の下書きを貼り付けると自動チェックします...",
        key="draft_check"
    )

    if draft.strip():
        checks = []

        # 秘匿感フレーズ
        secret_phrases = ["正直", "実は", "ド素人", "告白", "本当のこと", "恥ずかしい", "言えなかった", "初めて言う", "ここだけの"]
        has_secret = any(p in draft for p in secret_phrases)
        checks.append(("秘匿感フレーズ", has_secret,
                        f"あり（{next(p for p in secret_phrases if p in draft)}）" if has_secret else "なし ─ 「正直」「実は」「ド素人」などを追加推奨"))

        # 具体的な数字・固有名詞
        import re
        has_number = bool(re.search(r'\d+', draft))
        checks.append(("具体的な数字", has_number,
                        "あり" if has_number else "なし ─ 数字を入れると信頼感UP"))

        # CTA（行動喚起）
        cta_phrases = ["フォロー", "いいね", "RT", "リツイート", "シェア", "保存", "ブックマーク", "コメント", "拡散"]
        has_cta = any(p in draft for p in cta_phrases)
        checks.append(("CTAなし", not has_cta,
                        "問題なし" if not has_cta else f"CTA検出：「{next(p for p in cta_phrases if p in draft)}」─ 削除推奨（CTAなしの方がバズりやすい）"))

        # 絵文字
        emoji_pattern = re.compile(
            "[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0000FE00-\U0000FEFF]", re.UNICODE
        )
        has_emoji = bool(emoji_pattern.search(draft))
        checks.append(("絵文字なし", not has_emoji,
                        "問題なし" if not has_emoji else "絵文字検出 ─ 拓巳スタイルは絵文字なしが基本"))

        # 文字数
        char_len = len(draft)
        good_len = 130 <= char_len <= 170
        checks.append(("文字数130-170字", good_len,
                        f"{char_len}字（最適範囲内）" if good_len else f"{char_len}字 ─ {'短い（+{130-char_len}字推奨）' if char_len < 130 else '長い（{char_len-170}字削減推奨）'}"))

        passed = sum(1 for _, ok, _ in checks if ok)
        st.metric("チェック結果", f"{passed} / {len(checks)} 通過")

        for label, ok, detail in checks:
            icon = "✅" if ok else "⚠️"
            st.write(f"{icon} **{label}** ─ {detail}")

    st.divider()

    # ============================================================
    # 3. Claudeに貼る用プロンプト自動生成
    # ============================================================
    st.subheader("3. Claude用プロンプト自動生成")

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        selected_tmpl = st.selectbox(
            "テンプレートを選択",
            [t["name"] for t in TEMPLATES],
            key="prompt_tmpl"
        )
    with col_p2:
        keywords_input = st.text_input(
            "キーワード・テーマ（カンマ区切り）",
            placeholder="例: Claude, プロンプト, 失敗談",
            key="prompt_kw"
        )

    tone_note = st.text_area(
        "補足・トーン指定（任意）",
        placeholder="例: 自虐的に、18-21時投稿向け、サラリーマン向け",
        height=70,
        key="prompt_tone"
    )

    # ボタンを押すたびに新しいプロンプトを生成するためのカウンター
    if "prompt_gen_count" not in st.session_state:
        st.session_state["prompt_gen_count"] = 0

    if st.button("プロンプトを生成", type="primary", key="gen_prompt"):
        with st.spinner("生成中..."):
            tmpl_info = next(t for t in TEMPLATES if t["name"] == selected_tmpl)

            top5_features = ""
            if not top_posts.empty:
                top5_lines = []
                for _, r in top_posts.head(5).iterrows():
                    top5_lines.append(f"・いいね{r['likes']}件: {str(r['text'])[:80]}{'...' if len(str(r['text']))>80 else ''}")
                top5_features = "\n".join(top5_lines)

            kw_str = keywords_input.strip() if keywords_input.strip() else "（キーワード未入力）"
            tone_str = f"\n補足: {tone_note.strip()}" if tone_note.strip() else ""

            prompt = f"""以下の条件でポストを3パターン作って：

【テンプレート】{tmpl_info['name']}
構造: {tmpl_info['structure']}

【テーマ・キーワード】
{kw_str}{tone_str}

【制約条件】
- 文字数: 130〜170字
- CTA（フォロー/いいね/RT）なし
- 絵文字なし
- 「正直」「実は」「ド素人」などの自己開示フレーズを入れる
- 具体的な数字や固有名詞を使う
- 余韻で終わる（問いかけでも可）

【参考: DB内バズ投稿TOP5（いいね順）】
{top5_features}

上記の参考投稿のトーン・構造を参考に、3パターン作成して。
各パターンに「なぜこの構造にしたか」を1行で添えてください。"""

            # カウンターを増やしてwidgetキーを変え、毎回フレッシュ表示
            st.session_state["prompt_gen_count"] += 1
            st.session_state["generated_prompt"] = prompt

    if "generated_prompt" in st.session_state:
        prompt_text = st.session_state["generated_prompt"]

        # st.code でワンクリック全選択コピー
        st.markdown("**生成されたプロンプト**（右上のコピーアイコンでコピー）")
        st.code(prompt_text, language=None)

        # ダウンロードボタン
        st.download_button(
            label="テキストファイルでダウンロード",
            data=prompt_text.encode("utf-8"),
            file_name="claude_prompt.txt",
            mime="text/plain",
        )

# ============================================================
# TAB9: 読者心理分析
# ============================================================
with tab9:
    st.header("読者心理分析")
    st.caption("投稿を読んだ読者がなぜいいね/RT/リプ/ブクマ/フォローしたか、心理を言語化する")

    # ---- 1. 単体投稿分析 ----
    st.subheader("1. 投稿テキストを分析")

    # DBから選択した値を、ウィジェット生成前にセット（ウィジェットkeyへの直接代入をここで行う）
    if "psych_text_preload" in st.session_state:
        st.session_state["psych_text"] = st.session_state.pop("psych_text_preload")
        st.session_state["psych_likes"] = st.session_state.pop("psych_likes_preload", 0)
        st.session_state["psych_rt"] = st.session_state.pop("psych_rt_preload", 0)
        st.session_state["psych_rep"] = st.session_state.pop("psych_rep_preload", 0)

    col_psych_l, col_psych_r = st.columns([2, 1])
    with col_psych_l:
        psych_text = st.text_area(
            "投稿テキストを入力",
            height=120,
            key="psych_text",
            placeholder="投稿テキストを貼り付けてください..."
        )
    with col_psych_r:
        psych_likes = st.number_input("いいね数（参考値）", min_value=0, value=0, step=10, key="psych_likes")
        psych_rt = st.number_input("RT数", min_value=0, value=0, step=1, key="psych_rt")
        psych_rep = st.number_input("リプライ数", min_value=0, value=0, step=1, key="psych_rep")

    # DBから投稿を選択して入力欄を補完
    if total > 0:
        with st.expander("またはDBの投稿から選択"):
            conn = get_conn()
            df_psych_sample = pd.read_sql(
                "SELECT account, text, likes, retweets, replies FROM posts ORDER BY likes DESC LIMIT 50",
                conn
            )
            conn.close()
            sel_opts = [
                f"いいね{r['likes']}件 @{r['account']}: {r['text'][:40]}..."
                for _, r in df_psych_sample.iterrows()
            ]
            sel_idx = st.selectbox(
                "投稿を選択", range(len(sel_opts)),
                format_func=lambda i: sel_opts[i], key="psych_sel"
            )
            if st.button("この投稿を上の入力欄に反映", key="psych_from_db"):
                row = df_psych_sample.iloc[sel_idx]
                # preloadキーに書き込み → rerun後にウィジェット生成前で処理
                st.session_state["psych_text_preload"] = row["text"]
                st.session_state["psych_likes_preload"] = int(row["likes"])
                st.session_state["psych_rt_preload"] = int(row["retweets"])
                st.session_state["psych_rep_preload"] = int(row["replies"])
                st.rerun()

    if psych_text.strip():
        result = analyze_reader_psychology(psych_text, psych_likes, psych_rt, psych_rep)

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("読者の第一感情", result["primary_emotion"])
        col_m2.metric("Grokトーン評価", result["tone"])
        col_m3.metric("なぜバズったか", "↓確認")

        st.info(f"**分析サマリー:** {result['one_line_why']}")

        col_tl, col_tr = st.columns(2)
        with col_tl:
            if result["like_triggers"]:
                st.markdown("**❤️ いいねの心理**")
                for t in result["like_triggers"]:
                    st.write(f"• **{t['trigger']}**")
                    st.caption(f"  → {t['psychology']}")

            if result["rt_triggers"]:
                st.markdown("**🔁 RTの心理**")
                for t in result["rt_triggers"]:
                    st.write(f"• **{t['trigger']}**")
                    st.caption(f"  → {t['psychology']}")

        with col_tr:
            if result["reply_triggers"]:
                st.markdown("**💬 リプライの心理**")
                for t in result["reply_triggers"]:
                    st.write(f"• **{t['trigger']}**")
                    st.caption(f"  → {t['psychology']}")

            if result["bookmark_triggers"]:
                st.markdown("**🔖 ブックマーク要因**")
                for t in result["bookmark_triggers"]:
                    st.write(f"• **{t['trigger']}**")
                    st.caption(f"  → {t['psychology']}")

            if result["follow_triggers"]:
                st.markdown("**👤 フォロー要因**")
                for t in result["follow_triggers"]:
                    st.write(f"• **{t['trigger']}**")
                    st.caption(f"  → {t['psychology']}")

        if not any([result["like_triggers"], result["rt_triggers"], result["reply_triggers"]]):
            st.warning("明確なトリガーが検出されませんでした。拓巳の方程式（等身大の告白×具体的体験）を意識してみてください。")

    st.divider()

    # ---- 2. DB全体の心理パターン統計 ----
    st.subheader("2. DB全体の心理パターン統計（上位100件）")

    if total > 0:
        if st.button("統計を表示", key="psych_stats_btn"):
            conn = get_conn()
            df_psych_db = pd.read_sql(
                "SELECT text, likes, retweets, replies FROM posts WHERE likes > 0 ORDER BY likes DESC LIMIT 100",
                conn
            )
            conn.close()

            with st.spinner("100件を分析中..."):
                all_psych = [
                    analyze_reader_psychology(
                        str(r["text"] or ""),
                        int(r["likes"] or 0),
                        int(r["retweets"] or 0),
                        int(r["replies"] or 0),
                    )
                    for _, r in df_psych_db.iterrows()
                ]
                likes_list = df_psych_db["likes"].fillna(0).astype(int).tolist()

            # 感情分布
            emotion_cnt = Counter(r["primary_emotion"] for r in all_psych)
            emotion_likes_map = {}
            for r, lk in zip(all_psych, likes_list):
                emotion_likes_map.setdefault(r["primary_emotion"], []).append(lk)
            df_emotion = pd.DataFrame([
                {
                    "感情": e,
                    "出現数": c,
                    "平均いいね": round(sum(emotion_likes_map[e]) / len(emotion_likes_map[e])),
                }
                for e, c in emotion_cnt.most_common()
            ])

            col_e1, col_e2 = st.columns(2)
            with col_e1:
                st.markdown("**読者の第一感情 分布**")
                st.dataframe(df_emotion, use_container_width=True, hide_index=True)
            with col_e2:
                fig_e = px.bar(df_emotion, x="感情", y="平均いいね", title="感情別 平均いいね")
                fig_e.update_layout(margin=dict(t=30, b=20))
                st.plotly_chart(fig_e, use_container_width=True)

            # いいねトリガー分布
            like_trigger_cnt = Counter(
                t["trigger"] for r in all_psych for t in r["like_triggers"]
            )
            like_trigger_likes = {}
            for r, lk in zip(all_psych, likes_list):
                for t in r["like_triggers"]:
                    like_trigger_likes.setdefault(t["trigger"], []).append(lk)

            if like_trigger_cnt:
                df_like_trg = pd.DataFrame([
                    {
                        "トリガー": t,
                        "出現数": c,
                        "平均いいね": round(sum(like_trigger_likes[t]) / len(like_trigger_likes[t])),
                    }
                    for t, c in like_trigger_cnt.most_common()
                ])
                st.markdown("**いいねトリガー 出現頻度（上位100件中）**")
                st.dataframe(df_like_trg, use_container_width=True, hide_index=True)
    else:
        st.info("データがありません。")

# ============================================================
# TAB10: Xアルゴリズム分析
# ============================================================
with tab10:
    st.header("Xアルゴリズム分析")
    st.caption("Xの公開アルゴリズム（Phoenix/Grok）に基づく投稿スコア分析")

    # ---- 1. 単体スコア診断 ----
    st.subheader("1. 投稿スコア診断")

    algo_input = st.text_area(
        "投稿テキストを入力",
        height=120,
        key="algo_input",
        placeholder="テキストを貼り付けるとXアルゴリズムスコアを計算します..."
    )
    has_premium = st.checkbox("X Premium加入（4倍ブースト）", key="algo_premium")

    if algo_input.strip():
        algo_result = calculate_algorithm_score(algo_input, has_premium=has_premium)
        early_result = predict_early_engagement(algo_input)
        tone_result = analyze_tone(algo_input)

        col_a1, col_a2, col_a3 = st.columns(3)
        col_a1.metric("Xアルゴリズムスコア", f"{algo_result['total_score']} / 100点")
        col_a2.metric("早期反応速度", early_result["predicted_velocity"])
        col_a3.metric(
            "Grokトーン評価",
            tone_result["overall"],
            "Grokフレンドリー" if tone_result["grok_friendly"] else "要改善",
        )

        FACTOR_DESCS = {
            "リプライ誘発力": "リプライ重み13.5×。疑問形・意見求めフレーズで加点（最大25点）",
            "滞在時間": "2分超で+10重み。文字数・構造・数字で加点（最大20点）",
            "スレッド・会話": "スレッド=3倍ブースト。会話クリック重み11.0（最大15点）",
            "トーン": "Grokがポジティブ・建設的を評価。攻撃的は抑制（最大15点）",
            "ブックマーク誘発": "ブックマーク重み10.0。リスト・テンプレ・数字で加点（最大10点）",
            "外部リンク": "外部リンクで50%リーチ減（ペナルティ）",
            "プロフクリック誘発": "プロフクリック重み12.0。秘匿感・自己開示で加点（最大10点）",
            "早期反応性": "投稿後1時間で50%決まる。冒頭インパクトで加点（最大5点）",
        }

        st.subheader("要素別スコア内訳")
        df_factors = pd.DataFrame([
            {"要素": k, "得点": v, "説明": FACTOR_DESCS.get(k, "")}
            for k, v in algo_result["factors"].items()
        ])
        st.dataframe(df_factors, use_container_width=True, hide_index=True)

        # 改善アドバイス
        FACTOR_MAX = {
            "リプライ誘発力": 25, "滞在時間": 20, "スレッド・会話": 15, "トーン": 15,
            "ブックマーク誘発": 10, "プロフクリック誘発": 10, "早期反応性": 5,
        }
        FACTOR_ADVICE = {
            "リプライ誘発力": "疑問形・「みんなはどう思う？」など意見を求めるフレーズを追加",
            "滞在時間": "具体的な数字・箇条書き・ストーリー構造で読ませる工夫を",
            "スレッド・会話": "スレッド形式を試す（3倍ブースト）。「↓詳細は」などで誘導",
            "トーン": "学び・体験・提案の建設的トーンに。感情的批判は控える",
            "ブックマーク誘発": "「○○選」「チェックリスト」「テンプレ」形式で保存価値UP",
            "外部リンク": "外部リンクは本文ではなくリプライに書く（50%減衰回避）",
            "プロフクリック誘発": "「実は私…」「ここだけの話」で「誰？」と思わせる",
            "早期反応性": "冒頭30字以内にインパクト・感情ワードを入れる",
        }

        weak = [
            (k, v) for k, v in algo_result["factors"].items()
            if FACTOR_MAX.get(k, 0) > 0 and v < FACTOR_MAX.get(k, 10) * 0.5
        ]
        if weak:
            st.subheader("改善ポイント")
            for k, v in sorted(weak, key=lambda x: FACTOR_MAX.get(x[0], 10) - x[1], reverse=True):
                advice = FACTOR_ADVICE.get(k, "")
                st.write(f"⚠️ **{k}**（{v}/{FACTOR_MAX.get(k, 10)}点）: {advice}")
        else:
            st.success("全要素のスコアが高いです。このまま投稿してみましょう。")

        if early_result["signals"]:
            st.caption("早期エンゲージメントシグナル: " + " / ".join(early_result["signals"]))

    st.divider()

    # ---- 2. DB全体のXアルゴリズム分析 ----
    st.subheader("2. DB全体のXアルゴリズム分析")

    if total > 0:
        if st.button("DB全体を分析", key="algo_db_btn"):
            conn = get_conn()
            df_algo_raw = pd.read_sql(
                "SELECT text, likes, retweets, replies, account FROM posts WHERE likes > 0",
                conn
            )
            conn.close()
            df_algo_jp = df_algo_raw.rename(columns={
                "text": "本文", "likes": "いいね数",
                "retweets": "リポスト数", "replies": "リプライ数", "account": "ユーザー名",
            })

            with st.spinner("分析中..."):
                disc = analyze_discussion_algorithm_value(df_algo_jp)
                thread = analyze_thread_potential(df_algo_jp)
                link = analyze_link_impact(df_algo_jp)
                tone_dist = analyze_tone_distribution(df_algo_jp)
                dwell = analyze_dwell_potential(df_algo_jp)
                early_all = analyze_early_engagement_potential(df_algo_jp)

            # アルゴリズム加重ランキング
            st.markdown("### アルゴリズム加重スコア TOP10")
            st.caption("いいね×0.5 + RT×1.0 + リプライ×13.5（Xアルゴリズム公式重み）")
            if disc["top10_by_algorithm"]:
                df_disc = pd.DataFrame([
                    {
                        "アカウント": r["user"],
                        "いいね": r["likes"],
                        "RT": r["retweets"],
                        "リプライ": r["replies"],
                        "加重スコア": round(r["weighted_score"]),
                        "議論率": round(r["discussion_rate"], 3),
                        "本文": r["text"],
                    }
                    for r in disc["top10_by_algorithm"]
                ])
                st.dataframe(df_disc, use_container_width=True, hide_index=True)

            col_x1, col_x2 = st.columns(2)

            with col_x1:
                st.markdown("### スレッド vs 単発")
                df_th = pd.DataFrame([
                    {"種別": "スレッド型", "件数": thread["thread_count"],
                     "平均いいね": round(thread["thread_avg_likes"])},
                    {"種別": "単発投稿", "件数": thread["non_thread_count"],
                     "平均いいね": round(thread["non_thread_avg_likes"])},
                ])
                st.dataframe(df_th, use_container_width=True, hide_index=True)
                if thread["non_thread_avg_likes"] > 0:
                    ratio = thread["thread_avg_likes"] / thread["non_thread_avg_likes"]
                    st.caption(f"スレッドは単発の {ratio:.1f} 倍")

                st.markdown("### リンク有無の影響")
                df_lk = pd.DataFrame([
                    {"リンク": "外部リンクあり", "件数": link["external_count"],
                     "平均いいね": round(link["external_avg_likes"])},
                    {"リンク": "X内リンク", "件数": link["x_link_count"],
                     "平均いいね": round(link["x_link_avg_likes"])},
                    {"リンク": "リンクなし", "件数": link["no_link_count"],
                     "平均いいね": round(link["no_link_avg_likes"])},
                ])
                st.dataframe(df_lk, use_container_width=True, hide_index=True)
                if link["reach_penalty_confirmed"]:
                    st.caption("データで確認: リンクなし投稿の方が平均いいねが高い")

            with col_x2:
                st.markdown("### Grokトーン分布")
                df_tn = pd.DataFrame([
                    {
                        "トーン": k,
                        "件数": v,
                        "平均いいね": round(tone_dist["tone_avg_likes"].get(k, 0)),
                    }
                    for k, v in sorted(
                        tone_dist["tone_distribution"].items(),
                        key=lambda x: tone_dist["tone_avg_likes"].get(x[0], 0),
                        reverse=True,
                    )
                ])
                st.dataframe(df_tn, use_container_width=True, hide_index=True)

                st.markdown("### 早期反応速度別パフォーマンス")
                df_ev = pd.DataFrame([
                    {
                        "速度": v,
                        "件数": early_all["velocity_counts"].get(v, 0),
                        "平均いいね": round(early_all["velocity_avg_likes"].get(v, 0)),
                    }
                    for v in ["高速", "中速", "低速"]
                ])
                st.dataframe(df_ev, use_container_width=True, hide_index=True)

            st.markdown("### 滞在時間スコア帯別パフォーマンス")
            df_dw = pd.DataFrame([
                {
                    "滞在時間帯": k,
                    "件数": dwell["bucket_counts"].get(k, 0),
                    "平均いいね": round(dwell["bucket_avg_likes"].get(k, 0)),
                }
                for k in ["高(15-20)", "中(10-14)", "低(0-9)"]
            ])
            st.dataframe(df_dw, use_container_width=True, hide_index=True)

            if disc.get("cat_algorithm_scores"):
                st.markdown("### カテゴリ別 アルゴリズム加重スコア")
                df_cat = pd.DataFrame([
                    {"カテゴリ": k, "平均加重スコア": round(v)}
                    for k, v in sorted(
                        disc["cat_algorithm_scores"].items(), key=lambda x: x[1], reverse=True
                    )
                ])
                fig_c = px.bar(df_cat, x="カテゴリ", y="平均加重スコア")
                fig_c.update_xaxes(tickangle=-45)
                fig_c.update_layout(margin=dict(t=20, b=80))
                st.plotly_chart(fig_c, use_container_width=True)
    else:
        st.info("データがありません。")
