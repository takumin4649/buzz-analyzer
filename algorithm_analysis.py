"""Xアルゴリズム分析モジュール

Xの公開アルゴリズム（Phoenix/Grok）に基づいた投稿分析。
以下の分析を提供：
1. Xアルゴリズムスコア予測（エンゲージメント重みベース）
2. 議論誘発度（リプライ/いいね比率）のアルゴリズム価値
3. スレッド構造検出
4. 外部リンク検出とリーチ減衰推定
5. トーン分析（ポジティブ/ネガティブ/建設的）
6. 滞在時間推定（文字数×構造による推定）
7. 早期エンゲージメント予測

ソース: xai-org/x-algorithm, twitter/the-algorithm, Grok AI分析
"""

import re
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd

from analyze_posts import (
    classify_category,
    classify_opening_pattern,
    has_story,
    safe_get,
)


# ========================================
# Xアルゴリズム公式重み（2026年2月版）
# ========================================

X_ALGORITHM_WEIGHTS = {
    "author_reply":     75.0,   # 著者自身がリプに返信
    "reply":            13.5,   # リプライ
    "profile_click":    12.0,   # プロフィールクリック
    "conversation_click": 11.0, # 会話クリック（スレッド展開）
    "bookmark":         10.0,   # ブックマーク
    "retweet":           1.0,   # RT
    "like":              0.5,   # いいね
    "dwell_2min":       10.0,   # 滞在時間2分以上
    "negative":        -74.0,   # 非表示など
    "report":         -369.0,   # 通報
}

# Grok時代の追加ブースト係数
GROK_MULTIPLIERS = {
    "x_premium":         4.0,   # Premium加入者の投稿ブースト
    "text_vs_video":     1.3,   # テキストは動画より30%強い
    "thread_boost":      3.0,   # スレッドは単発の3倍
    "external_link_penalty": 0.5,  # 外部リンクで50%減
}


# ========================================
# 1. Xアルゴリズムスコア予測
# ========================================

def calculate_algorithm_score(text, likes=0, retweets=0, replies=0,
                               bookmarks=0, has_premium=False):
    """Xアルゴリズムに基づくスコア予測（0-100点）

    テキスト特徴からエンゲージメント確率を推定し、
    公式重みで加重スコアを算出する。
    """
    factors = {}
    total = 0

    # --- 1. リプライ誘発力 (25点) ---
    # リプライ重み13.5 + 著者返信75.0 → 最重要
    reply_triggers = 0
    # 疑問形（リプライ誘発）
    if re.search(r'[\?？]', text):
        reply_triggers += 3
    # 意見を求める表現
    if re.search(r'(どう思|教えて|みんなは|皆さんは|あなたは|聞きたい|知りたい)', text):
        reply_triggers += 4
    # 議論を生む対立構造
    if re.search(r'(vs|VS|それとも|どっち|AかBか|賛否|議論)', text):
        reply_triggers += 3
    # 体験共有の誘発
    if re.search(r'(同じ人|経験ある|やったことある|わかる人|共感)', text):
        reply_triggers += 2
    # 自己開示（共感リプライ誘発）
    if re.search(r'(正直|ぶっちゃけ|実は|告白|本音)', text):
        reply_triggers += 2
    # ツッコミどころ（意図的な隙）
    if re.search(r'(かもしれない|知らんけど|異論は認める|怒られそう)', text):
        reply_triggers += 2

    s = min(25, reply_triggers * 3)
    factors["リプライ誘発力"] = s
    total += s

    # --- 2. 滞在時間推定 (20点) ---
    # dwell_2min = +10.0の重み
    dwell_score = estimate_dwell_time_score(text)
    s = min(20, dwell_score)
    factors["滞在時間"] = s
    total += s

    # --- 3. スレッド・会話深度 (15点) ---
    # conversation_click = 11.0の重み
    thread_info = detect_thread_structure(text)
    if thread_info["is_thread_starter"]:
        s = 15  # スレッド開始 = 3倍ブースト
    elif thread_info["has_continuation_hint"]:
        s = 10  # 続きがありそう
    elif thread_info["invites_conversation"]:
        s = 8   # 会話を誘う
    else:
        s = 0
    factors["スレッド・会話"] = s
    total += s

    # --- 4. トーン評価 (15点) ---
    # Grokがトーンを直接評価
    tone = analyze_tone(text)
    if tone["overall"] == "建設的":
        s = 15
    elif tone["overall"] == "ポジティブ":
        s = 12
    elif tone["overall"] == "中立":
        s = 8
    elif tone["overall"] == "煽り（建設的）":
        s = 10  # 建設的な問題提起は評価される
    elif tone["overall"] == "ネガティブ":
        s = 3
    else:  # 攻撃的
        s = 0
    factors["トーン"] = s
    total += s

    # --- 5. ブックマーク誘発力 (10点) ---
    # bookmark = 10.0の重み
    bookmark_triggers = 0
    if re.search(r'(保存|ブクマ|ブックマーク|メモ|後で)', text):
        bookmark_triggers += 3
    # リスト・ノウハウ（保存したくなる）
    if re.search(r'(選|つのコツ|つの方法|ステップ|手順|まとめ|一覧|チェックリスト)', text):
        bookmark_triggers += 3
    # 具体的な数字（保存価値が高い）
    if re.search(r'\d+[万円個件つ%]', text):
        bookmark_triggers += 2
    # テンプレート・フレームワーク
    if re.search(r'(テンプレ|フレームワーク|型|フォーマット|雛形)', text):
        bookmark_triggers += 3

    s = min(10, bookmark_triggers * 2)
    factors["ブックマーク誘発"] = s
    total += s

    # --- 6. 外部リンクペナルティ (-15点) ---
    link_info = detect_external_links(text)
    if link_info["has_external_link"]:
        s = -15  # 30-50%リーチ減
    elif link_info["has_x_link"]:
        s = -3   # X内リンクは軽微
    else:
        s = 0
    factors["外部リンク"] = s
    total += s

    # --- 7. プロフィールクリック誘発 (10点) ---
    # profile_click = 12.0の重み
    profile_triggers = 0
    if re.search(r'(プロフ|固ツイ|固定ツイート|自己紹介)', text):
        profile_triggers += 2
    # 権威性（誰？と気になる）
    if re.search(r'(年目|月目|万フォロワー|実績|経歴|専門)', text):
        profile_triggers += 2
    # ミステリアスさ
    if re.search(r'(秘密|内緒|ここだけ|限定|非公開)', text):
        profile_triggers += 2
    # 自己開示（もっと知りたい）
    if re.search(r'(僕|私|俺).{0,10}(実は|正直|ぶっちゃけ)', text):
        profile_triggers += 2

    s = min(10, profile_triggers * 2)
    factors["プロフクリック誘発"] = s
    total += s

    # --- 8. 早期エンゲージメント予測 (5点) ---
    # 最初の1時間で50%が決まる → 即座にリアクションしやすい投稿か
    early_triggers = 0
    # 短いリアクション可能（すぐいいね・リプしやすい）
    first_line = text.split("\n")[0] if text else ""
    if len(first_line) <= 40 and re.search(r'[！!？?]', first_line):
        early_triggers += 2
    # 感情的反応を引き出す
    if re.search(r'(マジで|ガチで|ヤバい|やばい|すごい|神|最強|衝撃)', text):
        early_triggers += 2
    # 短文で完結（すぐ読める = すぐリアクション）
    if len(text) <= 140:
        early_triggers += 1

    s = min(5, early_triggers * 2)
    factors["早期反応性"] = s
    total += s

    total = max(0, min(100, total))

    return {
        "total_score": total,
        "factors": factors,
        "algorithm_weights_used": True,
    }


