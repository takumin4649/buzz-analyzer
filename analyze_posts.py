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


def filter_keywords(df):
    """炎上系・著作権問題系のみ除外（重複除去なし）"""
    exclude_keywords = [
        "著作権", "版権", "海賊版", "収益化停止", "収益化が停止",
        "剥奪", "侵害", "インプレゾンビ"
    ]

    def should_exclude(text):
        for keyword in exclude_keywords:
            if keyword in text:
                return True
        return False

    return df[~df["本文"].apply(should_exclude)].copy()


def filter_data(df):
    """データをフィルタリング"""
    original_count = len(df)

    # 1. 炎上系・著作権問題系を除外
    df_filtered = filter_keywords(df)
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


# === 新規分析関数: フォロワー正規化 ===

def analyze_follower_normalized(df):
    """フォロワー正規化エンゲージメント分析"""
    results = {
        "has_follower_data": False,
        "top10": [],
        "hidden_gems": [],
        "pattern_by_rate": {},
        "category_by_rate": {},
    }

    # フォロワー数を数値に変換
    df_work = df.copy()
    df_work["フォロワー数"] = pd.to_numeric(df_work["フォロワー数"], errors="coerce").fillna(0).astype(int)

    valid_followers = df_work[df_work["フォロワー数"] > 0]

    if len(valid_followers) >= 5:
        # フォロワーデータがある場合
        results["has_follower_data"] = True
        valid_followers = valid_followers.copy()
        valid_followers["エンゲージメント率"] = (valid_followers["いいね数"] / valid_followers["フォロワー数"]) * 100

        # TOP10
        top10 = valid_followers.nlargest(10, "エンゲージメント率")
        for _, row in top10.iterrows():
            results["top10"].append({
                "user": row["ユーザー名"],
                "likes": int(row["いいね数"]),
                "followers": int(row["フォロワー数"]),
                "rate": float(row["エンゲージメント率"]),
                "text": str(row["本文"])[:60],
            })

        # Hidden Gems: フォロワー数が中央値以下 & エンゲージメント率が75パーセンタイル以上
        median_followers = valid_followers["フォロワー数"].median()
        rate_75 = valid_followers["エンゲージメント率"].quantile(0.75)
        gems = valid_followers[
            (valid_followers["フォロワー数"] <= median_followers) &
            (valid_followers["エンゲージメント率"] >= rate_75)
        ].nlargest(5, "エンゲージメント率")
        for _, row in gems.iterrows():
            results["hidden_gems"].append({
                "user": row["ユーザー名"],
                "likes": int(row["いいね数"]),
                "followers": int(row["フォロワー数"]),
                "rate": float(row["エンゲージメント率"]),
                "text": str(row["本文"])[:60],
            })

        # パターン別エンゲージメント率
        for _, row in valid_followers.iterrows():
            text = safe_get(row, "本文", "")
            first_line = text.split("\n")[0] if text else ""
            pattern = classify_opening_pattern(first_line)
            if pattern not in results["pattern_by_rate"]:
                results["pattern_by_rate"][pattern] = []
            results["pattern_by_rate"][pattern].append(float(row["エンゲージメント率"]))

        # カテゴリ別エンゲージメント率
        for _, row in valid_followers.iterrows():
            text = safe_get(row, "本文", "")
            cat = classify_category(text)
            if cat not in results["category_by_rate"]:
                results["category_by_rate"][cat] = []
            results["category_by_rate"][cat].append(float(row["エンゲージメント率"]))
    else:
        # フォロワーデータがない場合: 総合エンゲージメントスコアで代替
        df_work["総合スコア"] = df_work["いいね数"] + df_work["リポスト数"] * 2 + df_work["リプライ数"] * 3
        top10 = df_work.nlargest(10, "総合スコア")
        for _, row in top10.iterrows():
            results["top10"].append({
                "user": row["ユーザー名"],
                "likes": int(row["いいね数"]),
                "followers": 0,
                "rate": float(row["総合スコア"]),
                "text": str(row["本文"])[:60],
            })

    return results


# === 新規分析関数: テキスト最適化 ===

EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF"
    "\U0000FE00-\U0000FE0F\U0000200D]+",
    flags=re.UNICODE,
)


