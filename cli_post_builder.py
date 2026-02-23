"""CLIポストビルダー（スマホからも使える版）

Streamlitなしで動く対話型ポスト生成ツール。
python cli_post_builder.py で起動。

使い方:
  python cli_post_builder.py              → メニュー表示
  python cli_post_builder.py build        → 新規ポスト作成
  python cli_post_builder.py improve      → 過去投稿を改善
  python cli_post_builder.py score "テキスト"  → スコア診断
  python cli_post_builder.py psych "テキスト"  → 読者心理分析
  python cli_post_builder.py compare      → 2つのポストを比較
"""

import argparse
import random
import re
import sys
import os

from buzz_score_v2 import calculate_buzz_score_v2
from algorithm_analysis import calculate_algorithm_score, analyze_tone
from reader_psychology import analyze_reader_psychology


# ========================================
# スコア診断
# ========================================

def diagnose_post(text):
    """投稿テキストのスコア診断を表示"""
    v2 = calculate_buzz_score_v2(text)
    algo = calculate_algorithm_score(text)
    char_len = len(text)

    print("\n" + "=" * 50)
    print("  投稿スコア診断")
    print("=" * 50)
    print(f"\n  v2スコア:   {v2['total_score']}点 / 100点")
    print(f"  Algoスコア: {algo['total_score']}点 / 100点")
    print(f"  文字数:     {char_len}字", end="")
    if 130 <= char_len <= 170:
        print(" (最適)")
    elif char_len < 130:
        print(f" (短い → あと{130 - char_len}字)")
    else:
        print(f" (長い → {char_len - 170}字削減)")

    # バズ要素チェック
    print("\n--- バズ要素チェック ---")
    checks = [
        ("秘匿感フレーズ", any(p in text for p in ["正直", "実は", "ド素人", "告白", "恥ずかしい", "ぶっちゃけ"])),
        ("具体的な数字", bool(re.search(r'\d+', text))),
        ("CTAなし", not any(p in text for p in ["フォロー", "いいね", "RT", "リツイート", "保存", "ブックマーク"])),
        ("文字数130-170字", 130 <= char_len <= 170),
        ("外部リンクなし", "http" not in text),
    ]
    passed = 0
    for label, ok in checks:
        icon = "OK" if ok else "NG"
        print(f"  [{icon}] {label}")
        if ok:
            passed += 1
    print(f"\n  結果: {passed}/{len(checks)} 通過")

    # v2要素別
    print("\n--- v2 要素別スコア ---")
    for k, v in v2["factors"].items():
        bar = "#" * min(v, 25)
        print(f"  {k:12s} {v:3d}点 {bar}")

    # Algo要素別
    print("\n--- Algo 要素別スコア ---")
    for k, v in algo["factors"].items():
        bar = "#" * max(0, min(v, 25))
        print(f"  {k:16s} {v:3d}点 {bar}")

    # アドバイス
    print("\n--- 改善アドバイス ---")
    if not checks[0][1]:
        print("  → 「正直」「実は」「ぶっちゃけ」などの自己開示フレーズを入れる")
    if not checks[1][1]:
        print("  → 具体的な数字を入れる（月〇万円、〇ヶ月、〇%など）")
    if not checks[2][1]:
        print("  → CTA（フォロー・いいね誘導）を削除（CTAなしの方がバズる）")
    if char_len < 130:
        print("  → 体験やエピソードを具体的に追加して130字以上にする")
    elif char_len > 170:
        print("  → 冗長な部分を削って170字以内に収める")
    if re.search(r'[\?？]', text):
        print("  ✓ 疑問形あり → リプライ誘発力が高い（良い）")
    else:
        print("  → 疑問形で終わるとリプライが増える（アルゴリズム重み27倍）")

    tone = analyze_tone(text)
    if tone["grok_friendly"]:
        print(f"  ✓ トーン「{tone['overall']}」→ Grokフレンドリー（良い）")
    else:
        print(f"  → トーン「{tone['overall']}」→ 建設的なトーンに変えると拡散されやすい")

    print(f"\n  投稿タイミング: 18〜21時が最適")
    print("=" * 50)

    return v2["total_score"], algo["total_score"]


