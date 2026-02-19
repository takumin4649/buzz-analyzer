"""バズ投稿 蓄積分析 Streamlit ダッシュボード"""

import os
import sqlite3
import tempfile
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from analyze_posts import calculate_buzz_score
from buzz_score_v2 import calculate_buzz_score_v2
from import_csv import DB_PATH, import_file, init_db

st.set_page_config(page_title="バズ分析ダッシュボード", layout="wide")
st.title("バズ投稿 分析ダッシュボード")

init_db()


def get_conn():
    return sqlite3.connect(DB_PATH)


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
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "投稿一覧", "アカウント別分析", "ソースファイル別", "投稿パターン分析",
    "スコア診断", "スコア精度推移", "重複管理", "投稿作成"
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
        all_accounts = conn.execute(
            "SELECT DISTINCT account FROM posts WHERE account != '' ORDER BY account"
        ).fetchall()
        conn.close()

        account_list = [r[0] for r in all_accounts]

        col_fw1, col_fw2, col_fw3 = st.columns([2, 1, 1])
        with col_fw1:
            fw_account = st.selectbox("アカウントを選択", account_list, key="fw_account")
        with col_fw2:
            # 既存値があれば初期値にセット
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
                # そのアカウントの全投稿にfollower_countを適用
                conn.execute(
                    "UPDATE posts SET follower_count=? WHERE account=?",
                    (fw_count, fw_account)
                )
                conn.commit()
                conn.close()
                st.success(f"{fw_account}: {fw_count:,}人を登録しました")
                st.rerun()

        # 登録済みフォロワー数一覧
        if not df_followers.empty:
            st.markdown("**登録済みフォロワー数**")
            df_fw_disp = df_followers.rename(columns={
                "account": "アカウント", "followers": "フォロワー数", "updated_at": "更新日時"
            })
            df_fw_disp["更新日時"] = df_fw_disp["更新日時"].str[:10]
            st.dataframe(df_fw_disp, use_container_width=True, hide_index=True)

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
            band_avg = df_fw_band.groupby("フォロワー帯", observed=True).agg(
                アカウント数=("account", "nunique"),
                平均いいね=("likes", "mean"),
                平均RT=("retweets", "mean"),
            ).round(1).reset_index()
            band_avg["エンゲージメント率(%)"] = (
                band_avg["平均いいね"] / df_fw_band.groupby(
                    pd.cut(df_fw_band["followers"], bins=bins, labels=labels, right=True),
                    observed=True
                )["followers"].mean() * 100
            ).round(2).values

            st.dataframe(band_avg, use_container_width=True, hide_index=True)
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