def analyze_text_length(df):
    """文字数×エンゲージメント分析"""
    buckets = {
        "0-50字": (0, 50), "51-100字": (51, 100), "101-150字": (101, 150),
        "151-200字": (151, 200), "201-300字": (201, 300),
        "301-500字": (301, 500), "500字以上": (501, 99999),
    }

    bucket_data = {k: [] for k in buckets}
    lengths_likes = []

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        length = len(text)
        lengths_likes.append((length, likes))

        for bucket_name, (lo, hi) in buckets.items():
            if lo <= length <= hi:
                bucket_data[bucket_name].append(likes)
                break

    # 最適レンジ: 平均いいねが最も高いバケット
    best_bucket = max(bucket_data.items(), key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0)

    # 相関係数
    if len(lengths_likes) > 2:
        df_corr = pd.DataFrame(lengths_likes, columns=["length", "likes"])
        correlation = float(df_corr["length"].corr(df_corr["likes"]))
    else:
        correlation = 0.0

    all_lengths = [x[0] for x in lengths_likes]

    return {
        "avg_length": sum(all_lengths) / len(all_lengths) if all_lengths else 0,
        "bucket_data": bucket_data,
        "best_bucket": best_bucket[0],
        "correlation": correlation,
        "lengths_likes": lengths_likes,
    }


def analyze_emoji_usage(df):
    """絵文字使用分析"""
    with_emoji = []
    without_emoji = []
    emoji_count_data = defaultdict(list)  # count -> [likes]
    emoji_counter = Counter()

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        emojis = EMOJI_PATTERN.findall(text)
        count = len(emojis)

        if count > 0:
            with_emoji.append(likes)
            for e in emojis:
                emoji_counter[e] += 1
        else:
            without_emoji.append(likes)

        # 個数帯
        if count == 0:
            emoji_count_data["0個"].append(likes)
        elif count <= 2:
            emoji_count_data["1-2個"].append(likes)
        elif count <= 5:
            emoji_count_data["3-5個"].append(likes)
        else:
            emoji_count_data["6個以上"].append(likes)

    # 人気絵文字 TOP5
    top_emoji = emoji_counter.most_common(5)

    return {
        "with_emoji": with_emoji,
        "without_emoji": without_emoji,
        "emoji_count_data": emoji_count_data,
        "top_emoji": top_emoji,
    }


def analyze_hashtag_usage(df):
    """ハッシュタグ使用分析"""
    hashtag_pattern = re.compile(r'[#＃]\S+')
    with_hashtag = []
    without_hashtag = []
    hashtag_counter = Counter()
    count_data = defaultdict(list)  # tag_count -> [likes]

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        tags = hashtag_pattern.findall(text)
        tag_count = len(tags)

        if tag_count > 0:
            with_hashtag.append(likes)
            for tag in tags:
                hashtag_counter[tag] += 1
        else:
            without_hashtag.append(likes)

        if tag_count == 0:
            count_data["0個"].append(likes)
        elif tag_count <= 2:
            count_data["1-2個"].append(likes)
        else:
            count_data["3個以上"].append(likes)

    return {
        "with_hashtag": with_hashtag,
        "without_hashtag": without_hashtag,
        "top_hashtags": hashtag_counter.most_common(10),
        "count_data": count_data,
    }


# === 新規分析関数: バズ予測スコア ===