# ========================================
# 2. 議論誘発度のアルゴリズム価値分析
# ========================================

def analyze_discussion_algorithm_value(df):
    """議論誘発度をアルゴリズム重みベースで分析

    リプライはいいねの27倍、著者返信は150倍の価値。
    この重みを使って「真のアルゴリズムスコア」を推定する。
    """
    results = []

    for _, row in df.iterrows():
        likes = safe_get(row, "いいね数", 0)
        replies = safe_get(row, "リプライ数", 0)
        retweets = safe_get(row, "リポスト数", 0)
        text = safe_get(row, "本文", "")
        user = safe_get(row, "ユーザー名", "")

        if likes <= 0:
            continue

        # アルゴリズム加重スコア（公式重みベース）
        weighted_score = (
            likes * X_ALGORITHM_WEIGHTS["like"] +
            retweets * X_ALGORITHM_WEIGHTS["retweet"] +
            replies * X_ALGORITHM_WEIGHTS["reply"]
        )

        # 従来のエンゲージメントスコア
        simple_score = likes + retweets * 2 + replies * 3

        # アルゴリズム加重 vs 単純スコアの乖離
        # 乖離が大きい = リプライが多い = アルゴリズムが高評価
        ratio = weighted_score / simple_score if simple_score > 0 else 0

        # 議論誘発率
        discussion_rate = replies / likes if likes > 0 else 0

        results.append({
            "text": text[:60],
            "user": user,
            "likes": likes,
            "retweets": retweets,
            "replies": replies,
            "discussion_rate": discussion_rate,
            "weighted_score": weighted_score,
            "simple_score": simple_score,
            "algorithm_boost": ratio,
            "category": classify_category(text),
        })

    results.sort(key=lambda x: x["weighted_score"], reverse=True)

    # カテゴリ別アルゴリズムスコア
    cat_scores = defaultdict(list)
    for r in results:
        cat_scores[r["category"]].append(r["weighted_score"])

    return {
        "top10_by_algorithm": results[:10],
        "top10_by_discussion": sorted(results, key=lambda x: x["discussion_rate"], reverse=True)[:10],
        "avg_weighted": sum(r["weighted_score"] for r in results) / len(results) if results else 0,
        "avg_discussion_rate": sum(r["discussion_rate"] for r in results) / len(results) if results else 0,
        "cat_algorithm_scores": {k: sum(v) / len(v) for k, v in cat_scores.items() if v},
        "all_results": results,
    }


# ========================================
# 3. スレッド構造検出
# ========================================

