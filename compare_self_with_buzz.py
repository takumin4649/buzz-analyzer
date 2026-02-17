"""自分の投稿とバズ投稿の詳細比較分析スクリプト"""

import os
import re
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd
import numpy as np


def load_self_posts(csv_path):
    """CSVから自分の投稿を読み込む"""
    df = pd.read_csv(csv_path, encoding='utf-8')
    # カラム名を統一
    df = df.rename(columns={
        'テキスト': '本文',
        'いいね数': 'いいね数',
        'imp': 'インプレッション数',
        '投稿日時': '投稿日時',
        'リプライ数': 'リプライ数',
        'RT数': 'リポスト数'
    })
    print(f"自分の投稿: {len(df)}件")
    return df


def load_buzz_posts(xlsx_path):
    """Excelからバズ投稿を読み込む（フィルタリング済み）"""
    df = pd.read_excel(xlsx_path)
    print(f"バズ投稿: {len(df)}件")

    # 炎上系除外
    exclude_keywords = [
        "著作権", "版権", "海賊版", "収益化停止", "収益化が停止",
        "剥奪", "侵害", "インプレゾンビ"
    ]
    def should_exclude(text):
        for kw in exclude_keywords:
            if kw in str(text):
                return True
        return False
    df = df[~df["本文"].apply(should_exclude)].copy()

    # 同一ユーザー重複除去
    df = df.sort_values("いいね数", ascending=False)
    df = df.drop_duplicates(subset=["ユーザー名"], keep="first")
    print(f"バズ投稿（フィルタ後）: {len(df)}件")
    return df.reset_index(drop=True)


def classify_opening_pattern(text):
    """冒頭パターンを分類"""
    first_line = text.split("\n")[0].strip()

    if re.search(r"[\?？]", first_line):
        return "疑問・問いかけ型"
    elif re.search(r"[!！]{1,}", first_line) and len(first_line) < 30:
        return "インパクト短文型"
    elif re.search(r"\d+[選つ個万円%]", first_line):
        return "数字リスト型"
    elif re.search(r"(知らない|知らなかった|まだ|実は|ぶっちゃけ|正直|ガチで|マジで)", first_line):
        return "秘匿・衝撃事実型"
    elif re.search(r"(やめ|するな|ダメ|禁止|注意|危険|ヤバい|やばい)", first_line):
        return "警告・否定型"
    elif re.search(r"(方法|やり方|コツ|ステップ|手順|始め方|稼ぎ方|稼げる)", first_line):
        return "ノウハウ提示型"
    elif re.search(r"(これ|この|あの|あれ)", first_line) and len(first_line) < 30:
        return "指示語フック型"
    elif re.search(r"(僕|私|俺|自分|ワイ)", first_line):
        return "体験談・自己開示型"
    elif re.search(r"(おすすめ|最強|神|便利|無料|0円)", first_line):
        return "推薦・絶賛型"
    else:
        return "その他"


