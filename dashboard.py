"""Streamlit ダッシュボード - バズポスト分析"""

import os
import re
from collections import defaultdict

import pandas as pd
import streamlit as st

# ===== ページ設定 =====
st.set_page_config(
    page_title="バズポスト分析ダッシュボード",
    page_icon="📊",
    layout="wide",
)


# ===== ユーティリティ関数 =====
def classify_category(text):
    """カテゴリ分類"""
    if re.search(r'達成|収益|稼げた|稼いだ|成功|実績|儲かった|〜万円|月収|年収|売上|報酬|利益', text, re.IGNORECASE):
        return "実績報告系"
    if re.search(r'方法|やり方|コツ|手順|ステップ|テクニック|攻略', text, re.IGNORECASE):
        return "ノウハウ系"
    if re.search(r'私が|僕が|自分が|実際に|やってみた|試してみた|体験|経験', text, re.IGNORECASE):
        return "体験談系"
    if re.search(r'は？|問題|危険|注意|警告|【悲報】|〜すぎる|ヤバい', text, re.IGNORECASE):
        return "問題提起系"
    if re.search(r'ツール|アプリ|サービス|おすすめ|紹介|AI|Claude|ChatGPT|GPT', text, re.IGNORECASE):
        return "ツール紹介系"
    if re.search(r'発表|リリース|開始|速報|最新|ニュース|公開', text, re.IGNORECASE):
        return "ニュース系"
    return "その他"


def find_data_files():
    """利用可能なデータファイルを検索"""
    files = []
    for search_dir in [".", "output"]:
        if not os.path.isdir(search_dir):
            continue
        for f in os.listdir(search_dir):
            if re.match(r"buzz_posts_\d{8}\.(csv|xlsx)$", f):
                files.append(os.path.join(search_dir, f))
    return sorted(files)


def load_data(file_path):
    """データ読み込み"""
    if file_path.endswith(".csv"):
        return pd.read_csv(file_path)
    else:
        return pd.read_excel(file_path)


# ===== サイドバー =====
st.sidebar.title("📊 バズポスト分析")
st.sidebar.markdown("---")

# ファイル選択
data_files = find_data_files()
if not data_files:
    st.error("データファイルが見つかりません。先に buzz_analyzer.py を実行してデータを取得してください。")
    st.stop()

selected_file = st.sidebar.selectbox("データファイル", data_files)

# データ読み込み
df = load_data(selected_file)

# カテゴリ列を追加
df["カテゴリ"] = df["本文"].apply(lambda x: classify_category(str(x)))

# フィルター
st.sidebar.markdown("### フィルター")

min_likes = st.sidebar.slider(
    "最小いいね数",
    min_value=0,
    max_value=int(df["いいね数"].max()) if "いいね数" in df.columns else 1000,
    value=0,
    step=50,
)

categories = st.sidebar.multiselect(
    "カテゴリ",
    options=sorted(df["カテゴリ"].unique()),
    default=sorted(df["カテゴリ"].unique()),
)

keyword_filter = st.sidebar.text_input("キーワード検索")

# フィルタ適用
df_filtered = df[df["いいね数"] >= min_likes]
df_filtered = df_filtered[df_filtered["カテゴリ"].isin(categories)]
if keyword_filter:
    df_filtered = df_filtered[df_filtered["本文"].str.contains(keyword_filter, na=False)]

st.sidebar.markdown(f"**表示件数:** {len(df_filtered)} / {len(df)}件")


# ===== メインコンテンツ =====
st.title("📊 バズポスト分析ダッシュボード")

# タブ
tab1, tab2, tab3, tab4 = st.tabs(["📈 概要", "📋 投稿一覧", "🔍 詳細分析", "✍️ テンプレート生成"])


