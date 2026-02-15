"""分析結果のグラフ可視化"""

import os
import re
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("Agg")  # GUIなし環境対応
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import pandas as pd

# 日本語フォント設定
def setup_japanese_font():
    """利用可能な日本語フォントを探して設定"""
    japanese_fonts = [
        "Noto Sans CJK JP", "Noto Sans JP", "IPAGothic", "IPAPGothic",
        "VL Gothic", "TakaoGothic", "Meiryo", "MS Gothic", "Yu Gothic",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for font in japanese_fonts:
        if font in available:
            plt.rcParams["font.family"] = font
            return font

    # フォントが見つからない場合はsans-serifで代用
    plt.rcParams["font.family"] = "sans-serif"
    return None

FONT = setup_japanese_font()

# 共通スタイル
COLORS = ["#4472C4", "#ED7D31", "#A5A5A5", "#FFC000", "#5B9BD5",
           "#70AD47", "#264478", "#9B59B6", "#E74C3C", "#1ABC9C"]


def _safe_text(row, col, default=""):
    val = row.get(col, default)
    return val if pd.notna(val) else default


def chart_category_likes(df, output_dir):
    """カテゴリ別平均いいね数の横棒グラフ"""
    from analyze_posts import classify_category

    cat_data = defaultdict(list)
    for _, row in df.iterrows():
        text = _safe_text(row, "本文")
        cat = classify_category(text)
        cat_data[cat].append(row.get("いいね数", 0))

    categories = []
    avg_likes = []
    counts = []
    for cat, likes in sorted(cat_data.items(), key=lambda x: sum(x[1])/len(x[1]) if x[1] else 0):
        categories.append(cat)
        avg_likes.append(sum(likes) / len(likes) if likes else 0)
        counts.append(len(likes))

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(categories, avg_likes, color=COLORS[:len(categories)])

    for bar, count in zip(bars, counts):
        ax.text(bar.get_width() + 10, bar.get_y() + bar.get_height()/2,
                f"{bar.get_width():.0f} ({count}件)", va="center", fontsize=10)

    ax.set_xlabel("平均いいね数" if FONT else "Avg Likes")
    ax.set_title("カテゴリ別 平均いいね数" if FONT else "Avg Likes by Category")
    plt.tight_layout()

    path = os.path.join(output_dir, "category_likes.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_opening_patterns(df, output_dir):
    """冒頭パターン別効果の棒グラフ"""
    from analyze_posts import classify_opening_pattern

    pattern_data = defaultdict(list)
    for _, row in df.iterrows():
        text = _safe_text(row, "本文")
        first_line = text.split("\n")[0] if text else ""
        pattern = classify_opening_pattern(first_line)
        pattern_data[pattern].append(row.get("いいね数", 0))

    patterns = []
    avg_likes = []
    for pat, likes in sorted(pattern_data.items(), key=lambda x: sum(x[1])/len(x[1]) if x[1] else 0, reverse=True):
        patterns.append(f"{pat}\n({len(likes)}件)")
        avg_likes.append(sum(likes) / len(likes) if likes else 0)

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(patterns, avg_likes, color=COLORS[:len(patterns)])

    for bar in bars:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                f"{bar.get_height():.0f}", ha="center", fontsize=10)

    ax.set_ylabel("平均いいね数" if FONT else "Avg Likes")
    ax.set_title("冒頭パターン別 平均いいね数" if FONT else "Avg Likes by Opening Pattern")
    plt.tight_layout()

    path = os.path.join(output_dir, "opening_patterns.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_time_slots(df, output_dir):
    """時間帯別いいね数の折れ線グラフ"""
    from analyze_posts import parse_datetime

    hourly = defaultdict(list)
    for _, row in df.iterrows():
        dt = parse_datetime(_safe_text(row, "投稿日時"))
        if dt:
            hour = (dt.hour + 9) % 24  # JST
            hourly[hour].append(row.get("いいね数", 0))

    hours = list(range(24))
    avg_likes = [sum(hourly[h]) / len(hourly[h]) if hourly[h] else 0 for h in hours]
    counts = [len(hourly[h]) for h in hours]

    fig, ax1 = plt.subplots(figsize=(12, 6))

    color1 = "#4472C4"
    ax1.plot(hours, avg_likes, "o-", color=color1, linewidth=2, markersize=6, label="平均いいね数")
    ax1.set_xlabel("時刻 (JST)" if FONT else "Hour (JST)")
    ax1.set_ylabel("平均いいね数" if FONT else "Avg Likes", color=color1)
    ax1.tick_params(axis="y", labelcolor=color1)
    ax1.set_xticks(hours)
    ax1.set_xticklabels([f"{h}時" for h in hours], rotation=45, fontsize=8)

    ax2 = ax1.twinx()
    color2 = "#ED7D31"
    ax2.bar(hours, counts, alpha=0.3, color=color2, label="投稿数")
    ax2.set_ylabel("投稿数" if FONT else "Post Count", color=color2)
    ax2.tick_params(axis="y", labelcolor=color2)

    ax1.set_title("時間帯別 平均いいね数と投稿数" if FONT else "Avg Likes & Post Count by Hour")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    plt.tight_layout()
    path = os.path.join(output_dir, "time_slots.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_cta_effect(df, output_dir):
    """CTA有無の比較棒グラフ"""
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
        text = _safe_text(row, "本文")
        likes = row.get("いいね数", 0)
        has_cta = False
        for cta_type, pattern in cta_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                cta_data[cta_type].append(likes)
                has_cta = True
        if not has_cta:
            no_cta.append(likes)

    labels = list(cta_data.keys()) + ["CTAなし"]
    avg_likes = [sum(v)/len(v) if v else 0 for v in cta_data.values()] + \
                [sum(no_cta)/len(no_cta) if no_cta else 0]
    post_counts = [len(v) for v in cta_data.values()] + [len(no_cta)]

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = COLORS[:len(labels)-1] + ["#A5A5A5"]
    bars = ax.bar(labels, avg_likes, color=colors)

    for bar, count in zip(bars, post_counts):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                f"{bar.get_height():.0f}\n({count}件)", ha="center", fontsize=9)

    ax.set_ylabel("平均いいね数" if FONT else "Avg Likes")
    ax.set_title("CTA種類別 平均いいね数" if FONT else "Avg Likes by CTA Type")
    plt.tight_layout()

    path = os.path.join(output_dir, "cta_effect.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_likes_distribution(df, output_dir):
    """いいね数の分布ヒストグラム"""
    likes = df["いいね数"].dropna().values

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(likes, bins=30, color="#4472C4", edgecolor="white", alpha=0.8)

    mean_likes = likes.mean()
    median_likes = pd.Series(likes).median()
    ax.axvline(mean_likes, color="#ED7D31", linestyle="--", linewidth=2,
               label=f"平均: {mean_likes:.0f}")
    ax.axvline(median_likes, color="#70AD47", linestyle="--", linewidth=2,
               label=f"中央値: {median_likes:.0f}")

    ax.set_xlabel("いいね数" if FONT else "Likes")
    ax.set_ylabel("投稿数" if FONT else "Post Count")
    ax.set_title("いいね数の分布" if FONT else "Likes Distribution")
    ax.legend()
    plt.tight_layout()

    path = os.path.join(output_dir, "likes_distribution.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_text_length_scatter(df, output_dir):
    """文字数×いいね数の散布図"""
    from analyze_posts import classify_category

    lengths = []
    likes_list = []
    cats = []
    for _, row in df.iterrows():
        text = _safe_text(row, "本文")
        lengths.append(len(text))
        likes_list.append(row.get("いいね数", 0))
        cats.append(classify_category(text))

    # カテゴリ別に色分け
    unique_cats = list(set(cats))
    cat_colors = {c: COLORS[i % len(COLORS)] for i, c in enumerate(unique_cats)}

    fig, ax = plt.subplots(figsize=(10, 6))

    for cat in unique_cats:
        x = [lengths[i] for i in range(len(cats)) if cats[i] == cat]
        y = [likes_list[i] for i in range(len(cats)) if cats[i] == cat]
        ax.scatter(x, y, c=cat_colors[cat], label=cat, alpha=0.6, s=50)

    # 最適レンジをハイライト
    from analyze_posts import analyze_text_length
    tl_data = analyze_text_length(df)
    best = tl_data["best_bucket"]
    bucket_ranges = {
        "0-50字": (0, 50), "51-100字": (51, 100), "101-150字": (101, 150),
        "151-200字": (151, 200), "201-300字": (201, 300),
        "301-500字": (301, 500), "500字以上": (501, max(lengths) if lengths else 1000),
    }
    if best in bucket_ranges:
        lo, hi = bucket_ranges[best]
        ax.axvspan(lo, hi, alpha=0.1, color="green", label=f"最適レンジ ({best})")

    ax.set_xlabel("文字数" if FONT else "Character Count")
    ax.set_ylabel("いいね数" if FONT else "Likes")
    ax.set_title("文字数 × いいね数の関係" if FONT else "Character Count vs Likes")
    ax.legend(fontsize=8, loc="upper right")
    plt.tight_layout()

    path = os.path.join(output_dir, "text_length_scatter.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_buzz_score(df, output_dir):
    """バズスコア×実いいね数の散布図 + スコア分布"""
    from analyze_posts import calculate_buzz_score, analyze_text_length
    tl_data = analyze_text_length(df)
    score_params = {}
    bucket_ranges = {
        "0-50字": (0, 50), "51-100字": (51, 100), "101-150字": (101, 150),
        "151-200字": (151, 200), "201-300字": (201, 300),
        "301-500字": (301, 500), "500字以上": (501, 1000),
    }
    if tl_data["best_bucket"] in bucket_ranges:
        rng = bucket_ranges[tl_data["best_bucket"]]
        score_params["optimal_min"] = rng[0]
        score_params["optimal_max"] = rng[1]

    scores = []
    likes_list = []
    for _, row in df.iterrows():
        text = _safe_text(row, "本文")
        result = calculate_buzz_score(text, score_params)
        scores.append(result["total_score"])
        likes_list.append(row.get("いいね数", 0))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # 左: 散布図 + トレンドライン
    ax1.scatter(scores, likes_list, alpha=0.5, c="#4472C4", s=40)
    if len(scores) > 2:
        z = np.polyfit(scores, likes_list, 1)
        p = np.poly1d(z)
        x_line = np.linspace(min(scores), max(scores), 100)
        ax1.plot(x_line, p(x_line), "--", color="#ED7D31", linewidth=2, label="トレンドライン")
        ax1.legend()
    ax1.set_xlabel("バズスコア" if FONT else "Buzz Score")
    ax1.set_ylabel("いいね数" if FONT else "Likes")
    ax1.set_title("バズスコア × 実際のいいね数" if FONT else "Buzz Score vs Likes")

    # 右: スコア分布ヒストグラム
    ax2.hist(scores, bins=15, color="#70AD47", edgecolor="white", alpha=0.8)
    mean_score = sum(scores) / len(scores) if scores else 0
    ax2.axvline(mean_score, color="#ED7D31", linestyle="--", linewidth=2,
                label=f"平均: {mean_score:.0f}点")
    ax2.set_xlabel("バズスコア" if FONT else "Buzz Score")
    ax2.set_ylabel("投稿数" if FONT else "Post Count")
    ax2.set_title("バズスコアの分布" if FONT else "Buzz Score Distribution")
    ax2.legend()

    plt.tight_layout()
    path = os.path.join(output_dir, "buzz_score.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_user_analysis(df_raw, output_dir):
    """ユーザー分析: 投稿数×平均いいねバブルチャート"""
    user_stats = {}
    for _, row in df_raw.iterrows():
        user = row.get("ユーザー名", "")
        likes = row.get("いいね数", 0)
        if user not in user_stats:
            user_stats[user] = {"likes": [], "total": 0}
        user_stats[user]["likes"].append(likes)
        user_stats[user]["total"] += likes

    post_counts = []
    avg_likes = []
    total_likes = []
    labels = []

    for user, stats in user_stats.items():
        count = len(stats["likes"])
        avg = sum(stats["likes"]) / count if count > 0 else 0
        post_counts.append(count)
        avg_likes.append(avg)
        total_likes.append(stats["total"])
        labels.append(user)

    fig, ax = plt.subplots(figsize=(10, 6))

    # バブルサイズ = 合計いいね
    max_total = max(total_likes) if total_likes else 1
    sizes = [max(30, (t / max_total) * 500) for t in total_likes]

    scatter = ax.scatter(post_counts, avg_likes, s=sizes, alpha=0.5, c="#4472C4", edgecolors="white")

    # リピーターにラベル
    for i, (pc, al, label) in enumerate(zip(post_counts, avg_likes, labels)):
        if pc >= 2:
            ax.annotate(f"@{label}", (pc, al), fontsize=7, alpha=0.7,
                        xytext=(5, 5), textcoords="offset points")

    ax.set_xlabel("投稿数" if FONT else "Post Count")
    ax.set_ylabel("平均いいね数" if FONT else "Avg Likes")
    ax.set_title("ユーザー別 投稿数 × 平均いいね数" if FONT else "Posts vs Avg Likes per User")
    plt.tight_layout()

    path = os.path.join(output_dir, "user_analysis.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def generate_all_charts(df, output_dir="output/charts", df_raw=None):
    """全チャートを生成"""
    os.makedirs(output_dir, exist_ok=True)

    chart_funcs = {
        "カテゴリ別平均いいね数": chart_category_likes,
        "冒頭パターン別効果": chart_opening_patterns,
        "時間帯別分析": chart_time_slots,
        "CTA効果比較": chart_cta_effect,
        "いいね数分布": chart_likes_distribution,
    }

    results = {}
    for name, func in chart_funcs.items():
        try:
            path = func(df, output_dir)
            results[name] = path
            print(f"  ✓ {name}: {path}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")

    # 新規チャート: 文字数散布図
    try:
        path = chart_text_length_scatter(df, output_dir)
        results["文字数×いいね数散布図"] = path
        print(f"  ✓ 文字数×いいね数散布図: {path}")
    except Exception as e:
        print(f"  ✗ 文字数×いいね数散布図: {e}")

    # 新規チャート: バズスコア分析
    try:
        path = chart_buzz_score(df, output_dir)
        results["バズスコア分析"] = path
        print(f"  ✓ バズスコア分析: {path}")
    except Exception as e:
        print(f"  ✗ バズスコア分析: {e}")

    # 新規チャート: ユーザー分析
    if df_raw is not None:
        try:
            path = chart_user_analysis(df_raw, output_dir)
            results["ユーザー分析"] = path
            print(f"  ✓ ユーザー分析: {path}")
        except Exception as e:
            print(f"  ✗ ユーザー分析: {e}")

    return results


if __name__ == "__main__":
    input_file = "buzz_posts_20260215.csv"
    if not os.path.exists(input_file):
        input_file = "output/buzz_posts_20260215.xlsx"

    if os.path.exists(input_file):
        if input_file.endswith(".csv"):
            df = pd.read_csv(input_file)
        else:
            df = pd.read_excel(input_file)
        print(f"読み込み完了: {len(df)}件")
        generate_all_charts(df)
    else:
        print("エラー: データファイルが見つかりません")
