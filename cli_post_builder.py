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
import sqlite3
import sys
import os

from buzz_score_v2 import calculate_buzz_score_v2
from algorithm_analysis import calculate_algorithm_score, analyze_tone
from reader_psychology import analyze_reader_psychology

DB_PATH = "data/buzz_database.db"


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


def _build_from_theme(pattern_key, theme):
    """テーマから最適化済みポストを直接生成する（等身大・挑戦中目線）"""
    # 実績を盛らない。まだ稼げてない「リアルな挑戦者」として書く
    period = random.choice(["3週間", "2週間", "10日"])
    hours = random.choice(["2時間", "1時間", "30分"])
    days = random.choice(["14日", "21日", "10日"])
    openings = ["正直に言う。", "実は、", "ぶっちゃけ、", "告白します。", "ここだけの話。"]
    opening = random.choice(openings)
    questions = [
        "同じような人いる？",
        "みんなはどうしてる？",
        "これって自分だけ？",
        "先に始めてる人、何が変わった？",
        "正直、不安しかないんだけど合ってる？",
    ]
    question = random.choice(questions)

    if pattern_key == "1":
        # 拓巳型: 等身大の自己開示 → リアルな今 → 疑問
        posts = [
            f"{opening}\n\n{theme}を始めて{period}。\nまだ1円も稼げてない。\n\nでも毎日{hours}やってたら\n「これ、前より確実にわかるようになってる」\nって瞬間があった。\n\n小さいけど、これが成長なのかもしれない。\n\n{question}",
            f"{opening}\n\n{theme}、ド素人の自分が始めて{days}目。\n\n正直まだ収益ゼロ。\nでも昨日、初めて「あ、これ自分で作れた」って思えた。\n\n稼げてないけど、確実に昨日の自分より前にいる。\n\n{question}",
            f"{opening}\n\n{theme}に手を出した。スキルゼロから。\n\n{period}経って、まだ1円にもなってない。\nでも不思議と「やめよう」とは思わない。\n\n毎日{hours}の積み重ねが\n少しずつ自信に変わってきてる。\n\n{question}",
        ]
    elif pattern_key == "2":
        # 不安×共感: 怖いけどやってる → リアルな葛藤 → 疑問
        posts = [
            f"「{theme}なんて自分には無理」\nって{period}前まで思ってた。\n\n正直、今もまだ1円も稼げてない。\nでも毎日{hours}触ってたら\n「無理」が「難しいけどできるかも」に変わった。\n\nこの感覚、伝わる人いる？\n\n{question}",
            f"{opening}\n\n{theme}を始めたけど\n周りに言えてない。\n\n「失敗したら恥ずかしい」って気持ちと\n「このまま何もしない方が怖い」って気持ちが\n毎日ぶつかってる。\n\nでも{days}続いてる。それだけは事実。\n\n{question}",
            f"ぶっちゃけ、{theme}始めて{period}。\n成果はまだゼロ。\n\n「本当にこれでいいのかな」って\n毎晩{hours}やりながら思ってる。\n\nでもやめたら「やらなかった人」で終わる。\nそれだけは嫌だから続けてる。\n\n{question}",
        ]
    elif pattern_key == "3":
        # Before→After（小さな変化）: 過去 → 今の小さな進歩 → 疑問
        posts = [
            f"{period}前: {theme}って何？状態\n今: まだ稼げてないけど毎日{hours}続いてる\n\n収益はゼロ。\nでも「何がわからないか」がわかるようになった。\n\n正直これだけでも、前の自分からしたら大進歩。\n\n{question}",
            f"【{theme}を始めて{days}目のリアル】\n\n収益: 0円\n学び: 毎日少しずつ増えてる\n不安: まだある\n後悔: ない\n\nぶっちゃけ結果は出てない。\nでも「やってる自分」は嫌いじゃない。\n\n{question}",
            f"{period}前→{theme}を全く知らなかった\n今→まだ1円も稼げてない\n\nでもこの{days}で変わったことがある。\n\n「自分には何もできない」って思い込みが\n「やれば少しずつわかる」に変わった。\n\n{question}",
        ]
    elif pattern_key == "4":
        # ノウハウ（初心者が気づいたこと）: 学び → 疑問
        posts = [
            f"{theme}を{period}やって気づいた3つのこと\n\n① 最初から完璧にやろうとすると止まる\n② 毎日{hours}でも続ければ確実に前に進む\n③ 「わからない」は恥ずかしくない\n\nまだ1円も稼げてないけど、これは本当。\n\n{question}",
            f"ド素人が{theme}を{days}やった正直な感想\n\n・思ったより難しい\n・でも思ったより楽しい\n・毎日{hours}は意外と続く\n・収益はまだゼロ\n\nそれでも続けてる理由は「昨日より成長してる実感」。\n\n{question}",
            f"{theme}初心者が{period}で学んだこと\n\n・調べるより手を動かす方が早い\n・完璧を目指すと1歩も進めない\n・{hours}の積み重ねはバカにできない\n\n正直まだ何も成果はない。\nでもやめる理由もない。\n\n{question}",
        ]
    else:
        posts = [f"{opening}{theme}について語りたい。\n\n{question}"]

    return random.choice(posts)


