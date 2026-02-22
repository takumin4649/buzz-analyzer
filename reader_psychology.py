"""読者心理分析エンジン

バズ投稿がなぜ刺さったのか、読者の視点で心理を言語化する。
各投稿に対して以下を分析：
1. なぜいいねしたか（共感・感嘆・応援）
2. なぜRTしたか（権威共有・自己表現・有益情報拡散）
3. なぜリプしたか（議論参加・体験共有・承認欲求）
4. なぜブクマしたか（保存価値・ノウハウ備忘録）
5. なぜフォローしたか（継続的価値・人物への興味）
"""

import os
import re
from collections import defaultdict
from datetime import datetime

import pandas as pd

from analyze_posts import (
    classify_category,
    classify_opening_pattern,
    has_story,
    safe_get,
)
from algorithm_analysis import (
    analyze_tone,
    calculate_algorithm_score,
    detect_external_links,
    detect_thread_structure,
)


# ========================================
# 読者心理トリガーの定義
# ========================================

# いいねの心理パターン
LIKE_TRIGGERS = {
    "共感（あるある）": {
        "patterns": [r'わかる|あるある|そうそう|私も|僕も|同じ|みんな'],
        "psychology": "「自分も同じだ」と感じて思わず押す。最も本能的な反応。",
    },
    "自己開示への応援": {
        "patterns": [r'正直|実は|ぶっちゃけ|告白|恥ずかしい|ド素人|初めて'],
        "psychology": "弱さを見せた人を応援したくなる。「正直に言ってくれてありがとう」の気持ち。",
    },
    "感嘆・尊敬": {
        "patterns": [r'達成|月\d+万|年収|成功|成果|実績|稼いだ|稼げた'],
        "psychology": "すごいと思った時の「拍手」としてのいいね。憧れの感情。",
    },
    "感情的衝動": {
        "patterns": [r'マジで|ガチで|ヤバい|やばい|すごい|神|最強|衝撃|驚'],
        "psychology": "強い感情が動いた瞬間に反射的に押す。考える前に手が動く。",
    },
    "希望・可能性": {
        "patterns": [r'誰でも|初心者でも|ゼロから|スキル不要|簡単|すぐできる'],
        "psychology": "「自分にもできるかも」という希望。いいね＝「信じたい」の表明。",
    },
}

# RTの心理パターン
RT_TRIGGERS = {
    "有益情報の拡散（利他）": {
        "patterns": [r'方法|やり方|コツ|手順|ステップ|\d+選|まとめ|テンプレ'],
        "psychology": "「フォロワーにも教えてあげたい」という利他心。RTした自分も有益な人に見える。",
    },
    "権威の借用": {
        "patterns": [r'\d+万円|月収|年収|\d+万フォロワー|実績|プロ|専門家'],
        "psychology": "すごい人の発言をRTすることで「自分もこの情報をキャッチできる人間」と見せたい。",
    },
    "自己表現・意見代弁": {
        "patterns": [r'これ|ほんこれ|これな|言いたかったこと|全人類|みんなに'],
        "psychology": "「自分の意見を代わりに言ってくれた」→ RTで同意を表明。自分の立場表明。",
    },
    "話題性・トレンド参加": {
        "patterns": [r'ChatGPT|Claude|AI|GPT|Grok|2026|最新|速報|発表'],
        "psychology": "トレンドをいち早くキャッチしてる自分を見せたい。情報感度の高さをアピール。",
    },
}

