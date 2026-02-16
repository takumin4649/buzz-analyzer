"""分析データに基づくバズポスト自動生成（テンプレート方式）"""

import random
import re
from collections import defaultdict
from datetime import datetime

import pandas as pd


def extract_trending_topics(df):
    """データからトレンドのトピック・キーワードを抽出"""
    tool_pattern = re.compile(
        r'(ChatGPT|Claude|Claude Code|Gemini|Copilot|Midjourney|'
        r'Stable Diffusion|DALL-E|Canva|Notion AI|Cursor|v0|Bolt)',
        re.IGNORECASE
    )
    work_pattern = re.compile(
        r'(ライティング|デザイン|プログラミング|動画編集|画像生成|'
        r'コンテンツ販売|アフィリエイト|コンサル|Web制作|自動化|'
        r'ブログ|YouTube|SNS運用|翻訳|データ分析)',
        re.IGNORECASE
    )

    # 正規化マッピング（大文字小文字の揺れを統一）
    tool_normalize = {
        "chatgpt": "ChatGPT", "claude": "Claude", "claude code": "Claude Code",
        "gemini": "Gemini", "copilot": "Copilot", "midjourney": "Midjourney",
        "stable diffusion": "Stable Diffusion", "dall-e": "DALL-E",
        "canva": "Canva", "notion ai": "Notion AI", "cursor": "Cursor",
        "v0": "v0", "bolt": "Bolt",
    }
    work_normalize = {
        "youtube": "YouTube", "sns運用": "SNS運用", "web制作": "Web制作",
    }

    tools = defaultdict(int)
    works = defaultdict(int)

    for _, row in df.iterrows():
        text = str(row.get("本文", ""))
        likes = row.get("いいね数", 0)

        for match in tool_pattern.finditer(text):
            normalized = tool_normalize.get(match.group().lower(), match.group())
            tools[normalized] += likes
        for match in work_pattern.finditer(text):
            normalized = work_normalize.get(match.group().lower(), match.group())
            works[normalized] += likes

    # Claude Code があれば Claude と統合しない（別ツールとして扱う）
    top_tools = sorted(tools.items(), key=lambda x: x[1], reverse=True)[:5]
    top_works = sorted(works.items(), key=lambda x: x[1], reverse=True)[:5]

    return (
        [t[0] for t in top_tools] if top_tools else ["ChatGPT", "Claude Code", "Canva"],
        [w[0] for w in top_works] if top_works else ["ライティング", "画像生成", "自動化"],
    )


def extract_effective_ctas(df):
    """効果的なCTAを分析データから抽出"""
    cta_patterns = {
        "保存して見返してね": r'保存',
        "フォローで最新情報をお届け": r'フォロー',
        "参考になったらいいね": r'いいね',
        "リポストで広めてくれると嬉しい": r'リポスト|RT|シェア|拡散',
        "気になる人はコメントで教えて": r'コメント|返信|教えて',
    }

    cta_scores = {}
    for cta_text, pattern in cta_patterns.items():
        likes = []
        for _, row in df.iterrows():
            text = str(row.get("本文", ""))
            if re.search(pattern, text, re.IGNORECASE):
                likes.append(row.get("いいね数", 0))
        if likes:
            cta_scores[cta_text] = sum(likes) / len(likes)

    sorted_ctas = sorted(cta_scores.items(), key=lambda x: x[1], reverse=True)
    return [c[0] for c in sorted_ctas] if sorted_ctas else list(cta_patterns.keys())


def extract_top_numbers(df):
    """上位投稿から使われている数字表現を抽出"""
    top = df.nlargest(20, "いいね数")
    numbers = []

    money_pattern = re.compile(r'(\d+万円|\d+,\d+万円|\d+億)')
    time_pattern = re.compile(r'(\d+ヶ月|\d+日|\d+時間|\d+分|\d+週間)')

    for _, row in top.iterrows():
        text = str(row.get("本文", ""))
        numbers.extend(money_pattern.findall(text))
        numbers.extend(time_pattern.findall(text))

    return numbers if numbers else ["30万円", "3ヶ月", "2時間", "月5万円"]