def build_from_args(pattern, theme):
    """引数モードのポスト生成（非対話）。最適化済みポストを出力。"""
    if pattern not in TEMPLATES:
        print(f"エラー: --pattern は 1〜4 を指定してください（指定値: {pattern}）")
        return

    tmpl = TEMPLATES[pattern]
    print(f"\n--- パターン{pattern}: {tmpl['name']} ---")
    print(f"--- テーマ: {theme} ---\n")

    post = _build_from_theme(pattern, theme)

    # スコアを確認し、足りなければ自動改善
    has_secret = any(p in post for p in ["正直", "実は", "ド素人", "告白", "恥ずかしい", "ぶっちゃけ", "ここだけ"])
    has_number = bool(re.search(r'\d+', post))
    has_question = bool(re.search(r'[？?]', post))
    has_cta = any(p in post for p in ["フォロー", "いいね", "RT", "保存"])
    post = _auto_improve(post, [], has_secret, has_number, has_question, has_cta)

    print("=" * 50)
    print("  生成されたポスト（最適化済み）")
    print("=" * 50)
    print()
    print(post)
    print()

    diagnose_post(post)
    show_psychology(post)

    # コピー用
    print("\n" + "=" * 50)
    print("  コピー用（以下をそのまま投稿）")
    print("=" * 50)
    print()
    print(post)
    print()
    print("投稿タイミング: 18〜21時が最適")
    print("=" * 50)


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

def improve_post(original=None):
    """過去の投稿を貼り付けて改善提案を受ける。originalを渡すと非対話モード。"""
    print("\n" + "=" * 50)
    print("  過去投稿の改善")
    print("=" * 50)

    if original is None:
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

def compare_posts(post_a=None, post_b=None):
    """2つのポストのスコアを比較。引数を渡すと非対話モード。"""
    print("\n" + "=" * 50)
    print("  ポスト比較")
    print("=" * 50)

    if post_a is None:
        print("\n【ポストA】を入力（空行で確定）:\n")
        lines_a = []
        while True:
            line = input()
            if line == "" and lines_a:
                break
            lines_a.append(line)
        post_a = "\n".join(lines_a).strip()

    if post_b is None:
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
# 自動ポスト生成（DBデータ駆動）
# ========================================

def _load_top_posts(min_likes=100, limit=200):
    """DBからバズ投稿を読み込む"""
    if not os.path.exists(DB_PATH):
        print("  エラー: データベースが見つかりません")
        return []

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT text, likes, retweets, replies FROM posts "
        "WHERE likes >= ? AND text != '' ORDER BY likes DESC LIMIT ?",
        (min_likes, limit),
    ).fetchall()
    conn.close()
    return [{"text": r[0], "likes": r[1], "retweets": r[2], "replies": r[3]} for r in rows]


