"""複数日のバズポスト トレンド比較分析"""

import os
import re
from collections import defaultdict
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from visualize import setup_japanese_font, COLORS

FONT = setup_japanese_font()


def find_data_files(data_dir="."):
    """データファイル（CSV/Excel）を日付順に検索"""
    files = []
    patterns = [
        (r"buzz_posts_(\d{8})\.csv", "csv"),
        (r"buzz_posts_(\d{8})\.xlsx", "xlsx"),
    ]

    for search_dir in [data_dir, os.path.join(data_dir, "output")]:
        if not os.path.isdir(search_dir):
            continue
        for filename in os.listdir(search_dir):
            for pattern, fmt in patterns:
                match = re.match(pattern, filename)
                if match:
                    date_str = match.group(1)
                    files.append({
                        "path": os.path.join(search_dir, filename),
                        "date": date_str,
                        "format": fmt,
                    })

    # 日付でソート、同日はExcel優先
    files.sort(key=lambda x: (x["date"], 0 if x["format"] == "xlsx" else 1))

    # 同日の重複除去（Excel優先）
    seen = set()
    unique = []
    for f in files:
        if f["date"] not in seen:
            seen.add(f["date"])
            unique.append(f)

    return unique


def load_data_file(file_info):
    """ファイルを読み込んでDataFrameを返す"""
    if file_info["format"] == "csv":
        return pd.read_csv(file_info["path"])
    else:
        return pd.read_excel(file_info["path"])


def classify_category(text):
    """カテゴリ分類（analyze_posts.pyと同じロジック）"""
    if re.search(r'達成|収益|稼げた|稼いだ|成功|実績|儲かった|〜万円|月収|年収|売上|報酬|利益', text, re.IGNORECASE):
        return "実績報告系"
    if re.search(r'方法|やり方|コツ|手順|ステップ|テクニック|攻略|マニュアル|ガイド|〜する方法|〜のやり方', text, re.IGNORECASE):
        return "ノウハウ系"
    if re.search(r'私が|僕が|自分が|実際に|やってみた|試してみた|体験|経験|〜したら|〜してみた', text, re.IGNORECASE):
        return "体験談系"
    if re.search(r'は？|問題|危険|注意|警告|【悲報】|〜すぎる|ヤバい|おかしい', text, re.IGNORECASE):
        return "問題提起系"
    if re.search(r'ツール|アプリ|サービス|プラグイン|拡張機能|おすすめ|紹介|AI|Claude|ChatGPT|GPT', text, re.IGNORECASE):
        return "ツール紹介系"
    if re.search(r'発表|リリース|開始|開催|速報|最新|ニュース|公開', text, re.IGNORECASE):
        return "ニュース系"
    return "その他"


def extract_keywords(df, top_n=10):
    """頻出キーワードを抽出"""
    keyword_pattern = re.compile(
        r'(ChatGPT|Claude|Claude Code|Gemini|Copilot|Midjourney|'
        r'Stable Diffusion|DALL-E|Canva|Notion AI|Cursor|v0|Bolt|'
        r'副業|稼ぐ|収益|自動化|AI|ライティング|プログラミング|'
        r'デザイン|動画|YouTube|SNS|ブログ|アフィリエイト)',
        re.IGNORECASE
    )

    counts = defaultdict(int)
    for _, row in df.iterrows():
        text = str(row.get("本文", ""))
        found = set()
        for match in keyword_pattern.finditer(text):
            word = match.group()
            if word not in found:
                counts[word] += 1
                found.add(word)

    return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]


def compare_trends(data_dir="."):
    """複数日のデータを比較分析"""
    files = find_data_files(data_dir)

    if len(files) < 2:
        print("比較には2日分以上のデータが必要です。")
        print(f"現在のデータファイル数: {len(files)}件")
        return None

    print(f"データファイル {len(files)}日分を検出:")
    for f in files:
        print(f"  - {f['date']}: {f['path']}")

    daily_stats = []

    for file_info in files:
        df = load_data_file(file_info)
        date = file_info["date"]

        # 基本統計
        stats = {
            "date": date,
            "post_count": len(df),
            "avg_likes": df["いいね数"].mean() if "いいね数" in df.columns else 0,
            "max_likes": df["いいね数"].max() if "いいね数" in df.columns else 0,
            "median_likes": df["いいね数"].median() if "いいね数" in df.columns else 0,
            "total_likes": df["いいね数"].sum() if "いいね数" in df.columns else 0,
        }

        # カテゴリ分布
        cat_counts = defaultdict(int)
        for _, row in df.iterrows():
            text = str(row.get("本文", ""))
            cat = classify_category(text)
            cat_counts[cat] += 1
        stats["categories"] = dict(cat_counts)

        # キーワード
        stats["keywords"] = extract_keywords(df)

        daily_stats.append(stats)

    return daily_stats, files


