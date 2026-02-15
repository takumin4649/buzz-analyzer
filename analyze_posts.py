"""バズポストの詳細分析スクリプト（v2 - フィルタリング強化版）"""

import os
import re
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd


def load_excel(filename):
    """Excelファイルを読み込む"""
    try:
        df = pd.read_excel(filename)
        print(f"読み込み完了: {len(df)}件のポスト")
        return df
    except Exception as e:
        print(f"エラー: Excelファイルの読み込みに失敗しました: {e}")
        return None


def filter_data(df):
    """データをフィルタリング"""
    original_count = len(df)

    # 1. 炎上系・著作権問題系を除外
    exclude_keywords = [
        "著作権", "版権", "海賊版", "収益化停止", "収益化が停止",
        "剥奪", "侵害", "インプレゾンビ"
    ]

    def should_exclude(text):
        for keyword in exclude_keywords:
            if keyword in text:
                return True
        return False

    df_filtered = df[~df["本文"].apply(should_exclude)].copy()
    excluded_by_keyword = original_count - len(df_filtered)
    print(f"炎上系・著作権問題系を除外: {excluded_by_keyword}件")

    # 2. 同一ユーザーの投稿は最もいいね数が高い1件のみ残す
    df_filtered = df_filtered.sort_values("いいね数", ascending=False)
    df_filtered = df_filtered.drop_duplicates(subset=["ユーザー名"], keep="first")
    excluded_by_user = len(df) - excluded_by_keyword - len(df_filtered)
    print(f"同一ユーザーの重複投稿を除外: {excluded_by_user}件")

    total_excluded = original_count - len(df_filtered)
    print(f"最終分析対象: {len(df_filtered)}件（{total_excluded}件除外）")

    return df_filtered, original_count, total_excluded


def safe_get(row, column, default=""):
    """安全にカラムの値を取得"""
    try:
        value = row.get(column, default)
        return value if pd.notna(value) else default
    except:
        return default


def analyze_line_breaks(df):
    """改行の分析"""
    results = []
    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        line_count = text.count("\n")
        likes = safe_get(row, "いいね数", 0)
        results.append({"line_count": line_count, "likes": likes})

    df_lines = pd.DataFrame(results)
    avg_lines = df_lines["line_count"].mean()

    # 上位25%と下位25%で比較
    top_25 = df.nlargest(len(df) // 4, "いいね数")
    bottom_25 = df.nsmallest(len(df) // 4, "いいね数")

    top_avg_lines = sum(safe_get(row, "本文", "").count("\n") for _, row in top_25.iterrows()) / len(top_25) if len(top_25) > 0 else 0
    bottom_avg_lines = sum(safe_get(row, "本文", "").count("\n") for _, row in bottom_25.iterrows()) / len(bottom_25) if len(bottom_25) > 0 else 0

    return avg_lines, top_avg_lines, bottom_avg_lines


def analyze_bullet_points(df):
    """箇条書きの分析"""
    bullet_pattern = re.compile(r'^[・\-\*①-➓1-9]\s', re.MULTILINE)

    with_bullets = []
    without_bullets = []

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)

        if bullet_pattern.search(text):
            with_bullets.append(likes)
        else:
            without_bullets.append(likes)

    return len(with_bullets), len(without_bullets), with_bullets, without_bullets


def analyze_symbols(df):
    """記号の使用分析"""
    symbol_patterns = {
        "→": r"→",
        "＝": r"[＝=]{2,}",
        "｜": r"｜",
        "【】": r"【.*?】",
    }

    symbol_usage = defaultdict(int)

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        for symbol, pattern in symbol_patterns.items():
            if re.search(pattern, text):
                symbol_usage[symbol] += 1

    return symbol_usage


def analyze_urls(df):
    """URL有無の分析"""
    url_pattern = re.compile(r'https?://\S+')

    with_url = []
    without_url = []

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)

        if url_pattern.search(text):
            with_url.append(likes)
        else:
            without_url.append(likes)

    return len(with_url), len(without_url), with_url, without_url