def _extract_buzz_patterns(posts):
    """バズ投稿から冒頭・構造・トピックのパターンを抽出"""
    openings = []
    tools_mentioned = []
    number_exprs = []
    structures = []

    tool_re = re.compile(
        r'(ChatGPT|Claude|Claude Code|Gemini|Copilot|Cursor|Manus|'
        r'Midjourney|Canva|Notion AI|Playwright|Shopify|v0|Bolt|Grok)',
        re.IGNORECASE,
    )
    number_re = re.compile(r'(\d+(?:万円|円|倍|選|つ|個|分|時間|日|ヶ月|年|%|件|ステップ))')

    for p in posts:
        text = str(p["text"])
        lines = text.strip().split("\n")
        first = lines[0].strip()

        # 冒頭パターン収集（短すぎ・URL除外）
        if len(first) > 5 and not first.startswith("http"):
            openings.append(first)

        # ツール名
        for m in tool_re.finditer(text):
            tools_mentioned.append(m.group())

        # 数字表現
        number_exprs.extend(number_re.findall(text))

        # 構造タイプ判定
        if re.search(r'[①②③④⑤]|[1-5][\.．]', text):
            structures.append("listicle")
        elif "→" in text or "Before" in text.lower() or "After" in text.lower():
            structures.append("before_after")
        elif any(w in text for w in ["正直", "実は", "ぶっちゃけ", "告白"]):
            structures.append("confession")
        elif "？" in text or "?" in text:
            structures.append("question")
        else:
            structures.append("statement")

    # ツール頻度でソート
    from collections import Counter
    tool_counts = Counter(tools_mentioned)
    top_tools = [t for t, _ in tool_counts.most_common(8)]

    return {
        "openings": openings,
        "top_tools": top_tools if top_tools else ["ChatGPT", "Claude", "Gemini"],
        "numbers": list(set(number_exprs)) if number_exprs else ["月5万円", "3倍", "5選", "2時間"],
        "structures": Counter(structures),
    }


# --- 自動生成テンプレート群 ---

def _gen_revelation(tools, numbers):
    """「知らないとヤバい」系"""
    tool = random.choice(tools[:4])
    templates = [
        f"{tool}をそのまま使ってる人、性能の半分も引き出せてないって知ってた？\n\n"
        f"僕も最初「微妙だな」って思ってた。\n\n"
        f"でも設定を少し変えただけで\n"
        f"精度もスピードも劇的に変わった。\n\n"
        f"やったのはたった3つだけ",

        f"正直に言う。\n\n"
        f"{tool}を触る前と後で\n"
        f"作業効率が全然違う。\n\n"
        f"以前: 1つの作業に{random.choice(['3時間', '半日', '丸1日'])}\n"
        f"今: {random.choice(['30分', '1時間', '15分'])}で終わる\n\n"
        f"知ってるか知らないかだけの差",

        f"「{tool}なんて大したことない」\n"
        f"って思ってた{random.choice(['3ヶ月', '半年', '1ヶ月'])}前の自分をぶん殴りたい。\n\n"
        f"使い方を変えただけで\n"
        f"副業の収入が{random.choice(['3倍', '5倍', '月5万円増'])}になった。\n\n"
        f"もっと早く知りたかった",
    ]
    return random.choice(templates)