# ========================================
# 読者心理分析（CLI版）
# ========================================

def show_psychology(text):
    """投稿テキストの読者心理分析を表示"""
    result = analyze_reader_psychology(text)

    print("\n" + "=" * 50)
    print("  読者心理分析")
    print("=" * 50)

    print(f"\n  読者の第一感情: {result['primary_emotion']}")
    print(f"  トーン: {result['tone']}")

    if result["like_triggers"]:
        print("\n  なぜいいねするか:")
        for t in result["like_triggers"]:
            print(f"    → {t['trigger']}: {t['psychology']}")

    if result["rt_triggers"]:
        print("\n  なぜRTするか:")
        for t in result["rt_triggers"]:
            print(f"    → {t['trigger']}: {t['psychology']}")

    if result["reply_triggers"]:
        print("\n  なぜリプするか:")
        for t in result["reply_triggers"]:
            print(f"    → {t['trigger']}: {t['psychology']}")

    if result["bookmark_triggers"]:
        print("\n  なぜブクマするか:")
        for t in result["bookmark_triggers"]:
            print(f"    → {t['trigger']}: {t['psychology']}")

    if result["follow_triggers"]:
        print("\n  なぜフォローするか:")
        for t in result["follow_triggers"]:
            print(f"    → {t['trigger']}: {t['psychology']}")

    print(f"\n  一行サマリー: {result['one_line_why']}")
    print("=" * 50)


# ========================================
# 対話型ポストビルダー
# ========================================

TEMPLATES = {
    "1": {
        "name": "拓巳型（自己開示×体験）",
        "desc": "「正直に言う」系の告白 → 体験 → 気づき → 余韻。CTAなし。",
        "prompts": [
            ("自己開示（失敗・弱点）", "disclosure"),
            ("具体的な体験（数字があると◎）", "experience"),
            ("気づき・学び", "insight"),
            ("締めの一文（空欄でもOK）", "ending"),
        ],
        "openings": ["正直に言う。", "実は、", "ぶっちゃけると、", "告白します。", "ここだけの話。"],
        "build": lambda fv, op: _build_takumi(fv, op),
    },
    "2": {
        "name": "問題提起×共感型",
        "desc": "読者の不安に共感 → 「でも実際は…」 → 解決策。",
        "prompts": [
            ("読者の不安・疑問", "fear"),
            ("実際にやった結果（数字を）", "result"),
            ("具体的にやったこと", "method"),
            ("締め（空欄でもOK）", "ending"),
        ],
        "openings": ["「", "正直、", "以前の自分も思ってた。", ""],
        "build": lambda fv, op: _build_empathy(fv, op),
    },
    "3": {
        "name": "Before→After型",
        "desc": "過去 → 現在の変化を数字で見せる。",
        "prompts": [
            ("いつ頃の話か", "before_time"),
            ("以前の状態（数字を入れる）", "before_state"),
            ("今の状態（数字を入れる）", "after_state"),
            ("変化のきっかけ", "method"),
            ("一言の気づき（空欄でもOK）", "insight"),
        ],
        "openings": [""],
        "build": lambda fv, op: _build_before_after(fv, op),
    },
    "4": {
        "name": "ノウハウ×箇条書き型",
        "desc": "「〇選」「〇つのコツ」形式。ブクマされやすい。",
        "prompts": [
            ("タイトル（〇選・〇つのコツ等）", "title"),
            ("ポイント①", "item1"),
            ("ポイント②", "item2"),
            ("ポイント③", "item3"),
            ("締め（空欄でもOK）", "ending"),
        ],
        "openings": [""],
        "build": lambda fv, op: _build_howto(fv, op),
    },
}