# リプライの心理パターン
REPLY_TRIGGERS = {
    "意見表明・議論参加": {
        "patterns": [r'[\?？]|どう思|教えて|みんなは|皆さんは|意見'],
        "psychology": "問いかけられると「自分の考えを述べたい」欲求が発動。参加感がほしい。",
    },
    "体験共有": {
        "patterns": [r'同じ人|経験ある|やったことある|私も|僕も|わかる人'],
        "psychology": "「自分もそうだった」を語りたい。共感を通じた自己開示。",
    },
    "ツッコミ・補足欲求": {
        "patterns": [r'かもしれない|知らんけど|異論は認める|怒られそう|多分'],
        "psychology": "あえて隙を見せることで「いや、それは…」と突っ込みたくなる。参加のハードルが下がる。",
    },
    "感謝・報告": {
        "patterns": [r'試してみて|やってみて|おすすめ|紹介|使ってみた'],
        "psychology": "「やってみました！」「ありがとう！」と報告したくなる。",
    },
    "対立構造の参加": {
        "patterns": [r'vs|VS|それとも|どっち|AかBか|賛否|論争'],
        "psychology": "二項対立を見ると「自分はこっち派」と宣言したくなる。",
    },
}

# ブックマークの心理パターン
BOOKMARK_TRIGGERS = {
    "ノウハウ備忘録": {
        "patterns": [r'方法|やり方|手順|ステップ|\d+選|チェックリスト|テンプレ|フレームワーク'],
        "psychology": "「あとで使う」「忘れたくない」。実用的な情報は保存価値が高い。",
    },
    "再読価値": {
        "patterns": [r'保存|ブクマ|ブックマーク|メモ|後で|見返'],
        "psychology": "保存を促されると「確かに保存しておこう」と行動する。",
    },
    "データ・数字の参照": {
        "patterns": [r'\d+万円|\d+%|\d+倍|\d+つの|統計|データ|調査'],
        "psychology": "具体的な数字は後で引用したい。自分の発言の裏付けにも使える。",
    },
}

# フォローの心理パターン
FOLLOW_TRIGGERS = {
    "継続的価値の期待": {
        "patterns": [r'毎日|毎週|シリーズ|第\d+|続き|次回|定期的'],
        "psychology": "「この人の投稿を見逃したくない」。継続的に有益な情報をくれそう。",
    },
    "人物への興味": {
        "patterns": [r'正直|実は|ぶっちゃけ|告白|(僕|私|俺).{0,10}(実は|正直)'],
        "psychology": "「この人、もっと知りたい」。自己開示がうまい人はフォローされやすい。",
    },
    "専門性の認知": {
        "patterns": [r'\d+年目|\d+月目|専門|プロ|経歴|実績|\d+万フォロワー'],
        "psychology": "「この人はこの分野の専門家だ」と認知。権威性がフォローに直結。",
    },
    "秘匿情報の続き": {
        "patterns": [r'秘密|内緒|ここだけ|限定|非公開|プロフ|固ツイ'],
        "psychology": "「この人の他の投稿にもっと情報があるかも」→プロフ→フォロー。",
    },
}


# ========================================
# 読者心理分析メイン
# ========================================

def analyze_reader_psychology(text, likes=0, retweets=0, replies=0):
    """1つの投稿に対して読者心理を分析し言語化する"""

    result = {
        "text": text,
        "like_triggers": [],
        "rt_triggers": [],
        "reply_triggers": [],
        "bookmark_triggers": [],
        "follow_triggers": [],
        "primary_emotion": "",
        "one_line_why": "",
    }

    # いいねの心理
    for trigger_name, cfg in LIKE_TRIGGERS.items():
        for pat in cfg["patterns"]:
            if re.search(pat, text, re.IGNORECASE):
                result["like_triggers"].append({
                    "trigger": trigger_name,
                    "psychology": cfg["psychology"],
                })
                break

    # RTの心理
    for trigger_name, cfg in RT_TRIGGERS.items():
        for pat in cfg["patterns"]:
            if re.search(pat, text, re.IGNORECASE):
                result["rt_triggers"].append({
                    "trigger": trigger_name,
                    "psychology": cfg["psychology"],
                })
                break

    # リプライの心理
    for trigger_name, cfg in REPLY_TRIGGERS.items():
        for pat in cfg["patterns"]:
            if re.search(pat, text, re.IGNORECASE):
                result["reply_triggers"].append({
                    "trigger": trigger_name,
                    "psychology": cfg["psychology"],
                })
                break

    # ブックマークの心理
    for trigger_name, cfg in BOOKMARK_TRIGGERS.items():
        for pat in cfg["patterns"]:
            if re.search(pat, text, re.IGNORECASE):
                result["bookmark_triggers"].append({
                    "trigger": trigger_name,
                    "psychology": cfg["psychology"],
                })
                break

    # フォローの心理
    for trigger_name, cfg in FOLLOW_TRIGGERS.items():
        for pat in cfg["patterns"]:
            if re.search(pat, text, re.IGNORECASE):
                result["follow_triggers"].append({
                    "trigger": trigger_name,
                    "psychology": cfg["psychology"],
                })
                break

    # 主要感情の判定
    tone = analyze_tone(text)
    result["tone"] = tone["overall"]

    # 一行サマリー生成
    result["one_line_why"] = _generate_one_line_why(result, text, likes, retweets, replies)
    result["primary_emotion"] = _detect_primary_emotion(text)

    return result


