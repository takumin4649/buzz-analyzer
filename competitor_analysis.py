"""競合アカウント分析

DB内のアカウントを横断比較し、各アカウントの強みと戦略を分析する。
バズ投稿のパターン、読者心理トリガー、アルゴリズムスコアを比較。

使い方:
  python competitor_analysis.py              → DB内の全アカウント比較
  python competitor_analysis.py --top 10     → TOP10アカウントだけ
  python competitor_analysis.py --accounts "Naoki_GPT,Kasta_AI" → 指定アカウント比較
"""

import argparse
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime

import pandas as pd

from analyze_posts import classify_category, classify_opening_pattern, safe_get
from algorithm_analysis import calculate_algorithm_score, analyze_tone
from reader_psychology import analyze_reader_psychology


DB_PATH = "data/buzz_database.db"


def load_accounts(db_path, min_posts=5, accounts=None):
    """DBからアカウント別の投稿を読み込む"""
    conn = sqlite3.connect(db_path)

    if accounts:
        placeholders = ",".join(["?"] * len(accounts))
        query = f"SELECT account, text, likes, retweets, replies, date FROM posts WHERE account IN ({placeholders}) ORDER BY account, likes DESC"
        df = pd.read_sql(query, conn, params=accounts)
    else:
        df = pd.read_sql(
            "SELECT account, text, likes, retweets, replies, date FROM posts ORDER BY account, likes DESC",
            conn
        )
    conn.close()

    # 最低投稿数フィルタ
    counts = df["account"].value_counts()
    valid = counts[counts >= min_posts].index
    df = df[df["account"].isin(valid)]

    return df


def analyze_account(df_account):
    """1アカウントを総合分析"""
    account = df_account["account"].iloc[0]
    posts = df_account.to_dict("records")

    total_likes = sum(p["likes"] or 0 for p in posts)
    avg_likes = total_likes / len(posts) if posts else 0
    max_likes = max((p["likes"] or 0) for p in posts)

    # カテゴリ分布
    categories = defaultdict(int)
    openings = defaultdict(int)
    tones = defaultdict(int)
    algo_scores = []
    psych_triggers = defaultdict(int)
    emotions = defaultdict(int)

    for p in posts:
        text = p["text"] or ""
        likes = p["likes"] or 0

        # カテゴリ
        cat = classify_category(text)
        categories[cat] += 1

        # 冒頭パターン
        first_line = text.split("\n")[0] if text else ""
        opening = classify_opening_pattern(first_line)
        openings[opening] += 1

        # トーン
        tone = analyze_tone(text)
        tones[tone["overall"]] += 1

        # アルゴリズムスコア
        algo = calculate_algorithm_score(text)
        algo_scores.append(algo["total_score"])

        # 読者心理
        psych = analyze_reader_psychology(text, likes)
        for t in psych["like_triggers"]:
            psych_triggers[f"いいね:{t['trigger']}"] += 1
        for t in psych["rt_triggers"]:
            psych_triggers[f"RT:{t['trigger']}"] += 1
        for t in psych["reply_triggers"]:
            psych_triggers[f"リプ:{t['trigger']}"] += 1
        emotions[psych["primary_emotion"]] += 1

    # 主要カテゴリ（最も多い）
    top_category = max(categories, key=categories.get) if categories else "不明"
    top_opening = max(openings, key=openings.get) if openings else "不明"
    top_tone = max(tones, key=tones.get) if tones else "不明"
    top_emotion = max(emotions, key=emotions.get) if emotions else "不明"
    top_triggers = sorted(psych_triggers.items(), key=lambda x: x[1], reverse=True)[:5]

    avg_algo = sum(algo_scores) / len(algo_scores) if algo_scores else 0

    # 秘匿感フレーズ使用率
    secret_count = sum(
        1 for p in posts
        if any(kw in (p["text"] or "") for kw in ["正直", "実は", "ぶっちゃけ", "告白", "ド素人"])
    )
    secret_rate = secret_count / len(posts) * 100 if posts else 0

    # 疑問形使用率
    question_count = sum(
        1 for p in posts
        if re.search(r'[\?？]', p["text"] or "")
    )
    question_rate = question_count / len(posts) * 100 if posts else 0

    # 平均文字数
    avg_len = sum(len(p["text"] or "") for p in posts) / len(posts) if posts else 0

    return {
        "account": account,
        "post_count": len(posts),
        "avg_likes": avg_likes,
        "max_likes": max_likes,
        "total_likes": total_likes,
        "top_category": top_category,
        "categories": dict(categories),
        "top_opening": top_opening,
        "top_tone": top_tone,
        "top_emotion": top_emotion,
        "top_triggers": top_triggers,
        "avg_algo_score": avg_algo,
        "secret_rate": secret_rate,
        "question_rate": question_rate,
        "avg_char_len": avg_len,
    }