def detect_thread_structure(text):
    """投稿がスレッド形式かどうかを検出

    スレッドは単発投稿の3倍のエンゲージメント。
    会話クリック重み = 11.0。
    """
    indicators = {
        "is_thread_starter": False,
        "has_continuation_hint": False,
        "invites_conversation": False,
        "thread_signals": [],
    }

    # スレッド開始のシグナル
    thread_start_patterns = [
        (r'[🧵スレッド]', "スレッド明示"),
        (r'(1/\d|①|1\.)', "番号付き開始"),
        (r'(以下|↓|👇|⬇)', "続きを示唆"),
        (r'(長くなるので|連投します|スレにします)', "スレッド宣言"),
    ]
    for pattern, signal in thread_start_patterns:
        if re.search(pattern, text):
            indicators["is_thread_starter"] = True
            indicators["thread_signals"].append(signal)

    # 続きがありそうなシグナル
    continuation_patterns = [
        (r'(続く|つづく|続きは|次は)', "続き示唆"),
        (r'(まず|最初に|第一に)', "順序開始"),
        (r'\.{3,}$|…$', "余韻（続きあり）"),
    ]
    for pattern, signal in continuation_patterns:
        if re.search(pattern, text):
            indicators["has_continuation_hint"] = True
            indicators["thread_signals"].append(signal)

    # 会話を誘うシグナル
    conversation_patterns = [
        (r'[\?？]$', "疑問で終わる"),
        (r'(どう思|教えて|みんなは|意見)', "意見を求める"),
        (r'(あなたは|君は|皆さんは)', "直接問いかけ"),
    ]
    for pattern, signal in conversation_patterns:
        if re.search(pattern, text):
            indicators["invites_conversation"] = True
            indicators["thread_signals"].append(signal)

    return indicators


def analyze_thread_potential(df):
    """全投稿のスレッドポテンシャルを分析"""
    thread_posts = []
    non_thread_posts = []

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        retweets = safe_get(row, "リポスト数", 0)
        replies = safe_get(row, "リプライ数", 0)

        thread_info = detect_thread_structure(text)
        is_thread_like = (
            thread_info["is_thread_starter"] or
            thread_info["has_continuation_hint"]
        )

        entry = {
            "text": text[:60],
            "likes": likes,
            "retweets": retweets,
            "replies": replies,
            "thread_info": thread_info,
        }

        if is_thread_like:
            thread_posts.append(entry)
        else:
            non_thread_posts.append(entry)

    # 比較統計
    def avg(posts, key):
        if not posts:
            return 0
        return sum(p[key] for p in posts) / len(posts)

    return {
        "thread_count": len(thread_posts),
        "non_thread_count": len(non_thread_posts),
        "thread_avg_likes": avg(thread_posts, "likes"),
        "non_thread_avg_likes": avg(non_thread_posts, "likes"),
        "thread_avg_replies": avg(thread_posts, "replies"),
        "non_thread_avg_replies": avg(non_thread_posts, "replies"),
        "thread_posts": thread_posts,
        "non_thread_posts": non_thread_posts,
    }


# ========================================
# 4. 外部リンク検出とリーチ減衰推定
# ========================================

def detect_external_links(text):
    """外部リンクの検出

    外部リンク → 30-50%リーチ減。
    X内リンク（x.com, twitter.com）は軽微。
    """
    url_pattern = re.compile(r'https?://([^\s/]+)')
    urls = url_pattern.findall(text)

    x_domains = {"x.com", "twitter.com", "t.co", "pbs.twimg.com"}
    external_urls = [u for u in urls if not any(d in u for d in x_domains)]
    x_urls = [u for u in urls if any(d in u for d in x_domains)]

    # リーチ減衰推定
    if external_urls:
        reach_multiplier = 0.5  # 50%減
    elif x_urls:
        reach_multiplier = 0.95  # 5%減
    else:
        reach_multiplier = 1.0  # 減衰なし

    return {
        "has_external_link": len(external_urls) > 0,
        "has_x_link": len(x_urls) > 0,
        "external_domains": external_urls,
        "x_links": x_urls,
        "reach_multiplier": reach_multiplier,
        "penalty_pct": round((1 - reach_multiplier) * 100),
    }


def analyze_link_impact(df):
    """全投稿のリンク有無とパフォーマンスを分析"""
    with_external = []
    with_x_link = []
    no_link = []

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        retweets = safe_get(row, "リポスト数", 0)
        replies = safe_get(row, "リプライ数", 0)

        link_info = detect_external_links(text)

        entry = {
            "likes": likes, "retweets": retweets, "replies": replies,
            "text": text[:60], "link_info": link_info,
        }

        if link_info["has_external_link"]:
            with_external.append(entry)
        elif link_info["has_x_link"]:
            with_x_link.append(entry)
        else:
            no_link.append(entry)

    def avg(posts, key):
        if not posts:
            return 0
        return sum(p[key] for p in posts) / len(posts)

    return {
        "external_count": len(with_external),
        "x_link_count": len(with_x_link),
        "no_link_count": len(no_link),
        "external_avg_likes": avg(with_external, "likes"),
        "x_link_avg_likes": avg(with_x_link, "likes"),
        "no_link_avg_likes": avg(no_link, "likes"),
        "reach_penalty_confirmed": avg(no_link, "likes") > avg(with_external, "likes"),
    }


# ========================================
# 5. トーン分析（Grok評価推定）
# ========================================