def _gen_confession(tools, numbers):
    """「自己開示×体験」系（拓巳型）"""
    tool = random.choice(tools[:4])
    templates = [
        f"ぶっちゃけ、副業で稼げるようになったのは\n"
        f"才能でもスキルでもなかった。\n\n"
        f"{tool}の使い方を覚えて\n"
        f"毎日{random.choice(['2時間', '1時間', '30分'])}だけやっただけ。\n\n"
        f"正直、自分でも驚いてる。\n"
        f"スキルゼロからでもいけるんだなって",

        f"実は、{random.choice(['先月', '3ヶ月前'])}まで\n"
        f"AI副業なんて怪しいと思ってた。\n\n"
        f"でも{tool}を使って実際にやってみたら\n"
        f"初月から{random.choice(['3万円', '5万円', '8万円'])}の収入になった。\n\n"
        f"行動する前に判断してた自分が恥ずかしい",

        f"正直に言うと、\n"
        f"会社の給料だけじゃ不安だった。\n\n"
        f"だから{tool}で副業を始めてみた。\n"
        f"最初の{random.choice(['2週間', '1ヶ月'])}は全然ダメだった。\n\n"
        f"でも続けたら{random.choice(['月5万', '月10万', '月8万'])}いくようになった。\n"
        f"あの時やめなくてよかった",
    ]
    return random.choice(templates)


def _gen_listicle(tools, numbers):
    """「〇選」リスト系"""
    tool = random.choice(tools[:4])
    tool2 = random.choice([t for t in tools[:4] if t != tool] or tools[:1])
    templates = [
        f"AI副業で失敗する人の共通点{random.choice(['5つ', '3つ'])}\n\n"
        f"① いきなり高単価案件を狙う\n"
        f"② {tool}に丸投げして納品\n"
        f"③ インプットばかりで手を動かさない\n\n"
        f"逆にこれの反対をやれば\n"
        f"{random.choice(['月5万', '月10万'])}は余裕でいける",

        f"AI使って{random.choice(['月5万', '月10万'])}稼いでる人がやってること\n\n"
        f"・{tool}で下書き→自分で仕上げ\n"
        f"・1日{random.choice(['2時間', '1時間'])}だけ集中\n"
        f"・完璧を求めず、まず納品\n"
        f"・{tool2}も併用して使い分け\n\n"
        f"才能じゃなくて「仕組み」の問題",

        f"{tool}の使い方、これだけ覚えれば十分\n\n"
        f"① 指示は「背景→条件→出力形式」の順番\n"
        f"② 1回で完璧を求めない（3回やりとり）\n"
        f"③ 出力は必ず自分の言葉に直す\n\n"
        f"これだけで精度が{random.choice(['3倍', '5倍', '格段に'])}変わる",
    ]
    return random.choice(templates)


def _gen_before_after(tools, numbers):
    """Before→After型"""
    tool = random.choice(tools[:4])
    templates = [
        f"{random.choice(['半年前', '3ヶ月前'])}: 残業月80時間で手取り{random.choice(['22万', '25万'])}\n"
        f"{random.choice(['2ヶ月前', '1ヶ月前'])}: AI副業開始→初月3万円\n"
        f"今: 副業だけで月{random.choice(['10万', '15万', '18万'])}円\n\n"
        f"使ってるのは{tool}だけ。\n"
        f"残業減らして収入は増えた",

        f"AI副業を始めて変わったこと\n\n"
        f"・毎月の貯金が{random.choice(['5万', '10万'])}増えた\n"
        f"・「お金ない」が口癖じゃなくなった\n"
        f"・将来の不安が減った\n"
        f"・本業にも余裕ができた\n\n"
        f"きっかけは{tool}を触ってみただけ",

        f"【{tool}導入のBefore/After】\n\n"
        f"Before:\n"
        f"・1案件{random.choice(['3時間', '5時間'])}\n"
        f"・月{random.choice(['3件', '5件'])}が限界\n\n"
        f"After:\n"
        f"・1案件{random.choice(['30分', '1時間'])}\n"
        f"・月{random.choice(['15件', '20件'])}こなせる\n\n"
        f"使い方を覚えただけでこの差",
    ]
    return random.choice(templates)