def _build_takumi(fv, opening):
    post = f"{opening}{fv['disclosure']}\n\n{fv['experience']}\n\nそれで気づいたのは、{fv['insight']}。"
    if fv.get("ending"):
        post += f"\n\n{fv['ending']}"
    return post


def _build_empathy(fv, opening):
    post = f"{opening}{fv['fear']}。\n\nでも実際やってみたら\n{fv['result']}。\n\n{fv['method']}"
    if fv.get("ending"):
        post += f"\n\n{fv['ending']}"
    return post


def _build_before_after(fv, opening):
    post = f"{fv['before_time']}: {fv['before_state']}\n今: {fv['after_state']}\n\n{fv['method']}"
    if fv.get("insight"):
        post += f"\n\n{fv['insight']}"
    return post


def _build_howto(fv, opening):
    items = [fv.get(f"item{i}", "") for i in range(1, 4)]
    items = [it for it in items if it]
    items_str = "\n".join(f"・{it}" for it in items)
    post = f"{fv['title']}\n\n{items_str}"
    if fv.get("ending"):
        post += f"\n\n{fv['ending']}"
    return post


def interactive_builder():
    """対話型ポストビルダー"""
    print("\n" + "=" * 50)
    print("  ポストビルダー（対話モード）")
    print("=" * 50)
    print("\nパターンを選んでください:")
    for key, tmpl in TEMPLATES.items():
        print(f"  {key}. {tmpl['name']}")
        print(f"     {tmpl['desc']}")
    print()

    choice = input("番号を入力 (1-4): ").strip()
    if choice not in TEMPLATES:
        print("1-4の番号を入力してください")
        return

    tmpl = TEMPLATES[choice]
    print(f"\n--- {tmpl['name']} ---")
    print("各項目を入力してください（空欄の場合はEnter）\n")

    fv = {}
    for label, key in tmpl["prompts"]:
        value = input(f"  {label}: ").strip()
        fv[key] = value if value else f"[{label}]"

    opening = random.choice(tmpl["openings"])
    post = tmpl["build"](fv, opening)

    print("\n" + "=" * 50)
    print("  生成されたポスト")
    print("=" * 50)
    print()
    print(post)
    print()

    # スコア診断
    diagnose_post(post)

    # 読者心理
    show_psychology(post)

    # シャッフルオプション
    while True:
        action = input("\n[s]書き出しシャッフル / [p]読者心理 / [Enter]終了: ").strip().lower()
        if action == "s":
            opening = random.choice(tmpl["openings"])
            post = tmpl["build"](fv, opening)
            print(f"\n--- 書き出し変更 ---\n\n{post}\n")
            diagnose_post(post)
        elif action == "p":
            show_psychology(post)
        else:
            break

    print("\n完成！上のテキストをコピーして投稿してください。")
    print("投稿タイミング: 18〜21時が最適\n")


# ========================================
# 過去投稿の改善機能
# ========================================