def analyze_tone(text):
    """投稿のトーンを分析（Grokの評価を推定）

    Grokは以下を評価:
    - ポジティブ/建設的 → 拡散促進
    - 攻撃的/rage bait → 抑制
    """
    scores = {
        "positive": 0,
        "constructive": 0,
        "negative": 0,
        "aggressive": 0,
        "neutral": 0,
    }

    # ポジティブシグナル
    positive_patterns = [
        r'嬉しい|楽しい|幸せ|最高|素晴らしい|感謝|ありがとう',
        r'おすすめ|良い|好き|素敵|神|便利|助かる',
        r'成功|達成|実現|できた|やった|頑張',
        r'ワクワク|期待|楽しみ|面白い',
    ]
    for p in positive_patterns:
        if re.search(p, text):
            scores["positive"] += 1

    # 建設的シグナル（最も評価される）
    constructive_patterns = [
        r'方法|やり方|コツ|ステップ|手順|始め方',
        r'解決|改善|対策|提案|アドバイス',
        r'学んだ|気づいた|発見|わかった|理解',
        r'共有|シェア|紹介|まとめ|レビュー',
        r'経験|体験|実践|試し|チャレンジ',
    ]
    for p in constructive_patterns:
        if re.search(p, text):
            scores["constructive"] += 1

    # ネガティブシグナル
    negative_patterns = [
        r'最悪|ひどい|つらい|辛い|苦しい|悲しい',
        r'失敗|後悔|損|無駄|意味ない',
        r'不安|怖い|心配|恐ろしい',
    ]
    for p in negative_patterns:
        if re.search(p, text):
            scores["negative"] += 1

    # 攻撃的シグナル（Grokが抑制）
    aggressive_patterns = [
        r'バカ|アホ|クソ|死ね|消えろ|うざい',
        r'炎上|叩[かき]|批判|攻撃|許さない|ふざけるな',
        r'嘘つき|詐欺|騙[しさ]|裏切り',
    ]
    for p in aggressive_patterns:
        if re.search(p, text):
            scores["aggressive"] += 1

    # 総合判定
    max_key = max(scores, key=scores.get)
    if scores[max_key] == 0:
        overall = "中立"
    elif max_key == "constructive":
        overall = "建設的"
    elif max_key == "positive":
        overall = "ポジティブ"
    elif max_key == "negative" and scores["constructive"] > 0:
        overall = "煽り（建設的）"  # 問題提起 + 解決策
    elif max_key == "negative":
        overall = "ネガティブ"
    elif max_key == "aggressive":
        overall = "攻撃的"
    else:
        overall = "中立"

    return {
        "scores": scores,
        "overall": overall,
        "grok_friendly": overall in ["建設的", "ポジティブ", "煽り（建設的）", "中立"],
    }


def analyze_tone_distribution(df):
    """全投稿のトーン分布とパフォーマンスを分析"""
    tone_data = defaultdict(list)

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)

        tone = analyze_tone(text)
        tone_data[tone["overall"]].append(likes)

    # Grokフレンドリー vs 非フレンドリー
    friendly_likes = []
    unfriendly_likes = []
    for tone_type, likes_list in tone_data.items():
        if tone_type in ["建設的", "ポジティブ", "煽り（建設的）", "中立"]:
            friendly_likes.extend(likes_list)
        else:
            unfriendly_likes.extend(likes_list)

    return {
        "tone_distribution": {k: len(v) for k, v in tone_data.items()},
        "tone_avg_likes": {k: sum(v) / len(v) if v else 0 for k, v in tone_data.items()},
        "friendly_avg": sum(friendly_likes) / len(friendly_likes) if friendly_likes else 0,
        "unfriendly_avg": sum(unfriendly_likes) / len(unfriendly_likes) if unfriendly_likes else 0,
        "friendly_count": len(friendly_likes),
        "unfriendly_count": len(unfriendly_likes),
    }


# ========================================
# 6. 滞在時間推定
# ========================================

def estimate_dwell_time_score(text):
    """投稿の推定滞在時間スコア（0-20点）

    Xのdwell time重み = +10.0（2分以上で発動）
    テキスト特徴から滞在時間を推定する。
    """
    score = 0

    # 文字数（長いほど滞在時間が長い）
    length = len(text)
    if length >= 400:
        score += 6   # 読むのに1分以上
    elif length >= 250:
        score += 5
    elif length >= 150:
        score += 3
    elif length >= 80:
        score += 2
    else:
        score += 1   # 短文はすぐ読める

    # 改行・構造（読みやすい構造 = 最後まで読む = 滞在時間増）
    line_count = text.count("\n")
    if 3 <= line_count <= 10:
        score += 3  # 適度な構造
    elif line_count > 10:
        score += 2  # 長すぎると離脱
    else:
        score += 1

    # 箇条書き（スキャンしやすい = 最後まで見る）
    if re.search(r'^[・\-✅☑①②③④⑤\d+[\.\)）]]', text, re.MULTILINE):
        score += 3

    # ストーリー性（先が気になる = 最後まで読む）
    if has_story(text):
        score += 2

    # 数字・データ（じっくり読む）
    number_count = len(re.findall(r'\d+[万円個件つ%倍]', text))
    if number_count >= 3:
        score += 3
    elif number_count >= 1:
        score += 1

    # 感情的フック（立ち止まって読む）
    if re.search(r'(衝撃|驚|ヤバ|やば|マジで|ガチで|信じられない)', text):
        score += 2

    # 画像・メディア示唆（見る時間が増える）
    if re.search(r'(画像|写真|スクショ|動画|📸|📹|🖼)', text):
        score += 1

    return min(20, score)


