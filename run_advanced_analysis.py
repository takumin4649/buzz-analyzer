"""高度分析レポート生成: バイラル係数・フォロワー正規化・バズ予測スコア検証"""

import os
import re
from collections import defaultdict
from datetime import datetime

import pandas as pd

from analyze_posts import (
    POWER_WORDS,
    analyze_buzz_scores,
    analyze_follower_normalized,
    analyze_viral_coefficient,
    calculate_buzz_score,
    classify_category,
    classify_opening_pattern,
    filter_data,
    has_story,
    load_excel,
    safe_get,
)

# === データ読み込み ===

BUZZ_FILE = "output/buzz_posts_20260215.xlsx"
SELF_FILE = "output/TwExport_20260217_191942.csv"
OUTPUT_FILE = "output/advanced_analysis_20260217.md"


def load_self_posts(filepath):
    """自分の投稿CSVを読み込む"""
    df = pd.read_csv(filepath, encoding="utf-8-sig")
    df["いいね数"] = pd.to_numeric(df["いいね数"], errors="coerce").fillna(0).astype(int)
    df["リポスト数"] = pd.to_numeric(df["リポスト数"], errors="coerce").fillna(0).astype(int)
    df["リプライ数"] = pd.to_numeric(df["リプライ数"], errors="coerce").fillna(0).astype(int)
    df["フォロワー数"] = pd.to_numeric(df["フォロワー数"], errors="coerce").fillna(0).astype(int)
    print(f"自分の投稿読み込み完了: {len(df)}件")
    return df


def detect_cta(text):
    """CTA有無を判定"""
    cta_patterns = [
        r"いいね|👍", r"保存|ブックマーク", r"フォロー",
        r"リポスト|RT|シェア|拡散", r"コメント|返信|教えて",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in cta_patterns)


def count_power_words(text):
    """パワーワードの種類数をカウント"""
    count = 0
    types = []
    for pw_type, pattern in POWER_WORDS.items():
        if pattern.search(text):
            count += 1
            types.append(pw_type)
    return count, types


# === 分析1: バイラル係数分析 ===