def calculate_buzz_score(text, score_params=None):
    """単一テキストのバズ予測スコアを計算（0-100点）"""
    if score_params is None:
        score_params = {}

    factors = {}
    total = 0

    # 1. 冒頭パターン (20点)
    first_line = text.split("\n")[0] if text else ""
    pattern = classify_opening_pattern(first_line)
    pattern_scores = {"数字提示": 20, "疑問形": 16, "煽り": 14, "共感": 14, "呼びかけ": 12, "断定形": 8, "その他": 5}
    s = pattern_scores.get(pattern, 5)
    factors["冒頭パターン"] = s
    total += s

    # 2. テキスト最適化 (15点)
    length = len(text)
    optimal_min = score_params.get("optimal_min", 100)
    optimal_max = score_params.get("optimal_max", 300)
    if optimal_min <= length <= optimal_max:
        s = 15
    elif length < optimal_min:
        s = max(3, int(15 * length / optimal_min))
    else:
        s = max(3, int(15 * optimal_max / length))
    factors["テキスト最適化"] = s
    total += s

    # 3. カテゴリ (15点)
    category = classify_category(text)
    cat_scores = score_params.get("cat_scores", {
        "実績報告系": 15, "ノウハウ系": 13, "問題提起系": 12,
        "体験談系": 11, "ツール紹介系": 10, "ニュース系": 8, "その他": 5,
    })
    s = cat_scores.get(category, 5)
    factors["カテゴリ"] = s
    total += s

    # 4. 感情トリガー (10点)
    emotion_patterns = {
        "期待": r'チャンス|可能性|稼げる|儲かる|成功|達成|実現|できる',
        "驚き": r'まさか|びっくり|驚き|すごい|やばい',
        "共感": r'わかる|そうそう|あるある|同じ|私も',
        "恐怖": r'危険|怖い|リスク|失敗|損|ヤバい|最悪',
    }
    emotion_count = sum(1 for pat in emotion_patterns.values() if re.search(pat, text, re.IGNORECASE))
    s = min(10, emotion_count * 4)
    factors["感情トリガー"] = s
    total += s

    # 5. CTA (10点)
    cta_patterns = [r'いいね|👍', r'保存|ブックマーク', r'フォロー', r'リポスト|RT|シェア|拡散', r'コメント|返信|教えて']
    has_cta = any(re.search(p, text, re.IGNORECASE) for p in cta_patterns)
    s = 10 if has_cta else 0
    factors["CTA"] = s
    total += s

    # 6. ストーリー性 (10点)
    s = 10 if has_story(text) else 0
    factors["ストーリー性"] = s
    total += s

    # 7. 絵文字・書式 (10点)
    emojis = EMOJI_PATTERN.findall(text)
    emoji_count = len(emojis)
    if 1 <= emoji_count <= 3:
        s = 10
    elif emoji_count == 0:
        s = 4
    else:
        s = 6
    factors["絵文字・書式"] = s
    total += s

    # 8. 読みやすさ (10点)
    line_breaks = text.count("\n")
    bullet_pattern = re.compile(r'^[・\-\*①-➓1-9]\s', re.MULTILINE)
    has_bullets = bool(bullet_pattern.search(text))
    s = 0
    if 3 <= line_breaks <= 10:
        s += 5
    elif line_breaks > 0:
        s += 3
    if has_bullets:
        s += 5
    factors["読みやすさ"] = s
    total += s

    return {"total_score": total, "factors": factors}


def analyze_buzz_scores(df, score_params=None):
    """全投稿のバズスコアを計算し分析"""
    scores = []

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        result = calculate_buzz_score(text, score_params)
        scores.append({
            "text": text[:60],
            "score": result["total_score"],
            "likes": likes,
            "factors": result["factors"],
        })

    # スコアと実いいね数の相関
    if len(scores) > 2:
        df_scores = pd.DataFrame(scores)
        correlation = float(df_scores["score"].corr(df_scores["likes"]))
    else:
        correlation = 0.0

    # スコア帯別の平均いいね数
    score_buckets = {"80-100点": [], "60-79点": [], "40-59点": [], "0-39点": []}
    for s in scores:
        sc = s["score"]
        if sc >= 80:
            score_buckets["80-100点"].append(s["likes"])
        elif sc >= 60:
            score_buckets["60-79点"].append(s["likes"])
        elif sc >= 40:
            score_buckets["40-59点"].append(s["likes"])
        else:
            score_buckets["0-39点"].append(s["likes"])

    # 要素別の平均寄与度
    factor_totals = defaultdict(list)
    for s in scores:
        for factor, value in s["factors"].items():
            factor_totals[factor].append(value)

    factor_avg = {k: sum(v) / len(v) if v else 0 for k, v in factor_totals.items()}

    return {
        "scores": sorted(scores, key=lambda x: x["score"], reverse=True),
        "correlation": correlation,
        "score_buckets": score_buckets,
        "factor_avg": factor_avg,
    }


# === 新規分析関数: ユーザー分析 ===