def improve_post():
    """過去の投稿を貼り付けて改善提案を受ける"""
    print("\n" + "=" * 50)
    print("  過去投稿の改善")
    print("=" * 50)
    print("\n過去の投稿を貼り付けてください。")
    print("（複数行の場合は入力後に空行でEnter）\n")

    lines = []
    while True:
        line = input()
        if line == "" and lines:
            break
        lines.append(line)
    original = "\n".join(lines).strip()

    if not original:
        print("テキストが入力されませんでした")
        return

    print("\n" + "-" * 50)
    print("  元の投稿を分析中...")
    print("-" * 50)

    # 分析
    v2 = calculate_buzz_score_v2(original)
    algo = calculate_algorithm_score(original)
    psych = analyze_reader_psychology(original)
    tone = analyze_tone(original)
    char_len = len(original)

    print(f"\n  v2スコア: {v2['total_score']}点 / Algoスコア: {algo['total_score']}点 / {char_len}字")
    print(f"  読者の第一感情: {psych['primary_emotion']}")
    print(f"  トーン: {tone['overall']}")

    # 弱点を特定
    weaknesses = []
    improvements = []

    # 秘匿感フレーズ
    has_secret = any(p in original for p in ["正直", "実は", "ド素人", "告白", "恥ずかしい", "ぶっちゃけ", "ここだけ"])
    if not has_secret:
        weaknesses.append("秘匿感フレーズがない")
        improvements.append("冒頭に「正直に言うと、」「実は、」「ぶっちゃけ、」を追加")

    # 数字
    has_number = bool(re.search(r'\d+', original))
    if not has_number:
        weaknesses.append("具体的な数字がない")
        improvements.append("時間・金額・期間などの数字を入れる（例: 3ヶ月、月5万、2時間）")

    # CTA
    has_cta = any(p in original for p in ["フォロー", "いいね", "RT", "リツイート", "保存", "ブックマーク", "シェア", "拡散"])
    if has_cta:
        weaknesses.append("CTAがある（バズを抑制する）")
        improvements.append("CTA（フォロー・いいね誘導）を削除")

    # 疑問形
    has_question = bool(re.search(r'[\?？]', original))
    if not has_question:
        weaknesses.append("疑問形がない（リプが来にくい）")
        improvements.append("末尾を疑問形に変える（リプライ = アルゴリズム27倍）")

    # 文字数
    if char_len < 100:
        weaknesses.append(f"短すぎる（{char_len}字 → 130-170字が最適）")
        improvements.append("体験やエピソードを追加して130字以上に")
    elif char_len > 200:
        weaknesses.append(f"長すぎる（{char_len}字 → 130-170字が最適）")
        improvements.append("冗長な部分を削って170字以内に")

    # 外部リンク
    if "http" in original:
        weaknesses.append("外部リンクあり（リーチ-50%）")
        improvements.append("リンクは本文から削除してリプライに書く")

    # ストーリー性
    from analyze_posts import has_story
    if not has_story(original):
        weaknesses.append("ストーリー性が薄い")
        improvements.append("Before→After構造か時系列の変化を入れる")

    # トーン
    if not tone["grok_friendly"]:
        weaknesses.append(f"トーン「{tone['overall']}」→ Grokに抑制される")
        improvements.append("建設的なトーン（学び・体験・提案）に変える")

    # 表示
    print("\n" + "=" * 50)
    print("  診断結果")
    print("=" * 50)

    if weaknesses:
        print("\n  【弱点】")
        for i, w in enumerate(weaknesses, 1):
            print(f"  {i}. {w}")

        print("\n  【改善提案】")
        for i, imp in enumerate(improvements, 1):
            print(f"  {i}. {imp}")
    else:
        print("\n  弱点は見つかりませんでした。このまま投稿してOK！")

    # 改善版の自動生成
    print("\n" + "=" * 50)
    print("  改善版を自動生成")
    print("=" * 50)

    improved = _auto_improve(original, weaknesses, has_secret, has_number, has_question, has_cta)

    print(f"\n--- 改善版 ---\n")
    print(improved)

    # 改善版のスコア
    v2_new = calculate_buzz_score_v2(improved)
    algo_new = calculate_algorithm_score(improved)
    print(f"\n--- スコア比較 ---")
    print(f"  v2:   {v2['total_score']}点 → {v2_new['total_score']}点 ({v2_new['total_score'] - v2['total_score']:+d})")
    print(f"  Algo: {algo['total_score']}点 → {algo_new['total_score']}点 ({algo_new['total_score'] - algo['total_score']:+d})")
    print(f"  文字: {char_len}字 → {len(improved)}字")

    # 読者心理
    psych_new = analyze_reader_psychology(improved)
    print(f"\n--- 読者心理の変化 ---")
    print(f"  感情: {psych['primary_emotion']} → {psych_new['primary_emotion']}")
    old_triggers = len(psych['like_triggers']) + len(psych['rt_triggers']) + len(psych['reply_triggers'])
    new_triggers = len(psych_new['like_triggers']) + len(psych_new['rt_triggers']) + len(psych_new['reply_triggers'])
    print(f"  心理トリガー数: {old_triggers} → {new_triggers}")

    # コピー用
    print(f"\n{'=' * 50}")
    print("  コピー用（以下をそのまま投稿）")
    print("=" * 50)
    print()
    print(improved)
    print()
    print("投稿タイミング: 18〜21時が最適")
    print("=" * 50)