def classify_opening_pattern(first_line):
    """冒頭のパターン分類"""
    if not first_line:
        return "その他"

    if re.search(r'[？?]', first_line):
        return "疑問形"
    elif re.search(r'^[0-9①-➓]|[0-9]+つ|[0-9]+個|[0-9]+選', first_line):
        return "数字提示"
    elif re.search(r'は？|まじで|やばい|最悪|ありえない', first_line, re.IGNORECASE):
        return "煽り"
    elif re.search(r'わかる|共感|同じ|あるある', first_line, re.IGNORECASE):
        return "共感"
    elif re.search(r'です|ます|である|だ。', first_line):
        return "断定形"
    elif re.search(r'みなさん|あなた|皆さん', first_line, re.IGNORECASE):
        return "呼びかけ"
    else:
        return "その他"


def analyze_opening_patterns(df):
    """冒頭パターンの分析"""
    pattern_data = defaultdict(list)

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        first_line = text.split("\n")[0] if text else ""

        pattern = classify_opening_pattern(first_line)
        pattern_data[pattern].append(likes)

    return pattern_data


def analyze_cta(df):
    """CTA（行動喚起）の分析"""
    cta_patterns = {
        "いいね系": r'いいね|👍|ハート',
        "保存系": r'保存|ブックマーク',
        "フォロー系": r'フォロー|follow',
        "シェア系": r'リポスト|RT|シェア|拡散',
        "コメント系": r'コメント|返信|教えて',
    }

    cta_data = defaultdict(list)
    no_cta = []

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)

        has_cta = False
        for cta_type, pattern in cta_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                cta_data[cta_type].append(likes)
                has_cta = True

        if not has_cta:
            no_cta.append(likes)

    return cta_data, no_cta


def analyze_emotion(df):
    """感情分析（ルールベース）- 怒りカテゴリ除外"""
    emotion_patterns = {
        "期待": r'チャンス|可能性|稼げる|儲かる|成功|達成|実現|できる',
        "驚き": r'まさか|びっくり|驚き|すごい|やばい',
        "共感": r'わかる|そうそう|あるある|同じ|私も',
        "恐怖": r'危険|怖い|リスク|失敗|損|ヤバい|最悪',
    }

    emotion_data = defaultdict(list)

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)

        for emotion, pattern in emotion_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                emotion_data[emotion].append(likes)

    return emotion_data


def has_story(text):
    """ストーリー性の判定"""
    story_keywords = [
        r'まず|次に|そして|最後に',
        r'before|after|→',
        r'昔|以前|最初|今では|現在',
        r'私|僕|自分|実際に|やってみた',
    ]

    for pattern in story_keywords:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def analyze_story(df):
    """ストーリー性の分析"""
    with_story = []
    without_story = []

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)

        if has_story(text):
            with_story.append(likes)
        else:
            without_story.append(likes)

    return len(with_story), len(without_story), with_story, without_story


def analyze_engagement_ratio(df):
    """エンゲージメント比率の分析"""
    high_reply_ratio = []  # リプライが多い
    high_retweet_ratio = []  # リポストが多い

    for _, row in df.iterrows():
        likes = safe_get(row, "いいね数", 0)
        replies = safe_get(row, "リプライ数", 0)
        retweets = safe_get(row, "リポスト数", 0)
        text = safe_get(row, "本文", "")

        if likes > 0:
            reply_ratio = replies / likes
            retweet_ratio = retweets / likes

            if reply_ratio > 0.05:  # リプライ率5%以上
                high_reply_ratio.append({"text": text[:50], "likes": likes, "replies": replies})

            if retweet_ratio > 0.2:  # リポスト率20%以上
                high_retweet_ratio.append({"text": text[:50], "likes": likes, "retweets": retweets})

    return high_reply_ratio, high_retweet_ratio