def generate_competitor_report(df, top_n=None):
    """競合分析レポートを生成"""
    accounts = df["account"].unique()
    print(f"分析対象: {len(accounts)}アカウント")

    results = []
    for i, account in enumerate(accounts):
        df_acc = df[df["account"] == account]
        print(f"  [{i+1}/{len(accounts)}] @{account} ({len(df_acc)}件)...")
        result = analyze_account(df_acc)
        results.append(result)

    # 平均いいね順でソート
    results.sort(key=lambda x: x["avg_likes"], reverse=True)

    if top_n:
        results = results[:top_n]

    # レポート生成
    lines = []
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    lines.append("# 競合アカウント分析レポート")
    lines.append("")
    lines.append(f"**分析日時:** {now}")
    lines.append(f"**分析対象:** {len(results)}アカウント")
    lines.append("")
    lines.append("---")
    lines.append("")

    # === 総合ランキング ===
    lines.append("## 1. 総合ランキング")
    lines.append("")
    lines.append("| 順位 | アカウント | 投稿数 | 平均いいね | 最大いいね | Algo平均 | 主要カテゴリ | 主要トーン |")
    lines.append("|------|----------|--------|----------|----------|---------|-----------|---------|")
    for i, r in enumerate(results, 1):
        lines.append(
            f"| {i} | @{r['account']} | {r['post_count']} | {r['avg_likes']:.0f} | "
            f"{r['max_likes']:,} | {r['avg_algo_score']:.0f} | {r['top_category']} | {r['top_tone']} |"
        )
    lines.append("")

    # === 戦略パターン分析 ===
    lines.append("## 2. 各アカウントの戦略パターン")
    lines.append("")

    for i, r in enumerate(results[:20], 1):
        lines.append(f"### #{i} @{r['account']}")
        lines.append("")
        lines.append(f"- **投稿数:** {r['post_count']}件 / **平均いいね:** {r['avg_likes']:.0f} / **最大:** {r['max_likes']:,}")
        lines.append(f"- **主要カテゴリ:** {r['top_category']}")
        lines.append(f"- **冒頭パターン:** {r['top_opening']}")
        lines.append(f"- **トーン:** {r['top_tone']}")
        lines.append(f"- **読者の第一感情:** {r['top_emotion']}")
        lines.append(f"- **秘匿感フレーズ使用率:** {r['secret_rate']:.0f}%")
        lines.append(f"- **疑問形使用率:** {r['question_rate']:.0f}%")
        lines.append(f"- **平均文字数:** {r['avg_char_len']:.0f}字")
        lines.append(f"- **Algoスコア平均:** {r['avg_algo_score']:.0f}点")

        if r["top_triggers"]:
            trigger_str = ", ".join(f"{name}({count})" for name, count in r["top_triggers"][:3])
            lines.append(f"- **主要心理トリガー:** {trigger_str}")

        # カテゴリ分布
        cat_str = ", ".join(f"{cat}:{cnt}" for cat, cnt in
                           sorted(r["categories"].items(), key=lambda x: x[1], reverse=True)[:3])
        lines.append(f"- **カテゴリ分布:** {cat_str}")
        lines.append("")

    # === 横断比較 ===
    lines.append("---")
    lines.append("")
    lines.append("## 3. 横断比較（真似すべきポイント）")
    lines.append("")

    # 秘匿感フレーズ使用率TOP
    secret_sorted = sorted(results, key=lambda x: x["secret_rate"], reverse=True)[:5]
    lines.append("### 秘匿感フレーズ使用率TOP5")
    lines.append("")
    for r in secret_sorted:
        lines.append(f"- @{r['account']}: {r['secret_rate']:.0f}%（平均いいね {r['avg_likes']:.0f}）")
    lines.append("")

    # 疑問形使用率TOP
    q_sorted = sorted(results, key=lambda x: x["question_rate"], reverse=True)[:5]
    lines.append("### 疑問形使用率TOP5（リプライ誘発力）")
    lines.append("")
    for r in q_sorted:
        lines.append(f"- @{r['account']}: {r['question_rate']:.0f}%（平均いいね {r['avg_likes']:.0f}）")
    lines.append("")

    # Algoスコア TOP
    algo_sorted = sorted(results, key=lambda x: x["avg_algo_score"], reverse=True)[:5]
    lines.append("### Algoスコア平均TOP5（アルゴリズムに最適化されてる人）")
    lines.append("")
    for r in algo_sorted:
        lines.append(f"- @{r['account']}: {r['avg_algo_score']:.0f}点（平均いいね {r['avg_likes']:.0f}）")
    lines.append("")

    # === 拓巳への提案 ===
    lines.append("---")
    lines.append("")
    lines.append("## 4. 拓巳が競合から学べること")
    lines.append("")

    # TOP3の共通点を抽出
    top3 = results[:3]
    if top3:
        common_cats = defaultdict(int)
        common_tones = defaultdict(int)
        for r in top3:
            common_cats[r["top_category"]] += 1
            common_tones[r["top_tone"]] += 1

        top_cat = max(common_cats, key=common_cats.get)
        top_tone = max(common_tones, key=common_tones.get)

        lines.append(f"### TOP3アカウントの共通点")
        lines.append(f"- **主要カテゴリ:** {top_cat}")
        lines.append(f"- **主要トーン:** {top_tone}")
        avg_secret = sum(r["secret_rate"] for r in top3) / 3
        avg_question = sum(r["question_rate"] for r in top3) / 3
        avg_algo_top3 = sum(r["avg_algo_score"] for r in top3) / 3
        lines.append(f"- **秘匿感フレーズ率:** 平均{avg_secret:.0f}%")
        lines.append(f"- **疑問形率:** 平均{avg_question:.0f}%")
        lines.append(f"- **Algoスコア:** 平均{avg_algo_top3:.0f}点")
        lines.append("")

    lines.append("### アクション")
    lines.append("")
    lines.append("1. TOP3の投稿パターンを自分の体験に置き換えて再現")
    lines.append("2. 秘匿感フレーズ率が高いアカウントの書き出しを参考に")
    lines.append("3. 疑問形率が高いアカウントの締め方を参考に")
    lines.append("4. Algoスコアが高いアカウントの構造を分析")
    lines.append("")

    return "\n".join(lines), results