def analyze_dwell_potential(df):
    """全投稿の滞在時間ポテンシャルを分析"""
    results = []

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)

        dwell_score = estimate_dwell_time_score(text)
        results.append({
            "text": text[:60],
            "likes": likes,
            "dwell_score": dwell_score,
            "length": len(text),
        })

    results.sort(key=lambda x: x["dwell_score"], reverse=True)

    # スコア帯別の平均いいね
    buckets = {"高(15-20)": [], "中(10-14)": [], "低(0-9)": []}
    for r in results:
        if r["dwell_score"] >= 15:
            buckets["高(15-20)"].append(r["likes"])
        elif r["dwell_score"] >= 10:
            buckets["中(10-14)"].append(r["likes"])
        else:
            buckets["低(0-9)"].append(r["likes"])

    return {
        "top10": results[:10],
        "avg_dwell_score": sum(r["dwell_score"] for r in results) / len(results) if results else 0,
        "bucket_avg_likes": {
            k: sum(v) / len(v) if v else 0 for k, v in buckets.items()
        },
        "bucket_counts": {k: len(v) for k, v in buckets.items()},
        "correlation_data": [(r["dwell_score"], r["likes"]) for r in results],
    }


# ========================================
# 7. 早期エンゲージメント予測
# ========================================

def predict_early_engagement(text):
    """早期エンゲージメント（投稿後1時間以内）の予測

    最初の1時間で全体の50%が決まる。
    「すぐにリアクションしやすいか」を評価。
    """
    score = 0
    signals = []

    first_line = text.split("\n")[0] if text else ""

    # 1. 冒頭インパクト（スクロール中に目を止めるか）
    if len(first_line) <= 30 and re.search(r'[！!？?]', first_line):
        score += 3
        signals.append("短文インパクト冒頭")
    elif re.search(r'(マジで|ガチで|衝撃|速報|緊急)', first_line):
        score += 3
        signals.append("緊急性ワード")
    elif re.search(r'\d+[万円%倍]', first_line):
        score += 2
        signals.append("冒頭に具体的数字")

    # 2. 即座のリアクション可能性
    if len(text) <= 140:
        score += 2
        signals.append("140字以内（即読み）")
    elif len(text) <= 280:
        score += 1
        signals.append("280字以内（速読可能）")

    # 3. 感情的即反応
    if re.search(r'(わかる|あるある|それ|これ|ほんこれ)', text):
        score += 2
        signals.append("共感即反応ワード")

    # 4. トレンド・話題性（時期依存だが構造的に判定）
    if re.search(r'(Claude|GPT|Grok|AI|ChatGPT|Gemini|OpenAI)', text, re.IGNORECASE):
        score += 2
        signals.append("AI話題（トレンド）")

    # 5. 問いかけ（即リプしやすい）
    if re.search(r'[\?？]$', text.strip()):
        score += 2
        signals.append("疑問で終わる")

    return {
        "score": min(10, score),
        "signals": signals,
        "predicted_velocity": "高速" if score >= 7 else "中速" if score >= 4 else "低速",
    }


def analyze_early_engagement_potential(df):
    """全投稿の早期エンゲージメントポテンシャルを分析"""
    results = []

    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)

        early = predict_early_engagement(text)
        results.append({
            "text": text[:60],
            "likes": likes,
            "early_score": early["score"],
            "velocity": early["predicted_velocity"],
            "signals": early["signals"],
        })

    # 速度別のパフォーマンス
    velocity_data = defaultdict(list)
    for r in results:
        velocity_data[r["velocity"]].append(r["likes"])

    return {
        "velocity_avg_likes": {k: sum(v) / len(v) if v else 0 for k, v in velocity_data.items()},
        "velocity_counts": {k: len(v) for k, v in velocity_data.items()},
        "top10_fast": sorted(
            [r for r in results if r["velocity"] == "高速"],
            key=lambda x: x["likes"], reverse=True
        )[:10],
    }


# ========================================
# 統合レポート生成
# ========================================

