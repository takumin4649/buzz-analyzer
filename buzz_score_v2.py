"""バズ予測スコアv2: データ駆動による重み最適化"""

import os
import re
from collections import defaultdict
from datetime import datetime

import pandas as pd

from analyze_posts import (
    EMOJI_PATTERN,
    POWER_WORDS,
    calculate_buzz_score,
    classify_category,
    classify_opening_pattern,
    filter_data,
    has_story,
    load_excel,
    safe_get,
)

BUZZ_FILE = "output/buzz_posts_20260215.xlsx"
SELF_FILE = "output/TwExport_20260217_191942.csv"
OUTPUT_FILE = "output/buzz_score_v2_20260217.md"


# === v2 スコア計算 ===

def calculate_buzz_score_v2(text, post_datetime=None):
    """データ駆動型バズ予測スコアv2（0-100点）

    v1からの主な変更:
    - 具体的数字を新要素として追加（最大正の相関 +0.225）
    - 文字数の最適レンジを0-170字に変更（短い方がバズる）
    - CTA・感情トリガーを削除（実データで負の効果）
    - 簡潔さ（改行数少ない）を重視
    - 冒頭パターン・カテゴリの配点をデータ駆動で再調整
    - 投稿時間帯を追加（参考値）
    """
    factors = {}
    total = 0

    # 1. 冒頭パターン (25点) - 数字提示が圧倒的（平均806いいね）
    first_line = text.split("\n")[0] if text else ""
    pattern = classify_opening_pattern(first_line)
    pattern_scores = {
        "数字提示": 25,  # 平均806いいね
        "共感": 18,      # 平均518いいね
        "疑問形": 12,    # 平均344いいね
        "その他": 10,    # 平均297いいね
        "断定形": 8,     # 平均267いいね
        "煽り": 6,
        "呼びかけ": 5,
    }
    s = pattern_scores.get(pattern, 10)
    factors["冒頭パターン"] = s
    total += s

    # 2. 文字数 (20点) - 短い方がバズる
    length = len(text)
    if length <= 80:
        s = 20       # 平均630いいね
    elif length <= 170:
        s = 17       # 131-170字で平均413いいね
    elif length <= 220:
        s = 10       # 171-220字で平均300いいね
    elif length <= 300:
        s = 4        # 221-300字で平均136いいね
    else:
        s = 2        # 301字以上
    # 81-130字は283いいねだが170字以下としてまとめる
    if 81 <= length <= 130:
        s = 13
    factors["文字数"] = s
    total += s

    # 3. カテゴリ (15点) - データ駆動
    category = classify_category(text)
    cat_scores = {
        "体験談系": 15,      # 平均558いいね
        "問題提起系": 15,    # 平均551いいね（n=1だが高い）
        "ツール紹介系": 10,  # 平均348いいね
        "ノウハウ系": 8,     # 平均289いいね
        "実績報告系": 7,     # 平均254いいね
        "その他": 5,
    }
    s = cat_scores.get(category, 5)
    factors["カテゴリ"] = s
    total += s

    # 4. 具体的数字 (15点) - 最強の正の相関 (+0.225)
    has_numbers = bool(re.search(
        r'[0-9０-９]+[万円個件つ選ステップヶ月日時間分秒%％倍]', text
    ))
    has_money = bool(re.search(r'[0-9０-９]+万|[0-9０-９]+円|月収|年収|売上', text))
    s = 0
    if has_numbers:
        s += 10
    if has_money:
        s += 5
    s = min(15, s)
    factors["具体的数字"] = s
    total += s

    # 5. 簡潔さ (10点) - 改行少ない方がバズる（相関-0.177）
    line_breaks = text.count("\n")
    if line_breaks <= 3:
        s = 10
    elif line_breaks <= 7:
        s = 7
    elif line_breaks <= 12:
        s = 4
    else:
        s = 1
    factors["簡潔さ"] = s
    total += s

    # 6. 絵文字 (10点) - 少ない方がバズる（相関-0.142）
    emoji_count = len(EMOJI_PATTERN.findall(text))
    if emoji_count == 0:
        s = 10       # TOP20平均0.5個
    elif emoji_count <= 2:
        s = 6
    else:
        s = 2        # 多すぎると逆効果
    factors["絵文字"] = s
    total += s

    # 7. ストーリー性 (5点) - 弱い正の相関（+0.054）
    s = 5 if has_story(text) else 0
    factors["ストーリー性"] = s
    total += s

    # 参考: 投稿時間帯（スコアには含めないが表示用）
    hour = -1
    if post_datetime:
        m = re.search(r'(\d{1,2}):\d{2}', str(post_datetime))
        if m:
            hour = int(m.group(1))
    factors["_hour"] = hour

    return {"total_score": total, "factors": factors}