def _detect_primary_emotion(text):
    """読者が最初に感じる感情を1つ判定"""
    emotion_checks = [
        ("驚き", r'マジで|ガチで|ヤバい|やばい|衝撃|信じられない|驚'),
        ("共感", r'わかる|あるある|そうそう|私も|僕も|同じ経験'),
        ("希望", r'誰でも|初心者でも|ゼロから|稼げ|始められ'),
        ("危機感", r'危険|注意|知らないと損|やばい|怖い|リスク'),
        ("応援", r'正直|実は|告白|ド素人|恥ずかしい|初めて'),
        ("憧れ", r'月\d+万|達成|成功|実績|年収'),
        ("好奇心", r'秘密|ここだけ|内緒|実は.*意外|知られてない'),
        ("参加欲", r'[\?？]|どう思|みんなは|教えて'),
    ]
    for emotion, pattern in emotion_checks:
        if re.search(pattern, text, re.IGNORECASE):
            return emotion
    return "関心"


def _generate_one_line_why(result, text, likes, retweets, replies):
    """なぜバズったかを一行で言語化"""
    parts = []

    # いいねの理由
    if result["like_triggers"]:
        top = result["like_triggers"][0]
        parts.append(f"いいね理由: {top['trigger']}")

    # RTの理由
    if result["rt_triggers"]:
        top = result["rt_triggers"][0]
        parts.append(f"RT理由: {top['trigger']}")

    # リプの理由
    if result["reply_triggers"]:
        top = result["reply_triggers"][0]
        parts.append(f"リプ理由: {top['trigger']}")

    if not parts:
        # トリガーがない場合は構造から推定
        category = classify_category(text)
        opening = classify_opening_pattern(text.split("\n")[0] if text else "")
        parts.append(f"構造: {category}×{opening}")

    return " / ".join(parts)


# ========================================
# 全投稿の読者心理レポート
# ========================================