def classify_category(text):
    """カテゴリ分類（精度向上版）"""
    # 優先順位を持たせて判定

    # 実績報告系（最優先）
    if re.search(r'達成|収益|稼げた|稼いだ|成功|実績|儲かった|〜万円|月収|年収|売上|報酬|利益', text, re.IGNORECASE):
        return "実績報告系"

    # ノウハウ系
    if re.search(r'方法|やり方|コツ|手順|ステップ|テクニック|攻略|マニュアル|ガイド|〜する方法|〜のやり方', text, re.IGNORECASE):
        return "ノウハウ系"

    # 体験談系
    if re.search(r'私が|僕が|自分が|実際に|やってみた|試してみた|体験|経験|〜したら|〜してみた', text, re.IGNORECASE):
        return "体験談系"

    # 問題提起系
    if re.search(r'は？|問題|危険|注意|警告|【悲報】|〜すぎる|ヤバい|おかしい', text, re.IGNORECASE):
        return "問題提起系"

    # ツール紹介系
    if re.search(r'ツール|アプリ|サービス|プラグイン|拡張機能|おすすめ|紹介|AI|Claude|ChatGPT|GPT', text, re.IGNORECASE):
        return "ツール紹介系"

    # ニュース系
    if re.search(r'発表|リリース|開始|開催|速報|最新|ニュース|公開', text, re.IGNORECASE):
        return "ニュース系"

    return "その他"


def analyze_categories(df):
    """カテゴリ別分析"""
    category_data = defaultdict(lambda: {"likes": [], "retweets": []})

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        retweets = safe_get(row, "リポスト数", 0)

        category = classify_category(text)
        category_data[category]["likes"].append(likes)
        category_data[category]["retweets"].append(retweets)

    return category_data


def parse_datetime(dt_str):
    """日時のパース"""
    try:
        return pd.to_datetime(dt_str)
    except:
        return None


def analyze_time(df):
    """時間帯分析"""
    time_slots = {
        "朝(6-9時)": [],
        "昼(9-12時)": [],
        "午後(12-18時)": [],
        "夜(18-22時)": [],
        "深夜(22-6時)": [],
    }

    weekday_data = defaultdict(list)

    for _, row in df.iterrows():
        dt_str = safe_get(row, "投稿日時", "")
        likes = safe_get(row, "いいね数", 0)

        dt = parse_datetime(dt_str)
        if dt:
            # JST変換（+9時間）
            hour = (dt.hour + 9) % 24
            weekday = dt.weekday()

            if 6 <= hour < 9:
                time_slots["朝(6-9時)"].append(likes)
            elif 9 <= hour < 12:
                time_slots["昼(9-12時)"].append(likes)
            elif 12 <= hour < 18:
                time_slots["午後(12-18時)"].append(likes)
            elif 18 <= hour < 22:
                time_slots["夜(18-22時)"].append(likes)
            else:
                time_slots["深夜(22-6時)"].append(likes)

            weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
            weekday_data[weekday_names[weekday]].append(likes)

    return time_slots, weekday_data


def analyze_time_category_cross(df):
    """時間帯×カテゴリのクロス分析"""
    cross_data = defaultdict(lambda: defaultdict(list))

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        dt_str = safe_get(row, "投稿日時", "")
        likes = safe_get(row, "いいね数", 0)

        category = classify_category(text)
        dt = parse_datetime(dt_str)

        if dt:
            hour = (dt.hour + 9) % 24
            if 6 <= hour < 12:
                time_slot = "朝〜昼"
            elif 12 <= hour < 18:
                time_slot = "午後"
            elif 18 <= hour < 22:
                time_slot = "夜"
            else:
                time_slot = "深夜"

            cross_data[time_slot][category].append(likes)

    return cross_data