def extract_features(text):
    """テキストから全特徴量を抽出（分析用）"""
    first_line = text.split("\n")[0] if text else ""
    length = len(text)
    line_breaks = text.count("\n")
    emoji_count = len(EMOJI_PATTERN.findall(text))
    pw_count = sum(1 for p in POWER_WORDS.values() if p.search(text))

    has_numbers = bool(re.search(r'[0-9０-９]+[万円個件つ選ステップヶ月日時間分秒%％倍]', text))
    has_money = bool(re.search(r'[0-9０-９]+万|[0-9０-９]+円|月収|年収|売上', text))

    cta_patterns = [r'いいね|👍', r'保存|ブックマーク', r'フォロー', r'リポスト|RT|シェア|拡散', r'コメント|返信|教えて']
    has_cta = any(re.search(p, text, re.IGNORECASE) for p in cta_patterns)

    emotion_patterns = {
        "期待": r'チャンス|可能性|稼げる|儲かる|成功|達成|実現|できる',
        "驚き": r'まさか|びっくり|驚き|すごい|やばい|ヤバい|えぐい',
        "共感": r'わかる|そうそう|あるある|同じ|私も',
        "恐怖": r'危険|怖い|リスク|失敗|損|最悪',
    }
    emotion_count = sum(1 for p in emotion_patterns.values() if re.search(p, text, re.IGNORECASE))

    secret_patterns = [
        r'知らないと', r'正直', r'マジで', r'ぶっちゃけ', r'本当は',
        r'実は', r'こっそり', r'秘密', r'裏技', r'内緒',
        r'ここだけ', r'言いにくい', r'ド素人', r'素人',
    ]
    secret_count = sum(1 for p in secret_patterns if re.search(p, text))

    return {
        "category": classify_category(text),
        "opening_pattern": classify_opening_pattern(first_line),
        "length": length,
        "line_breaks": line_breaks,
        "emoji_count": emoji_count,
        "pw_count": pw_count,
        "has_numbers": has_numbers,
        "has_money": has_money,
        "has_cta": has_cta,
        "has_story": has_story(text),
        "emotion_count": emotion_count,
        "secret_count": secret_count,
    }