def _gen_question(tools, numbers):
    """疑問形×問題提起型（リプ誘発）"""
    tool = random.choice(tools[:4])
    templates = [
        f"{tool}使ってる人に聞きたいんだけど、\n\n"
        f"ぶっちゃけ副業の収入って\n"
        f"どのくらい変わった？\n\n"
        f"自分は{random.choice(['月3万→月10万', '月0→月5万', '月5万→月15万'])}になったけど\n"
        f"もっと上手く使ってる人いそう",

        f"AIで副業してる人、\n"
        f"ガチで聞きたいんだけど\n\n"
        f"何のジャンルが一番稼ぎやすかった？\n\n"
        f"自分は{random.choice(['ライティング', 'コンテンツ販売', 'SNS運用代行'])}が\n"
        f"一番コスパ良かったけど、みんなはどう？",

        f"正直、{tool}が出てから\n"
        f"「これ自分の仕事なくなるんじゃ…」\n"
        f"って不安になった人いない？\n\n"
        f"自分はむしろ逆で、\n"
        f"AIを使う側に回ったら収入増えた。\n\n"
        f"奪われる前に使う側になった方がよくない？",
    ]
    return random.choice(templates)


GENERATOR_TYPES = [
    ("知らないとヤバい系", _gen_revelation),
    ("自己開示×体験（拓巳型）", _gen_confession),
    ("リスト・箇条書き系", _gen_listicle),
    ("Before→After系", _gen_before_after),
    ("疑問形×リプ誘発系", _gen_question),
]