def generate_viral_section(df_buzz, df_self):
    """バイラル係数分析セクションを生成"""
    viral = analyze_viral_coefficient(df_buzz)
    lines = []

    lines.append("## 1. バイラル係数分析")
    lines.append("")
    lines.append("> バイラル係数 = リポスト数 / いいね数（シェアされやすさの指標）")
    lines.append("")

    # 1.1 全体概要
    lines.append("### 1.1 全体概要")
    lines.append("")
    lines.append(f"- **平均バイラル係数:** {viral['avg_coeff']:.3f}")
    lines.append(f"- **中央値:** {viral['median_coeff']:.3f}")
    lines.append(f"- **高バイラル群:** {viral['high_viral_traits']['count']}件（平均いいね: {viral['high_viral_traits']['avg_likes']:.0f}）")
    lines.append(f"- **低バイラル群:** {viral['low_viral_traits']['count']}件（平均いいね: {viral['low_viral_traits']['avg_likes']:.0f}）")
    lines.append("")

    # 1.2 バイラル係数TOP10
    lines.append("### 1.2 バイラル係数 TOP10（シェアされやすい投稿）")
    lines.append("")
    lines.append("| 順位 | ユーザー | いいね | RT | バイラル係数 | 本文（冒頭） |")
    lines.append("|------|---------|--------|-----|------------|------------|")
    for i, d in enumerate(viral["top10_viral"][:10], 1):
        text_preview = d["text"].replace("|", "｜").replace("\n", " ")[:40]
        lines.append(f"| {i} | @{d['user']} | {d['likes']:,} | {d['retweets']:,} | {d['viral_coeff']:.3f} | {text_preview} |")
    lines.append("")

    # 1.3 高いいね×低RT vs 高RT の特徴比較
    lines.append("### 1.3 高いいね×低RT vs 高RT投稿の特徴比較")
    lines.append("")

    # バイラルデータを再計算（投稿単位の詳細が必要）
    all_viral = []
    for _, row in df_buzz.iterrows():
        likes = safe_get(row, "いいね数", 0)
        rts = safe_get(row, "リポスト数", 0)
        text = safe_get(row, "本文", "")
        if likes > 0:
            vc = rts / likes
            pw_count, pw_types = count_power_words(text)
            all_viral.append({
                "likes": likes, "rts": rts, "viral_coeff": vc,
                "text": text, "category": classify_category(text),
                "has_cta": detect_cta(text), "has_story": has_story(text),
                "pw_count": pw_count, "pw_types": pw_types,
                "length": len(text),
            })

    all_viral.sort(key=lambda x: x["viral_coeff"], reverse=True)
    median_vc = viral["median_coeff"]

    # 高いいね×低RT: いいね上位25%で、バイラル係数が中央値以下
    likes_75 = sorted([d["likes"] for d in all_viral])[int(len(all_viral) * 0.75)] if all_viral else 0
    high_like_low_rt = [d for d in all_viral if d["likes"] >= likes_75 and d["viral_coeff"] <= median_vc]
    high_rt = [d for d in all_viral if d["viral_coeff"] > median_vc and d["likes"] >= likes_75]

    def group_stats(group, label):
        if not group:
            return f"**{label}:** データなし\n"
        avg_likes = sum(d["likes"] for d in group) / len(group)
        avg_rts = sum(d["rts"] for d in group) / len(group)
        avg_vc = sum(d["viral_coeff"] for d in group) / len(group)
        avg_len = sum(d["length"] for d in group) / len(group)
        cta_rate = sum(1 for d in group if d["has_cta"]) / len(group) * 100
        story_rate = sum(1 for d in group if d["has_story"]) / len(group) * 100
        avg_pw = sum(d["pw_count"] for d in group) / len(group)

        # カテゴリ分布
        cats = defaultdict(int)
        for d in group:
            cats[d["category"]] += 1
        top_cat = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
        cat_str = ", ".join(f"{c}({n}件)" for c, n in top_cat)

        # パワーワード種類
        pw_freq = defaultdict(int)
        for d in group:
            for t in d["pw_types"]:
                pw_freq[t] += 1
        top_pw = sorted(pw_freq.items(), key=lambda x: x[1], reverse=True)[:3]
        pw_str = ", ".join(f"{p}({n})" for p, n in top_pw)

        result = f"**{label}**（{len(group)}件）\n"
        result += f"- 平均いいね: {avg_likes:.0f} / 平均RT: {avg_rts:.0f} / 平均バイラル係数: {avg_vc:.3f}\n"
        result += f"- 平均文字数: {avg_len:.0f}字\n"
        result += f"- CTA使用率: {cta_rate:.0f}% / ストーリー性: {story_rate:.0f}%\n"
        result += f"- 平均パワーワード種類数: {avg_pw:.1f}\n"
        result += f"- 主なカテゴリ: {cat_str}\n"
        result += f"- 主なパワーワード: {pw_str}\n"
        return result

    lines.append(group_stats(high_like_low_rt, "高いいね×低RT群（いいねは多いがシェアされにくい）"))
    lines.append("")
    lines.append(group_stats(high_rt, "高いいね×高RT群（いいねもRTも多い）"))
    lines.append("")

    # 1.4 何がシェアを生むのか
    lines.append("### 1.4 何がシェアを生むのか（特徴抽出）")
    lines.append("")

    # カテゴリ別バイラル係数
    lines.append("**カテゴリ別バイラル係数:**")
    lines.append("")
    lines.append("| カテゴリ | 平均バイラル係数 |")
    lines.append("|---------|----------------|")
    for cat, avg in sorted(viral["cat_viral"].items(), key=lambda x: x[1], reverse=True):
        lines.append(f"| {cat} | {avg:.3f} |")
    lines.append("")

    # パターン別バイラル係数
    lines.append("**冒頭パターン別バイラル係数:**")
    lines.append("")
    lines.append("| パターン | 平均バイラル係数 |")
    lines.append("|---------|----------------|")
    for pat, avg in sorted(viral["pattern_viral"].items(), key=lambda x: x[1], reverse=True):
        lines.append(f"| {pat} | {avg:.3f} |")
    lines.append("")

    # シェアを生む要因まとめ
    top_cat_viral = max(viral["cat_viral"].items(), key=lambda x: x[1]) if viral["cat_viral"] else ("N/A", 0)
    top_pat_viral = max(viral["pattern_viral"].items(), key=lambda x: x[1]) if viral["pattern_viral"] else ("N/A", 0)

    lines.append("**シェアを生む主な要因:**")
    lines.append(f"- カテゴリ「{top_cat_viral[0]}」がバイラル係数最高（{top_cat_viral[1]:.3f}）")
    lines.append(f"- 冒頭パターン「{top_pat_viral[0]}」がシェアされやすい（{top_pat_viral[1]:.3f}）")

    # 高バイラル群のCTA・ストーリー率
    high_viral_posts = [d for d in all_viral if d["viral_coeff"] > median_vc]
    low_viral_posts = [d for d in all_viral if d["viral_coeff"] <= median_vc]
    if high_viral_posts and low_viral_posts:
        hv_cta = sum(1 for d in high_viral_posts if d["has_cta"]) / len(high_viral_posts) * 100
        lv_cta = sum(1 for d in low_viral_posts if d["has_cta"]) / len(low_viral_posts) * 100
        hv_story = sum(1 for d in high_viral_posts if d["has_story"]) / len(high_viral_posts) * 100
        lv_story = sum(1 for d in low_viral_posts if d["has_story"]) / len(low_viral_posts) * 100
        lines.append(f"- CTA使用率: 高バイラル群 {hv_cta:.0f}% vs 低バイラル群 {lv_cta:.0f}%")
        lines.append(f"- ストーリー性: 高バイラル群 {hv_story:.0f}% vs 低バイラル群 {lv_story:.0f}%")
    lines.append("")

    # 1.5 @Mr_botenのバイラル係数
    lines.append("### 1.5 @Mr_botenのバイラル係数")
    lines.append("")
    self_viral = []
    for _, row in df_self.iterrows():
        likes = safe_get(row, "いいね数", 0)
        rts = safe_get(row, "リポスト数", 0)
        text = safe_get(row, "本文", "")
        if likes > 0:
            vc = rts / likes
            self_viral.append({"likes": likes, "rts": rts, "viral_coeff": vc, "text": text[:50]})

    if self_viral:
        avg_self_vc = sum(d["viral_coeff"] for d in self_viral) / len(self_viral)
        lines.append(f"- **自分の平均バイラル係数:** {avg_self_vc:.3f}（バズ投稿平均: {viral['avg_coeff']:.3f}）")
        diff_pct = ((avg_self_vc - viral["avg_coeff"]) / viral["avg_coeff"] * 100) if viral["avg_coeff"] > 0 else 0
        if diff_pct > 0:
            lines.append(f"- バズ投稿より **{diff_pct:.0f}%高い** → シェアされやすい投稿傾向")
        else:
            lines.append(f"- バズ投稿より **{abs(diff_pct):.0f}%低い** → いいねは付くがシェアされにくい傾向")
        lines.append("")

        # 自分のバイラル係数TOP5
        self_viral.sort(key=lambda x: x["viral_coeff"], reverse=True)
        lines.append("**自分のバイラル係数 TOP5:**")
        lines.append("")
        lines.append("| 順位 | いいね | RT | バイラル係数 | 本文（冒頭） |")
        lines.append("|------|--------|-----|------------|------------|")
        for i, d in enumerate(self_viral[:5], 1):
            text_preview = d["text"].replace("|", "｜").replace("\n", " ")[:40]
            lines.append(f"| {i} | {d['likes']:,} | {d['rts']:,} | {d['viral_coeff']:.3f} | {text_preview} |")
        lines.append("")
    else:
        lines.append("自分の投稿でいいね数>0のデータがありません。")
        lines.append("")

    return "\n".join(lines)