def load_self_posts(filepath):
    """自分の投稿CSVを読み込む"""
    df = pd.read_csv(filepath, encoding="utf-8-sig")
    for col in ["いいね数", "リポスト数", "リプライ数", "フォロワー数"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df


# === レポート生成 ===

def generate_report(df_buzz, df_self):
    """バズ予測スコアv2レポートを生成"""
    lines = []
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    lines.append("# バズ予測スコアv2 改善レポート")
    lines.append("")
    lines.append(f"**分析日時:** {now}")
    lines.append(f"**分析対象:** バズ投稿{len(df_buzz)}件")
    if len(df_self) > 0:
        lines.append(f"**自分の投稿:** {len(df_self)}件（@Mr_boten）")
    lines.append("")
    lines.append("---")
    lines.append("")

    # === セクション1: 現行v1の問題点 ===
    lines.append("## 1. 現行スコア（v1）の問題点")
    lines.append("")
    lines.append("### 1.1 v1のスコア計算ロジック")
    lines.append("")
    lines.append("| 要素 | 配点 | 算出方法 |")
    lines.append("|------|------|---------|")
    lines.append("| 冒頭パターン | 20点 | 数字提示(20)→疑問形(16)→煽り/共感(14)→呼びかけ(12)→断定形(8)→その他(5) |")
    lines.append("| テキスト最適化 | 15点 | 100-300字で満点、範囲外は按分 |")
    lines.append("| カテゴリ | 15点 | 実績報告(15)→ノウハウ(13)→問題提起(12)→体験談(11)→ツール(10) |")
    lines.append("| 感情トリガー | 10点 | 4種類の感情パターン、1種4点（最大10） |")
    lines.append("| CTA | 10点 | CTA有=10、無=0 |")
    lines.append("| ストーリー性 | 10点 | ストーリーキーワード有=10、無=0 |")
    lines.append("| 絵文字・書式 | 10点 | 1-3個で満点(10)、0個(4)、4個以上(6) |")
    lines.append("| 読みやすさ | 10点 | 改行3-10本(5) + 箇条書き有(5) |")
    lines.append("| **合計** | **100点** | |")
    lines.append("")

    # v1スコアを全投稿に計算
    v1_scores = []
    v2_scores = []
    for _, row in df_buzz.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        dt_str = safe_get(row, "投稿日時", "")
        v1 = calculate_buzz_score(text)
        v2 = calculate_buzz_score_v2(text, dt_str)
        features = extract_features(text)
        v1_scores.append({"text": text, "likes": likes, "v1": v1["total_score"], "v1_factors": v1["factors"]})
        v2_scores.append({
            "text": text, "likes": likes,
            "v2": v2["total_score"], "v2_factors": v2["factors"],
            "v1": v1["total_score"],
            "features": features,
        })

    df_scores = pd.DataFrame([{"likes": s["likes"], "v1": s["v1"], "v2": s["v2"]} for s in v2_scores])
    corr_v1 = float(df_scores["likes"].corr(df_scores["v1"]))
    corr_v2 = float(df_scores["likes"].corr(df_scores["v2"]))

    lines.append("### 1.2 v1の致命的な問題")
    lines.append("")
    lines.append(f"**相関係数: {corr_v1:+.3f}（ほぼ無相関）**")
    lines.append("")

    # TOP20 vs WORST20
    sorted_by_likes = sorted(v2_scores, key=lambda x: x["likes"], reverse=True)
    top20 = sorted_by_likes[:20]
    worst20 = sorted_by_likes[-20:]

    avg_v1_top = sum(s["v1"] for s in top20) / 20
    avg_v1_worst = sum(s["v1"] for s in worst20) / 20

    lines.append("**TOP20 vs WORST20の平均v1スコア:**")
    lines.append(f"- TOP20（いいね上位）: 平均 **{avg_v1_top:.1f}点**")
    lines.append(f"- WORST20（いいね下位）: 平均 **{avg_v1_worst:.1f}点**")
    lines.append(f"- → v1スコアが **逆方向に作用** している（高スコア = 低いいね）")
    lines.append("")

    lines.append("**v1で加点される要素が実際には逆効果:**")
    lines.append("")
    lines.append("| 要素 | v1の仮定 | 実データ | 問題 |")
    lines.append("|------|---------|---------|------|")

    # CTA
    cta_yes = [s for s in v2_scores if s["features"]["has_cta"]]
    cta_no = [s for s in v2_scores if not s["features"]["has_cta"]]
    avg_cta_yes = sum(s["likes"] for s in cta_yes) / len(cta_yes) if cta_yes else 0
    avg_cta_no = sum(s["likes"] for s in cta_no) / len(cta_no) if cta_no else 0
    lines.append(f"| CTA (+10点) | CTA有 → バズる | CTAあり平均{avg_cta_yes:.0f} vs なし{avg_cta_no:.0f} | **CTAなしの方が高い** |")

    # 感情トリガー
    emo0 = [s for s in v2_scores if s["features"]["emotion_count"] == 0]
    emo1 = [s for s in v2_scores if s["features"]["emotion_count"] >= 1]
    avg_emo0 = sum(s["likes"] for s in emo0) / len(emo0) if emo0 else 0
    avg_emo1 = sum(s["likes"] for s in emo1) / len(emo1) if emo1 else 0
    lines.append(f"| 感情トリガー (+10点) | 感情多 → バズる | 0種{avg_emo0:.0f} vs 1種以上{avg_emo1:.0f} | **感情なしの方が高い** |")

    # 絵文字
    emoji0 = [s for s in v2_scores if s["features"]["emoji_count"] == 0]
    emoji_some = [s for s in v2_scores if s["features"]["emoji_count"] >= 1]
    avg_emoji0 = sum(s["likes"] for s in emoji0) / len(emoji0) if emoji0 else 0
    avg_emoji_some = sum(s["likes"] for s in emoji_some) / len(emoji_some) if emoji_some else 0
    lines.append(f"| 絵文字 (0個=4点, 1-3個=10点) | 絵文字あり → バズる | 0個{avg_emoji0:.0f} vs 1個以上{avg_emoji_some:.0f} | **絵文字なしの方が高い** |")

    # テキスト長
    short = [s for s in v2_scores if len(s["text"]) <= 170]
    long_text = [s for s in v2_scores if len(s["text"]) > 300]
    avg_short = sum(s["likes"] for s in short) / len(short) if short else 0
    avg_long = sum(s["likes"] for s in long_text) / len(long_text) if long_text else 0
    lines.append(f"| テキスト最適化 (100-300字) | 100-300字 → 満点 | 170字以下{avg_short:.0f} vs 300字超{avg_long:.0f} | **短い方が圧倒的に高い** |")

    lines.append("")

    # === セクション2: 特徴量と相関 ===
    lines.append("---")
    lines.append("")
    lines.append("## 2. 特徴量とバズの相関分析（TOP20 vs WORST20）")
    lines.append("")

    # 特徴量の比較テーブル
    feature_comparisons = [
        ("文字数", lambda s: len(s["text"])),
        ("改行数", lambda s: s["features"]["line_breaks"]),
        ("具体的数字あり率", lambda s: 1 if s["features"]["has_numbers"] else 0),
        ("金額表現あり率", lambda s: 1 if s["features"]["has_money"] else 0),
        ("絵文字数", lambda s: s["features"]["emoji_count"]),
        ("CTA使用率", lambda s: 1 if s["features"]["has_cta"] else 0),
        ("ストーリー性率", lambda s: 1 if s["features"]["has_story"] else 0),
        ("感情トリガー数", lambda s: s["features"]["emotion_count"]),
        ("秘匿感フレーズ数", lambda s: s["features"]["secret_count"]),
        ("パワーワード種類数", lambda s: s["features"]["pw_count"]),
    ]

    lines.append("| 特徴量 | TOP20平均 | WORST20平均 | 差分 | バズとの関係 |")
    lines.append("|--------|----------|------------|------|-----------|")

    for name, func in feature_comparisons:
        t_avg = sum(func(s) for s in top20) / 20
        w_avg = sum(func(s) for s in worst20) / 20
        diff = t_avg - w_avg
        if name.endswith("率"):
            relation = f"TOP20: {t_avg*100:.0f}% / WORST20: {w_avg*100:.0f}%"
        else:
            relation = f"{'バズに正' if diff > 0 else 'バズに負' if diff < 0 else '差なし'}"
        lines.append(f"| {name} | {t_avg:.2f} | {w_avg:.2f} | {diff:+.2f} | {relation} |")
    lines.append("")

    # カテゴリ別
    lines.append("**カテゴリ別平均いいね数（データ根拠）:**")
    lines.append("")
    cat_data = defaultdict(list)
    for s in v2_scores:
        cat_data[s["features"]["category"]].append(s["likes"])
    lines.append("| カテゴリ | 平均いいね | 件数 | v1配点 | v2配点 |")
    lines.append("|---------|----------|------|--------|--------|")
    v1_cat = {"実績報告系": 15, "ノウハウ系": 13, "問題提起系": 12, "体験談系": 11, "ツール紹介系": 10, "その他": 5}
    v2_cat = {"体験談系": 15, "問題提起系": 15, "ツール紹介系": 10, "ノウハウ系": 8, "実績報告系": 7, "その他": 5}
    for cat, likes_list in sorted(cat_data.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True):
        avg = sum(likes_list) / len(likes_list)
        lines.append(f"| {cat} | {avg:.0f} | {len(likes_list)} | {v1_cat.get(cat, 5)} | {v2_cat.get(cat, 5)} |")
    lines.append("")

    # 冒頭パターン別
    lines.append("**冒頭パターン別平均いいね数（データ根拠）:**")
    lines.append("")
    pat_data = defaultdict(list)
    for s in v2_scores:
        pat_data[s["features"]["opening_pattern"]].append(s["likes"])
    lines.append("| パターン | 平均いいね | 件数 | v1配点 | v2配点 |")
    lines.append("|---------|----------|------|--------|--------|")
    v1_pat = {"数字提示": 20, "疑問形": 16, "煽り": 14, "共感": 14, "呼びかけ": 12, "断定形": 8, "その他": 5}
    v2_pat = {"数字提示": 25, "共感": 18, "疑問形": 12, "その他": 10, "断定形": 8, "煽り": 6, "呼びかけ": 5}
    for pat, likes_list in sorted(pat_data.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True):
        avg = sum(likes_list) / len(likes_list)
        lines.append(f"| {pat} | {avg:.0f} | {len(likes_list)} | {v1_pat.get(pat, 5)} | {v2_pat.get(pat, 10)} |")
    lines.append("")

    # 文字数帯別
    lines.append("**文字数帯別平均いいね数（データ根拠）:**")
    lines.append("")
    lines.append("| 文字数帯 | 平均いいね | 件数 | v2配点 |")
    lines.append("|---------|----------|------|--------|")
    bins = [(0, 80, 20), (81, 130, 13), (131, 170, 17), (171, 220, 10), (221, 300, 4), (301, 999, 2)]
    for lo, hi, pts in bins:
        subset = [s for s in v2_scores if lo <= len(s["text"]) <= hi]
        if subset:
            avg = sum(s["likes"] for s in subset) / len(subset)
            label = f"{lo}-{hi}字" if hi < 999 else f"{lo}字以上"
            lines.append(f"| {label} | {avg:.0f} | {len(subset)} | {pts} |")
    lines.append("")

    # === セクション3: v2スコア設計 ===
    lines.append("---")
    lines.append("")
    lines.append("## 3. 新スコア（v2）の設計")
    lines.append("")
    lines.append("### 3.1 v1 → v2 変更サマリ")
    lines.append("")
    lines.append("| 要素 | v1 | v2 | 変更理由 |")
    lines.append("|------|-----|-----|---------|")
    lines.append("| 冒頭パターン | 20点 | **25点** | 数字提示の影響力が最大。配点増 |")
    lines.append("| 文字数 | 15点（100-300字） | **20点（0-170字）** | 短い投稿が圧倒的にバズる |")
    lines.append("| カテゴリ | 15点（実績報告最高） | **15点（体験談最高）** | データ駆動で順位逆転 |")
    lines.append("| 具体的数字 | なし | **15点（新規）** | 唯一の正の相関(+0.225) |")
    lines.append("| 簡潔さ | なし | **10点（新規）** | 改行少ない方がバズる(-0.177) |")
    lines.append("| 絵文字 | 10点（1-3個最高） | **10点（0個最高）** | 絵文字なしが最もバズる |")
    lines.append("| ストーリー性 | 10点 | **5点** | 弱い正の相関、配点縮小 |")
    lines.append("| 感情トリガー | 10点 | **削除** | 感情多いほどバズらない |")
    lines.append("| CTA | 10点 | **削除** | CTAなしの方がバズる |")
    lines.append("| 読みやすさ | 10点 | **→簡潔さに統合** | 箇条書き・改行多い=逆効果 |")
    lines.append("| **合計** | **100点** | **100点** | |")
    lines.append("")

    lines.append("### 3.2 v2スコア詳細ロジック")
    lines.append("")
    lines.append("```")
    lines.append("1. 冒頭パターン (25点)")
    lines.append("   数字提示=25 / 共感=18 / 疑問形=12 / その他=10 / 断定形=8 / 煽り=6 / 呼びかけ=5")
    lines.append("")
    lines.append("2. 文字数 (20点)")
    lines.append("   0-80字=20 / 131-170字=17 / 81-130字=13 / 171-220字=10 / 221-300字=4 / 301字+=2")
    lines.append("")
    lines.append("3. カテゴリ (15点)")
    lines.append("   体験談系=15 / 問題提起系=15 / ツール紹介系=10 / ノウハウ系=8 / 実績報告系=7 / その他=5")
    lines.append("")
    lines.append("4. 具体的数字 (15点) ★新規")
    lines.append("   数字+単位あり=10 / 金額表現あり=+5 / なし=0")
    lines.append("")
    lines.append("5. 簡潔さ (10点) ★新規")
    lines.append("   改行0-3=10 / 4-7=7 / 8-12=4 / 13+=1")
    lines.append("")
    lines.append("6. 絵文字 (10点) ★逆転")
    lines.append("   0個=10 / 1-2個=6 / 3個+=2")
    lines.append("")
    lines.append("7. ストーリー性 (5点)")
    lines.append("   あり=5 / なし=0")
    lines.append("```")
    lines.append("")

    # === セクション4: 改善結果 ===
    lines.append("---")
    lines.append("")
    lines.append("## 4. 改善前後の比較")
    lines.append("")
    lines.append("### 4.1 相関係数")
    lines.append("")
    lines.append(f"| | v1 | v2 | 改善幅 |")
    lines.append(f"|---|-----|-----|--------|")
    lines.append(f"| **相関係数** | {corr_v1:+.3f} | **{corr_v2:+.3f}** | **{corr_v2 - corr_v1:+.3f}** |")
    lines.append("")

    if corr_v2 > 0.3:
        lines.append(f"→ v2では中程度の正の相関を達成。スコアが高いほどバズりやすい傾向を捉えている。")
    elif corr_v2 > 0.1:
        lines.append(f"→ v2では弱い正の相関。v1の無相関から改善。")
    elif corr_v2 > corr_v1:
        lines.append(f"→ v1より改善したが、まだ弱い相関。投稿者の影響力やタイミングなど、テキスト以外の要因が大きい。")
    lines.append("")

    # TOP20/WORST20のv2スコア比較
    avg_v2_top = sum(s["v2"] for s in top20) / 20
    avg_v2_worst = sum(s["v2"] for s in worst20) / 20

    lines.append("### 4.2 TOP20 vs WORST20のスコア比較")
    lines.append("")
    lines.append("| | TOP20平均 | WORST20平均 | 差 |")
    lines.append("|---|----------|------------|-----|")
    lines.append(f"| v1スコア | {avg_v1_top:.1f} | {avg_v1_worst:.1f} | {avg_v1_top - avg_v1_worst:+.1f}（逆転） |")
    lines.append(f"| **v2スコア** | **{avg_v2_top:.1f}** | **{avg_v2_worst:.1f}** | **{avg_v2_top - avg_v2_worst:+.1f}** |")
    lines.append("")

    # スコア帯別平均いいね
    lines.append("### 4.3 v2スコア帯別の平均いいね数")
    lines.append("")
    lines.append("| スコア帯 | 件数 | 平均いいね | 中央値 |")
    lines.append("|---------|------|----------|--------|")
    buckets = {"80-100点": [], "60-79点": [], "40-59点": [], "0-39点": []}
    for s in v2_scores:
        sc = s["v2"]
        if sc >= 80:
            buckets["80-100点"].append(s["likes"])
        elif sc >= 60:
            buckets["60-79点"].append(s["likes"])
        elif sc >= 40:
            buckets["40-59点"].append(s["likes"])
        else:
            buckets["0-39点"].append(s["likes"])
    for bucket, likes_list in buckets.items():
        if likes_list:
            avg = sum(likes_list) / len(likes_list)
            med = sorted(likes_list)[len(likes_list) // 2]
            lines.append(f"| {bucket} | {len(likes_list)} | {avg:.0f} | {med} |")
        else:
            lines.append(f"| {bucket} | 0 | - | - |")
    lines.append("")

    # 要素別寄与度
    lines.append("### 4.4 v2要素別の平均スコアと充足率")
    lines.append("")
    max_points = {
        "冒頭パターン": 25, "文字数": 20, "カテゴリ": 15,
        "具体的数字": 15, "簡潔さ": 10, "絵文字": 10, "ストーリー性": 5,
    }
    factor_totals = defaultdict(list)
    for s in v2_scores:
        for k, v in s["v2_factors"].items():
            if not k.startswith("_"):
                factor_totals[k].append(v)

    lines.append("| 要素 | 配点 | 平均スコア | 充足率 |")
    lines.append("|------|------|----------|--------|")
    for factor in max_points:
        vals = factor_totals.get(factor, [0])
        avg_val = sum(vals) / len(vals) if vals else 0
        max_pt = max_points[factor]
        fill = avg_val / max_pt * 100 if max_pt > 0 else 0
        lines.append(f"| {factor} | {max_pt}点 | {avg_val:.1f} | {fill:.0f}% |")
    lines.append("")

    # === セクション5: 乖離投稿分析 ===
    lines.append("---")
    lines.append("")
    lines.append("## 5. v2スコアの乖離投稿分析")
    lines.append("")

    sorted_by_v2 = sorted(v2_scores, key=lambda x: x["v2"], reverse=True)
    median_likes = sorted([s["likes"] for s in v2_scores])[len(v2_scores) // 2]
    score_75 = sorted([s["v2"] for s in v2_scores])[int(len(v2_scores) * 0.75)]
    score_25 = sorted([s["v2"] for s in v2_scores])[int(len(v2_scores) * 0.25)]

    # 高スコア×低いいね
    high_low = [s for s in v2_scores if s["v2"] >= score_75 and s["likes"] <= median_likes]
    high_low.sort(key=lambda x: x["likes"])

    lines.append(f"### 5.1 高スコアなのにバズってない投稿（v2≥{score_75}点 & いいね≤{median_likes}）")
    lines.append("")
    if high_low:
        lines.append("| v2 | v1 | いいね | 要因 | 本文（冒頭） |")
        lines.append("|-----|-----|--------|------|------------|")
        for s in high_low[:5]:
            factors_str = " / ".join(f"{k}:{v}" for k, v in s["v2_factors"].items() if not k.startswith("_") and v > 0)
            text_preview = s["text"][:35].replace("|", "｜").replace("\n", " ")
            lines.append(f"| {s['v2']} | {s['v1']} | {s['likes']:,} | {factors_str} | {text_preview} |")
        lines.append("")
        lines.append("**考察:** テキスト品質は高いが、投稿者のフォロワー規模やタイミングなどテキスト外要因が影響")
    else:
        lines.append("該当なし")
    lines.append("")

    # 低スコア×高いいね
    low_high = [s for s in v2_scores if s["v2"] <= score_25 and s["likes"] >= median_likes]
    low_high.sort(key=lambda x: x["likes"], reverse=True)

    lines.append(f"### 5.2 低スコアなのにバズった投稿（v2≤{score_25}点 & いいね≥{median_likes}）")
    lines.append("")
    if low_high:
        lines.append("| v2 | v1 | いいね | 要因 | 本文（冒頭） |")
        lines.append("|-----|-----|--------|------|------------|")
        for s in low_high[:5]:
            factors_str = " / ".join(f"{k}:{v}" for k, v in s["v2_factors"].items() if not k.startswith("_") and v > 0)
            text_preview = s["text"][:35].replace("|", "｜").replace("\n", " ")
            lines.append(f"| {s['v2']} | {s['v1']} | {s['likes']:,} | {factors_str} | {text_preview} |")
        lines.append("")
        lines.append("**考察:** インフルエンサー効果やトレンド話題など、テキスト以外の要因で大きくバズった投稿")
    else:
        lines.append("該当なし")
    lines.append("")

    # === セクション6: 全投稿v2スコアランキング ===
    lines.append("---")
    lines.append("")
    lines.append("## 6. 全投稿 v2スコアランキング TOP10 / WORST10")
    lines.append("")
    lines.append("### TOP10（v2スコア順）")
    lines.append("")
    lines.append("| 順位 | v2 | v1 | いいね | 本文（冒頭） |")
    lines.append("|------|-----|-----|--------|------------|")
    for i, s in enumerate(sorted_by_v2[:10], 1):
        text_preview = s["text"][:40].replace("|", "｜").replace("\n", " ")
        lines.append(f"| {i} | {s['v2']} | {s['v1']} | {s['likes']:,} | {text_preview} |")
    lines.append("")

    lines.append("### WORST10（v2スコア順）")
    lines.append("")
    lines.append("| 順位 | v2 | v1 | いいね | 本文（冒頭） |")
    lines.append("|------|-----|-----|--------|------------|")
    for i, s in enumerate(sorted_by_v2[-10:], 1):
        text_preview = s["text"][:40].replace("|", "｜").replace("\n", " ")
        lines.append(f"| {i} | {s['v2']} | {s['v1']} | {s['likes']:,} | {text_preview} |")
    lines.append("")

    # === セクション7: @Mr_botenのスコア ===
    lines.append("---")
    lines.append("")
    lines.append("## 7. @Mr_botenの投稿スコア（v1 vs v2）")
    lines.append("")

    if len(df_self) > 0:
        self_scores = []
        for _, row in df_self.iterrows():
            text = safe_get(row, "本文", "")
            likes = safe_get(row, "いいね数", 0)
            dt_str = safe_get(row, "投稿日時", "")
            v1 = calculate_buzz_score(text)
            v2 = calculate_buzz_score_v2(text, dt_str)
            self_scores.append({
                "text": text, "likes": likes,
                "v1": v1["total_score"], "v1_factors": v1["factors"],
                "v2": v2["total_score"], "v2_factors": v2["factors"],
            })

        avg_self_v1 = sum(s["v1"] for s in self_scores) / len(self_scores)
        avg_self_v2 = sum(s["v2"] for s in self_scores) / len(self_scores)
        avg_buzz_v1 = sum(s["v1"] for s in v2_scores) / len(v2_scores)
        avg_buzz_v2 = sum(s["v2"] for s in v2_scores) / len(v2_scores)

        lines.append(f"| | 自分の平均 | バズ投稿平均 | 差 |")
        lines.append(f"|---|----------|------------|-----|")
        lines.append(f"| v1スコア | {avg_self_v1:.1f} | {avg_buzz_v1:.1f} | {avg_self_v1 - avg_buzz_v1:+.1f} |")
        lines.append(f"| **v2スコア** | **{avg_self_v2:.1f}** | **{avg_buzz_v2:.1f}** | **{avg_self_v2 - avg_buzz_v2:+.1f}** |")
        lines.append("")

        # 要素別比較
        lines.append("**v2要素別 自分 vs バズ投稿:**")
        lines.append("")
        lines.append("| 要素 | 自分の平均 | バズ平均 | 差 | 改善アドバイス |")
        lines.append("|------|----------|--------|-----|-------------|")
        self_factor_avg = defaultdict(list)
        buzz_factor_avg = defaultdict(list)
        for s in self_scores:
            for k, v in s["v2_factors"].items():
                if not k.startswith("_"):
                    self_factor_avg[k].append(v)
        for s in v2_scores:
            for k, v in s["v2_factors"].items():
                if not k.startswith("_"):
                    buzz_factor_avg[k].append(v)

        advice = {
            "冒頭パターン": "数字で始める（「3つの理由」「月5万円」等）",
            "文字数": "170字以内を目指す。短く強いメッセージ",
            "カテゴリ": "体験談・問題提起が強い",
            "具体的数字": "金額・期間・個数を具体的に入れる",
            "簡潔さ": "改行は3回以内。ワンメッセージに絞る",
            "絵文字": "絵文字は使わないか最小限に",
            "ストーリー性": "before/after構成を意識",
        }

        for factor in max_points:
            s_vals = self_factor_avg.get(factor, [0])
            b_vals = buzz_factor_avg.get(factor, [0])
            s_avg = sum(s_vals) / len(s_vals)
            b_avg = sum(b_vals) / len(b_vals)
            diff = s_avg - b_avg
            adv = advice.get(factor, "")
            lines.append(f"| {factor} | {s_avg:.1f} | {b_avg:.1f} | {diff:+.1f} | {adv} |")
        lines.append("")

        # 自分のTOP5
        self_scores.sort(key=lambda x: x["v2"], reverse=True)
        lines.append("**自分のv2スコア TOP5:**")
        lines.append("")
        lines.append("| 順位 | v2 | v1 | いいね | 要因 | 本文（冒頭） |")
        lines.append("|------|-----|-----|--------|------|------------|")
        for i, s in enumerate(self_scores[:5], 1):
            factors_str = " / ".join(f"{k}:{v}" for k, v in s["v2_factors"].items() if not k.startswith("_") and v > 0)
            text_preview = s["text"][:30].replace("|", "｜").replace("\n", " ")
            lines.append(f"| {i} | {s['v2']} | {s['v1']} | {s['likes']:,} | {factors_str} | {text_preview} |")
        lines.append("")

        # 改善が最も効果的な要素
        lines.append("**最も改善余地が大きい要素:**")
        lines.append("")
        improvements = []
        for factor, max_pt in max_points.items():
            s_vals = self_factor_avg.get(factor, [0])
            s_avg = sum(s_vals) / len(s_vals)
            gap = max_pt - s_avg
            fill = s_avg / max_pt * 100
            if fill < 70:
                improvements.append((factor, s_avg, max_pt, gap, fill))
        improvements.sort(key=lambda x: x[3], reverse=True)
        for factor, avg_val, max_pt, gap, fill in improvements:
            lines.append(f"- **{factor}**: {avg_val:.1f}/{max_pt}点（充足率{fill:.0f}%）→ {advice.get(factor, '')}")
        lines.append("")
    else:
        lines.append("`output/TwExport_20260217_191942.csv` が見つからないため、自分の投稿スコアリングはスキップしました。")
        lines.append("")
        lines.append("> CSVファイルを配置して `python buzz_score_v2.py` を再実行すると、自分の投稿のv1/v2比較が表示されます。")
        lines.append("")

    # === セクション8: 残課題 ===
    lines.append("---")
    lines.append("")
    lines.append("## 8. v2でも捉えきれない要因と今後の改善案")
    lines.append("")
    lines.append("v2はテキスト特徴量のみでスコアリングしているため、以下の要因は未反映:")
    lines.append("")
    lines.append("| 要因 | 影響度（推定） | 対応方法 |")
    lines.append("|------|-------------|---------|")
    lines.append("| 投稿者のフォロワー数 | 極めて高い | フォロワー数データを再取得してv3に組み込む |")
    lines.append("| 投稿タイミング | 中程度 | 時間帯データは取得済み、ただし今回のデータでは18-21時が低い（n=5で信頼性低） |")
    lines.append("| トレンド・話題性 | 高い | 「Claude Code」「Antigravity」等のバズワードは時期依存 |")
    lines.append("| リプライ・引用による拡散 | 中程度 | インフルエンサーのリプライやQTによるブースト効果 |")
    lines.append("| アカウントの権威性 | 高い | フォロワー数だけでなく、過去のバズ実績も影響 |")
    lines.append("")
    lines.append("**次のステップ:**")
    lines.append("1. `buzz_analyzer.py` でフォロワー数を正しく取得して再スクレイピング")
    lines.append("2. フォロワー数を組み込んだv3スコアを作成")
    lines.append("3. 1-2週間後に自分の投稿の実績データで効果検証")
    lines.append("")

    return "\n".join(lines)


# === メイン ===

def main():
    print("=" * 60)
    print("バズ予測スコアv2 改善分析")
    print("=" * 60)

    if not os.path.exists(BUZZ_FILE):
        print(f"エラー: {BUZZ_FILE} が見つかりません")
        return

    df_raw = load_excel(BUZZ_FILE)
    if df_raw is None:
        return

    df_buzz, original_count, excluded_count = filter_data(df_raw)

    if os.path.exists(SELF_FILE):
        df_self = load_self_posts(SELF_FILE)
    else:
        print(f"注意: {SELF_FILE} が見つかりません。自分の投稿スコアリングはスキップします。")
        df_self = pd.DataFrame(columns=["本文", "いいね数", "リポスト数", "リプライ数", "フォロワー数"])

    print(f"\nバズ投稿: {len(df_buzz)}件 / 自分の投稿: {len(df_self)}件")
    print()

    # v1/v2の相関を計算して表示
    v1_data = []
    v2_data = []
    for _, row in df_buzz.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        dt_str = safe_get(row, "投稿日時", "")
        v1 = calculate_buzz_score(text)
        v2 = calculate_buzz_score_v2(text, dt_str)
        v1_data.append({"likes": likes, "score": v1["total_score"]})
        v2_data.append({"likes": likes, "score": v2["total_score"]})

    df_v1 = pd.DataFrame(v1_data)
    df_v2 = pd.DataFrame(v2_data)
    corr_v1 = float(df_v1["likes"].corr(df_v1["score"]))
    corr_v2 = float(df_v2["likes"].corr(df_v2["score"]))
    print(f"v1相関係数: {corr_v1:+.3f}")
    print(f"v2相関係数: {corr_v2:+.3f}")
    print(f"改善幅: {corr_v2 - corr_v1:+.3f}")

    # レポート生成
    print("\nレポート生成中...")
    report = generate_report(df_buzz, df_self)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nレポート保存完了: {OUTPUT_FILE}")
    print(f"文字数: {len(report):,}文字")


if __name__ == "__main__":
    main()
