"""CLIポストビルダー（スマホからも使える版）

Streamlitなしで動く対話型ポスト生成ツール。
python cli_post_builder.py で起動。

使い方:
  python cli_post_builder.py           → 対話モード
  python cli_post_builder.py --score "テキスト"  → スコア診断のみ
  python cli_post_builder.py --psychology "テキスト" → 読者心理分析
"""

import argparse
import random
import re
import sys

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
# メイン
# ========================================

def main():
    parser = argparse.ArgumentParser(description="CLIポストビルダー")
    parser.add_argument("--score", type=str, help="投稿テキストのスコア診断")
    parser.add_argument("--psychology", type=str, help="投稿テキストの読者心理分析")
    args = parser.parse_args()

    if args.score:
        diagnose_post(args.score)
    elif args.psychology:
        show_psychology(args.psychology)
    else:
        interactive_builder()


if __name__ == "__main__":
    main()