def main():
    parser = argparse.ArgumentParser(description="競合アカウント分析")
    parser.add_argument("--top", type=int, default=None, help="上位N件のアカウントだけ分析")
    parser.add_argument("--accounts", type=str, default=None, help="カンマ区切りのアカウント名")
    parser.add_argument("--min-posts", type=int, default=50, help="最低投稿数（デフォルト50）")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"エラー: {DB_PATH} が見つかりません")
        return

    print("=" * 60)
    print("競合アカウント分析")
    print("=" * 60)

    accounts_list = None
    if args.accounts:
        accounts_list = [a.strip() for a in args.accounts.split(",")]
        print(f"指定アカウント: {accounts_list}")

    df = load_accounts(DB_PATH, min_posts=args.min_posts, accounts=accounts_list)
    print(f"読み込み: {len(df)}件（{df['account'].nunique()}アカウント）")

    if df.empty:
        print("分析対象のアカウントがありません")
        return

    report, results = generate_competitor_report(df, top_n=args.top)

    output_file = "output/competitor_analysis_20260223.md"
    os.makedirs("output", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nレポート保存: {output_file}")
    print(f"文字数: {len(report):,}文字")

    # サマリー表示
    print("\n" + "=" * 60)
    print("TOP5 サマリー")
    print("=" * 60)
    for i, r in enumerate(results[:5], 1):
        print(f"\n#{i} @{r['account']}")
        print(f"  平均いいね: {r['avg_likes']:.0f} / 投稿数: {r['post_count']}")
        print(f"  カテゴリ: {r['top_category']} / トーン: {r['top_tone']}")
        print(f"  Algo: {r['avg_algo_score']:.0f}点 / 秘匿感: {r['secret_rate']:.0f}% / 疑問形: {r['question_rate']:.0f}%")


if __name__ == "__main__":
    main()