# ===== タブ1: 概要 =====
with tab1:
    # 基本統計
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("投稿数", f"{len(df_filtered)}件")
    with col2:
        st.metric("平均いいね", f"{df_filtered['いいね数'].mean():.0f}")
    with col3:
        st.metric("最大いいね", f"{df_filtered['いいね数'].max():,}")
    with col4:
        st.metric("中央値", f"{df_filtered['いいね数'].median():.0f}")

    st.markdown("---")

    # チャート
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("カテゴリ別 平均いいね数")
        cat_stats = df_filtered.groupby("カテゴリ")["いいね数"].agg(["mean", "count"]).reset_index()
        cat_stats.columns = ["カテゴリ", "平均いいね数", "件数"]
        cat_stats = cat_stats.sort_values("平均いいね数", ascending=True)
        st.bar_chart(cat_stats.set_index("カテゴリ")["平均いいね数"])

    with col_right:
        st.subheader("カテゴリ別 投稿数")
        cat_counts = df_filtered["カテゴリ"].value_counts()
        st.bar_chart(cat_counts)

    # いいね数分布
    st.subheader("いいね数の分布")
    hist_data = df_filtered["いいね数"].clip(upper=df_filtered["いいね数"].quantile(0.95))
    st.bar_chart(hist_data.value_counts().sort_index())


# ===== タブ2: 投稿一覧 =====
with tab2:
    st.subheader("投稿一覧")

    sort_col = st.selectbox("並び替え", ["いいね数", "リポスト数", "リプライ数"], index=0)
    df_sorted = df_filtered.sort_values(sort_col, ascending=False)

    for i, (_, row) in enumerate(df_sorted.head(50).iterrows(), 1):
        with st.expander(
            f"#{i} | ❤️ {row['いいね数']:,} | 🔄 {row['リポスト数']:,} | "
            f"[{row['カテゴリ']}] @{row['ユーザー名']}"
        ):
            st.markdown(f"**本文:**")
            st.text(str(row["本文"])[:500])
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("いいね", f"{row['いいね数']:,}")
            with col2:
                st.metric("リポスト", f"{row['リポスト数']:,}")
            with col3:
                st.metric("リプライ", f"{row['リプライ数']:,}")
            if pd.notna(row.get("ポストURL")):
                st.markdown(f"[ポストを見る]({row['ポストURL']})")