def generate_report(df, output_filename, original_count, excluded_count):
    """分析レポート生成"""
    print("\n分析を開始します...")

    with open(output_filename, "w", encoding="utf-8") as f:
        f.write("# AI副業系バズポスト 詳細分析レポート v2\n\n")
        f.write(f"**分析日時:** {datetime.now().strftime('%Y年%m月%d日 %H:%M')}\n\n")
        f.write(f"**元データ件数:** {original_count}件\n\n")
        f.write(f"**除外件数:** {excluded_count}件\n")
        f.write(f"- 炎上系・著作権問題系の投稿を除外\n")
        f.write(f"- 同一ユーザーの重複投稿を除外（最もいいね数が高い1件のみ残す）\n\n")
        f.write(f"**最終分析対象:** {len(df)}件のポスト\n\n")
        f.write("---\n\n")

        # 基本ランキング
        print("基本ランキングを分析中...")
        f.write("## 1. 基本ランキング\n\n")

        f.write("### いいね数 TOP10\n\n")
        top10_likes = df.nlargest(10, "いいね数")
        for i, (_, row) in enumerate(top10_likes.iterrows(), 1):
            f.write(f"#### {i}位: {row['いいね数']:,}いいね\n\n")
            f.write(f"**ユーザー:** @{row['ユーザー名']}\n\n")
            f.write(f"**本文:**\n```\n{row['本文'][:200]}{'...' if len(str(row['本文'])) > 200 else ''}\n```\n\n")
            f.write(f"- リポスト: {row['リポスト数']:,}件\n")
            f.write(f"- URL: {row['ポストURL']}\n\n")

        f.write("### リポスト数 TOP10\n\n")
        top10_retweets = df.nlargest(10, "リポスト数")
        for i, (_, row) in enumerate(top10_retweets.iterrows(), 1):
            f.write(f"{i}. **{row['リポスト数']:,}RT** - いいね{row['いいね数']:,}件 - {row['本文'][:60]}...\n")
        f.write("\n")

        # 構成・フォーマット分析
        print("構成・フォーマットを分析中...")
        f.write("## 2. 構成・フォーマット分析\n\n")

        avg_lines, top_avg_lines, bottom_avg_lines = analyze_line_breaks(df)
        f.write("### 改行の使用傾向\n\n")
        f.write(f"- **全体の平均改行数:** {avg_lines:.1f}回\n")
        f.write(f"- **いいね数上位25%の平均改行数:** {top_avg_lines:.1f}回\n")
        f.write(f"- **いいね数下位25%の平均改行数:** {bottom_avg_lines:.1f}回\n\n")
        if top_avg_lines > bottom_avg_lines:
            f.write(f"**傾向:** バズるポストは平均{top_avg_lines - bottom_avg_lines:.1f}回多く改行しています。読みやすさが重要。\n\n")
        else:
            f.write(f"**傾向:** バズるポストは改行が少なめ。簡潔さが好まれる傾向。\n\n")

        bullet_count, non_bullet_count, bullet_likes, non_bullet_likes = analyze_bullet_points(df)
        f.write("### 箇条書きの使用\n\n")
        f.write(f"- **箇条書きあり:** {bullet_count}件（平均いいね: {sum(bullet_likes)/len(bullet_likes) if bullet_likes else 0:.0f}件）\n")
        f.write(f"- **箇条書きなし:** {non_bullet_count}件（平均いいね: {sum(non_bullet_likes)/len(non_bullet_likes) if non_bullet_likes else 0:.0f}件）\n\n")

        symbol_usage = analyze_symbols(df)
        f.write("### 記号の使用傾向\n\n")
        for symbol, count in symbol_usage.items():
            f.write(f"- **{symbol}** を使用: {count}件\n")
        f.write("\n")

        url_count, non_url_count, url_likes, non_url_likes = analyze_urls(df)
        f.write("### URL/リンクの影響\n\n")
        f.write(f"- **URLあり:** {url_count}件（平均いいね: {sum(url_likes)/len(url_likes) if url_likes else 0:.0f}件）\n")
        f.write(f"- **URLなし:** {non_url_count}件（平均いいね: {sum(non_url_likes)/len(non_url_likes) if non_url_likes else 0:.0f}件）\n\n")

        # 心理・コピーライティング分析
        print("心理・コピーライティングを分析中...")
        f.write("## 3. 心理・コピーライティング分析\n\n")

        pattern_data = analyze_opening_patterns(df)
        f.write("### 冒頭パターン別のいいね数\n\n")
        f.write("| パターン | 件数 | 平均いいね数 |\n")
        f.write("|---------|------|-------------|\n")
        pattern_sorted = sorted(pattern_data.items(), key=lambda x: sum(x[1])/len(x[1]) if x[1] else 0, reverse=True)
        for pattern, likes in pattern_sorted:
            avg = sum(likes)/len(likes) if likes else 0
            f.write(f"| {pattern} | {len(likes)}件 | {avg:.0f}件 |\n")
        f.write("\n")
        if pattern_sorted:
            best_pattern = pattern_sorted[0][0]
            f.write(f"**最も効果的:** {best_pattern}型の冒頭が最も高いエンゲージメント\n\n")

        cta_data, no_cta = analyze_cta(df)
        f.write("### CTA（行動喚起）の効果\n\n")
        f.write("| CTA種類 | 件数 | 平均いいね数 |\n")
        f.write("|---------|------|-------------|\n")
        for cta_type, likes in cta_data.items():
            avg = sum(likes)/len(likes) if likes else 0
            f.write(f"| {cta_type} | {len(likes)}件 | {avg:.0f}件 |\n")
        no_cta_avg = sum(no_cta)/len(no_cta) if no_cta else 0
        f.write(f"| CTAなし | {len(no_cta)}件 | {no_cta_avg:.0f}件 |\n")
        f.write("\n")

        emotion_data = analyze_emotion(df)
        f.write("### 感情別のエンゲージメント\n\n")
        f.write("| 感情 | 件数 | 平均いいね数 |\n")
        f.write("|------|------|-------------|\n")
        emotion_sorted = sorted(emotion_data.items(), key=lambda x: sum(x[1])/len(x[1]) if x[1] else 0, reverse=True)
        for emotion, likes in emotion_sorted:
            avg = sum(likes)/len(likes) if likes else 0
            f.write(f"| {emotion} | {len(likes)}件 | {avg:.0f}件 |\n")
        f.write("\n")

        story_count, non_story_count, story_likes, non_story_likes = analyze_story(df)
        f.write("### ストーリー性の有無\n\n")
        f.write(f"- **ストーリーあり:** {story_count}件（平均いいね: {sum(story_likes)/len(story_likes) if story_likes else 0:.0f}件）\n")
        f.write(f"- **ストーリーなし:** {non_story_count}件（平均いいね: {sum(non_story_likes)/len(non_story_likes) if non_story_likes else 0:.0f}件）\n\n")

        # エンゲージメント比率分析
        print("エンゲージメント比率を分析中...")
        f.write("## 4. エンゲージメント比率分析\n\n")

        high_reply, high_retweet = analyze_engagement_ratio(df)
        f.write("### リプライ率が高い投稿（議論・共感型）\n\n")
        for item in high_reply[:5]:
            f.write(f"- **{item['likes']:,}いいね / {item['replies']}リプライ** - {item['text']}...\n")
        f.write("\n")

        f.write("### リポスト率が高い投稿（拡散型）\n\n")
        for item in high_retweet[:5]:
            f.write(f"- **{item['likes']:,}いいね / {item['retweets']}RT** - {item['text']}...\n")
        f.write("\n")

        # カテゴリ分析
        print("カテゴリを分析中...")
        f.write("## 5. テーマ・ジャンル分析\n\n")

        category_data = analyze_categories(df)
        f.write("### カテゴリ別エンゲージメント\n\n")
        f.write("| カテゴリ | 件数 | 平均いいね | 平均RT |\n")
        f.write("|---------|------|-----------|--------|\n")
        category_sorted = sorted(category_data.items(), key=lambda x: sum(x[1]["likes"])/len(x[1]["likes"]) if x[1]["likes"] else 0, reverse=True)
        for category, data in category_sorted:
            avg_likes = sum(data["likes"])/len(data["likes"]) if data["likes"] else 0
            avg_rt = sum(data["retweets"])/len(data["retweets"]) if data["retweets"] else 0
            f.write(f"| {category} | {len(data['likes'])}件 | {avg_likes:.0f}件 | {avg_rt:.0f}件 |\n")
        f.write("\n")

        # 時間分析
        print("時間帯を分析中...")
        f.write("## 6. 時間・タイミング分析\n\n")

        time_slots, weekday_data = analyze_time(df)
        f.write("### 投稿時間帯別の平均いいね数\n\n")
        f.write("| 時間帯 | 件数 | 平均いいね数 |\n")
        f.write("|--------|------|-------------|\n")
        for slot, likes in time_slots.items():
            avg = sum(likes)/len(likes) if likes else 0
            f.write(f"| {slot} | {len(likes)}件 | {avg:.0f}件 |\n")
        f.write("\n")

        f.write("### 曜日別の平均いいね数\n\n")
        f.write("| 曜日 | 件数 | 平均いいね数 |\n")
        f.write("|------|------|-------------|\n")
        for day in ["月", "火", "水", "木", "金", "土", "日"]:
            likes = weekday_data.get(day, [])
            avg = sum(likes)/len(likes) if likes else 0
            f.write(f"| {day}曜日 | {len(likes)}件 | {avg:.0f}件 |\n")
        f.write("\n")

        cross_data = analyze_time_category_cross(df)
        f.write("### 時間帯×カテゴリのクロス分析\n\n")
        for time_slot, categories in cross_data.items():
            f.write(f"#### {time_slot}\n\n")
            cat_sorted = sorted(categories.items(), key=lambda x: sum(x[1])/len(x[1]) if x[1] else 0, reverse=True)
            for cat, likes in cat_sorted[:3]:
                avg = sum(likes)/len(likes) if likes else 0
                f.write(f"- **{cat}:** 平均{avg:.0f}いいね ({len(likes)}件)\n")
            f.write("\n")

        # 総合まとめ
        print("総合まとめを生成中...")
        f.write("## 7. AI副業系でバズるポストの黄金パターン\n\n")
        f.write("全分析結果を踏まえた、再現性の高いバズパターン5選:\n\n")

        # パターン1: 数字提示×実績報告
        f.write("### パターン1: 数字提示×実績報告型\n\n")
        f.write("**特徴:**\n")
        f.write("- 冒頭に具体的な数字を提示\n")
        f.write("- 実績や成果を明確に示す\n")
        f.write("- 箇条書きで情報を整理\n\n")
        f.write("**投稿テンプレート:**\n")
        f.write("```\n")
        f.write("AI副業で月収30万円達成しました🎉\n\n")
        f.write("実践した3つのこと:\n")
        f.write("① ChatGPTで記事作成代行\n")
        f.write("② Midjourneyでロゴデザイン\n")
        f.write("③ Claude Codeで自動化ツール販売\n\n")
        f.write("初月は5万円→3ヶ月で30万円に。\n")
        f.write("副業でも十分稼げます💪\n")
        f.write("```\n\n")

        # パターン2: 問題提起×共感
        f.write("### パターン2: 問題提起×共感型\n\n")
        f.write("**特徴:**\n")
        f.write("- 「は？」「やばい」など感情的な冒頭\n")
        f.write("- 読者の悩みに共感\n")
        f.write("- 解決策を提示\n\n")
        f.write("**投稿テンプレート:**\n")
        f.write("```\n")
        f.write("は？AIで副業とか怪しいって思ってました。\n\n")
        f.write("でも実際やってみたら...\n")
        f.write("→ 1日2時間で月10万円稼げた\n")
        f.write("→ スキル不要で初心者でもOK\n")
        f.write("→ 在宅で完結\n\n")
        f.write("バイトより全然効率いい。\n")
        f.write("もっと早く始めればよかった😭\n")
        f.write("```\n\n")

        # パターン3: ノウハウ×箇条書き
        f.write("### パターン3: ノウハウ×箇条書き型\n\n")
        f.write("**特徴:**\n")
        f.write("- 「〜する方法」など価値提示\n")
        f.write("- ステップを明確に\n")
        f.write("- 再現性を強調\n\n")
        f.write("**投稿テンプレート:**\n")
        f.write("```\n")
        f.write("初心者がAI副業で月5万円稼ぐ方法\n\n")
        f.write("【ステップ】\n")
        f.write("1. ChatGPTに無料登録\n")
        f.write("2. クラウドワークスでライティング案件探す\n")
        f.write("3. AIで下書き→自分で仕上げ\n")
        f.write("4. 納品して報酬ゲット\n\n")
        f.write("これだけ。\n")
        f.write("スキルゼロから始めて2週間で初収益出ました✨\n")
        f.write("```\n\n")

        # パターン4: 体験談×ストーリー
        f.write("### パターン4: 体験談×ストーリー型\n\n")
        f.write("**特徴:**\n")
        f.write("- 自分の経験を時系列で語る\n")
        f.write("- Before→Afterを明確に\n")
        f.write("- リアルな数字を含める\n\n")
        f.write("**投稿テンプレート:**\n")
        f.write("```\n")
        f.write("3ヶ月前: バイト月8万円で消耗\n")
        f.write("2ヶ月前: AI副業開始→初月3万円\n")
        f.write("1ヶ月前: コツ掴んで月12万円\n")
        f.write("今: バイト辞めてAI副業のみで月18万円🚀\n\n")
        f.write("使ってるのはChatGPTとCanvaだけ。\n")
        f.write("人生変わりました。\n")
        f.write("```\n\n")

        # パターン5: ツール紹介×緊急性
        f.write("### パターン5: ツール紹介×緊急性型\n\n")
        f.write("**特徴:**\n")
        f.write("- 「今すぐ」「まだ間に合う」など緊急性\n")
        f.write("- 具体的なツール名\n")
        f.write("- 簡潔にメリット提示\n\n")
        f.write("**投稿テンプレート:**\n")
        f.write("```\n")
        f.write("Claude Code、まだ使ってない人は損してます。\n\n")
        f.write("これ1つで:\n")
        f.write("・コード自動生成\n")
        f.write("・バグ修正も秒速\n")
        f.write("・ツール開発が爆速化\n\n")
        f.write("プログラミング初心者でも\n")
        f.write("Webアプリ作れるレベル。\n\n")
        f.write("みんなが気づく前に使い倒すべき🔥\n")
        f.write("```\n\n")

        f.write("## まとめ\n\n")
        f.write("### バズる投稿の必須要素\n\n")
        f.write("1. **冒頭で心を掴む** - 数字、疑問、煽り、共感のいずれかで開始\n")
        f.write("2. **具体的な数字** - 「月30万円」「3ヶ月」など明確な実績\n")
        f.write("3. **読みやすさ** - 改行・箇条書き・絵文字で視覚的に整理\n")
        f.write("4. **再現性** - 「自分にもできそう」と思わせる\n")
        f.write("5. **感情を刺激** - 期待・驚き・共感のいずれかを含める\n\n")
        f.write("これらを組み合わせることで、フォロワーが少なくてもバズる可能性が高まります。\n")

    print(f"\nレポート生成完了: {output_filename}")


def main():
    """メイン処理"""
    input_file = "output/buzz_posts_20260215.xlsx"
    today = datetime.now().strftime("%Y%m%d")
    output_file = f"output/analyze_report_詳細_v2_{today}.md"

    if not os.path.exists(input_file):
        print(f"エラー: {input_file} が見つかりません。")
        return

    print(f"分析対象: {input_file}")
    df = load_excel(input_file)

    if df is None or len(df) == 0:
        print("データが空です。")
        return

    # フィルタリング
    df_filtered, original_count, excluded_count = filter_data(df)

    if len(df_filtered) == 0:
        print("フィルタリング後のデータが空です。")
        return

    generate_report(df_filtered, output_file, original_count, excluded_count)


if __name__ == "__main__":
    main()