def generate_algorithm_report(df_buzz, df_self=None):
    """Xアルゴリズム分析レポートを生成"""
    lines = []
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    lines.append("# Xアルゴリズム分析レポート")
    lines.append("")
    lines.append(f"**分析日時:** {now}")
    lines.append(f"**分析対象:** バズ投稿{len(df_buzz)}件")
    lines.append("")
    lines.append("> Xの公開アルゴリズム（Phoenix/Grok）の重みに基づいた分析")
    lines.append("> ソース: xai-org/x-algorithm, Grok AI, エンゲージメント重み公開値")
    lines.append("")
    lines.append("---")
    lines.append("")

    # === セクション1: アルゴリズム加重ランキング ===
    lines.append("## 1. アルゴリズム加重エンゲージメントランキング")
    lines.append("")
    lines.append("> 従来の「いいね数順」ではなく、Xアルゴリズムの公式重みで加重した真のスコア")
    lines.append("> いいね×0.5 + RT×1.0 + リプライ×13.5")
    lines.append("")

    disc_result = analyze_discussion_algorithm_value(df_buzz)

    lines.append("### 1.1 アルゴリズム加重スコア TOP10")
    lines.append("")
    lines.append("| 順位 | ユーザー | いいね | RT | リプ | 加重スコア | 議論率 | 本文 |")
    lines.append("|------|---------|--------|-----|------|----------|--------|------|")
    for i, r in enumerate(disc_result["top10_by_algorithm"], 1):
        text = r["text"].replace("|", "｜").replace("\n", " ")[:30]
        lines.append(f"| {i} | @{r['user']} | {r['likes']:,} | {r['retweets']:,} | {r['replies']:,} | {r['weighted_score']:,.0f} | {r['discussion_rate']:.3f} | {text} |")
    lines.append("")

    lines.append("### 1.2 議論誘発度 TOP10（リプライ/いいね比率）")
    lines.append("")
    lines.append("> リプライはいいねの27倍の価値。議論誘発度が高い投稿 = アルゴリズムが最も評価")
    lines.append("")
    lines.append("| 順位 | ユーザー | いいね | リプ | 議論率 | 加重スコア | 本文 |")
    lines.append("|------|---------|--------|------|--------|----------|------|")
    for i, r in enumerate(disc_result["top10_by_discussion"], 1):
        text = r["text"].replace("|", "｜").replace("\n", " ")[:30]
        lines.append(f"| {i} | @{r['user']} | {r['likes']:,} | {r['replies']:,} | {r['discussion_rate']:.3f} | {r['weighted_score']:,.0f} | {text} |")
    lines.append("")

    lines.append("### 1.3 カテゴリ別アルゴリズム加重スコア")
    lines.append("")
    lines.append("| カテゴリ | 平均加重スコア |")
    lines.append("|---------|-------------|")
    for cat, score in sorted(disc_result["cat_algorithm_scores"].items(),
                              key=lambda x: x[1], reverse=True):
        lines.append(f"| {cat} | {score:,.0f} |")
    lines.append("")

    # === セクション2: スレッド構造分析 ===
    lines.append("---")
    lines.append("")
    lines.append("## 2. スレッド構造分析")
    lines.append("")
    lines.append("> スレッドは単発投稿の3倍のエンゲージメント（会話クリック重み=11.0）")
    lines.append("")

    thread_result = analyze_thread_potential(df_buzz)

    lines.append(f"- **スレッド型投稿:** {thread_result['thread_count']}件（平均いいね: {thread_result['thread_avg_likes']:.0f}）")
    lines.append(f"- **単発投稿:** {thread_result['non_thread_count']}件（平均いいね: {thread_result['non_thread_avg_likes']:.0f}）")
    if thread_result['non_thread_avg_likes'] > 0:
        ratio = thread_result['thread_avg_likes'] / thread_result['non_thread_avg_likes']
        lines.append(f"- **スレッド倍率:** {ratio:.1f}倍")
    lines.append("")

    # === セクション3: 外部リンクの影響 ===
    lines.append("---")
    lines.append("")
    lines.append("## 3. 外部リンクの影響分析")
    lines.append("")
    lines.append("> 外部リンク → 30-50%リーチ減（非Premiumはほぼゼロになるケースも）")
    lines.append("")

    link_result = analyze_link_impact(df_buzz)

    lines.append("| リンク種別 | 件数 | 平均いいね |")
    lines.append("|-----------|------|----------|")
    lines.append(f"| 外部リンクあり | {link_result['external_count']} | {link_result['external_avg_likes']:.0f} |")
    lines.append(f"| X内リンクのみ | {link_result['x_link_count']} | {link_result['x_link_avg_likes']:.0f} |")
    lines.append(f"| リンクなし | {link_result['no_link_count']} | {link_result['no_link_avg_likes']:.0f} |")
    lines.append("")

    if link_result['reach_penalty_confirmed']:
        lines.append("**データで確認:** リンクなし投稿の方が平均いいねが高い → アルゴリズムのリンクペナルティが実データでも確認")
    else:
        lines.append("**注意:** このデータセットでは外部リンクのペナルティが明確に現れていない（投稿者の影響力等の要因）")
    lines.append("")

    # === セクション4: トーン分析 ===
    lines.append("---")
    lines.append("")
    lines.append("## 4. トーン分析（Grok評価推定）")
    lines.append("")
    lines.append("> Grokはポジティブ・建設的なコンテンツを拡散、攻撃的なrage baitを抑制")
    lines.append("")

    tone_result = analyze_tone_distribution(df_buzz)

    lines.append("### 4.1 トーン分布")
    lines.append("")
    lines.append("| トーン | 件数 | 平均いいね |")
    lines.append("|--------|------|----------|")
    for tone, count in sorted(tone_result["tone_distribution"].items(),
                               key=lambda x: tone_result["tone_avg_likes"].get(x[0], 0),
                               reverse=True):
        avg = tone_result["tone_avg_likes"].get(tone, 0)
        lines.append(f"| {tone} | {count} | {avg:.0f} |")
    lines.append("")

    lines.append("### 4.2 Grokフレンドリー vs 非フレンドリー")
    lines.append("")
    lines.append(f"- **Grokフレンドリー:** {tone_result['friendly_count']}件（平均いいね: {tone_result['friendly_avg']:.0f}）")
    lines.append(f"- **非フレンドリー:** {tone_result['unfriendly_count']}件（平均いいね: {tone_result['unfriendly_avg']:.0f}）")
    lines.append("")

    # === セクション5: 滞在時間推定 ===
    lines.append("---")
    lines.append("")
    lines.append("## 5. 滞在時間推定")
    lines.append("")
    lines.append("> 滞在時間2分以上 → +10.0の重み。Xが最重視する指標の一つ")
    lines.append("")

    dwell_result = analyze_dwell_potential(df_buzz)

    lines.append(f"**平均滞在時間スコア:** {dwell_result['avg_dwell_score']:.1f}/20点")
    lines.append("")

    lines.append("| 滞在時間帯 | 件数 | 平均いいね |")
    lines.append("|-----------|------|----------|")
    for bucket, avg_likes in sorted(dwell_result["bucket_avg_likes"].items(),
                                      key=lambda x: x[1], reverse=True):
        count = dwell_result["bucket_counts"][bucket]
        lines.append(f"| {bucket} | {count} | {avg_likes:.0f} |")
    lines.append("")

    # === セクション6: 早期エンゲージメント予測 ===
    lines.append("---")
    lines.append("")
    lines.append("## 6. 早期エンゲージメント予測")
    lines.append("")
    lines.append("> 投稿後1時間以内で全体の50%が決まる。「すぐリアクションしやすいか」を評価")
    lines.append("")

    early_result = analyze_early_engagement_potential(df_buzz)

    lines.append("| 予測速度 | 件数 | 平均いいね |")
    lines.append("|---------|------|----------|")
    for velocity in ["高速", "中速", "低速"]:
        count = early_result["velocity_counts"].get(velocity, 0)
        avg = early_result["velocity_avg_likes"].get(velocity, 0)
        lines.append(f"| {velocity} | {count} | {avg:.0f} |")
    lines.append("")

    # === セクション7: アルゴリズムスコアで全投稿を再評価 ===
    lines.append("---")
    lines.append("")
    lines.append("## 7. Xアルゴリズムスコア TOP10 / WORST10")
    lines.append("")
    lines.append("> テキスト特徴からXアルゴリズムのスコアを予測（0-100点）")
    lines.append("")

    all_algo_scores = []
    for _, row in df_buzz.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        user = safe_get(row, "ユーザー名", "")

        algo = calculate_algorithm_score(text)
        all_algo_scores.append({
            "text": text[:40],
            "likes": likes,
            "user": user,
            "algo_score": algo["total_score"],
            "factors": algo["factors"],
        })

    all_algo_scores.sort(key=lambda x: x["algo_score"], reverse=True)

    lines.append("### TOP10")
    lines.append("")
    lines.append("| 順位 | Algoスコア | いいね | 主要因 | 本文 |")
    lines.append("|------|----------|--------|--------|------|")
    for i, s in enumerate(all_algo_scores[:10], 1):
        top_factors = sorted(s["factors"].items(), key=lambda x: x[1], reverse=True)[:3]
        factors_str = ", ".join(f"{k}:{v}" for k, v in top_factors if v > 0)
        text = s["text"].replace("|", "｜").replace("\n", " ")
        lines.append(f"| {i} | {s['algo_score']} | {s['likes']:,} | {factors_str} | {text} |")
    lines.append("")

    lines.append("### WORST10")
    lines.append("")
    lines.append("| 順位 | Algoスコア | いいね | 主要因 | 本文 |")
    lines.append("|------|----------|--------|--------|------|")
    for i, s in enumerate(all_algo_scores[-10:], 1):
        top_factors = sorted(s["factors"].items(), key=lambda x: x[1], reverse=True)[:3]
        factors_str = ", ".join(f"{k}:{v}" for k, v in top_factors if v > 0)
        text = s["text"].replace("|", "｜").replace("\n", " ")
        lines.append(f"| {i} | {s['algo_score']} | {s['likes']:,} | {factors_str} | {text} |")
    lines.append("")

    # === セクション8: @Mr_botenの分析 ===
    if df_self is not None and len(df_self) > 0:
        lines.append("---")
        lines.append("")
        lines.append("## 8. @Mr_botenのアルゴリズム分析")
        lines.append("")

        self_algo_scores = []
        for _, row in df_self.iterrows():
            text = safe_get(row, "本文", "")
            likes = safe_get(row, "いいね数", 0)

            algo = calculate_algorithm_score(text)
            self_algo_scores.append({
                "text": text[:40],
                "likes": likes,
                "algo_score": algo["total_score"],
                "factors": algo["factors"],
            })

        self_algo_scores.sort(key=lambda x: x["algo_score"], reverse=True)

        avg_self = sum(s["algo_score"] for s in self_algo_scores) / len(self_algo_scores)
        avg_buzz = sum(s["algo_score"] for s in all_algo_scores) / len(all_algo_scores)

        lines.append(f"- **自分の平均Algoスコア:** {avg_self:.1f}点（バズ投稿平均: {avg_buzz:.1f}点）")
        lines.append("")

        # 要素別比較
        lines.append("### 要素別比較")
        lines.append("")
        lines.append("| 要素 | 自分の平均 | バズ平均 | 差 | 改善アドバイス |")
        lines.append("|------|----------|--------|-----|-------------|")

        advice_map = {
            "リプライ誘発力": "疑問形で終わる、意見を求める表現を入れる",
            "滞在時間": "具体的数字・箇条書き・ストーリー構造で読ませる",
            "スレッド・会話": "スレッド形式を試す（3倍ブースト）",
            "トーン": "建設的なトーン（学び・共有・体験）を意識",
            "ブックマーク誘発": "「保存推奨」「まとめ」「チェックリスト」形式",
            "外部リンク": "リンクはリプライに。本文には入れない",
            "プロフクリック誘発": "秘匿感・自己開示で「誰？」と思わせる",
            "早期反応性": "冒頭30字以内にインパクト、感情ワード入れる",
        }

        self_factor_avg = defaultdict(list)
        buzz_factor_avg = defaultdict(list)
        for s in self_algo_scores:
            for k, v in s["factors"].items():
                self_factor_avg[k].append(v)
        for s in all_algo_scores:
            for k, v in s["factors"].items():
                buzz_factor_avg[k].append(v)

        for factor in advice_map:
            s_vals = self_factor_avg.get(factor, [0])
            b_vals = buzz_factor_avg.get(factor, [0])
            s_avg = sum(s_vals) / len(s_vals) if s_vals else 0
            b_avg = sum(b_vals) / len(b_vals) if b_vals else 0
            diff = s_avg - b_avg
            adv = advice_map[factor]
            lines.append(f"| {factor} | {s_avg:.1f} | {b_avg:.1f} | {diff:+.1f} | {adv} |")
        lines.append("")

        # 自分のTOP5
        lines.append("### 自分のAlgoスコアTOP5")
        lines.append("")
        lines.append("| 順位 | Algoスコア | いいね | 主要因 | 本文 |")
        lines.append("|------|----------|--------|--------|------|")
        for i, s in enumerate(self_algo_scores[:5], 1):
            top_factors = sorted(s["factors"].items(), key=lambda x: x[1], reverse=True)[:3]
            factors_str = ", ".join(f"{k}:{v}" for k, v in top_factors if v > 0)
            text = s["text"].replace("|", "｜").replace("\n", " ")
            lines.append(f"| {i} | {s['algo_score']} | {s['likes']:,} | {factors_str} | {text} |")
        lines.append("")

    # === セクション9: アクション提案 ===
    lines.append("---")
    lines.append("")
    lines.append("## 9. アルゴリズムに基づくアクション提案")
    lines.append("")
    lines.append("### 最高優先度（即実践可能）")
    lines.append("1. **リプライに必ず返信する**（150倍ブースト。これだけで劇的に変わる）")
    lines.append("2. **外部リンクは本文に入れない**（リプライに書く。本文に入れると50%減）")
    lines.append("3. **疑問形で終わる**（リプライ誘発 = 27倍の価値）")
    lines.append("")
    lines.append("### 高優先度（投稿設計に組み込む）")
    lines.append("4. **スレッド形式を試す**（3倍エンゲージメント）")
    lines.append("5. **保存したくなる構造**（箇条書き・数字・テンプレ → ブックマーク20倍）")
    lines.append("6. **建設的なトーン**（学び・体験・提案 → Grokが拡散促進）")
    lines.append("")
    lines.append("### 中優先度（継続的に意識）")
    lines.append("7. **18-21時に投稿**（早期エンゲージメント最大化）")
    lines.append("8. **長文テキスト > 動画**（テキストは動画より30%強い）")
    lines.append("9. **X Premiumの活用**（4倍ブースト）")
    lines.append("")

    return "\n".join(lines)