def generate_achievement_post(tools, works, numbers):
    """パターン1: 実績報告×数字提示型"""
    tool = random.choice(tools)
    work = random.choice(works)
    amount = random.choice(["5万円", "10万円", "15万円", "20万円", "30万円"])
    steps = random.sample(works, min(3, len(works)))

    templates = [
        f"""AI副業で月収{amount}達成しました

実践した3つのこと：
① {tool}で{steps[0]}
② AIツールで{steps[1] if len(steps) > 1 else "コンテンツ作成"}
③ 空き時間に{steps[2] if len(steps) > 2 else "案件対応"}

初月は3万円→3ヶ月で{amount}に。
スキルゼロからでも十分いけます""",
        f"""{tool}を使い始めて1ヶ月。

正直、もっと早く始めればよかった。

【成果】
・{work}の作業時間が1/3に
・クオリティは逆に上がった
・月の副収入が{amount}増えた

やり方は簡単で、{tool}に指示を出すだけ。
知ってるか知らないかの差でしかない""",
        f"""副業で月{amount}稼いでる人の共通点

✅ {tool}を使いこなしてる
✅ {work}に特化してる
✅ 毎日2時間だけ集中してる
✅ 完璧を求めずまず納品する

才能じゃなくて「仕組み」の問題""",
    ]

    return {
        "type": "実績報告×数字提示型",
        "text": random.choice(templates),
        "tips": "具体的な数字を入れるほどバズりやすい。自分の実績に合わせて数字を調整してください",
    }


def generate_problem_empathy_post(tools, works, numbers):
    """パターン2: 問題提起×共感型"""
    tool = random.choice(tools)
    work = random.choice(works)
    amount = random.choice(["5万円", "10万円", "15万円"])

    templates = [
        f"""「AI副業なんて怪しい」って思ってた。

でも実際やってみたら…
→ 1日2時間で月{amount}稼げた
→ {tool}があればスキル不要
→ 在宅で完結

バイトより全然効率いい。
もっと早く始めればよかった""",
        f"""会社の給料、3年間ほぼ変わってない。

でもAI副業始めて2ヶ月で
月{amount}プラスになった。

やったことは
・{tool}で{work}
・1日2時間だけ
・土日は休み

本業の昇給待つより
よっぽど現実的だった""",
        f"""「AIに仕事奪われる」って
怖がってる場合じゃない。

AIを使って稼ぐ側に回るだけ。

実際に{tool}使って{work}始めたら
初月から{amount}の収入になった。

奪われる前に、使う側になろう""",
    ]

    return {
        "type": "問題提起×共感型",
        "text": random.choice(templates),
        "tips": "読者の不安や悩みに共感してから解決策を提示するのがポイント",
    }


def generate_howto_post(tools, works, numbers):
    """パターン3: ノウハウ×箇条書き型"""
    tool = random.choice(tools)
    work = random.choice(works)
    amount = random.choice(["5万円", "10万円"])

    templates = [
        f"""初心者がAI副業で月{amount}稼ぐ方法

【ステップ】
1. {tool}に無料登録
2. クラウドソーシングで{work}案件を探す
3. AIで下書き→自分で仕上げ
4. 納品して報酬ゲット

これだけ。
スキルゼロから始めて2週間で初収益出ました""",
        f"""AI副業で失敗する人の特徴5選

① いきなり高額案件を狙う
② {tool}に丸投げして納品
③ 1つのジャンルに絞らない
④ 毎日やらない（週1だけ）
⑤ インプットばかりで行動しない

逆にこれの反対をやれば
月{amount}は余裕で狙える""",
        f"""{tool}で{work}を爆速化する方法

【Before】
・1案件に3時間
・月5件が限界
・報酬月3万円

【After】
・1案件30分
・月20件こなせる
・報酬月{amount}

やったのは{tool}の使い方を覚えただけ""",
    ]

    return {
        "type": "ノウハウ×箇条書き型",
        "text": random.choice(templates),
        "tips": "ステップを明確にして「自分にもできそう」と思わせるのがコツ",
    }