# ===== タブ3: 詳細分析 =====
with tab3:
    st.subheader("詳細分析")

    analysis_type = st.selectbox(
        "分析タイプ",
        ["CTA分析", "感情分析", "文字数分析", "TOP投稿の共通点"],
    )

    if analysis_type == "CTA分析":
        cta_patterns = {
            "いいね系": r'いいね|👍|ハート',
            "保存系": r'保存|ブックマーク',
            "フォロー系": r'フォロー|follow',
            "シェア系": r'リポスト|RT|シェア|拡散',
            "コメント系": r'コメント|返信|教えて',
        }

        cta_results = []
        for cta_type, pattern in cta_patterns.items():
            matches = df_filtered[df_filtered["本文"].str.contains(pattern, na=False, flags=re.IGNORECASE)]
            cta_results.append({
                "CTA種類": cta_type,
                "件数": len(matches),
                "平均いいね": matches["いいね数"].mean() if len(matches) > 0 else 0,
            })

        no_cta = df_filtered.copy()
        for pattern in cta_patterns.values():
            no_cta = no_cta[~no_cta["本文"].str.contains(pattern, na=False, flags=re.IGNORECASE)]
        cta_results.append({
            "CTA種類": "CTAなし",
            "件数": len(no_cta),
            "平均いいね": no_cta["いいね数"].mean() if len(no_cta) > 0 else 0,
        })

        cta_df = pd.DataFrame(cta_results)
        st.dataframe(cta_df, use_container_width=True)
        st.bar_chart(cta_df.set_index("CTA種類")["平均いいね"])

    elif analysis_type == "感情分析":
        emotion_patterns = {
            "期待": r'チャンス|可能性|稼げる|儲かる|成功|達成|実現|できる',
            "驚き": r'まさか|びっくり|驚き|すごい|やばい',
            "共感": r'わかる|そうそう|あるある|同じ|私も',
            "恐怖": r'危険|怖い|リスク|失敗|損|ヤバい|最悪',
        }

        emotion_results = []
        for emotion, pattern in emotion_patterns.items():
            matches = df_filtered[df_filtered["本文"].str.contains(pattern, na=False, flags=re.IGNORECASE)]
            emotion_results.append({
                "感情": emotion,
                "件数": len(matches),
                "平均いいね": matches["いいね数"].mean() if len(matches) > 0 else 0,
            })

        em_df = pd.DataFrame(emotion_results)
        st.dataframe(em_df, use_container_width=True)
        st.bar_chart(em_df.set_index("感情")["平均いいね"])

    elif analysis_type == "文字数分析":
        df_temp = df_filtered.copy()
        df_temp["文字数"] = df_temp["本文"].apply(lambda x: len(str(x)))

        col1, col2 = st.columns(2)
        with col1:
            st.metric("平均文字数", f"{df_temp['文字数'].mean():.0f}字")
        with col2:
            st.metric("中央値", f"{df_temp['文字数'].median():.0f}字")

        # 上位25%と下位25%の比較
        top_25 = df_temp.nlargest(len(df_temp) // 4, "いいね数")
        bottom_25 = df_temp.nsmallest(len(df_temp) // 4, "いいね数")

        st.markdown("### いいね数上位25% vs 下位25%")
        comp_col1, comp_col2 = st.columns(2)
        with comp_col1:
            st.metric("上位25%の平均文字数", f"{top_25['文字数'].mean():.0f}字")
        with comp_col2:
            st.metric("下位25%の平均文字数", f"{bottom_25['文字数'].mean():.0f}字")

    elif analysis_type == "TOP投稿の共通点":
        top10 = df_filtered.nlargest(10, "いいね数")

        st.markdown("### TOP10投稿")
        for i, (_, row) in enumerate(top10.iterrows(), 1):
            st.markdown(f"**{i}位** ({row['いいね数']:,}いいね) - [{row['カテゴリ']}]")
            st.text(str(row["本文"])[:200])
            st.markdown("---")

        # 共通点分析
        st.markdown("### 共通点")
        avg_len = top10["本文"].apply(lambda x: len(str(x))).mean()
        top_cats = top10["カテゴリ"].value_counts()

        st.markdown(f"- **平均文字数:** {avg_len:.0f}字")
        st.markdown(f"- **最多カテゴリ:** {top_cats.index[0]}（{top_cats.values[0]}件）")

        has_url = top10["本文"].str.contains(r'https?://', na=False).sum()
        st.markdown(f"- **URL含む:** {has_url}件 / 10件")

        has_emoji = top10["本文"].str.contains(r'[😀-🙏🌀-🗿🚀-🛿🤀-🧿🩰-🫿]', na=False, regex=True).sum()
        st.markdown(f"- **絵文字あり:** {has_emoji}件 / 10件")


# ===== タブ4: テンプレート生成 =====
with tab4:
    st.subheader("✍️ バズポスト テンプレート生成")
    st.markdown("分析データに基づいて、バズりやすい投稿テンプレートを生成します。")

    if st.button("🎲 テンプレートを生成する", type="primary"):
        try:
            from generate_posts import generate_posts, extract_trending_topics, extract_effective_ctas

            posts, tools, works, ctas = generate_posts(df_filtered, n=5)

            st.markdown("### トレンド情報")
            st.markdown(f"- **人気ツール:** {', '.join(tools)}")
            st.markdown(f"- **人気ジャンル:** {', '.join(works)}")
            st.markdown(f"- **効果的なCTA:** {', '.join(ctas[:3])}")

            st.markdown("---")

            for i, post in enumerate(posts, 1):
                st.markdown(f"### 生成案{i}: {post['type']}")
                st.code(post["text"] + (f"\n\n{post['cta']}" if post.get("cta") else ""), language=None)
                st.info(f"💡 **Tips:** {post['tips']}")

        except Exception as e:
            st.error(f"テンプレート生成に失敗しました: {e}")

    st.markdown("---")
    st.markdown("### 使い方")
    st.markdown("""
    1. 「テンプレートを生成する」ボタンを押す
    2. 気に入ったテンプレートを選ぶ
    3. 数字・ツール名を自分の実績に置き換え
    4. 絵文字を2〜3個追加
    5. 朝7〜9時 or 夜19〜21時に投稿
    """)