# ========================================
# メイン実行
# ========================================

def main():
    """Xアルゴリズム分析を実行"""
    import os

    BUZZ_FILE = "output/buzz_posts_20260215.xlsx"
    SELF_FILE = "output/TwExport_20260217_191942.csv"
    DB_FILE = "data/buzz_database.db"
    OUTPUT_FILE = "output/x_algorithm_analysis_20260221.md"

    print("=" * 60)
    print("Xアルゴリズム分析")
    print("=" * 60)

    # データ読み込み
    if os.path.exists(DB_FILE):
        from buzz_score_v2 import load_from_db, load_self_posts
        print(f"データベースから読み込み: {DB_FILE}")
        df_raw = load_from_db(DB_FILE)
        self_accounts = {"Mr_boten", "mr_boten"}
        df_self = df_raw[df_raw["ユーザー名"].str.lower().isin({a.lower() for a in self_accounts})]
        df_buzz = df_raw[~df_raw["ユーザー名"].str.lower().isin({a.lower() for a in self_accounts})]
        df_buzz = df_buzz[df_buzz["いいね数"] > 0].copy()
    else:
        from analyze_posts import filter_data, load_excel
        print(f"Excelから読み込み: {BUZZ_FILE}")
        df_raw = load_excel(BUZZ_FILE)
        if df_raw is None:
            return
        df_buzz, _, _ = filter_data(df_raw)

        if os.path.exists(SELF_FILE):
            from buzz_score_v2 import load_self_posts
            df_self = load_self_posts(SELF_FILE)
        else:
            df_self = pd.DataFrame()

    print(f"バズ投稿: {len(df_buzz)}件 / 自分の投稿: {len(df_self)}件")

    # レポート生成
    print("\nレポート生成中...")
    report = generate_algorithm_report(df_buzz, df_self)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nレポート保存完了: {OUTPUT_FILE}")
    print(f"文字数: {len(report):,}文字")


if __name__ == "__main__":
    main()