def _pick_compatible_pair(tools, works):
    """ツールとジャンルの自然な組み合わせを選ぶ"""
    compatibility = {
        "ChatGPT": ["ライティング", "コンテンツ販売", "ブログ", "SNS運用", "翻訳", "自動化"],
        "Claude": ["ライティング", "コンテンツ販売", "データ分析", "ブログ", "翻訳"],
        "Claude Code": ["プログラミング", "自動化", "Web制作"],
        "Canva": ["デザイン", "画像生成", "SNS運用", "YouTube"],
        "Midjourney": ["デザイン", "画像生成"],
        "Cursor": ["プログラミング", "自動化", "Web制作"],
    }
    random.shuffle(tools)
    for tool in tools:
        compatible = compatibility.get(tool, works)
        matches = [w for w in works if w in compatible]
        if matches:
            return tool, random.choice(matches)
    return random.choice(tools), random.choice(works)


def generate_story_post(tools, works, numbers):
    """パターン4: 体験談×ストーリー型"""
    tool, work = _pick_compatible_pair(tools, works)

    templates = [
        f"""3ヶ月前: 残業月80時間で手取り25万
2ヶ月前: AI副業開始→初月3万円
1ヶ月前: コツ掴んで月10万円
今: 副業だけで月18万円

使ってるのは{tool}だけ。
残業減らして収入は増えた。
人生変わりました""",
        f"""去年の自分に教えてあげたい。

「{tool}で{work}やれ」って。

1年前: 副業に興味あるけど何すれば…
半年前: AI副業を知って開始
3ヶ月前: 月5万円達成
今: 月15万円を安定して稼いでる

スタートが早いほど有利。
迷ってる時間がもったいない""",
        f"""AI副業を始めて変わったこと

・毎月の貯金額が10万円増えた
・「お金ない」が口癖じゃなくなった
・将来の不安が減った
・新しいスキルが身についた
・本業にも余裕ができた

きっかけは{tool}を触ってみただけ。
あの日の自分に感謝してる""",
    ]

    return {
        "type": "体験談×ストーリー型",
        "text": random.choice(templates),
        "tips": "Before→Afterを明確にして、リアルな数字を含めると共感されやすい",
    }


def generate_tool_intro_post(tools, works, numbers):
    """パターン5: ツール紹介×緊急性型"""
    tool = random.choice(tools)
    work = random.choice(works)

    # ランキング用にユニークなツール3つを確保
    unique_tools = list(dict.fromkeys(tools))  # 重複除去、順序保持
    fallback = ["ChatGPT", "Claude", "Canva"]
    while len(unique_tools) < 3:
        for fb in fallback:
            if fb not in unique_tools:
                unique_tools.append(fb)
                if len(unique_tools) >= 3:
                    break

    tool_descs = {
        "ChatGPT": "万能。迷ったらこれ",
        "Claude": "長文・分析に強い",
        "Claude Code": "コード生成が爆速",
        "Canva": "デザイン系ならこれ一択",
        "Midjourney": "画像生成のクオリティ最強",
        "Cursor": "AI搭載エディタ",
        "Gemini": "Google連携が便利",
    }

    templates = [
        f"""{tool}、まだ使ってない人は損してます。

これ1つで：
・{work}が10倍速
・プロ級のクオリティ
・初心者でもすぐ使える

みんなが気づく前に使い倒すべき""",
        f"""AI副業に使えるツール、これだけでOK

1位: {unique_tools[0]}
→ {tool_descs.get(unique_tools[0], "使いやすくて高性能")}

2位: {unique_tools[1]}
→ {tool_descs.get(unique_tools[1], "コスパ最強")}

3位: {unique_tools[2]}
→ {tool_descs.get(unique_tools[2], "特化型で強い")}

全部無料で始められる。
まず触ってみて""",
        f"""【2026年最新】AI副業おすすめジャンル

① {work}（{tool}で効率化）
→ 初心者でも月5万円〜

② コンテンツ販売
→ AIで量産可能

③ SNS運用代行
→ 企業からの需要が爆増中

今年はAI使える人が勝つ年。
始めるなら今""",
    ]

    return {
        "type": "ツール紹介×緊急性型",
        "text": random.choice(templates),
        "tips": "具体的なツール名を出すと検索流入も狙える。「今」「まだ」で緊急性を出す",
    }