def analyze_users(df_raw, df_filtered):
    """ユーザー分析（重複除去前のデータを使用）"""
    user_stats = []
    grouped = df_raw.groupby("ユーザー名")

    for user, group in grouped:
        likes_list = group["いいね数"].tolist()
        user_stats.append({
            "user": user,
            "post_count": len(group),
            "avg_likes": sum(likes_list) / len(likes_list) if likes_list else 0,
            "max_likes": max(likes_list) if likes_list else 0,
            "total_likes": sum(likes_list),
            "std_likes": pd.Series(likes_list).std() if len(likes_list) > 1 else 0,
        })

    user_stats.sort(key=lambda x: x["total_likes"], reverse=True)

    # リピートバズユーザー
    repeat_buzzers = [u for u in user_stats if u["post_count"] >= 2]

    # 投稿頻度とエンゲージメントの関係
    freq_data = defaultdict(list)
    for u in user_stats:
        count = u["post_count"]
        if count == 1:
            freq_data["1件"].append(u["avg_likes"])
        elif count == 2:
            freq_data["2件"].append(u["avg_likes"])
        else:
            freq_data["3件以上"].append(u["avg_likes"])

    # 常連バズアカウントの共通特徴
    common_traits = {"categories": Counter(), "openings": Counter(), "cta_count": 0, "total": 0, "text_lengths": []}
    for user in repeat_buzzers[:10]:
        user_posts = df_raw[df_raw["ユーザー名"] == user["user"]]
        for _, row in user_posts.iterrows():
            text = safe_get(row, "本文", "")
            common_traits["categories"][classify_category(text)] += 1
            first_line = text.split("\n")[0] if text else ""
            common_traits["openings"][classify_opening_pattern(first_line)] += 1
            common_traits["text_lengths"].append(len(text))
            common_traits["total"] += 1
            cta_pats = [r'いいね|👍', r'保存|ブックマーク', r'フォロー', r'リポスト|RT|シェア|拡散', r'コメント|返信|教えて']
            if any(re.search(p, text, re.IGNORECASE) for p in cta_pats):
                common_traits["cta_count"] += 1

    return {
        "user_stats": user_stats,
        "repeat_buzzers": repeat_buzzers,
        "freq_data": freq_data,
        "common_traits": common_traits,
    }