def classify_structure_pattern(text):
    """文章構成パターンを分類"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    has_url = bool(re.search(r"https?://", text))
    has_list = bool(re.search(r"^[・\-・▶▸✅☑✓◆■●①②③④⑤⑥⑦⑧⑨⑩\d+[\.\)）]]", text, re.MULTILINE))
    has_question = bool(re.search(r"[\?？]", lines[0] if lines else ""))
    has_cta = bool(re.search(r"(フォロー|いいね|リプ|RT|保存|リツイート|拡散|シェア|ブクマ|ブックマーク|プロフ|固ツイ|リンク|詳細|続き)", text))
    has_self_story = bool(re.search(r"(僕は|私は|俺は|自分は|ワイは|〜した|〜だった|〜してた|経験|体験)", text))

    if has_list and has_url:
        return "リスト型 → URL誘導"
    elif has_list and has_cta:
        return "リスト型 → CTA"
    elif has_list:
        return "リスト型（単独）"
    elif has_question and has_cta:
        return "問題提起 → 解決策 → CTA"
    elif has_question and has_url:
        return "問題提起 → 解決策 → URL"
    elif has_question:
        return "問題提起 → 回答"
    elif has_self_story and has_cta:
        return "体験談 → 教訓 → CTA"
    elif has_self_story and has_url:
        return "体験談 → URL誘導"
    elif has_self_story:
        return "体験談 → 教訓"
    elif has_url and has_cta:
        return "主張 → URL + CTA"
    elif has_url:
        return "主張 → URL誘導"
    elif has_cta:
        return "主張 → CTA"
    else:
        return "主張のみ（短文完結）"


def has_cta(text):
    """CTA（行動喚起）を含むかチェック"""
    return bool(re.search(
        r"(フォロー|いいね|リプ|RT|保存|リツイート|拡散|シェア|ブクマ|ブックマーク|プロフ|固ツイ|リンク|詳細|続き|DM|👇|↓|⬇)",
        text
    ))


def classify_emotion_trigger(text):
    """感情トリガーを分類（複数該当可能）"""
    triggers = []

    # 共感・親近感
    if re.search(r"(わかる|そう|そうそう|あるある|共感|同じ|僕も|私も|俺も)", text):
        triggers.append("共感・親近感")

    # 驚き・衝撃
    if re.search(r"(ヤバい|やばい|マジで|ガチで|すごい|凄い|衝撃|びっくり|ビックリ|えぐい|エグい|知らなかった)", text):
        triggers.append("驚き・衝撃")

    # 恐怖・不安
    if re.search(r"(危険|注意|ダメ|禁止|やめ|気をつけ|知らないと|損|失敗|後悔|怖い)", text):
        triggers.append("恐怖・不安")

    # 期待・ワクワク
    if re.search(r"(無料|0円|プレゼント|簡単|すぐ|今すぐ|稼げる|儲かる|最強|神|便利|おすすめ)", text):
        triggers.append("期待・ワクワク")

    # 好奇心
    if re.search(r"(知ってる|知らない|実は|本当は|意外|秘密|裏技|コツ|方法|やり方)", text):
        triggers.append("好奇心")

    # 怒り・不満
    if re.search(r"(ひどい|酷い|最悪|許せない|ムカつく|腹立つ|イライラ)", text):
        triggers.append("怒り・不満")

    return triggers if triggers else ["感情トリガーなし"]


def calculate_buzz_score(text, likes=0, rts=0, replies=0):
    """バズ予測スコアを計算（0-100点）"""
    score = 0

    # 1. 冒頭パターン（20点）
    opening_pattern = classify_opening_pattern(text)
    high_performing_patterns = ["疑問・問いかけ型", "秘匿・衝撃事実型", "警告・否定型", "ノウハウ提示型"]
    if opening_pattern in high_performing_patterns:
        score += 20
    elif opening_pattern != "その他":
        score += 10

    # 2. 文字数（15点）
    text_length = len(text)
    if 100 <= text_length <= 200:
        score += 15
    elif 80 <= text_length <= 250:
        score += 10
    elif text_length > 50:
        score += 5

    # 3. CTAあり（15点）
    if has_cta(text):
        score += 15

    # 4. 感情トリガー（20点）
    triggers = classify_emotion_trigger(text)
    trigger_count = len([t for t in triggers if t != "感情トリガーなし"])
    score += min(trigger_count * 7, 20)

    # 5. 構成パターン（15点）
    structure = classify_structure_pattern(text)
    high_performing_structures = ["リスト型 → CTA", "問題提起 → 解決策 → CTA", "体験談 → 教訓 → CTA"]
    if structure in high_performing_structures:
        score += 15
    elif "CTA" in structure or "URL" in structure:
        score += 10
    elif structure != "主張のみ（短文完結）":
        score += 5

    # 6. 絵文字使用（5点）
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # 顔文字
        "\U0001F300-\U0001F5FF"  # 記号・絵文字
        "\U0001F680-\U0001F6FF"  # 乗り物・場所
        "\U0001F1E0-\U0001F1FF"  # 旗
        "]+", flags=re.UNICODE
    )
    if emoji_pattern.search(text):
        score += 5

    # 7. 改行・見やすさ（10点）
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if 3 <= len(lines) <= 10:
        score += 10
    elif len(lines) >= 2:
        score += 5

    return min(score, 100)


def analyze_time_slots(df):
    """投稿時間帯別のインプレッション分析"""
    if '投稿日時' not in df.columns or 'インプレッション数' not in df.columns:
        return None

    def get_time_slot(dt_str):
        try:
            dt = pd.to_datetime(dt_str)
            hour = dt.hour
            if 5 <= hour < 9:
                return "早朝(5-9時)"
            elif 9 <= hour < 12:
                return "午前(9-12時)"
            elif 12 <= hour < 15:
                return "昼(12-15時)"
            elif 15 <= hour < 18:
                return "夕方(15-18時)"
            elif 18 <= hour < 21:
                return "夜(18-21時)"
            elif 21 <= hour < 24:
                return "深夜(21-24時)"
            else:
                return "深夜(0-5時)"
        except:
            return "不明"

    df['時間帯'] = df['投稿日時'].apply(get_time_slot)
    time_stats = df.groupby('時間帯').agg({
        'インプレッション数': ['mean', 'sum', 'count']
    }).round(0)

    return time_stats


def compare_distributions(self_df, buzz_df):
    """分布比較を実行"""
    results = {}

    # 1. 冒頭パターンの分布
    self_df['冒頭パターン'] = self_df['本文'].apply(lambda x: classify_opening_pattern(str(x)))
    buzz_df['冒頭パターン'] = buzz_df['本文'].apply(lambda x: classify_opening_pattern(str(x)))

    self_opening = self_df['冒頭パターン'].value_counts(normalize=True) * 100
    buzz_opening = buzz_df['冒頭パターン'].value_counts(normalize=True) * 100
    results['opening'] = (self_opening, buzz_opening)

    # 2. 文章構成の分布
    self_df['構成パターン'] = self_df['本文'].apply(lambda x: classify_structure_pattern(str(x)))
    buzz_df['構成パターン'] = buzz_df['本文'].apply(lambda x: classify_structure_pattern(str(x)))

    self_structure = self_df['構成パターン'].value_counts(normalize=True) * 100
    buzz_structure = buzz_df['構成パターン'].value_counts(normalize=True) * 100
    results['structure'] = (self_structure, buzz_structure)

    # 3. 文字数の比較
    self_df['文字数'] = self_df['本文'].apply(lambda x: len(str(x)))
    buzz_df['文字数'] = buzz_df['本文'].apply(lambda x: len(str(x)))
    results['text_length'] = (self_df['文字数'], buzz_df['文字数'])

    # 4. CTA使用率
    self_df['CTA有無'] = self_df['本文'].apply(lambda x: has_cta(str(x)))
    buzz_df['CTA有無'] = buzz_df['本文'].apply(lambda x: has_cta(str(x)))

    self_cta_rate = self_df['CTA有無'].sum() / len(self_df) * 100
    buzz_cta_rate = buzz_df['CTA有無'].sum() / len(buzz_df) * 100
    results['cta_rate'] = (self_cta_rate, buzz_cta_rate)

    # 5. 感情トリガーの分布
    self_df['感情トリガー'] = self_df['本文'].apply(lambda x: classify_emotion_trigger(str(x)))
    buzz_df['感情トリガー'] = buzz_df['本文'].apply(lambda x: classify_emotion_trigger(str(x)))

    # 感情トリガーを展開してカウント
    self_triggers = []
    for triggers in self_df['感情トリガー']:
        self_triggers.extend(triggers)
    buzz_triggers = []
    for triggers in buzz_df['感情トリガー']:
        buzz_triggers.extend(triggers)

    self_emotion = pd.Series(self_triggers).value_counts(normalize=True) * 100
    buzz_emotion = pd.Series(buzz_triggers).value_counts(normalize=True) * 100
    results['emotion'] = (self_emotion, buzz_emotion)

    # 6. バズ予測スコア
    self_df['バズスコア'] = self_df.apply(
        lambda row: calculate_buzz_score(
            str(row['本文']),
            row.get('いいね数', 0),
            row.get('リポスト数', 0),
            row.get('リプライ数', 0)
        ), axis=1
    )
    buzz_df['バズスコア'] = buzz_df.apply(
        lambda row: calculate_buzz_score(
            str(row['本文']),
            row.get('いいね数', 0),
            row.get('リポスト数', 0),
            row.get('リプライ数', 0)
        ), axis=1
    )
    results['buzz_score'] = (self_df['バズスコア'], buzz_df['バズスコア'])

    return results, self_df, buzz_df


def generate_comparison_report(self_df, buzz_df, results, output_path):
    """比較レポートを生成"""
    lines = []
    lines.append("# 自分の投稿 vs バズ投稿 詳細比較分析レポート")
    lines.append(f"\n**分析日**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**自分の投稿**: {len(self_df)}件（@Mr_boten）")
    lines.append(f"**バズ投稿**: {len(buzz_df)}件（フィルタリング済み）")
    lines.append("")

    # ===== 1. 冒頭パターンの分布比較 =====
    lines.append("---")
    lines.append("## 1. 冒頭パターンの分布比較")
    lines.append("")

    self_opening, buzz_opening = results['opening']
    all_patterns = sorted(set(self_opening.index) | set(buzz_opening.index))

    lines.append("| 冒頭パターン | 自分 | バズ投稿 | 差分 |")
    lines.append("|:---|---:|---:|---:|")
    for pattern in all_patterns:
        self_pct = self_opening.get(pattern, 0)
        buzz_pct = buzz_opening.get(pattern, 0)
        diff = self_pct - buzz_pct
        diff_str = f"+{diff:.1f}%" if diff > 0 else f"{diff:.1f}%"
        lines.append(f"| {pattern} | {self_pct:.1f}% | {buzz_pct:.1f}% | {diff_str} |")
    lines.append("")

    # 最も差がある パターン
    diffs = {p: self_opening.get(p, 0) - buzz_opening.get(p, 0) for p in all_patterns}
    most_over = max(diffs.items(), key=lambda x: x[1])
    most_under = min(diffs.items(), key=lambda x: x[1])

    lines.append(f"**📊 分析**: 自分は「{most_over[0]}」が{most_over[1]:.1f}%多く、「{most_under[0]}」が{abs(most_under[1]):.1f}%少ない")
    lines.append("")

    # ===== 2. 文章構成の型の分布比較 =====
    lines.append("---")
    lines.append("## 2. 文章構成の型の分布比較")
    lines.append("")

    self_structure, buzz_structure = results['structure']
    all_structures = sorted(set(self_structure.index) | set(buzz_structure.index))

    lines.append("| 構成パターン | 自分 | バズ投稿 | 差分 |")
    lines.append("|:---|---:|---:|---:|")
    for struct in all_structures:
        self_pct = self_structure.get(struct, 0)
        buzz_pct = buzz_structure.get(struct, 0)
        diff = self_pct - buzz_pct
        diff_str = f"+{diff:.1f}%" if diff > 0 else f"{diff:.1f}%"
        lines.append(f"| {struct} | {self_pct:.1f}% | {buzz_pct:.1f}% | {diff_str} |")
    lines.append("")

    # CTAを含む構成の割合
    self_cta_struct = sum(self_structure.get(s, 0) for s in self_structure.index if 'CTA' in s or 'URL' in s)
    buzz_cta_struct = sum(buzz_structure.get(s, 0) for s in buzz_structure.index if 'CTA' in s or 'URL' in s)
    lines.append(f"**📊 分析**: CTAまたはURL誘導を含む構成の割合 - 自分: {self_cta_struct:.1f}%、バズ投稿: {buzz_cta_struct:.1f}%")
    lines.append("")

    # ===== 3. 文字数の平均・分布比較 =====
    lines.append("---")
    lines.append("## 3. 文字数の平均・分布比較")
    lines.append("")

    self_length, buzz_length = results['text_length']

    lines.append("| 指標 | 自分 | バズ投稿 | 差分 |")
    lines.append("|:---|---:|---:|---:|")
    lines.append(f"| 平均文字数 | {self_length.mean():.0f}文字 | {buzz_length.mean():.0f}文字 | {self_length.mean() - buzz_length.mean():.0f}文字 |")
    lines.append(f"| 中央値 | {self_length.median():.0f}文字 | {buzz_length.median():.0f}文字 | {self_length.median() - buzz_length.median():.0f}文字 |")
    lines.append(f"| 最小 | {self_length.min():.0f}文字 | {buzz_length.min():.0f}文字 | - |")
    lines.append(f"| 最大 | {self_length.max():.0f}文字 | {buzz_length.max():.0f}文字 | - |")
    lines.append(f"| 標準偏差 | {self_length.std():.0f}文字 | {buzz_length.std():.0f}文字 | - |")
    lines.append("")

    # 文字数分布
    lines.append("### 文字数分布")
    lines.append("")
    bins = [0, 50, 100, 150, 200, 250, 300, 500, 1000]
    self_dist = pd.cut(self_length, bins=bins).value_counts(normalize=True).sort_index() * 100
    buzz_dist = pd.cut(buzz_length, bins=bins).value_counts(normalize=True).sort_index() * 100

    lines.append("| 文字数範囲 | 自分 | バズ投稿 |")
    lines.append("|:---|---:|---:|")
    for interval in self_dist.index:
        self_pct = self_dist.get(interval, 0)
        buzz_pct = buzz_dist.get(interval, 0)
        lines.append(f"| {interval} | {self_pct:.1f}% | {buzz_pct:.1f}% |")
    lines.append("")

    optimal_range = "100-200文字"
    self_optimal = sum(self_dist.iloc[2:4]) if len(self_dist) >= 4 else 0
    buzz_optimal = sum(buzz_dist.iloc[2:4]) if len(buzz_dist) >= 4 else 0
    lines.append(f"**📊 分析**: 最適文字数範囲（{optimal_range}）の割合 - 自分: {self_optimal:.1f}%、バズ投稿: {buzz_optimal:.1f}%")
    lines.append("")

    # ===== 4. CTA使用率の比較 =====
    lines.append("---")
    lines.append("## 4. CTA使用率の比較")
    lines.append("")

    self_cta_rate, buzz_cta_rate = results['cta_rate']

    lines.append("| 指標 | 自分 | バズ投稿 | 差分 |")
    lines.append("|:---|---:|---:|---:|")
    lines.append(f"| CTA使用率 | {self_cta_rate:.1f}% | {buzz_cta_rate:.1f}% | {self_cta_rate - buzz_cta_rate:.1f}% |")
    lines.append(f"| CTA有り | {self_df['CTA有無'].sum()}件 | {buzz_df['CTA有無'].sum()}件 | - |")
    lines.append(f"| CTA無し | {len(self_df) - self_df['CTA有無'].sum()}件 | {len(buzz_df) - buzz_df['CTA有無'].sum()}件 | - |")
    lines.append("")

    lines.append(f"**📊 分析**: バズ投稿の方がCTA使用率が{abs(buzz_cta_rate - self_cta_rate):.1f}%高い" if buzz_cta_rate > self_cta_rate else f"**📊 分析**: 自分の方がCTA使用率が{abs(self_cta_rate - buzz_cta_rate):.1f}%高い")
    lines.append("")

    # ===== 5. 感情トリガーの分布比較 =====
    lines.append("---")
    lines.append("## 5. 感情トリガーの分布比較")
    lines.append("")

    self_emotion, buzz_emotion = results['emotion']
    all_emotions = sorted(set(self_emotion.index) | set(buzz_emotion.index))

    lines.append("| 感情トリガー | 自分 | バズ投稿 | 差分 |")
    lines.append("|:---|---:|---:|---:|")
    for emotion in all_emotions:
        self_pct = self_emotion.get(emotion, 0)
        buzz_pct = buzz_emotion.get(emotion, 0)
        diff = self_pct - buzz_pct
        diff_str = f"+{diff:.1f}%" if diff > 0 else f"{diff:.1f}%"
        lines.append(f"| {emotion} | {self_pct:.1f}% | {buzz_pct:.1f}% | {diff_str} |")
    lines.append("")

    # 感情トリガーなしの割合
    self_no_trigger = self_emotion.get("感情トリガーなし", 0)
    buzz_no_trigger = buzz_emotion.get("感情トリガーなし", 0)
    lines.append(f"**📊 分析**: 感情トリガーなしの割合 - 自分: {self_no_trigger:.1f}%、バズ投稿: {buzz_no_trigger:.1f}%")
    lines.append("")

    # ===== 6. バズ予測スコアの平均・分布比較 =====
    lines.append("---")
    lines.append("## 6. バズ予測スコアの平均・分布比較")
    lines.append("")

    self_score, buzz_score = results['buzz_score']

    lines.append("| 指標 | 自分 | バズ投稿 | 差分 |")
    lines.append("|:---|---:|---:|---:|")
    lines.append(f"| 平均スコア | {self_score.mean():.1f}点 | {buzz_score.mean():.1f}点 | {self_score.mean() - buzz_score.mean():.1f}点 |")
    lines.append(f"| 中央値 | {self_score.median():.1f}点 | {buzz_score.median():.1f}点 | {self_score.median() - buzz_score.median():.1f}点 |")
    lines.append(f"| 最高スコア | {self_score.max():.1f}点 | {buzz_score.max():.1f}点 | - |")
    lines.append(f"| 最低スコア | {self_score.min():.1f}点 | {buzz_score.min():.1f}点 | - |")
    lines.append("")

    # スコア分布
    lines.append("### バズスコア分布")
    lines.append("")
    score_bins = [0, 30, 50, 70, 85, 100]
    score_labels = ['0-30点', '31-50点', '51-70点', '71-85点', '86-100点']
    self_score_dist = pd.cut(self_score, bins=score_bins, labels=score_labels).value_counts(normalize=True).sort_index() * 100
    buzz_score_dist = pd.cut(buzz_score, bins=score_bins, labels=score_labels).value_counts(normalize=True).sort_index() * 100

    lines.append("| スコア範囲 | 自分 | バズ投稿 |")
    lines.append("|:---|---:|---:|")
    for label in score_labels:
        self_pct = self_score_dist.get(label, 0)
        buzz_pct = buzz_score_dist.get(label, 0)
        lines.append(f"| {label} | {self_pct:.1f}% | {buzz_pct:.1f}% |")
    lines.append("")

    lines.append(f"**📊 分析**: バズ投稿の平均スコアが{abs(buzz_score.mean() - self_score.mean()):.1f}点高い" if buzz_score.mean() > self_score.mean() else f"**📊 分析**: 自分の平均スコアが{abs(self_score.mean() - buzz_score.mean()):.1f}点高い")
    lines.append("")

    # ===== 7. 自分に足りないものの具体的指摘 =====
    lines.append("---")
    lines.append("## 7. 🔍 自分に足りないもの（具体的指摘）")
    lines.append("")

    gaps = []

    # 冒頭パターン
    buzz_top_opening = buzz_opening.nlargest(3)
    for pattern in buzz_top_opening.index:
        self_pct = self_opening.get(pattern, 0)
        buzz_pct = buzz_opening.get(pattern, 0)
        if buzz_pct - self_pct > 10:
            gaps.append(f"**冒頭パターン「{pattern}」の使用が少ない**: バズ投稿は{buzz_pct:.1f}%使用しているが、自分は{self_pct:.1f}%のみ（差: {buzz_pct - self_pct:.1f}%）")

    # 構成パターン
    buzz_top_structure = buzz_structure.nlargest(3)
    for struct in buzz_top_structure.index:
        self_pct = self_structure.get(struct, 0)
        buzz_pct = buzz_structure.get(struct, 0)
        if buzz_pct - self_pct > 10:
            gaps.append(f"**構成パターン「{struct}」の使用が少ない**: バズ投稿は{buzz_pct:.1f}%使用しているが、自分は{self_pct:.1f}%のみ（差: {buzz_pct - self_pct:.1f}%）")

    # CTA使用率
    if buzz_cta_rate - self_cta_rate > 10:
        gaps.append(f"**CTA（行動喚起）の使用が少ない**: バズ投稿は{buzz_cta_rate:.1f}%使用しているが、自分は{self_cta_rate:.1f}%のみ（差: {buzz_cta_rate - self_cta_rate:.1f}%）")

    # 感情トリガー
    buzz_top_emotion = buzz_emotion.nlargest(3)
    for emotion in buzz_top_emotion.index:
        if emotion == "感情トリガーなし":
            continue
        self_pct = self_emotion.get(emotion, 0)
        buzz_pct = buzz_emotion.get(emotion, 0)
        if buzz_pct - self_pct > 10:
            gaps.append(f"**感情トリガー「{emotion}」の使用が少ない**: バズ投稿は{buzz_pct:.1f}%使用しているが、自分は{self_pct:.1f}%のみ（差: {buzz_pct - self_pct:.1f}%）")

    # 文字数
    if abs(self_length.mean() - buzz_length.mean()) > 30:
        if self_length.mean() > buzz_length.mean():
            gaps.append(f"**文章が長すぎる**: 自分の平均{self_length.mean():.0f}文字に対し、バズ投稿は平均{buzz_length.mean():.0f}文字（差: {self_length.mean() - buzz_length.mean():.0f}文字）")
        else:
            gaps.append(f"**文章が短すぎる**: 自分の平均{self_length.mean():.0f}文字に対し、バズ投稿は平均{buzz_length.mean():.0f}文字（差: {buzz_length.mean() - self_length.mean():.0f}文字）")

    # バズスコア
    if buzz_score.mean() - self_score.mean() > 5:
        gaps.append(f"**バズ予測スコアが低い**: 自分の平均{self_score.mean():.1f}点に対し、バズ投稿は平均{buzz_score.mean():.1f}点（差: {buzz_score.mean() - self_score.mean():.1f}点）")

    for i, gap in enumerate(gaps, 1):
        lines.append(f"{i}. {gap}")
    lines.append("")

    # ===== 8. インプレッション数といいね数の関係 =====
    lines.append("---")
    lines.append("## 8. 📊 インプレッション数といいね数の関係（@Mr_botenのみ）")
    lines.append("")

    if 'インプレッション数' in self_df.columns and 'いいね数' in self_df.columns:
        # インプ→いいね転換率
        self_df['転換率'] = (self_df['いいね数'] / self_df['インプレッション数'] * 100).fillna(0)
        avg_conversion = self_df['転換率'].mean()

        lines.append("| 指標 | 値 |")
        lines.append("|:---|---:|")
        lines.append(f"| 平均インプレッション数 | {self_df['インプレッション数'].mean():.0f} |")
        lines.append(f"| 平均いいね数 | {self_df['いいね数'].mean():.1f} |")
        lines.append(f"| 平均転換率（いいね/インプ） | {avg_conversion:.2f}% |")
        lines.append(f"| 最高転換率 | {self_df['転換率'].max():.2f}% |")
        lines.append(f"| 最低転換率 | {self_df['転換率'].min():.2f}% |")
        lines.append("")

        # 転換率TOP5の投稿
        lines.append("### 転換率TOP5の投稿")
        lines.append("")
        top_conversion = self_df.nlargest(5, '転換率')
        for idx, row in top_conversion.iterrows():
            text_preview = str(row['本文'])[:50].replace('\n', ' ')
            lines.append(f"- **{row['転換率']:.2f}%** (インプ: {row['インプレッション数']:.0f}, いいね: {row['いいね数']}) - 「{text_preview}...」")
        lines.append("")

        lines.append(f"**📊 分析**: 平均転換率は{avg_conversion:.2f}%。転換率を上げるには、インプレッションを獲得した人により「いいね」したくなる内容に改善する必要がある。")
        lines.append("")
    else:
        lines.append("（インプレッション数データが不足しているため分析不可）")
        lines.append("")

    # ===== 9. 投稿時間帯別のインプレッション数 =====
    lines.append("---")
    lines.append("## 9. ⏰ 投稿時間帯別のインプレッション数（@Mr_botenのみ）")
    lines.append("")

    time_stats = analyze_time_slots(self_df)
    if time_stats is not None:
        lines.append("| 時間帯 | 投稿数 | 合計インプ | 平均インプ |")
        lines.append("|:---|---:|---:|---:|")
        for time_slot in time_stats.index:
            count = int(time_stats.loc[time_slot, ('インプレッション数', 'count')])
            total = int(time_stats.loc[time_slot, ('インプレッション数', 'sum')])
            avg = int(time_stats.loc[time_slot, ('インプレッション数', 'mean')])
            lines.append(f"| {time_slot} | {count} | {total} | {avg} |")
        lines.append("")

        # 最もインプが高い時間帯
        best_time_idx = time_stats[('インプレッション数', 'mean')].idxmax()
        best_time_avg = int(time_stats.loc[best_time_idx, ('インプレッション数', 'mean')])
        lines.append(f"**📊 分析**: 最もインプレッションが高い時間帯は「{best_time_idx}」（平均{best_time_avg}インプ）")
        lines.append("")
    else:
        lines.append("（投稿日時またはインプレッション数データが不足しているため分析不可）")
        lines.append("")

    # ===== 10. 最もインプレッションが高かった投稿の特徴分析 =====
    lines.append("---")
    lines.append("## 10. 🏆 最もインプレッションが高かった投稿の特徴分析（@Mr_botenのみ）")
    lines.append("")

    if 'インプレッション数' in self_df.columns:
        top_imp_post = self_df.nlargest(1, 'インプレッション数').iloc[0]

        lines.append(f"### インプレッション数: {top_imp_post['インプレッション数']:.0f}")
        lines.append(f"- **いいね数**: {top_imp_post.get('いいね数', 'N/A')}")
        lines.append(f"- **リポスト数**: {top_imp_post.get('リポスト数', 'N/A')}")
        lines.append(f"- **リプライ数**: {top_imp_post.get('リプライ数', 'N/A')}")
        lines.append(f"- **投稿日時**: {top_imp_post.get('投稿日時', 'N/A')}")
        lines.append(f"- **文字数**: {top_imp_post['文字数']}文字")
        lines.append(f"- **冒頭パターン**: {top_imp_post['冒頭パターン']}")
        lines.append(f"- **構成パターン**: {top_imp_post['構成パターン']}")
        lines.append(f"- **CTA有無**: {'あり' if top_imp_post['CTA有無'] else 'なし'}")
        lines.append(f"- **感情トリガー**: {', '.join(top_imp_post['感情トリガー'])}")
        lines.append(f"- **バズスコア**: {top_imp_post['バズスコア']:.1f}点")
        if '転換率' in top_imp_post:
            lines.append(f"- **転換率**: {top_imp_post['転換率']:.2f}%")
        lines.append("")

        lines.append("#### 全文")
        lines.append("```")
        lines.append(str(top_imp_post['本文']))
        lines.append("```")
        lines.append("")

        lines.append("**📊 分析**: この投稿が最もインプレッションを獲得した理由を分析し、再現可能な要素を抽出する。")
        lines.append("")
    else:
        lines.append("（インプレッション数データが不足しているため分析不可）")
        lines.append("")

    # ===== 11. 拓巳がバズるために明日から変えるべきことTOP3 =====
    lines.append("---")
    lines.append("## 🚀 拓巳がバズるために明日から変えるべきこと TOP3")
    lines.append("")

    # ギャップと統計から優先順位付け
    recommendations = []

    # 1. CTA使用率
    if buzz_cta_rate - self_cta_rate > 10:
        impact = buzz_cta_rate - self_cta_rate
        recommendations.append({
            'title': 'CTA（行動喚起）を投稿に必ず入れる',
            'impact': impact,
            'detail': f"バズ投稿の{buzz_cta_rate:.0f}%がCTAを使用しているのに対し、自分は{self_cta_rate:.0f}%のみ。"
                     f"「いいね・RTお願いします」「プロフもチェック」などの行動喚起を投稿の最後に追加する。",
            'example': '例: 「参考になったらいいね＆RTお願いします🙏」「続きはプロフのリンクから👇」'
        })

    # 2. 冒頭パターン
    for pattern in buzz_opening.nlargest(2).index:
        self_pct = self_opening.get(pattern, 0)
        buzz_pct = buzz_opening.get(pattern, 0)
        if buzz_pct - self_pct > 15:
            impact = buzz_pct - self_pct
            recommendations.append({
                'title': f'冒頭を「{pattern}」に変える',
                'impact': impact,
                'detail': f"バズ投稿の{buzz_pct:.0f}%がこのパターンを使用（自分は{self_pct:.0f}%）。"
                         f"投稿の最初の1-2行を工夫して読者の興味を引く。",
                'example': get_opening_example(pattern)
            })

    # 3. 感情トリガー
    for emotion in buzz_emotion.nlargest(2).index:
        if emotion == "感情トリガーなし":
            continue
        self_pct = self_emotion.get(emotion, 0)
        buzz_pct = buzz_emotion.get(emotion, 0)
        if buzz_pct - self_pct > 15:
            impact = buzz_pct - self_pct
            recommendations.append({
                'title': f'感情トリガー「{emotion}」を意識的に使う',
                'impact': impact,
                'detail': f"バズ投稿の{buzz_pct:.0f}%がこのトリガーを使用（自分は{self_pct:.0f}%）。"
                         f"読者の{emotion}を刺激する言葉や表現を取り入れる。",
                'example': get_emotion_example(emotion)
            })

    # 4. 文字数
    if abs(self_length.mean() - buzz_length.mean()) > 50:
        impact = abs(self_length.mean() - buzz_length.mean()) / 10
        if self_length.mean() > buzz_length.mean():
            recommendations.append({
                'title': '文章を短く簡潔にまとめる',
                'impact': impact,
                'detail': f"自分の平均{self_length.mean():.0f}文字は長すぎる。バズ投稿の平均{buzz_length.mean():.0f}文字を目指す。"
                         f"最適な文字数は100-200文字程度。",
                'example': '例: 冗長な表現を削り、箇条書きやリスト形式で見やすくまとめる'
            })
        else:
            recommendations.append({
                'title': '文章をもう少し詳しく書く',
                'impact': impact,
                'detail': f"自分の平均{self_length.mean():.0f}文字は短すぎる。バズ投稿の平均{buzz_length.mean():.0f}文字を目指す。"
                         f"最適な文字数は100-200文字程度。",
                'example': '例: 理由や具体例を追加して、読者により多くの価値を提供する'
            })

    # 5. 構成パターン
    for struct in buzz_structure.nlargest(2).index:
        self_pct = self_structure.get(struct, 0)
        buzz_pct = buzz_structure.get(struct, 0)
        if buzz_pct - self_pct > 15:
            impact = buzz_pct - self_pct
            recommendations.append({
                'title': f'構成を「{struct}」にする',
                'impact': impact,
                'detail': f"バズ投稿の{buzz_pct:.0f}%がこの構成を使用（自分は{self_pct:.0f}%）。"
                         f"投稿全体の流れをこのパターンに沿って組み立てる。",
                'example': get_structure_example(struct)
            })

    # インパクト順にソート
    recommendations.sort(key=lambda x: x['impact'], reverse=True)

    # TOP3を表示
    for i, rec in enumerate(recommendations[:3], 1):
        lines.append(f"### {i}位: {rec['title']}")
        lines.append("")
        lines.append(f"**📌 優先度**: {'高' if rec['impact'] > 25 else '中' if rec['impact'] > 15 else '低'} （差分: {rec['impact']:.1f}%）")
        lines.append("")
        lines.append(f"**📝 詳細**: {rec['detail']}")
        lines.append("")
        lines.append(f"**💡 具体例**: {rec['example']}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ファイル出力
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n比較レポート出力完了: {output_path}")
    return output_path


def get_opening_example(pattern):
    """冒頭パターンの具体例を返す"""
    examples = {
        "疑問・問いかけ型": "例: 「なぜ9割の人はClaude Codeで挫折するのか？」「あなたはまだ手動でコード書いてるの？」",
        "秘匿・衝撃事実型": "例: 「マジで知らなかった。Claude Codeって○○もできるんだ...」「ガチでヤバい。これ知らない人損してるわ」",
        "警告・否定型": "例: 「これやめとけ。Claude Codeで絶対やってはいけない3つのこと」「注意！この使い方は危険です」",
        "ノウハウ提示型": "例: 「Claude Codeで月10万稼ぐ方法を教えます」「3ステップで自動化ツールを作る手順」",
        "数字リスト型": "例: 「Claude Code使い倒すための5つのコツ」「3日で作った副業ツールで5万円稼いだ話」",
        "指示語フック型": "例: 「これ、マジで全員やった方がいい」「この方法、もっと早く知りたかった」",
        "体験談・自己開示型": "例: 「僕がClaude Codeで人生変わった話」「ド素人の自分でも3日でツール作れた」",
        "推薦・絶賛型": "例: 「これ最強。Claude Codeの神機能見つけた」「無料でここまでできるとか、控えめに言って神」",
        "インパクト短文型": "例: 「ヤバすぎる！」「これエグい。」「マジか...」"
    }
    return examples.get(pattern, "（具体例なし）")


def get_emotion_example(emotion):
    """感情トリガーの具体例を返す"""
    examples = {
        "共感・親近感": "例: 「わかる、そうそう」「僕もそう思ってた」「あるあるだよね」",
        "驚き・衝撃": "例: 「マジでヤバい」「すごすぎる」「知らなかった」「これエグい」",
        "恐怖・不安": "例: 「これ知らないと損する」「やめとけ」「危険」「失敗する前に」",
        "期待・ワクワク": "例: 「無料でできる」「簡単に稼げる」「今すぐ試せる」「最強」",
        "好奇心": "例: 「実は」「意外と」「知ってた？」「裏技」「コツ」",
        "怒り・不満": "例: 「許せない」「ひどすぎる」「最悪」「ムカつく」"
    }
    return examples.get(emotion, "（具体例なし）")


def get_structure_example(struct):
    """構成パターンの具体例を返す"""
    examples = {
        "リスト型 → CTA": "例: 箇条書きでポイントを列挙 → 「詳しくはプロフから」",
        "問題提起 → 解決策 → CTA": "例: 「なぜ稼げないのか？」→ 理由と解決策 → 「フォローして最新情報チェック」",
        "体験談 → 教訓 → CTA": "例: 自分の体験を語る → 学んだこと → 「同じ失敗したくない人はRT」",
        "主張 → CTA": "例: 強い主張や意見 → 「共感したらいいね」",
        "リスト型 → URL誘導": "例: ノウハウを箇条書き → 「続きはこちら [URL]」",
        "問題提起 → 解決策 → URL": "例: 問題を投げかける → 解決策を示す → 「詳細記事はこちら」"
    }
    return examples.get(struct, "（具体例なし）")


if __name__ == "__main__":
    # ファイルパス
    self_csv = "output/TwExport_20260217_191942.csv"
    buzz_xlsx = "output/buzz_posts_20260215.xlsx"
    output_md = "output/self_comparison_20260217.md"

    # データ読み込み
    print("=== データ読み込み中 ===")
    self_df = load_self_posts(self_csv)
    buzz_df = load_buzz_posts(buzz_xlsx)

    # 比較分析実行
    print("\n=== 比較分析実行中 ===")
    results, self_df, buzz_df = compare_distributions(self_df, buzz_df)

    # レポート生成
    print("\n=== レポート生成中 ===")
    generate_comparison_report(self_df, buzz_df, results, output_md)

    print("\n=== 分析完了 ===")