def generate_trend_charts(daily_stats, output_dir="output/charts"):
    """トレンド比較チャートを生成"""
    os.makedirs(output_dir, exist_ok=True)

    dates = [s["date"] for s in daily_stats]
    date_labels = [f"{d[4:6]}/{d[6:8]}" for d in dates]

    # 投稿数と平均いいね数の推移
    fig, ax1 = plt.subplots(figsize=(10, 6))

    counts = [s["post_count"] for s in daily_stats]
    avg_likes = [s["avg_likes"] for s in daily_stats]

    ax1.bar(date_labels, counts, color="#4472C4", alpha=0.7, label="投稿数")
    ax1.set_xlabel("日付" if FONT else "Date")
    ax1.set_ylabel("投稿数" if FONT else "Post Count", color="#4472C4")

    ax2 = ax1.twinx()
    ax2.plot(date_labels, avg_likes, "o-", color="#ED7D31", linewidth=2, markersize=8, label="平均いいね数")
    ax2.set_ylabel("平均いいね数" if FONT else "Avg Likes", color="#ED7D31")

    ax1.set_title("日別 投稿数と平均いいね数の推移" if FONT else "Daily Post Count & Avg Likes")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    plt.tight_layout()
    path = os.path.join(output_dir, "trend_daily.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    # カテゴリ別推移（積み上げ棒グラフ）
    all_categories = set()
    for s in daily_stats:
        all_categories.update(s["categories"].keys())
    all_categories = sorted(all_categories)

    fig, ax = plt.subplots(figsize=(12, 6))
    bottom = [0] * len(daily_stats)

    for i, cat in enumerate(all_categories):
        values = [s["categories"].get(cat, 0) for s in daily_stats]
        ax.bar(date_labels, values, bottom=bottom, label=cat,
               color=COLORS[i % len(COLORS)])
        bottom = [b + v for b, v in zip(bottom, values)]

    ax.set_xlabel("日付" if FONT else "Date")
    ax.set_ylabel("投稿数" if FONT else "Post Count")
    ax.set_title("カテゴリ別投稿数の推移" if FONT else "Category Distribution Over Time")
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.tight_layout()

    path2 = os.path.join(output_dir, "trend_categories.png")
    fig.savefig(path2, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return {"日別推移": path, "カテゴリ別推移": path2}


def generate_trend_report(daily_stats, output_file):
    """トレンド比較レポートを生成"""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# バズポスト トレンド比較レポート\n\n")
        f.write(f"**生成日時:** {datetime.now().strftime('%Y年%m月%d日 %H:%M')}\n\n")
        f.write(f"**比較期間:** {daily_stats[0]['date']} 〜 {daily_stats[-1]['date']}\n\n")
        f.write("---\n\n")

        # 日別サマリー
        f.write("## 1. 日別サマリー\n\n")
        f.write("| 日付 | 投稿数 | 平均いいね | 最大いいね | 中央値 |\n")
        f.write("|------|--------|-----------|-----------|--------|\n")
        for s in daily_stats:
            d = s["date"]
            f.write(f"| {d[4:6]}/{d[6:8]} | {s['post_count']}件 | "
                    f"{s['avg_likes']:.0f} | {s['max_likes']:,} | {s['median_likes']:.0f} |\n")
        f.write("\n")

        # トレンド変化
        if len(daily_stats) >= 2:
            prev = daily_stats[-2]
            curr = daily_stats[-1]

            f.write("## 2. 前日比の変化\n\n")

            count_diff = curr["post_count"] - prev["post_count"]
            likes_diff = curr["avg_likes"] - prev["avg_likes"]
            count_emoji = "📈" if count_diff > 0 else "📉" if count_diff < 0 else "→"
            likes_emoji = "📈" if likes_diff > 0 else "📉" if likes_diff < 0 else "→"

            f.write(f"- **投稿数:** {prev['post_count']}件 → {curr['post_count']}件 "
                    f"({count_emoji} {count_diff:+d}件)\n")
            f.write(f"- **平均いいね:** {prev['avg_likes']:.0f} → {curr['avg_likes']:.0f} "
                    f"({likes_emoji} {likes_diff:+.0f})\n\n")

        # カテゴリ別推移
        f.write("## 3. カテゴリ別推移\n\n")
        all_categories = set()
        for s in daily_stats:
            all_categories.update(s["categories"].keys())

        header = "| カテゴリ | " + " | ".join(f"{s['date'][4:6]}/{s['date'][6:8]}" for s in daily_stats) + " |\n"
        separator = "|---------|" + "|".join(["------" for _ in daily_stats]) + "|\n"
        f.write(header)
        f.write(separator)

        for cat in sorted(all_categories):
            row = f"| {cat} | "
            row += " | ".join(f"{s['categories'].get(cat, 0)}件" for s in daily_stats)
            row += " |\n"
            f.write(row)
        f.write("\n")

        # キーワード比較
        f.write("## 4. トレンドキーワード比較\n\n")
        for s in daily_stats:
            f.write(f"### {s['date'][4:6]}/{s['date'][6:8]}のトップキーワード\n\n")
            for word, count in s["keywords"][:10]:
                f.write(f"- **{word}**: {count}件\n")
            f.write("\n")

        # 新登場キーワード検出
        if len(daily_stats) >= 2:
            prev_words = {w for w, _ in daily_stats[-2]["keywords"]}
            curr_words = {w for w, _ in daily_stats[-1]["keywords"]}
            new_words = curr_words - prev_words

            if new_words:
                f.write("### 新たにトレンド入りしたキーワード\n\n")
                for word in new_words:
                    f.write(f"- **{word}** (NEW)\n")
                f.write("\n")

        f.write("---\n\n")
        f.write("*グラフは `output/charts/` に保存されています*\n")

    print(f"トレンドレポート生成完了: {output_file}")


def main():
    """メイン処理"""
    result = compare_trends(".")

    if result is None:
        return

    daily_stats, files = result

    os.makedirs("output", exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    output_file = f"output/trend_report_{today}.md"

    # チャート生成
    print("\nトレンドチャートを生成中...")
    chart_paths = generate_trend_charts(daily_stats)
    for name, path in chart_paths.items():
        print(f"  ✓ {name}: {path}")

    # レポート生成
    print("\nトレンドレポートを生成中...")
    generate_trend_report(daily_stats, output_file)


if __name__ == "__main__":
    main()