def generate_psychology_report(df):
    """全バズ投稿の読者心理分析レポートを生成"""
    lines = []
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    lines.append("# バズ投稿 読者心理分析レポート")
    lines.append("")
    lines.append(f"**分析日時:** {now}")
    lines.append(f"**分析対象:** {len(df)}件")
    lines.append("")
    lines.append("> 各投稿がなぜバズったのか、読者の心理を言語化したレポート。")
    lines.append("> 「この投稿を見た読者は何を感じ、なぜいいね/RT/リプ/ブクマ/フォローしたか」を分析。")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 全投稿を分析
    all_results = []
    for _, row in df.iterrows():
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        retweets = safe_get(row, "リポスト数", 0)
        replies = safe_get(row, "リプライ数", 0)
        user = safe_get(row, "ユーザー名", "")

        if likes <= 0 or not text.strip():
            continue

        result = analyze_reader_psychology(text, likes, retweets, replies)
        result["likes"] = likes
        result["retweets"] = retweets
        result["replies"] = replies
        result["user"] = user
        all_results.append(result)

    all_results.sort(key=lambda x: x["likes"], reverse=True)

    # ========================================
    # セクション1: 読者心理パターンの統計
    # ========================================
    lines.append("## 1. 読者心理パターン統計")
    lines.append("")

    # いいねトリガー集計
    like_trigger_counts = defaultdict(int)
    like_trigger_likes = defaultdict(list)
    for r in all_results:
        for t in r["like_triggers"]:
            like_trigger_counts[t["trigger"]] += 1
            like_trigger_likes[t["trigger"]].append(r["likes"])

    lines.append("### いいねの心理（なぜいいねを押したか）")
    lines.append("")
    lines.append("| 心理トリガー | 出現数 | 平均いいね | 読者の気持ち |")
    lines.append("|------------|--------|----------|------------|")
    for trigger, count in sorted(like_trigger_counts.items(), key=lambda x: x[1], reverse=True):
        avg = sum(like_trigger_likes[trigger]) / len(like_trigger_likes[trigger])
        psych = LIKE_TRIGGERS[trigger]["psychology"][:30]
        lines.append(f"| {trigger} | {count} | {avg:.0f} | {psych}… |")
    lines.append("")

    # RTトリガー集計
    rt_trigger_counts = defaultdict(int)
    rt_trigger_likes = defaultdict(list)
    for r in all_results:
        for t in r["rt_triggers"]:
            rt_trigger_counts[t["trigger"]] += 1
            rt_trigger_likes[t["trigger"]].append(r["likes"])

    lines.append("### RTの心理（なぜRTしたか）")
    lines.append("")
    lines.append("| 心理トリガー | 出現数 | 平均いいね | 読者の気持ち |")
    lines.append("|------------|--------|----------|------------|")
    for trigger, count in sorted(rt_trigger_counts.items(), key=lambda x: x[1], reverse=True):
        avg = sum(rt_trigger_likes[trigger]) / len(rt_trigger_likes[trigger])
        psych = RT_TRIGGERS[trigger]["psychology"][:30]
        lines.append(f"| {trigger} | {count} | {avg:.0f} | {psych}… |")
    lines.append("")

    # リプトリガー集計
    reply_trigger_counts = defaultdict(int)
    reply_trigger_likes = defaultdict(list)
    for r in all_results:
        for t in r["reply_triggers"]:
            reply_trigger_counts[t["trigger"]] += 1
            reply_trigger_likes[t["trigger"]].append(r["likes"])

    lines.append("### リプの心理（なぜリプしたか）")
    lines.append("")
    lines.append("| 心理トリガー | 出現数 | 平均いいね | 読者の気持ち |")
    lines.append("|------------|--------|----------|------------|")
    for trigger, count in sorted(reply_trigger_counts.items(), key=lambda x: x[1], reverse=True):
        avg = sum(reply_trigger_likes[trigger]) / len(reply_trigger_likes[trigger])
        psych = REPLY_TRIGGERS[trigger]["psychology"][:30]
        lines.append(f"| {trigger} | {count} | {avg:.0f} | {psych}… |")
    lines.append("")

    # 感情分布
    emotion_counts = defaultdict(int)
    emotion_likes = defaultdict(list)
    for r in all_results:
        emotion_counts[r["primary_emotion"]] += 1
        emotion_likes[r["primary_emotion"]].append(r["likes"])

    lines.append("### 読者の第一感情（投稿を見た瞬間の感情）")
    lines.append("")
    lines.append("| 感情 | 出現数 | 平均いいね | 解説 |")
    lines.append("|------|--------|----------|------|")
    emotion_desc = {
        "驚き": "「えっ？」で止まる→読む→反応",
        "共感": "「わかる！」で即いいね",
        "希望": "「自分もできるかも」で保存・フォロー",
        "危機感": "「やばい知らなかった」で保存・RT",
        "応援": "「正直に言ってくれて…」で応援いいね",
        "憧れ": "「すごい…」で尊敬のいいね・フォロー",
        "好奇心": "「もっと知りたい」でプロフクリック",
        "参加欲": "「自分も言いたい」でリプライ",
        "関心": "興味は持ったが強い感情は動かず",
    }
    for emotion, count in sorted(emotion_counts.items(), key=lambda x: x[1], reverse=True):
        avg = sum(emotion_likes[emotion]) / len(emotion_likes[emotion])
        desc = emotion_desc.get(emotion, "")
        lines.append(f"| {emotion} | {count} | {avg:.0f} | {desc} |")
    lines.append("")

    # ========================================
    # セクション2: TOP20 個別心理分析
    # ========================================
    lines.append("---")
    lines.append("")
    lines.append("## 2. バズ投稿 個別心理分析 TOP20")
    lines.append("")
    lines.append("> いいね順に上位20件の投稿を、読者心理の観点から分析")
    lines.append("")

    for i, r in enumerate(all_results[:20], 1):
        text_preview = r["text"].replace("\n", " ")[:80]
        lines.append(f"### #{i} @{r['user']} （いいね{r['likes']:,} / RT{r['retweets']:,} / リプ{r['replies']:,}）")
        lines.append("")
        lines.append(f"> {text_preview}{'…' if len(r['text']) > 80 else ''}")
        lines.append("")

        # 第一感情
        lines.append(f"**読者の第一感情:** {r['primary_emotion']}")
        lines.append("")

        # なぜいいねしたか
        if r["like_triggers"]:
            lines.append("**なぜいいねしたか:**")
            for t in r["like_triggers"]:
                lines.append(f"- {t['trigger']} → {t['psychology']}")
        else:
            lines.append("**なぜいいねしたか:** 明確なトリガーなし（投稿者の影響力・タイミングが要因）")
        lines.append("")

        # なぜRTしたか
        if r["rt_triggers"]:
            lines.append("**なぜRTしたか:**")
            for t in r["rt_triggers"]:
                lines.append(f"- {t['trigger']} → {t['psychology']}")
        lines.append("")

        # なぜリプしたか
        if r["reply_triggers"]:
            lines.append("**なぜリプしたか:**")
            for t in r["reply_triggers"]:
                lines.append(f"- {t['trigger']} → {t['psychology']}")
        lines.append("")

        # ブクマ・フォロー要因
        if r["bookmark_triggers"]:
            bm_names = [t["trigger"] for t in r["bookmark_triggers"]]
            lines.append(f"**ブックマーク要因:** {', '.join(bm_names)}")
        if r["follow_triggers"]:
            fl_names = [t["trigger"] for t in r["follow_triggers"]]
            lines.append(f"**フォロー要因:** {', '.join(fl_names)}")
        lines.append("")

        # 一行サマリー
        lines.append(f"**一行サマリー:** {r['one_line_why']}")
        lines.append("")

        lines.append("---")
        lines.append("")

    # ========================================
    # セクション3: バズの方程式（心理面）
    # ========================================
    lines.append("## 3. 読者心理に基づくバズの方程式")
    lines.append("")

    # 最も効果的なトリガーの組み合わせを分析
    combo_data = defaultdict(list)
    for r in all_results:
        like_names = tuple(sorted(t["trigger"] for t in r["like_triggers"]))
        if like_names:
            combo_data[like_names].append(r["likes"])

    lines.append("### 最強のいいねトリガー組み合わせ")
    lines.append("")
    lines.append("| トリガーの組み合わせ | 件数 | 平均いいね |")
    lines.append("|-------------------|------|----------|")
    for combo, likes_list in sorted(combo_data.items(), key=lambda x: sum(x[1])/len(x[1]) if x[1] else 0, reverse=True)[:10]:
        avg = sum(likes_list) / len(likes_list)
        combo_str = " × ".join(combo)
        lines.append(f"| {combo_str} | {len(likes_list)} | {avg:.0f} |")
    lines.append("")

    lines.append("### 投稿設計に使える心理法則")
    lines.append("")
    lines.append("1. **共感 → いいね**: 「あるある」「わかる」を引き出す体験を書く")
    lines.append("2. **自己開示 → 応援いいね + フォロー**: 弱さを見せると「この人もっと知りたい」になる")
    lines.append("3. **有益情報 → RT + ブクマ**: 箇条書き・ステップ・数字でまとめると保存&拡散される")
    lines.append("4. **問いかけ → リプライ**: 疑問で終わると「自分も言いたい」が発動する")
    lines.append("5. **対立構造 → 議論リプ**: 「AとB、どっち？」で参加欲求を刺激")
    lines.append("6. **驚き → 即反応 + RT**: 冒頭で「えっ？」と思わせたら勝ち")
    lines.append("7. **秘匿感 → プロフクリック → フォロー**: 「ここだけの話」はプロフまで見に行く")
    lines.append("")

    # 拓巳向けアドバイス
    lines.append("### 拓巳型バズの心理メカニズム")
    lines.append("")
    lines.append("拓巳の強み「等身大の告白×具体的体験」は、読者の中で以下の心理連鎖を起こす：")
    lines.append("")
    lines.append("```")
    lines.append("自己開示を読む")
    lines.append("  → 「この人、正直だな」（信頼）")
    lines.append("  → 「自分も同じだった」（共感）")
    lines.append("  → いいね（応援 + 共感）")
    lines.append("  → 「この人の他の投稿も見たい」（好奇心）")
    lines.append("  → プロフクリック → フォロー")
    lines.append("```")
    lines.append("")
    lines.append("これが最も自然にフォローまで繋がるパターン。")
    lines.append("CTAで「フォローして」と言わなくても、**心理が自然にフォローに導く**。")
    lines.append("")

    return "\n".join(lines)