def generate_report(df, output_filename, original_count, excluded_count, df_raw=None):
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

        # === セクション8: フォロワー正規化エンゲージメント分析 ===
        print("フォロワー正規化分析中...")
        f.write("## 8. フォロワー正規化エンゲージメント分析\n\n")

        follower_data = analyze_follower_normalized(df)

        if follower_data["has_follower_data"]:
            f.write("### エンゲージメント率 TOP10\n\n")
            f.write("| 順位 | ユーザー | いいね数 | フォロワー数 | エンゲージメント率 |\n")
            f.write("|------|---------|---------|------------|------------------|\n")
            for i, item in enumerate(follower_data["top10"], 1):
                f.write(f"| {i} | @{item['user']} | {item['likes']:,} | {item['followers']:,} | {item['rate']:.1f}% |\n")
            f.write("\n")

            if follower_data["hidden_gems"]:
                f.write("### Hidden Gems（隠れた名投稿）\n\n")
                f.write("低フォロワーでも高エンゲージメント率を達成したポスト：\n\n")
                for item in follower_data["hidden_gems"]:
                    f.write(f"- **@{item['user']}** (フォロワー: {item['followers']:,}人) - エンゲージメント率: {item['rate']:.1f}% - {item['text']}...\n")
                f.write("\n")

            if follower_data["pattern_by_rate"]:
                f.write("### パターン別エンゲージメント率\n\n")
                f.write("| パターン | 件数 | 平均エンゲージメント率 |\n")
                f.write("|---------|------|---------------------|\n")
                pat_sorted = sorted(follower_data["pattern_by_rate"].items(), key=lambda x: sum(x[1])/len(x[1]) if x[1] else 0, reverse=True)
                for pat, rates in pat_sorted:
                    avg_rate = sum(rates) / len(rates) if rates else 0
                    f.write(f"| {pat} | {len(rates)}件 | {avg_rate:.1f}% |\n")
                f.write("\n")

            if follower_data["category_by_rate"]:
                f.write("### カテゴリ別エンゲージメント率\n\n")
                f.write("| カテゴリ | 件数 | 平均エンゲージメント率 |\n")
                f.write("|---------|------|---------------------|\n")
                cat_sorted = sorted(follower_data["category_by_rate"].items(), key=lambda x: sum(x[1])/len(x[1]) if x[1] else 0, reverse=True)
                for cat, rates in cat_sorted:
                    avg_rate = sum(rates) / len(rates) if rates else 0
                    f.write(f"| {cat} | {len(rates)}件 | {avg_rate:.1f}% |\n")
                f.write("\n")
        else:
            f.write("**注意:** フォロワー数データが取得されていないため、総合エンゲージメントスコア（いいね + リポスト*2 + リプライ*3）で代替分析を行います。\n\n")
            f.write("### 総合エンゲージメントスコア TOP10\n\n")
            f.write("| 順位 | ユーザー | いいね数 | 総合スコア | 本文 |\n")
            f.write("|------|---------|---------|-----------|------|\n")
            for i, item in enumerate(follower_data["top10"], 1):
                f.write(f"| {i} | @{item['user']} | {item['likes']:,} | {item['rate']:.0f} | {item['text']}... |\n")
            f.write("\n")

        # === セクション9: テキスト最適化分析 ===
        print("テキスト最適化を分析中...")
        f.write("## 9. テキスト最適化分析\n\n")

        text_length_data = analyze_text_length(df)
        f.write("### 最適文字数分析\n\n")
        f.write(f"- **全体の平均文字数:** {text_length_data['avg_length']:.0f}字\n")
        f.write(f"- **最適文字数帯:** {text_length_data['best_bucket']}\n")
        f.write(f"- **文字数といいね数の相関:** r={text_length_data['correlation']:.2f}\n\n")

        f.write("| 文字数帯 | 件数 | 平均いいね数 |\n")
        f.write("|---------|------|-------------|\n")
        for bucket_name, likes in text_length_data["bucket_data"].items():
            avg = sum(likes) / len(likes) if likes else 0
            f.write(f"| {bucket_name} | {len(likes)}件 | {avg:.0f}件 |\n")
        f.write("\n")

        emoji_data = analyze_emoji_usage(df)
        f.write("### 絵文字使用分析\n\n")
        avg_with = sum(emoji_data["with_emoji"]) / len(emoji_data["with_emoji"]) if emoji_data["with_emoji"] else 0
        avg_without = sum(emoji_data["without_emoji"]) / len(emoji_data["without_emoji"]) if emoji_data["without_emoji"] else 0
        f.write(f"- **絵文字あり:** {len(emoji_data['with_emoji'])}件（平均いいね: {avg_with:.0f}件）\n")
        f.write(f"- **絵文字なし:** {len(emoji_data['without_emoji'])}件（平均いいね: {avg_without:.0f}件）\n\n")

        f.write("| 絵文字数 | 件数 | 平均いいね数 |\n")
        f.write("|---------|------|-------------|\n")
        for count_label in ["0個", "1-2個", "3-5個", "6個以上"]:
            likes = emoji_data["emoji_count_data"].get(count_label, [])
            avg = sum(likes) / len(likes) if likes else 0
            f.write(f"| {count_label} | {len(likes)}件 | {avg:.0f}件 |\n")
        f.write("\n")

        if emoji_data["top_emoji"]:
            f.write("**人気絵文字TOP5:**\n\n")
            for i, (emoji, count) in enumerate(emoji_data["top_emoji"], 1):
                f.write(f"{i}. {emoji} ({count}件)\n")
            f.write("\n")

        hashtag_data = analyze_hashtag_usage(df)
        f.write("### ハッシュタグ分析\n\n")
        avg_with_ht = sum(hashtag_data["with_hashtag"]) / len(hashtag_data["with_hashtag"]) if hashtag_data["with_hashtag"] else 0
        avg_without_ht = sum(hashtag_data["without_hashtag"]) / len(hashtag_data["without_hashtag"]) if hashtag_data["without_hashtag"] else 0
        f.write(f"- **ハッシュタグあり:** {len(hashtag_data['with_hashtag'])}件（平均いいね: {avg_with_ht:.0f}件）\n")
        f.write(f"- **ハッシュタグなし:** {len(hashtag_data['without_hashtag'])}件（平均いいね: {avg_without_ht:.0f}件）\n\n")

        if hashtag_data["top_hashtags"]:
            f.write("**人気ハッシュタグTOP10:**\n\n")
            for i, (tag, count) in enumerate(hashtag_data["top_hashtags"], 1):
                f.write(f"{i}. {tag} ({count}件)\n")
            f.write("\n")

        # === セクション10: バズ予測スコア ===
        print("バズ予測スコアを計算中...")
        f.write("## 10. バズ予測スコア\n\n")

        # スコアパラメータをデータから推定
        score_params = {}
        tl = text_length_data
        if tl["best_bucket"]:
            buckets_ranges = {
                "0-50字": (0, 50), "51-100字": (51, 100), "101-150字": (101, 150),
                "151-200字": (151, 200), "201-300字": (201, 300),
                "301-500字": (301, 500), "500字以上": (501, 1000),
            }
            rng = buckets_ranges.get(tl["best_bucket"], (100, 300))
            score_params["optimal_min"] = rng[0]
            score_params["optimal_max"] = rng[1]

        buzz_data = analyze_buzz_scores(df, score_params)

        f.write("### スコアリングモデル\n\n")
        f.write("| 要素 | 配点 | 説明 |\n")
        f.write("|------|------|------|\n")
        f.write("| 冒頭パターン | 20点 | 数字提示・疑問形が高得点 |\n")
        f.write("| テキスト最適化 | 15点 | 最適文字数範囲内かどうか |\n")
        f.write("| カテゴリ | 15点 | 高エンゲージメントカテゴリか |\n")
        f.write("| 感情トリガー | 10点 | 感情を刺激する要素 |\n")
        f.write("| CTA | 10点 | 行動喚起の有無 |\n")
        f.write("| ストーリー性 | 10点 | 物語的要素の有無 |\n")
        f.write("| 絵文字・書式 | 10点 | 適切な絵文字使用 |\n")
        f.write("| 読みやすさ | 10点 | 改行・箇条書きの使用 |\n")
        f.write("\n")

        corr = buzz_data["correlation"]
        strength = "強い" if abs(corr) > 0.5 else "中程度の" if abs(corr) > 0.3 else "弱い"
        f.write("### モデル精度\n\n")
        f.write(f"- **予測スコアと実際のいいね数の相関:** r={corr:.2f}\n")
        f.write(f"- **判定:** {strength}相関\n\n")

        f.write("### スコア帯別の実際のいいね数\n\n")
        f.write("| スコア帯 | 件数 | 平均いいね数 |\n")
        f.write("|---------|------|-------------|\n")
        for bucket_name in ["80-100点", "60-79点", "40-59点", "0-39点"]:
            likes = buzz_data["score_buckets"].get(bucket_name, [])
            avg = sum(likes) / len(likes) if likes else 0
            f.write(f"| {bucket_name} | {len(likes)}件 | {avg:.0f}件 |\n")
        f.write("\n")

        f.write("### 要素別の平均スコア（影響度ランキング）\n\n")
        factor_sorted = sorted(buzz_data["factor_avg"].items(), key=lambda x: x[1], reverse=True)
        for i, (factor, avg_score) in enumerate(factor_sorted, 1):
            f.write(f"{i}. **{factor}** - 平均{avg_score:.1f}点\n")
        f.write("\n")

        f.write("### TOP10投稿のスコア分析\n\n")
        f.write("| 順位 | いいね数 | バズスコア | 主な高得点要因 |\n")
        f.write("|------|---------|-----------|-------------|\n")
        top_by_likes = sorted(buzz_data["scores"], key=lambda x: x["likes"], reverse=True)[:10]
        for i, item in enumerate(top_by_likes, 1):
            top_factors = sorted(item["factors"].items(), key=lambda x: x[1], reverse=True)[:2]
            factor_str = ", ".join(f"{f[0]}({f[1]}点)" for f in top_factors)
            f.write(f"| {i} | {item['likes']:,} | {item['score']}点 | {factor_str} |\n")
        f.write("\n")

        # === セクション11: ユーザー分析 ===
        if df_raw is not None:
            print("ユーザー分析中...")
            f.write("## 11. ユーザー分析\n\n")
            f.write(f"**注意:** この分析はフィルタリング前のデータ（{len(df_raw)}件）を使用しています。\n\n")

            user_data = analyze_users(df_raw, df)

            if user_data["repeat_buzzers"]:
                f.write("### リピートバズユーザー\n\n")
                f.write("複数の高エンゲージメント投稿を持つユーザー：\n\n")
                f.write("| ユーザー | 投稿数 | 平均いいね | 最大いいね | 合計いいね |\n")
                f.write("|---------|--------|-----------|-----------|----------|\n")
                for u in user_data["repeat_buzzers"][:15]:
                    f.write(f"| @{u['user']} | {u['post_count']}件 | {u['avg_likes']:.0f} | {u['max_likes']:,} | {u['total_likes']:,} |\n")
                f.write("\n")

            traits = user_data["common_traits"]
            if traits["total"] > 0:
                f.write("### 常連バズアカウントの共通特徴\n\n")
                avg_len = sum(traits["text_lengths"]) / len(traits["text_lengths"]) if traits["text_lengths"] else 0
                f.write(f"- **平均投稿文字数:** {avg_len:.0f}字\n")
                if traits["categories"]:
                    top_cat = traits["categories"].most_common(1)[0]
                    f.write(f"- **最多カテゴリ:** {top_cat[0]}（{top_cat[1]}件）\n")
                if traits["openings"]:
                    top_open = traits["openings"].most_common(1)[0]
                    f.write(f"- **最多冒頭パターン:** {top_open[0]}（{top_open[1]}件）\n")
                cta_rate = (traits["cta_count"] / traits["total"]) * 100 if traits["total"] > 0 else 0
                f.write(f"- **CTA使用率:** {cta_rate:.0f}%\n\n")

            f.write("### 投稿頻度とエンゲージメントの関係\n\n")
            f.write("| 投稿数 | ユーザー数 | 平均いいね |\n")
            f.write("|--------|-----------|----------|\n")
            for freq_label in ["1件", "2件", "3件以上"]:
                likes = user_data["freq_data"].get(freq_label, [])
                avg = sum(likes) / len(likes) if likes else 0
                f.write(f"| {freq_label} | {len(likes)}人 | {avg:.0f} |\n")
            f.write("\n")

        # === まとめ ===
        f.write("## まとめ\n\n")
        f.write("### バズる投稿の必須要素\n\n")
        f.write("1. **冒頭で心を掴む** - 数字、疑問、煽り、共感のいずれかで開始\n")
        f.write("2. **具体的な数字** - 「月30万円」「3ヶ月」など明確な実績\n")
        f.write("3. **読みやすさ** - 改行・箇条書き・絵文字で視覚的に整理\n")
        f.write("4. **再現性** - 「自分にもできそう」と思わせる\n")
        f.write("5. **感情を刺激** - 期待・驚き・共感のいずれかを含める\n")
        f.write(f"6. **最適な文字数** - {text_length_data['best_bucket']}が最もエンゲージメントが高い\n")
        f.write(f"7. **バズ予測スコア** - スコアと実いいね数の相関 r={corr:.2f}\n\n")
        f.write("これらを組み合わせることで、フォロワーが少なくてもバズる可能性が高まります。\n\n")

        # セクション12: バズポスト自動生成
        print("バズポストテンプレートを生成中...")
        try:
            from generate_posts import generate_posts, format_posts_markdown
            posts, tools, works, ctas = generate_posts(df)
            md = format_posts_markdown(posts, tools, works, ctas, section_num=12)
            f.write(md)
        except Exception as e:
            print(f"  投稿テンプレート生成をスキップ: {e}")

        # セクション13: グラフ可視化
        print("グラフを生成中...")
        try:
            from visualize import generate_all_charts
            chart_dir = os.path.join(os.path.dirname(output_filename), "charts")
            chart_paths = generate_all_charts(df, chart_dir, df_raw=df_raw)
            f.write("\n## 13. 可視化グラフ\n\n")
            f.write("以下のグラフが生成されました：\n\n")
            for name, path in chart_paths.items():
                f.write(f"- **{name}**: `{path}`\n")
            f.write("\n")
        except Exception as e:
            print(f"  グラフ生成をスキップ: {e}")

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

    # キーワードフィルタのみ（ユーザー分析用）
    df_keyword_filtered = filter_keywords(df)

    # フィルタリング（キーワード + 重複除去）
    df_filtered, original_count, excluded_count = filter_data(df)

    if len(df_filtered) == 0:
        print("フィルタリング後のデータが空です。")
        return

    generate_report(df_filtered, output_file, original_count, excluded_count, df_raw=df_keyword_filtered)


if __name__ == "__main__":
    main()