# === 分析2: フォロワー正規化 ===

def generate_follower_section(df_buzz, df_self):
    """フォロワー正規化エンゲージメントセクションを生成"""
    fnorm = analyze_follower_normalized(df_buzz)
    lines = []

    lines.append("## 2. フォロワー正規化エンゲージメント")
    lines.append("")

    # フォロワーデータがあるか判定
    has_follower = fnorm["has_follower_data"]

    if has_follower:
        lines.append("> エンゲージメント率 = (いいね数 / フォロワー数) × 100")
        lines.append("")

        # 2.1 エンゲージメント率ランキング
        lines.append("### 2.1 エンゲージメント率ランキング TOP10")
        lines.append("")
        lines.append("| 順位 | ユーザー | いいね | フォロワー | エンゲージメント率 | 本文（冒頭） |")
        lines.append("|------|---------|--------|-----------|-----------------|------------|")
        for i, d in enumerate(fnorm["top10"], 1):
            text_preview = d["text"].replace("|", "｜").replace("\n", " ")[:35]
            lines.append(f"| {i} | @{d['user']} | {d['likes']:,} | {d['followers']:,} | {d['rate']:.2f}% | {text_preview} |")
        lines.append("")

        # 2.2 Hidden Gems
        lines.append("### 2.2 Hidden Gems（少フォロワー × 高エンゲージメント）")
        lines.append("")
        if fnorm["hidden_gems"]:
            lines.append("> フォロワー数が中央値以下 & エンゲージメント率が75パーセンタイル以上の投稿")
            lines.append("")
            lines.append("| ユーザー | いいね | フォロワー | エンゲージメント率 | 本文（冒頭） |")
            lines.append("|---------|--------|-----------|-----------------|------------|")
            for d in fnorm["hidden_gems"]:
                text_preview = d["text"].replace("|", "｜").replace("\n", " ")[:35]
                lines.append(f"| @{d['user']} | {d['likes']:,} | {d['followers']:,} | {d['rate']:.2f}% | {text_preview} |")
        else:
            lines.append("Hidden Gemsに該当する投稿は見つかりませんでした。")
        lines.append("")

        # 2.3 カテゴリ別・パターン別
        lines.append("### 2.3 カテゴリ別・パターン別エンゲージメント率")
        lines.append("")

        if fnorm["category_by_rate"]:
            lines.append("**カテゴリ別:**")
            lines.append("")
            lines.append("| カテゴリ | 平均エンゲージメント率 | 件数 |")
            lines.append("|---------|---------------------|------|")
            for cat, rates in sorted(fnorm["category_by_rate"].items(),
                                      key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0, reverse=True):
                avg_rate = sum(rates) / len(rates) if rates else 0
                lines.append(f"| {cat} | {avg_rate:.2f}% | {len(rates)} |")
            lines.append("")

        if fnorm["pattern_by_rate"]:
            lines.append("**冒頭パターン別:**")
            lines.append("")
            lines.append("| パターン | 平均エンゲージメント率 | 件数 |")
            lines.append("|---------|---------------------|------|")
            for pat, rates in sorted(fnorm["pattern_by_rate"].items(),
                                      key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0, reverse=True):
                avg_rate = sum(rates) / len(rates) if rates else 0
                lines.append(f"| {pat} | {avg_rate:.2f}% | {len(rates)} |")
            lines.append("")

    else:
        # フォロワーデータなし → 総合エンゲージメントスコアで代替
        lines.append("> フォロワー数データが未取得のため、**総合エンゲージメントスコア**で代替分析")
        lines.append("> 総合スコア = いいね + リポスト×2 + リプライ×3")
        lines.append("")

        # 総合スコアを計算
        buzz_engagement = []
        for _, row in df_buzz.iterrows():
            likes = safe_get(row, "いいね数", 0)
            rts = safe_get(row, "リポスト数", 0)
            replies = safe_get(row, "リプライ数", 0)
            text = safe_get(row, "本文", "")
            user = safe_get(row, "ユーザー名", "")
            total = likes + rts * 2 + replies * 3
            buzz_engagement.append({
                "user": user, "likes": likes, "rts": rts, "replies": replies,
                "total": total, "text": text,
            })
        buzz_engagement.sort(key=lambda x: x["total"], reverse=True)

        # 2.1 総合スコアランキング
        lines.append("### 2.1 総合エンゲージメントスコア ランキング TOP10")
        lines.append("")
        lines.append("| 順位 | ユーザー | いいね | RT | リプライ | 総合スコア | 本文（冒頭） |")
        lines.append("|------|---------|--------|-----|---------|----------|------------|")
        for i, d in enumerate(buzz_engagement[:10], 1):
            text_preview = d["text"][:35].replace("|", "｜").replace("\n", " ")
            lines.append(f"| {i} | @{d['user']} | {d['likes']:,} | {d['rts']:,} | {d['replies']:,} | {d['total']:,} | {text_preview} |")
        lines.append("")

        # 2.2 Hidden Gems: いいね数は中央値以下だが総合スコアが高い
        lines.append("### 2.2 Hidden Gems（いいね数以上にエンゲージメントが高い投稿）")
        lines.append("")
        lines.append("> いいね数は中央値以下だが、RT・リプライを含む総合スコアが75パーセンタイル以上")
        lines.append("")

        if buzz_engagement:
            likes_list = sorted([d["likes"] for d in buzz_engagement])
            total_list = sorted([d["total"] for d in buzz_engagement])
            median_likes = likes_list[len(likes_list) // 2]
            total_75 = total_list[int(len(total_list) * 0.75)]

            gems = [d for d in buzz_engagement if d["likes"] <= median_likes and d["total"] >= total_75]
            gems.sort(key=lambda x: x["total"], reverse=True)

            if gems:
                lines.append("| ユーザー | いいね | RT | リプライ | 総合スコア | 本文（冒頭） |")
                lines.append("|---------|--------|-----|---------|----------|------------|")
                for d in gems[:5]:
                    text_preview = d["text"][:35].replace("|", "｜").replace("\n", " ")
                    lines.append(f"| @{d['user']} | {d['likes']:,} | {d['rts']:,} | {d['replies']:,} | {d['total']:,} | {text_preview} |")
                lines.append("")
                lines.append(f"Hidden Gems特徴: いいね数が{median_likes}以下でも、RT・リプライで総合スコア{total_75}以上を達成")
            else:
                lines.append("該当する投稿はありませんでした。")
        lines.append("")

        # 2.3 カテゴリ別・パターン別 総合スコア
        lines.append("### 2.3 カテゴリ別・パターン別 総合エンゲージメントスコア")
        lines.append("")

        # カテゴリ別
        cat_scores = defaultdict(list)
        pat_scores = defaultdict(list)
        for d in buzz_engagement:
            cat = classify_category(d["text"])
            cat_scores[cat].append(d["total"])
            first_line = d["text"].split("\n")[0] if d["text"] else ""
            pat = classify_opening_pattern(first_line)
            pat_scores[pat].append(d["total"])

        lines.append("**カテゴリ別:**")
        lines.append("")
        lines.append("| カテゴリ | 平均総合スコア | 件数 |")
        lines.append("|---------|-------------|------|")
        for cat, scores in sorted(cat_scores.items(), key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0, reverse=True):
            avg = sum(scores) / len(scores) if scores else 0
            lines.append(f"| {cat} | {avg:.0f} | {len(scores)} |")
        lines.append("")

        lines.append("**冒頭パターン別:**")
        lines.append("")
        lines.append("| パターン | 平均総合スコア | 件数 |")
        lines.append("|---------|-------------|------|")
        for pat, scores in sorted(pat_scores.items(), key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0, reverse=True):
            avg = sum(scores) / len(scores) if scores else 0
            lines.append(f"| {pat} | {avg:.0f} | {len(scores)} |")
        lines.append("")

    # 2.4 @Mr_botenのポジション
    lines.append("### 2.4 @Mr_botenのポジション")
    lines.append("")

    if len(df_self) == 0:
        lines.append("自分の投稿データが見つからないため、ポジション分析はスキップします。")
        lines.append("")
        lines.append("> `output/TwExport_20260217_191942.csv` を配置して再実行すると、自分の投稿との比較が表示されます。")
        lines.append("")
    else:
        self_followers = df_self["フォロワー数"].max() if len(df_self) > 0 else 0

        if self_followers > 0 and has_follower:
            self_rates = []
            for _, row in df_self.iterrows():
                likes = safe_get(row, "いいね数", 0)
                text = safe_get(row, "本文", "")
                rate = (likes / self_followers) * 100
                self_rates.append({"likes": likes, "rate": rate, "text": text[:50]})

            avg_self_rate = sum(d["rate"] for d in self_rates) / len(self_rates) if self_rates else 0

            buzz_rates_all = []
            for rates in fnorm["category_by_rate"].values():
                buzz_rates_all.extend(rates)
            avg_buzz_rate = sum(buzz_rates_all) / len(buzz_rates_all) if buzz_rates_all else 0

            lines.append(f"- **フォロワー数:** {self_followers:,}")
            lines.append(f"- **平均エンゲージメント率:** {avg_self_rate:.2f}%（バズ投稿平均: {avg_buzz_rate:.2f}%）")
            lines.append("")

            self_rates.sort(key=lambda x: x["rate"], reverse=True)
            lines.append("**自分のエンゲージメント率 TOP5:**")
            lines.append("")
            lines.append("| 順位 | いいね | エンゲージメント率 | 本文（冒頭） |")
            lines.append("|------|--------|-----------------|------------|")
            for i, d in enumerate(self_rates[:5], 1):
                text_preview = d["text"].replace("|", "｜").replace("\n", " ")[:40]
                lines.append(f"| {i} | {d['likes']:,} | {d['rate']:.2f}% | {text_preview} |")
            lines.append("")
        else:
            # 総合スコアで比較
            lines.append("**総合エンゲージメントスコアでの比較:**")
            lines.append("")
            self_eng = []
            for _, row in df_self.iterrows():
                likes = safe_get(row, "いいね数", 0)
                rts = safe_get(row, "リポスト数", 0)
                replies = safe_get(row, "リプライ数", 0)
                text = safe_get(row, "本文", "")
                total = likes + rts * 2 + replies * 3
                self_eng.append({"total": total, "likes": likes, "text": text[:50]})
            self_eng.sort(key=lambda x: x["total"], reverse=True)

            avg_self = sum(d["total"] for d in self_eng) / len(self_eng) if self_eng else 0
            avg_buzz = sum(d["total"] for d in buzz_engagement) / len(buzz_engagement) if buzz_engagement else 0

            lines.append(f"- **自分の平均総合スコア:** {avg_self:.0f}（バズ投稿平均: {avg_buzz:.0f}）")
            lines.append("")

            if self_eng:
                lines.append("**自分の総合スコア TOP5:**")
                lines.append("")
                lines.append("| 順位 | いいね | 総合スコア | 本文（冒頭） |")
                lines.append("|------|--------|-----------|------------|")
                for i, d in enumerate(self_eng[:5], 1):
                    text_preview = d["text"].replace("|", "｜").replace("\n", " ")[:40]
                    lines.append(f"| {i} | {d['likes']:,} | {d['total']:,} | {text_preview} |")
                lines.append("")

    return "\n".join(lines)


# === 分析3: バズ予測スコア検証 ===

def generate_buzz_score_section(df_buzz, df_self):
    """バズ予測スコア検証セクションを生成"""
    buzz_result = analyze_buzz_scores(df_buzz)
    lines = []

    lines.append("## 3. バズ予測スコア検証")
    lines.append("")
    lines.append("> バズ予測スコア（0-100点）: 冒頭パターン(20) + テキスト最適化(15) + カテゴリ(15) + 感情トリガー(10) + CTA(10) + ストーリー性(10) + 絵文字(10) + 読みやすさ(10)")
    lines.append("")

    # 3.1 スコア分布と相関
    lines.append("### 3.1 スコア分布と実いいね数の相関")
    lines.append("")
    lines.append(f"- **相関係数:** {buzz_result['correlation']:.3f}")
    if buzz_result["correlation"] > 0.5:
        lines.append("  → 強い正の相関。スコアはバズ予測にかなり有効")
    elif buzz_result["correlation"] > 0.3:
        lines.append("  → 中程度の正の相関。スコアは参考になるが改善の余地あり")
    elif buzz_result["correlation"] > 0.1:
        lines.append("  → 弱い正の相関。スコアの予測力は限定的")
    elif buzz_result["correlation"] > -0.1:
        lines.append("  → ほぼ無相関。スコアといいね数に関連性が薄い")
    else:
        lines.append("  → 負の相関。スコアが高いほどいいねが少ない逆転現象")
    lines.append("")

    scores = buzz_result["scores"]
    if scores:
        avg_score = sum(s["score"] for s in scores) / len(scores)
        max_score = max(s["score"] for s in scores)
        min_score = min(s["score"] for s in scores)
        lines.append(f"- **平均スコア:** {avg_score:.1f}点 / **最高:** {max_score}点 / **最低:** {min_score}点")
        lines.append("")

    # 3.2 スコア帯別平均いいね数
    lines.append("### 3.2 スコア帯別の平均いいね数")
    lines.append("")
    lines.append("| スコア帯 | 件数 | 平均いいね | 中央値いいね |")
    lines.append("|---------|------|----------|------------|")
    for bucket_name in ["80-100点", "60-79点", "40-59点", "0-39点"]:
        likes_list = buzz_result["score_buckets"].get(bucket_name, [])
        if likes_list:
            avg_l = sum(likes_list) / len(likes_list)
            med_l = sorted(likes_list)[len(likes_list) // 2]
            lines.append(f"| {bucket_name} | {len(likes_list)} | {avg_l:.0f} | {med_l:,} |")
        else:
            lines.append(f"| {bucket_name} | 0 | - | - |")
    lines.append("")

    # 3.3 乖離投稿分析
    lines.append("### 3.3 乖離投稿分析")
    lines.append("")

    if scores:
        # スコアといいね数の中央値を基準に乖離を計算
        median_likes = sorted([s["likes"] for s in scores])[len(scores) // 2]
        median_score_val = sorted([s["score"] for s in scores])[len(scores) // 2]

        # 高スコア×低いいね（スコアが上位25%なのに、いいねが下位50%）
        score_75 = sorted([s["score"] for s in scores])[int(len(scores) * 0.75)]
        high_score_low_likes = [s for s in scores if s["score"] >= score_75 and s["likes"] <= median_likes]
        high_score_low_likes.sort(key=lambda x: x["likes"])

        lines.append("**高スコアなのにバズってない投稿:**")
        lines.append(f"（スコア{score_75}点以上 & いいね{median_likes}以下）")
        lines.append("")
        if high_score_low_likes:
            lines.append("| スコア | いいね | 要因内訳 | 本文（冒頭） |")
            lines.append("|--------|--------|---------|------------|")
            for s in high_score_low_likes[:5]:
                factors_str = " / ".join(f"{k}:{v}" for k, v in s["factors"].items() if v > 0)
                text_preview = s["text"].replace("|", "｜").replace("\n", " ")[:35]
                lines.append(f"| {s['score']} | {s['likes']:,} | {factors_str} | {text_preview} |")
            lines.append("")
            lines.append("**なぜバズらなかった？考えられる要因:**")
            for s in high_score_low_likes[:3]:
                text_preview = s["text"].replace("\n", " ")[:40]
                weak_factors = [k for k, v in s["factors"].items() if v <= 3]
                lines.append(f"- 「{text_preview}...」→ 弱い要素: {', '.join(weak_factors) if weak_factors else 'スコア上は問題なし（タイミングや競合の影響か）'}")
            lines.append("")
        else:
            lines.append("該当する投稿はありませんでした。")
            lines.append("")

        # 低スコア×高いいね
        score_25 = sorted([s["score"] for s in scores])[int(len(scores) * 0.25)]
        low_score_high_likes = [s for s in scores if s["score"] <= score_25 and s["likes"] >= median_likes]
        low_score_high_likes.sort(key=lambda x: x["likes"], reverse=True)

        lines.append("**低スコアなのにバズった投稿:**")
        lines.append(f"（スコア{score_25}点以下 & いいね{median_likes}以上）")
        lines.append("")
        if low_score_high_likes:
            lines.append("| スコア | いいね | 要因内訳 | 本文（冒頭） |")
            lines.append("|--------|--------|---------|------------|")
            for s in low_score_high_likes[:5]:
                factors_str = " / ".join(f"{k}:{v}" for k, v in s["factors"].items() if v > 0)
                text_preview = s["text"].replace("|", "｜").replace("\n", " ")[:35]
                lines.append(f"| {s['score']} | {s['likes']:,} | {factors_str} | {text_preview} |")
            lines.append("")
            lines.append("**なぜバズった？スコアが捉えられていない要因:**")
            for s in low_score_high_likes[:3]:
                text_preview = s["text"].replace("\n", " ")[:40]
                lines.append(f"- 「{text_preview}...」→ スコアに含まれない要因（話題性、インフルエンサー効果、タイミング等）が寄与")
            lines.append("")
        else:
            lines.append("該当する投稿はありませんでした。")
            lines.append("")

    # 3.4 要素別寄与度
    lines.append("### 3.4 要素別寄与度")
    lines.append("")
    lines.append("| 要素 | 配点 | 平均スコア | 充足率 |")
    lines.append("|------|------|----------|--------|")
    max_points = {
        "冒頭パターン": 20, "テキスト最適化": 15, "カテゴリ": 15,
        "感情トリガー": 10, "CTA": 10, "ストーリー性": 10,
        "絵文字・書式": 10, "読みやすさ": 10,
    }
    for factor, avg_val in sorted(buzz_result["factor_avg"].items(),
                                   key=lambda x: x[1] / max_points.get(x[0], 10), reverse=True):
        max_pt = max_points.get(factor, 10)
        fill_rate = (avg_val / max_pt) * 100 if max_pt > 0 else 0
        lines.append(f"| {factor} | {max_pt}点 | {avg_val:.1f} | {fill_rate:.0f}% |")
    lines.append("")

    # 3.5 @Mr_botenの投稿スコア
    lines.append("### 3.5 @Mr_botenの投稿スコア")
    lines.append("")

    self_scores = []
    for _, row in df_self.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        result = calculate_buzz_score(text)
        self_scores.append({
            "text": text[:50], "score": result["total_score"],
            "likes": likes, "factors": result["factors"],
        })
    self_scores.sort(key=lambda x: x["score"], reverse=True)

    if self_scores:
        avg_self_score = sum(s["score"] for s in self_scores) / len(self_scores)
        avg_buzz_score_val = sum(s["score"] for s in scores) / len(scores) if scores else 0
        lines.append(f"- **自分の平均スコア:** {avg_self_score:.1f}点（バズ投稿平均: {avg_buzz_score_val:.1f}点）")
        diff = avg_self_score - avg_buzz_score_val
        lines.append(f"- **差分:** {diff:+.1f}点")
        lines.append("")

        # 自分のTOP5
        lines.append("**自分の投稿スコア TOP5:**")
        lines.append("")
        lines.append("| 順位 | スコア | いいね | 要因内訳 | 本文（冒頭） |")
        lines.append("|------|--------|--------|---------|------------|")
        for i, s in enumerate(self_scores[:5], 1):
            factors_str = " / ".join(f"{k}:{v}" for k, v in s["factors"].items() if v > 0)
            text_preview = s["text"].replace("|", "｜").replace("\n", " ")[:30]
            lines.append(f"| {i} | {s['score']} | {s['likes']:,} | {factors_str} | {text_preview} |")
        lines.append("")

        # 要素別の自分 vs バズ投稿比較
        lines.append("**要素別比較（自分 vs バズ投稿）:**")
        lines.append("")
        lines.append("| 要素 | 自分の平均 | バズ投稿平均 | 差分 |")
        lines.append("|------|----------|------------|------|")
        self_factor_avg = defaultdict(list)
        for s in self_scores:
            for k, v in s["factors"].items():
                self_factor_avg[k].append(v)
        for factor in max_points:
            self_avg = sum(self_factor_avg[factor]) / len(self_factor_avg[factor]) if self_factor_avg[factor] else 0
            buzz_avg = buzz_result["factor_avg"].get(factor, 0)
            diff_val = self_avg - buzz_avg
            lines.append(f"| {factor} | {self_avg:.1f} | {buzz_avg:.1f} | {diff_val:+.1f} |")
        lines.append("")
    else:
        lines.append("自分の投稿データがありません。")
        lines.append("")

    # 3.6 スコアの精度と改善提案
    lines.append("### 3.6 スコアの精度と改善提案")
    lines.append("")

    corr = buzz_result["correlation"]
    lines.append(f"**現在の精度:** 相関係数 {corr:.3f}")
    lines.append("")

    lines.append("**スコアが捉えられていない要因（改善提案）:**")
    lines.append("")
    lines.append("1. **投稿タイミング**: 18-21時のゴールデンタイム投稿はバズりやすいが、現在のスコアに時間帯は未反映")
    lines.append("2. **アカウント影響力**: フォロワー数やアカウントの権威性がバズに大きく影響するが未考慮")
    lines.append("3. **話題性・トレンド**: 旬のトピック（AI新ツール発表直後など）に乗った投稿はスコア以上にバズる")
    lines.append("4. **秘匿感・告白フレーズ**: 「正直に言うと」「ぶっちゃけ」等の自己開示フレーズの重みが軽い可能性")

    # 乖離投稿の分析から追加の改善点を抽出
    if scores:
        high_score_low_likes_posts = [s for s in scores if s["score"] >= score_75 and s["likes"] <= median_likes]
        if high_score_low_likes_posts:
            # 高スコア低いいねの共通パターンを分析
            weak_in_high = defaultdict(int)
            for s in high_score_low_likes_posts:
                for k, v in s["factors"].items():
                    if v <= max_points.get(k, 10) * 0.3:
                        weak_in_high[k] += 1
            if weak_in_high:
                most_common_weak = max(weak_in_high.items(), key=lambda x: x[1])
                lines.append(f"5. **{most_common_weak[0]}の重み調整**: 高スコア低バズ投稿の{most_common_weak[1]}件中で弱い要素 → 配点が過大な可能性")

    lines.append("")

    return "\n".join(lines)


# === 総合まとめ ===

def generate_summary(df_buzz, df_self, viral_result, fnorm_result, buzz_result):
    """総合まとめセクションを生成"""
    lines = []
    lines.append("## 4. 総合まとめ・アクション提案")
    lines.append("")

    lines.append("### 発見された主要インサイト")
    lines.append("")

    # バイラル係数からの発見
    lines.append("**バイラル係数分析から:**")
    top_cat = max(viral_result["cat_viral"].items(), key=lambda x: x[1]) if viral_result["cat_viral"] else ("N/A", 0)
    lines.append(f"- シェアされやすいカテゴリは「{top_cat[0]}」（バイラル係数: {top_cat[1]:.3f}）")
    lines.append(f"- バズ投稿の平均バイラル係数: {viral_result['avg_coeff']:.3f}")
    lines.append("")

    # フォロワー正規化からの発見
    lines.append("**フォロワー正規化から:**")
    if fnorm_result["hidden_gems"]:
        gems = fnorm_result["hidden_gems"]
        lines.append(f"- Hidden Gems発見: {len(gems)}件（少フォロワーでも高エンゲージメント率を実現）")
        lines.append(f"  - TOP: @{gems[0]['user']}（フォロワー{gems[0]['followers']:,} → エンゲージメント率{gems[0]['rate']:.2f}%）")
    lines.append("")

    # バズスコアからの発見
    lines.append("**バズ予測スコアから:**")
    lines.append(f"- スコアと実いいね数の相関: {buzz_result['correlation']:.3f}")
    if buzz_result["factor_avg"]:
        weakest = min(buzz_result["factor_avg"].items(),
                      key=lambda x: x[1] / max(1, {"冒頭パターン": 20, "テキスト最適化": 15, "カテゴリ": 15}.get(x[0], 10)))
        lines.append(f"- 全体的に弱い要素: {weakest[0]}（平均{weakest[1]:.1f}点）")
    lines.append("")

    # @Mr_botenへのアクション提案
    lines.append("### @Mr_botenへのアクション提案")
    lines.append("")

    # 自分のデータから改善点を特定
    self_scores = []
    for _, row in df_self.iterrows():
        text = safe_get(row, "本文", "")
        result = calculate_buzz_score(text)
        self_scores.append(result)

    if self_scores:
        self_factor_avg = defaultdict(list)
        for s in self_scores:
            for k, v in s["factors"].items():
                self_factor_avg[k].append(v)

        max_points = {
            "冒頭パターン": 20, "テキスト最適化": 15, "カテゴリ": 15,
            "感情トリガー": 10, "CTA": 10, "ストーリー性": 10,
            "絵文字・書式": 10, "読みやすさ": 10,
        }

        # 改善余地が大きい要素を特定
        improvements = []
        for factor, max_pt in max_points.items():
            vals = self_factor_avg.get(factor, [0])
            avg_val = sum(vals) / len(vals) if vals else 0
            gap = max_pt - avg_val
            fill = avg_val / max_pt * 100
            if fill < 50:
                improvements.append((factor, avg_val, max_pt, gap))

        improvements.sort(key=lambda x: x[3], reverse=True)

        if improvements:
            lines.append("**改善すべき要素（充足率50%未満）:**")
            for factor, avg_val, max_pt, gap in improvements:
                fill = avg_val / max_pt * 100
                lines.append(f"- **{factor}**: 現在{avg_val:.1f}/{max_pt}点（充足率{fill:.0f}%）→ +{gap:.0f}点の伸びしろ")
            lines.append("")

    lines.append("**具体的アクション:**")
    lines.append("1. シェアされやすい投稿を狙うなら、バイラル係数の高いカテゴリ・パターンを意識")
    lines.append("2. Hidden Gemsの投稿スタイルを参考に、フォロワー規模に見合った高エンゲージ投稿を目指す")
    lines.append("3. バズスコアの弱い要素を1つずつ改善（冒頭パターン・感情トリガーが効果大）")
    lines.append("4. 投稿タイミング（18-21時）× 等身大の告白スタイルは引き続き最強の武器")
    lines.append("")

    return "\n".join(lines)


# === メイン処理 ===

def main():
    print("=" * 60)
    print("高度分析レポート生成")
    print("=" * 60)

    # データ読み込み
    if not os.path.exists(BUZZ_FILE):
        print(f"エラー: {BUZZ_FILE} が見つかりません")
        return
    df_buzz_raw = load_excel(BUZZ_FILE)
    if df_buzz_raw is None:
        return

    df_buzz, original_count, excluded_count = filter_data(df_buzz_raw)

    if os.path.exists(SELF_FILE):
        df_self = load_self_posts(SELF_FILE)
    else:
        print(f"注意: {SELF_FILE} が見つかりません。自分の投稿との比較はスキップします。")
        df_self = pd.DataFrame(columns=["本文", "いいね数", "リポスト数", "リプライ数", "フォロワー数", "ユーザー名"])

    print(f"\nバズ投稿: {len(df_buzz)}件 / 自分の投稿: {len(df_self)}件")
    print()

    # 分析実行
    print("分析1: バイラル係数分析...")
    viral_result = analyze_viral_coefficient(df_buzz)

    print("分析2: フォロワー正規化...")
    fnorm_result = analyze_follower_normalized(df_buzz)

    print("分析3: バズ予測スコア検証...")
    buzz_result = analyze_buzz_scores(df_buzz)

    # レポート生成
    print("\nレポート生成中...")

    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    report = []
    report.append("# 高度分析レポート: バイラル係数・フォロワー正規化・バズ予測スコア検証")
    report.append("")
    report.append(f"**分析日時:** {now}")
    report.append(f"**バズ投稿データ:** {len(df_buzz)}件（元データ{original_count}件から{excluded_count}件除外）")
    report.append(f"**自分の投稿データ:** {len(df_self)}件（@Mr_boten）")
    report.append("")
    report.append("---")
    report.append("")

    # 各セクション生成
    report.append(generate_viral_section(df_buzz, df_self))
    report.append("")
    report.append("---")
    report.append("")
    report.append(generate_follower_section(df_buzz, df_self))
    report.append("")
    report.append("---")
    report.append("")
    report.append(generate_buzz_score_section(df_buzz, df_self))
    report.append("")
    report.append("---")
    report.append("")
    report.append(generate_summary(df_buzz, df_self, viral_result, fnorm_result, buzz_result))

    # ファイル出力
    output_text = "\n".join(report)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output_text)

    print(f"\nレポート保存完了: {OUTPUT_FILE}")
    print(f"文字数: {len(output_text):,}文字")


if __name__ == "__main__":
    main()
