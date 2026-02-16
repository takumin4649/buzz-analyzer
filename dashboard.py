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

# フォロワー帯フィルタ
df["フォロワー数_num"] = pd.to_numeric(df["フォロワー数"], errors="coerce").fillna(0).astype(int)
has_follower_data = (df["フォロワー数_num"] > 0).sum() >= 5
if has_follower_data:
    max_followers = int(df["フォロワー数_num"].max())
    follower_range = st.sidebar.slider(
        "フォロワー数の範囲",
        min_value=0,
        max_value=max_followers,
        value=(0, max_followers),
        step=100,
    )
else:
    follower_range = None

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
if follower_range is not None:
    df_filtered = df_filtered[
        (df_filtered["フォロワー数_num"] >= follower_range[0]) &
        (df_filtered["フォロワー数_num"] <= follower_range[1])
    ]

st.sidebar.markdown(f"**表示件数:** {len(df_filtered)} / {len(df)}件")


# ===== メインコンテンツ =====
st.title("📊 バズポスト分析ダッシュボード")

# タブ
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 概要", "📋 投稿一覧", "🔍 詳細分析", "✍️ テンプレート生成", "🔬 高度な分析"])


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


# ===== タブ5: 高度な分析 =====
with tab5:
    st.subheader("🔬 高度な分析")

    advanced_type = st.selectbox(
        "分析タイプを選択",
        ["バズ予測スコア", "テキスト最適化", "ユーザー分析", "バイラル係数", "競合ポジション", "フック強度", "議論誘発度"],
        key="advanced_analysis",
    )

    if advanced_type == "バズ予測スコア":
        st.markdown("### 投稿テキストのバズ予測")
        st.markdown("投稿テキストを入力すると、バズりやすさを0-100点で予測します。")

        user_text = st.text_area("投稿テキストを入力してください", height=150, key="buzz_score_input")
        if st.button("スコアを計算", type="primary", key="calc_score"):
            if user_text.strip():
                try:
                    from analyze_posts import calculate_buzz_score
                    result = calculate_buzz_score(user_text)
                    score = result["total_score"]

                    col1, col2 = st.columns([1, 2])
                    with col1:
                        st.metric("バズ予測スコア", f"{score}/100点")
                        if score >= 70:
                            st.success("バズる可能性が高い！")
                        elif score >= 50:
                            st.info("改善の余地あり")
                        else:
                            st.warning("要改善")

                    with col2:
                        st.markdown("#### 要素別スコア")
                        factor_df = pd.DataFrame([
                            {"要素": k, "スコア": v} for k, v in result["factors"].items()
                        ])
                        st.bar_chart(factor_df.set_index("要素")["スコア"])

                except Exception as e:
                    st.error(f"スコア計算に失敗: {e}")
            else:
                st.warning("テキストを入力してください")

        # 全投稿のスコア分布
        st.markdown("---")
        st.markdown("### 全投稿のスコア分析")
        try:
            from analyze_posts import analyze_buzz_scores
            buzz_data = analyze_buzz_scores(df_filtered)

            st.markdown(f"**予測スコアと実いいね数の相関:** r={buzz_data['correlation']:.2f}")

            score_df = pd.DataFrame([
                {"スコア帯": k, "件数": len(v), "平均いいね": sum(v)/len(v) if v else 0}
                for k, v in buzz_data["score_buckets"].items()
            ])
            st.dataframe(score_df, use_container_width=True)

        except Exception as e:
            st.error(f"分析に失敗: {e}")

    elif advanced_type == "テキスト最適化":
        try:
            from analyze_posts import analyze_text_length, analyze_emoji_usage, analyze_hashtag_usage

            st.markdown("### 文字数分析")
            tl_data = analyze_text_length(df_filtered)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("平均文字数", f"{tl_data['avg_length']:.0f}字")
            with col2:
                st.metric("最適文字数帯", tl_data["best_bucket"])
            with col3:
                st.metric("相関係数", f"r={tl_data['correlation']:.2f}")

            bucket_df = pd.DataFrame([
                {"文字数帯": k, "件数": len(v), "平均いいね": sum(v)/len(v) if v else 0}
                for k, v in tl_data["bucket_data"].items()
            ])
            st.bar_chart(bucket_df.set_index("文字数帯")["平均いいね"])

            st.markdown("---")
            st.markdown("### 絵文字分析")
            emoji_data = analyze_emoji_usage(df_filtered)
            col1, col2 = st.columns(2)
            with col1:
                avg_with = sum(emoji_data["with_emoji"]) / len(emoji_data["with_emoji"]) if emoji_data["with_emoji"] else 0
                st.metric("絵文字あり 平均いいね", f"{avg_with:.0f}")
            with col2:
                avg_without = sum(emoji_data["without_emoji"]) / len(emoji_data["without_emoji"]) if emoji_data["without_emoji"] else 0
                st.metric("絵文字なし 平均いいね", f"{avg_without:.0f}")

            emoji_count_df = pd.DataFrame([
                {"絵文字数": k, "件数": len(v), "平均いいね": sum(v)/len(v) if v else 0}
                for k, v in emoji_data["emoji_count_data"].items()
            ])
            st.dataframe(emoji_count_df, use_container_width=True)

            st.markdown("---")
            st.markdown("### ハッシュタグ分析")
            ht_data = analyze_hashtag_usage(df_filtered)
            col1, col2 = st.columns(2)
            with col1:
                avg_ht = sum(ht_data["with_hashtag"]) / len(ht_data["with_hashtag"]) if ht_data["with_hashtag"] else 0
                st.metric("ハッシュタグあり 平均いいね", f"{avg_ht:.0f}")
            with col2:
                avg_no_ht = sum(ht_data["without_hashtag"]) / len(ht_data["without_hashtag"]) if ht_data["without_hashtag"] else 0
                st.metric("ハッシュタグなし 平均いいね", f"{avg_no_ht:.0f}")

            if ht_data["top_hashtags"]:
                st.markdown("**人気ハッシュタグ:**")
                for tag, count in ht_data["top_hashtags"][:10]:
                    st.markdown(f"- {tag} ({count}件)")

        except Exception as e:
            st.error(f"分析に失敗: {e}")

    elif advanced_type == "ユーザー分析":
        try:
            from analyze_posts import analyze_users, filter_keywords

            # 重複除去前のデータを使用
            df_raw = filter_keywords(df)

            user_data = analyze_users(df_raw, df_filtered)

            st.markdown("### リピートバズユーザー")
            if user_data["repeat_buzzers"]:
                repeat_df = pd.DataFrame(user_data["repeat_buzzers"][:20])
                repeat_df.columns = ["ユーザー", "投稿数", "平均いいね", "最大いいね", "合計いいね", "標準偏差"]
                st.dataframe(repeat_df, use_container_width=True)
            else:
                st.info("リピートバズユーザーが見つかりません")

            st.markdown("---")
            st.markdown("### 投稿頻度とエンゲージメント")
            freq_df = pd.DataFrame([
                {"投稿数": k, "ユーザー数": len(v), "平均いいね": sum(v)/len(v) if v else 0}
                for k, v in user_data["freq_data"].items()
            ])
            st.dataframe(freq_df, use_container_width=True)

            traits = user_data["common_traits"]
            if traits["total"] > 0:
                st.markdown("---")
                st.markdown("### 常連バズアカウントの特徴")
                avg_len = sum(traits["text_lengths"]) / len(traits["text_lengths"]) if traits["text_lengths"] else 0
                st.markdown(f"- **平均投稿文字数:** {avg_len:.0f}字")
                if traits["categories"]:
                    top_cat = traits["categories"].most_common(1)[0]
                    st.markdown(f"- **最多カテゴリ:** {top_cat[0]}（{top_cat[1]}件）")
                cta_rate = (traits["cta_count"] / traits["total"]) * 100
                st.markdown(f"- **CTA使用率:** {cta_rate:.0f}%")

        except Exception as e:
            st.error(f"分析に失敗: {e}")

    elif advanced_type == "バイラル係数":
        try:
            from analyze_posts import analyze_viral_coefficient
            viral = analyze_viral_coefficient(df_filtered)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("平均バイラル係数", f"{viral['avg_coeff']:.3f}")
            with col2:
                st.metric("中央値", f"{viral['median_coeff']:.3f}")

            st.markdown("### カテゴリ別バイラル係数")
            cat_df = pd.DataFrame([
                {"カテゴリ": k, "バイラル係数": v} for k, v in
                sorted(viral["cat_viral"].items(), key=lambda x: x[1], reverse=True)
            ])
            st.dataframe(cat_df, use_container_width=True)

            st.markdown("### 拡散力TOP10")
            for i, item in enumerate(viral["top10_viral"][:10], 1):
                st.markdown(f"{i}. **{item['likes']:,}いいね / {item['retweets']:,}RT** (係数: {item['viral_coeff']:.3f}) - {item['text']}...")

        except Exception as e:
            st.error(f"分析に失敗: {e}")

    elif advanced_type == "競合ポジション":
        try:
            from analyze_posts import analyze_competitive_position
            comp = analyze_competitive_position(df_filtered)

            st.markdown("### 四象限マトリクス")
            pos_df = pd.DataFrame(comp["positions"])
            pos_df.columns = ["カテゴリ", "投稿数", "平均いいね", "ポジション"]
            st.dataframe(pos_df, use_container_width=True)

            blue = [p for p in comp["positions"] if "ブルーオーシャン" in p["quadrant"]]
            if blue:
                st.success("**狙い目:** " + ", ".join(p["category"] for p in blue))
            red = [p for p in comp["positions"] if "レッドオーシャン" in p["quadrant"]]
            if red:
                st.warning("**飽和:** " + ", ".join(p["category"] for p in red))

        except Exception as e:
            st.error(f"分析に失敗: {e}")

    elif advanced_type == "フック強度":
        try:
            from analyze_posts import analyze_hook_strength
            hook = analyze_hook_strength(df_filtered)

            st.markdown("### パワーワード種類別の効果")
            pw_df = pd.DataFrame([
                {"パワーワード": k, "件数": len(v), "平均いいね": sum(v)/len(v) if v else 0}
                for k, v in sorted(hook["pw_type_data"].items(), key=lambda x: sum(x[1])/len(x[1]) if x[1] else 0, reverse=True)
            ])
            st.dataframe(pw_df, use_container_width=True)
            if pw_df is not None and len(pw_df) > 0:
                st.bar_chart(pw_df.set_index("パワーワード")["平均いいね"])

            st.markdown("### TOP10高パフォーマンスフック")
            for i, h in enumerate(hook["top_hooks"][:10], 1):
                pw_str = ", ".join(h["power_words"]) if h["power_words"] else "なし"
                st.markdown(f"{i}. **{h['likes']:,}いいね** [{pw_str}] - {h['first_line']}")

        except Exception as e:
            st.error(f"分析に失敗: {e}")

    elif advanced_type == "議論誘発度":
        try:
            from analyze_posts import analyze_discussion_inducement
            disc = analyze_discussion_inducement(df_filtered)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("平均議論誘発度", f"{disc['avg_rate']:.3f}")
            with col2:
                st.metric("中央値", f"{disc['median_rate']:.3f}")

            st.markdown("### カテゴリ別議論誘発度")
            cat_df = pd.DataFrame([
                {"カテゴリ": k, "議論誘発度": v} for k, v in
                sorted(disc["cat_discussion"].items(), key=lambda x: x[1], reverse=True)
            ])
            st.dataframe(cat_df, use_container_width=True)

            st.markdown("### 議論を呼ぶポストTOP10")
            for i, item in enumerate(disc["top10_discussion"][:10], 1):
                st.markdown(f"{i}. **{item['likes']:,}いいね / {item['replies']}リプ** (誘発度: {item['discussion_rate']:.3f}) - {item['text']}...")

        except Exception as e:
            st.error(f"分析に失敗: {e}")