def generate_posts(df, n=5, topic=None):
    """分析データに基づいてバズポストのテンプレートを生成

    Args:
        df: 分析済みのDataFrame
        n: 生成する投稿数（デフォルト5）
        topic: 特定のトピック（指定なしならデータから自動抽出）

    Returns:
        list: 生成された投稿テンプレートのリスト
    """
    tools, works = extract_trending_topics(df)
    numbers = extract_top_numbers(df)
    ctas = extract_effective_ctas(df)

    generators = [
        generate_achievement_post,
        generate_problem_empathy_post,
        generate_howto_post,
        generate_story_post,
        generate_tool_intro_post,
    ]

    posts = []
    for i in range(n):
        gen = generators[i % len(generators)]
        post = gen(tools, works, numbers)
        # 効果的なCTAを追加
        if ctas and random.random() > 0.3:
            post["cta"] = random.choice(ctas)
        posts.append(post)

    return posts, tools, works, ctas


def format_posts_markdown(posts, tools, works, ctas, section_num=8):
    """生成した投稿をMarkdown形式でフォーマット"""
    lines = []
    lines.append(f"## {section_num}. バズポスト自動生成（テンプレート）\n")
    lines.append("分析データに基づいて、バズりやすい投稿テンプレートを自動生成しました。\n")
    lines.append("**自分の経験・数字に置き換えて使ってください。**\n")

    lines.append("### データから抽出したトレンド\n")
    lines.append(f"- **人気ツール:** {', '.join(tools)}")
    lines.append(f"- **人気ジャンル:** {', '.join(works)}")
    lines.append(f"- **効果的なCTA:** {', '.join(ctas[:3])}\n")

    for i, post in enumerate(posts, 1):
        lines.append(f"### 生成案{i}: {post['type']}\n")
        lines.append("```")
        lines.append(post["text"])
        if post.get("cta"):
            lines.append(f"\n{post['cta']}")
        lines.append("```\n")
        lines.append(f"> **Tips:** {post['tips']}\n")

    lines.append("### 使い方\n")
    lines.append("1. 上記テンプレートから自分に合うものを選ぶ")
    lines.append("2. 数字・ツール名・ジャンルを自分の実績に置き換え")
    lines.append("3. 絵文字を2〜3個追加（入れすぎ注意）")
    lines.append("4. 投稿前に音読して自然な日本語か確認")
    lines.append("5. 朝7〜9時 or 夜19〜21時に投稿するのがベスト\n")

    return "\n".join(lines)


def generate_posts_standalone(input_file, output_file=None):
    """スタンドアロン実行用"""
    df = pd.read_excel(input_file)
    print(f"読み込み完了: {len(df)}件のポスト")

    posts, tools, works, ctas = generate_posts(df, n=5)
    md = format_posts_markdown(posts, tools, works, ctas)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"# バズポスト自動生成レポート\n\n")
            f.write(f"**生成日時:** {datetime.now().strftime('%Y年%m月%d日 %H:%M')}\n\n")
            f.write(f"**元データ:** {input_file}（{len(df)}件）\n\n---\n\n")
            f.write(md)
        print(f"保存完了: {output_file}")
    else:
        print(md)

    return posts


if __name__ == "__main__":
    import os
    import sys

    input_file = "output/buzz_posts_20260215.xlsx"

    if not os.path.exists(input_file):
        # CSVフォールバック
        csv_file = "buzz_posts_20260215.csv"
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file)
            os.makedirs("output", exist_ok=True)
            df.to_excel(input_file, index=False)
        else:
            print(f"エラー: データファイルが見つかりません")
            sys.exit(1)

    today = datetime.now().strftime("%Y%m%d")
    output_file = f"output/generated_posts_{today}.md"
    os.makedirs("output", exist_ok=True)
    generate_posts_standalone(input_file, output_file)