def _auto_improve(original, weaknesses, has_secret, has_number, has_question, has_cta):
    """投稿を自動改善する"""
    improved = original

    # CTA削除
    if has_cta:
        cta_patterns = [
            r'フォローしてね[。！!]?', r'いいねしてね[。！!]?', r'RT[お願い]*[。！!]?',
            r'フォロー&?RT[。！!]?', r'保存推奨[。！!]?', r'ブックマークしてね[。！!]?',
            r'[いい]ねお願い[。！!]?', r'拡散希望[。！!]?', r'シェアお願い[。！!]?',
        ]
        for pat in cta_patterns:
            improved = re.sub(pat, '', improved)
        improved = improved.strip()

    # 外部リンク削除
    improved = re.sub(r'https?://\S+', '', improved).strip()

    # 秘匿感フレーズ追加（冒頭に）
    if not has_secret:
        first_line = improved.split("\n")[0]
        openings = ["正直に言うと、", "実は、", "ぶっちゃけ、"]
        # 冒頭が「」で始まるなら中に入れる
        if first_line.startswith("「"):
            pass  # そのまま
        else:
            opening = random.choice(openings)
            improved = opening + improved

    # 疑問形追加（末尾に）
    if not has_question:
        endings = [
            "\n\n同じ経験ある人いる？",
            "\n\nみんなはどう思う？",
            "\n\nこれって自分だけ？",
        ]
        improved = improved.rstrip("。") + random.choice(endings)

    # 改行整理（読みやすく）
    lines = improved.split("\n")
    if len(lines) <= 2 and len(improved) > 80:
        # 長い1-2行なら適切に改行を入れる
        sentences = re.split(r'([。！!])', improved)
        new_lines = []
        current = ""
        for s in sentences:
            current += s
            if s in ("。", "！", "!") and len(current) > 30:
                new_lines.append(current)
                current = ""
        if current:
            new_lines.append(current)
        if len(new_lines) >= 2:
            improved = "\n\n".join(new_lines)

    return improved.strip()


# ========================================
# 2つのポストを比較
# ========================================