# ========================================
# メイン実行
# ========================================

def main():
    """読者心理分析を実行"""
    DB_FILE = "data/buzz_database.db"
    BUZZ_FILE = "output/buzz_posts_20260215.xlsx"
    OUTPUT_FILE = "output/reader_psychology_20260221.md"

    print("=" * 60)
    print("バズ投稿 読者心理分析")
    print("=" * 60)

    if os.path.exists(DB_FILE):
        from buzz_score_v2 import load_from_db
        print(f"データベースから読み込み: {DB_FILE}")
        df_raw = load_from_db(DB_FILE)
        self_accounts = {"mr_boten"}
        df = df_raw[~df_raw["ユーザー名"].str.lower().isin(self_accounts)]
        df = df[df["いいね数"] > 0].copy()
    elif os.path.exists(BUZZ_FILE):
        from analyze_posts import filter_data, load_excel
        print(f"Excelから読み込み: {BUZZ_FILE}")
        df_raw = load_excel(BUZZ_FILE)
        if df_raw is None:
            return
        df, _, _ = filter_data(df_raw)
    else:
        print("エラー: データファイルが見つかりません")
        return

    print(f"分析対象: {len(df)}件")
    print("\n読者心理を分析中...")

    report = generate_psychology_report(df)

    os.makedirs("output", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nレポート保存完了: {OUTPUT_FILE}")
    print(f"文字数: {len(report):,}文字")

    # サマリーをターミナルに表示
    print("\n" + "=" * 60)
    print("サマリー（TOP5の読者心理）")
    print("=" * 60)

    df_sorted = df.sort_values("いいね数", ascending=False)
    for i, (_, row) in enumerate(df_sorted.head(5).iterrows(), 1):
        text = safe_get(row, "本文", "")
        likes = safe_get(row, "いいね数", 0)
        result = analyze_reader_psychology(text, likes)
        print(f"\n#{i} いいね{likes:,}件")
        print(f"  本文: {text[:50]}...")
        print(f"  感情: {result['primary_emotion']}")
        print(f"  分析: {result['one_line_why']}")


if __name__ == "__main__":
    main()