def auto_generate(count=5):
    """DBデータからバズパターンを抽出して自動でポストを生成する"""
    print("\n" + "=" * 50)
    print("  自動ポスト生成（DBデータ駆動）")
    print("=" * 50)
    print("\n  データベースからバズパターンを分析中...\n")

    # DBからデータ取得
    posts = _load_top_posts(min_likes=100, limit=200)
    if not posts:
        print("  データが見つかりません。先にデータをインポートしてください。")
        return []

    patterns = _extract_buzz_patterns(posts)

    print(f"  分析対象: {len(posts)}件のバズ投稿")
    print(f"  トレンドツール: {', '.join(patterns['top_tools'][:5])}")
    top_struct = patterns["structures"].most_common(3)
    struct_str = ", ".join(f"{s}({c}件)" for s, c in top_struct)
    print(f"  多い構造: {struct_str}")

    # ポスト生成
    generated = []
    used_types = set()

    for i in range(count):
        # タイプをなるべくばらけさせる
        available = [(name, gen) for name, gen in GENERATOR_TYPES if name not in used_types]
        if not available:
            used_types.clear()
            available = GENERATOR_TYPES
        type_name, gen_func = random.choice(available)
        used_types.add(type_name)

        text = gen_func(patterns["top_tools"], patterns["numbers"])

        # スコア計算
        v2 = calculate_buzz_score_v2(text)
        algo = calculate_algorithm_score(text)
        total = v2["total_score"] + algo["total_score"]

        generated.append({
            "type": type_name,
            "text": text,
            "v2": v2["total_score"],
            "algo": algo["total_score"],
            "total": total,
            "chars": len(text),
        })

    # スコア順にソート
    generated.sort(key=lambda x: x["total"], reverse=True)

    # 表示
    print(f"\n{'=' * 50}")
    print(f"  生成結果（スコア順 / {count}件）")
    print(f"{'=' * 50}")

    for i, g in enumerate(generated, 1):
        medal = {1: " ← BEST", 2: "", 3: ""}.get(i, "")
        print(f"\n--- [{i}] {g['type']}  v2:{g['v2']}点 Algo:{g['algo']}点 合計:{g['total']}点 {g['chars']}字{medal} ---\n")
        print(g["text"])
        print()

    # 合計スコアの目安
    print("=" * 50)
    print("  スコア目安: 合計120+で投稿OK / 140+でバズ期待大")
    print("  投稿タイミング: 18〜21時が最適")
    print("  リプには必ず返信（アルゴリズム150倍）")
    print("=" * 50)

    # もう一回生成するか
    print("\n  [r] もう1回生成 / [数字] その番号を改善 / [Enter] 終了")
    try:
        action = input("  → ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        action = ""

    if action == "r":
        return auto_generate(count)
    elif action.isdigit():
        idx = int(action) - 1
        if 0 <= idx < len(generated):
            print(f"\n  [{idx + 1}]を改善します...\n")
            original = generated[idx]["text"]
            v2_old = generated[idx]["v2"]
            algo_old = generated[idx]["algo"]

            has_secret = any(p in original for p in ["正直", "実は", "ぶっちゃけ", "告白", "ここだけ"])
            has_number = bool(re.search(r'\d+', original))
            has_question = bool(re.search(r'[？?]', original))
            has_cta = any(p in original for p in ["フォロー", "いいね", "RT", "保存"])

            improved = _auto_improve(original, [], has_secret, has_number, has_question, has_cta)
            v2_new = calculate_buzz_score_v2(improved)
            algo_new = calculate_algorithm_score(improved)

            print("--- 改善版 ---\n")
            print(improved)
            print(f"\n--- スコア ---")
            print(f"  v2:   {v2_old}点 → {v2_new['total_score']}点 ({v2_new['total_score'] - v2_old:+d})")
            print(f"  Algo: {algo_old}点 → {algo_new['total_score']}点 ({algo_new['total_score'] - algo_old:+d})")
            print(f"  文字: {len(original)}字 → {len(improved)}字")

    return generated


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
    print("  6. 自動ポスト生成（DB分析→即使える投稿）")
    print("  q. 終了")
    print()

    choice = input("番号を入力: ").strip()
    return choice


# ========================================
# メイン
# ========================================

def main():
    parser = argparse.ArgumentParser(
        description="CLIポストビルダー",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使い方:
  python cli_post_builder.py                          → メニュー
  python cli_post_builder.py build                    → 対話型ポスト作成
  python cli_post_builder.py build --pattern 1 --theme "AI副業"  → 引数で即生成
  python cli_post_builder.py improve                  → 対話型改善
  python cli_post_builder.py improve "投稿テキスト"   → 引数で即改善
  python cli_post_builder.py compare "投稿A" "投稿B"  → 引数で即比較
  python cli_post_builder.py score "テキスト"         → スコア診断
  python cli_post_builder.py psych "テキスト"         → 読者心理分析
        """,
    )
    parser.add_argument("command", nargs="?", default=None,
                        help="build/improve/score/psych/compare/auto")
    parser.add_argument("text", nargs="?", default=None,
                        help="score/psych/improve の対象テキスト、または compare の投稿A")
    parser.add_argument("text2", nargs="?", default=None,
                        help="compare の投稿B")
    parser.add_argument("--pattern", default=None,
                        help="build: テンプレート番号 (1〜4)")
    parser.add_argument("--theme", default=None,
                        help="build: テーマ・トピック文字列")
    args = parser.parse_args()

    if args.command == "score" and args.text:
        diagnose_post(args.text)
    elif args.command == "psych" and args.text:
        show_psychology(args.text)
    elif args.command == "build":
        if args.pattern and args.theme:
            build_from_args(args.pattern, args.theme)
        else:
            interactive_builder()
    elif args.command == "improve":
        improve_post(args.text)  # Noneなら対話モード
    elif args.command == "compare":
        compare_posts(args.text, args.text2)  # Noneなら対話モード
    elif args.command == "auto":
        auto_generate()
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
            elif choice == "6":
                auto_generate()
            elif choice in ("q", "Q", "quit", "exit"):
                print("\n終了します\n")
                break
            else:
                print("1-5 または q を入力してください")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