def compare_posts():
    """2つのポストのスコアを比較"""
    print("\n" + "=" * 50)
    print("  ポスト比較")
    print("=" * 50)

    print("\n【ポストA】を入力（空行で確定）:\n")
    lines_a = []
    while True:
        line = input()
        if line == "" and lines_a:
            break
        lines_a.append(line)
    post_a = "\n".join(lines_a).strip()

    print("\n【ポストB】を入力（空行で確定）:\n")
    lines_b = []
    while True:
        line = input()
        if line == "" and lines_b:
            break
        lines_b.append(line)
    post_b = "\n".join(lines_b).strip()

    if not post_a or not post_b:
        print("両方のポストを入力してください")
        return

    v2_a = calculate_buzz_score_v2(post_a)
    v2_b = calculate_buzz_score_v2(post_b)
    algo_a = calculate_algorithm_score(post_a)
    algo_b = calculate_algorithm_score(post_b)
    psych_a = analyze_reader_psychology(post_a)
    psych_b = analyze_reader_psychology(post_b)

    print("\n" + "=" * 50)
    print("  比較結果")
    print("=" * 50)
    print(f"\n{'':20s} {'ポストA':>10s} {'ポストB':>10s} {'差':>10s}")
    print(f"  {'-' * 50}")

    v2_diff = v2_b['total_score'] - v2_a['total_score']
    algo_diff = algo_b['total_score'] - algo_a['total_score']
    len_a, len_b = len(post_a), len(post_b)

    print(f"  {'v2スコア':20s} {v2_a['total_score']:>8d}点 {v2_b['total_score']:>8d}点 {v2_diff:>+8d}")
    print(f"  {'Algoスコア':20s} {algo_a['total_score']:>8d}点 {algo_b['total_score']:>8d}点 {algo_diff:>+8d}")
    print(f"  {'文字数':20s} {len_a:>8d}字 {len_b:>8d}字 {len_b - len_a:>+8d}")

    print(f"\n  ポストA 第一感情: {psych_a['primary_emotion']}")
    print(f"  ポストB 第一感情: {psych_b['primary_emotion']}")

    triggers_a = len(psych_a['like_triggers']) + len(psych_a['rt_triggers']) + len(psych_a['reply_triggers'])
    triggers_b = len(psych_b['like_triggers']) + len(psych_b['rt_triggers']) + len(psych_b['reply_triggers'])
    print(f"\n  心理トリガー数: A={triggers_a} / B={triggers_b}")

    # どっちが良いか判定
    score_a = v2_a['total_score'] + algo_a['total_score']
    score_b = v2_b['total_score'] + algo_b['total_score']
    if score_b > score_a:
        print(f"\n  → ポストBの方がスコアが高い（+{score_b - score_a}点）")
    elif score_a > score_b:
        print(f"\n  → ポストAの方がスコアが高い（+{score_a - score_b}点）")
    else:
        print(f"\n  → 同スコア")

    print("=" * 50)


# ========================================
# メインメニュー
# ========================================

def show_menu():
    """メインメニューを表示"""
    print("\n" + "=" * 50)
    print("  バズ投稿ビルダー")
    print("=" * 50)
    print()
    print("  1. 新規ポスト作成（テンプレートから）")
    print("  2. 過去投稿を改善（貼り付けて分析→自動改善）")
    print("  3. スコア診断（テキストを診断）")
    print("  4. 読者心理分析（なぜバズるか言語化）")
    print("  5. 2つのポストを比較")
    print("  q. 終了")
    print()

    choice = input("番号を入力: ").strip()
    return choice


# ========================================
# メイン
# ========================================

def main():
    parser = argparse.ArgumentParser(description="CLIポストビルダー")
    parser.add_argument("command", nargs="?", default=None,
                        help="build/improve/score/psych/compare")
    parser.add_argument("text", nargs="?", default=None,
                        help="score/psychの対象テキスト")
    args = parser.parse_args()

    if args.command == "score" and args.text:
        diagnose_post(args.text)
    elif args.command == "psych" and args.text:
        show_psychology(args.text)
    elif args.command == "build":
        interactive_builder()
    elif args.command == "improve":
        improve_post()
    elif args.command == "compare":
        compare_posts()
    elif args.command is None:
        # メニューモード
        while True:
            choice = show_menu()
            if choice == "1":
                interactive_builder()
            elif choice == "2":
                improve_post()
            elif choice == "3":
                print("\n投稿テキストを入力（空行で確定）:\n")
                text_lines = []
                while True:
                    line = input()
                    if line == "" and text_lines:
                        break
                    text_lines.append(line)
                text = "\n".join(text_lines).strip()
                if text:
                    diagnose_post(text)
            elif choice == "4":
                print("\n投稿テキストを入力（空行で確定）:\n")
                text_lines = []
                while True:
                    line = input()
                    if line == "" and text_lines:
                        break
                    text_lines.append(line)
                text = "\n".join(text_lines).strip()
                if text:
                    show_psychology(text)
            elif choice == "5":
                compare_posts()
            elif choice in ("q", "Q", "quit", "exit"):
                print("\n終了します\n")
                break
            else:
                print("1-5 または q を入力してください")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
