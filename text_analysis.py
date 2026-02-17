"""バズポスト テキスト詳細分析スクリプト"""

import os
import re
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd


def load_and_filter(filepath):
    """Excelを読み込み、フィルタリング済み76件を返す"""
    df = pd.read_excel(filepath)
    print(f"読み込み: {len(df)}件")

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
    print(f"フィルタ後: {len(df)}件")
    return df.reset_index(drop=True)


def extract_opening_phrases(df):
    """1. 冒頭フレーズのパターン分類"""
    categories = defaultdict(list)

    for _, row in df.iterrows():
        text = str(row["本文"]).strip()
        first_line = text.split("\n")[0].strip()
        likes = row["いいね数"]

        # 分類
        if re.search(r"[\?？]", first_line):
            cat = "疑問・問いかけ型"
        elif re.search(r"[!！]{1,}", first_line) and len(first_line) < 30:
            cat = "インパクト短文型"
        elif re.search(r"\d+[選つ個万円%]", first_line):
            cat = "数字リスト型"
        elif re.search(r"(知らない|知らなかった|まだ|実は|ぶっちゃけ|正直|ガチで|マジで)", first_line):
            cat = "秘匿・衝撃事実型"
        elif re.search(r"(やめ|するな|ダメ|禁止|注意|危険|ヤバい|やばい)", first_line):
            cat = "警告・否定型"
        elif re.search(r"(方法|やり方|コツ|ステップ|手順|始め方|稼ぎ方|稼げる)", first_line):
            cat = "ノウハウ提示型"
        elif re.search(r"(これ|この|あの|あれ)", first_line) and len(first_line) < 30:
            cat = "指示語フック型"
        elif re.search(r"(僕|私|俺|自分|ワイ)", first_line):
            cat = "体験談・自己開示型"
        elif re.search(r"(おすすめ|最強|神|便利|無料|0円)", first_line):
            cat = "推薦・絶賛型"
        else:
            cat = "その他"

        categories[cat].append({
            "first_line": first_line[:80],
            "likes": likes
        })

    return categories


def classify_structure(df):
    """2. 文章構成の型を全投稿で分類"""
    structures = defaultdict(list)

    for _, row in df.iterrows():
        text = str(row["本文"]).strip()
        likes = row["いいね数"]
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        has_url = bool(re.search(r"https?://", text))
        has_list = bool(re.search(r"^[・\-・▶▸✅☑✓◆■●①②③④⑤⑥⑦⑧⑨⑩\d+[\.\)）]]", text, re.MULTILINE))
        has_question = bool(re.search(r"[\?？]", lines[0] if lines else ""))
        has_cta = bool(re.search(r"(フォロー|いいね|リプ|RT|保存|リツイート|拡散|シェア|ブクマ|ブックマーク|プロフ|固ツイ|リンク|詳細|続き)", text))
        has_self_story = bool(re.search(r"(僕は|私は|俺は|自分は|ワイは|〜した|〜だった|〜してた|経験|体験)", text))

        if has_list and has_url:
            struct = "リスト型 → URL誘導"
        elif has_list and has_cta:
            struct = "リスト型 → CTA"
        elif has_list:
            struct = "リスト型（単独）"
        elif has_question and has_cta:
            struct = "問題提起 → 解決策 → CTA"
        elif has_question and has_url:
            struct = "問題提起 → 解決策 → URL"
        elif has_question:
            struct = "問題提起 → 回答"
        elif has_self_story and has_cta:
            struct = "体験談 → 教訓 → CTA"
        elif has_self_story and has_url:
            struct = "体験談 → URL誘導"
        elif has_self_story:
            struct = "体験談 → 教訓"
        elif has_url and has_cta:
            struct = "主張 → URL + CTA"
        elif has_url:
            struct = "主張 → URL誘導"
        elif has_cta:
            struct = "主張 → CTA"
        else:
            struct = "主張のみ（短文完結）"

        structures[struct].append({
            "first_line": lines[0][:60] if lines else "",
            "likes": likes
        })

    return structures


def extract_cta_phrases(df):
    """3. CTAフレーズ一覧の抽出"""
    cta_patterns = [
        (r"フォロー[してくださいしろよろしくお願い]*", "フォロー系"),
        (r"いいね[してくださいしろお願い]*", "いいね系"),
        (r"(リプ|リプライ|コメント)[してくださいしろお願い欄で]*", "リプライ系"),
        (r"(RT|リツイート|リポスト|拡散)[してくださいしろお願い]*", "RT・拡散系"),
        (r"(保存|ブクマ|ブックマーク)[してくださいしろお願い推奨]*", "保存系"),
        (r"(プロフ|プロフィール)[から見てチェック確認]*", "プロフ誘導系"),
        (r"(固ツイ|固定ツイート)[から見てチェック確認]*", "固ツイ誘導系"),
        (r"(リンク|URL|詳細|続き|こちら).{0,10}(から|は|を|に|で|👇|↓|⬇)", "リンク誘導系"),
        (r"(無料|0円|タダ).{0,20}(配布|プレゼント|あげ|DM)", "無料配布系"),
        (r"(DM|ディーエム).{0,10}(ください|くれ|して|送)", "DM誘導系"),
    ]

    results = defaultdict(list)

    for _, row in df.iterrows():
        text = str(row["本文"]).strip()
        likes = row["いいね数"]

        for pattern, category in cta_patterns:
            matches = re.findall(pattern, text)
            if matches:
                # 実際のCTA文脈を抽出（前後含む）
                for m in re.finditer(pattern, text):
                    start = max(0, m.start() - 15)
                    end = min(len(text), m.end() + 15)
                    context = text[start:end].replace("\n", " ").strip()
                    results[category].append({
                        "phrase": context,
                        "likes": likes
                    })

    return results


def extract_frequent_keywords(df, top_n=20):
    """4. 頻出キーワード・フレーズTOP20"""
    # 単語レベル（2-6文字のカタカナ・漢字フレーズ）
    all_text = " ".join(df["本文"].astype(str).tolist())

    # キーフレーズ抽出（よく使われる意味のあるフレーズ）
    # カタカナ語
    katakana = re.findall(r"[ァ-ヶー]{3,}", all_text)
    # 漢字フレーズ
    kanji = re.findall(r"[一-龥]{2,6}", all_text)
    # 英数字キーワード
    english = re.findall(r"[A-Za-z]{3,}", all_text)

    # ストップワード
    stop_words = {
        "する", "できる", "ある", "いる", "なる", "やる", "くる", "もの", "こと",
        "それ", "これ", "あれ", "ため", "よう", "とき", "ところ", "ほう",
        "てる", "している", "した", "して", "から", "まで", "ので", "けど",
        "という", "ている", "たち", "など", "って", "ない", "ません",
        "https", "http", "www", "com", "the", "and", "for", "you",
    }

    all_words = katakana + kanji + english
    filtered = [w for w in all_words if w not in stop_words and len(w) >= 2]
    counter = Counter(filtered)

    # バズ文脈でよく使われるフレーズ（2-3語の複合）
    phrase_patterns = [
        r"AI副業", r"副業[で月]", r"月[0-9０-９]+万",
        r"[0-9０-９]+万円", r"ChatGPT", r"AI[でを使]",
        r"完全無料", r"知らないと損", r"今すぐ",
        r"副業初心者", r"稼[いげぐ]", r"収益化",
        r"自動化", r"不労所得", r"コンテンツ販売",
        r"SNS運用", r"個人で稼", r"脱サラ",
        r"AI時代", r"プログラミング不要", r"ノーコード",
    ]
    phrase_counter = Counter()
    for pattern in phrase_patterns:
        count = len(re.findall(pattern, all_text))
        if count > 0:
            phrase_counter[pattern.replace(r"[でを使]", "活用").replace(r"[いげぐ]", "ぐ").replace(r"[0-9０-９]+", "N")] = count

    return counter.most_common(top_n), phrase_counter.most_common(20)


def decompose_top_posts(df, top_n=5):
    """5. いいね数TOP5の投稿を構造分解"""
    top_df = df.nlargest(top_n, "いいね数")
    results = []

    for _, row in top_df.iterrows():
        text = str(row["本文"]).strip()
        likes = row["いいね数"]
        rts = row["リポスト数"]
        replies = row["リプライ数"]
        user = row["ユーザー名"]
        url = str(row.get("ポストURL", ""))

        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # 冒頭（1-2行目）
        opening = lines[0] if lines else ""

        # URL抽出
        urls_in_text = re.findall(r"https?://\S+", text)

        # CTA抽出（最後の方の行から）
        cta_lines = []
        for line in reversed(lines):
            if re.search(r"(フォロー|いいね|リプ|RT|保存|拡散|プロフ|固ツイ|リンク|DM|👇|↓|⬇|詳細|続き|こちら|ブクマ|シェア)", line):
                cta_lines.insert(0, line)
            elif urls_in_text and any(u in line for u in urls_in_text):
                continue  # URL行はスキップ
            else:
                break

        # 本文（冒頭とCTAを除いた中間部分）
        body_start = 1
        body_end = len(lines) - len(cta_lines)
        body_lines = lines[body_start:body_end]
        # URL行を除外
        body_lines = [l for l in body_lines if not re.match(r"^https?://", l)]

        results.append({
            "rank": len(results) + 1,
            "likes": likes,
            "rts": rts,
            "replies": replies,
            "user": user,
            "url": url,
            "opening": opening,
            "body": "\n".join(body_lines) if body_lines else "（冒頭に集約）",
            "cta": "\n".join(cta_lines) if cta_lines else "（CTAなし）",
            "urls": urls_in_text,
            "full_text": text
        })

    return results


def generate_report(df, output_path):
    """Markdownレポートを生成"""
    lines = []
    lines.append("# バズポスト テキスト詳細分析レポート")
    lines.append(f"\n**分析日**: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"**分析対象**: {len(df)}件のフィルタリング済みポスト")
    lines.append(f"**データソース**: buzz_posts_20260215.xlsx")
    lines.append("")

    # ===== 1. 冒頭フレーズのパターン =====
    print("1. 冒頭フレーズ分析中...")
    categories = extract_opening_phrases(df)
    lines.append("---")
    lines.append("## 1. 冒頭フレーズのパターン分類")
    lines.append("")
    lines.append("投稿の書き出し（1行目）を分類し、各パターンの実例といいね数を示す。")
    lines.append("")

    # いいね平均で降順ソート
    cat_stats = []
    for cat, items in categories.items():
        avg_likes = sum(i["likes"] for i in items) / len(items)
        cat_stats.append((cat, items, avg_likes))
    cat_stats.sort(key=lambda x: x[2], reverse=True)

    for cat, items, avg_likes in cat_stats:
        lines.append(f"### {cat}（{len(items)}件 / 平均いいね: {avg_likes:.0f}）")
        lines.append("")
        # いいね数順でTOP5を表示
        sorted_items = sorted(items, key=lambda x: x["likes"], reverse=True)
        for item in sorted_items[:5]:
            lines.append(f"- **{item['likes']}いいね**: 「{item['first_line']}」")
        if len(items) > 5:
            lines.append(f"- *...他{len(items)-5}件*")
        lines.append("")

    # ===== 2. 文章構成の型 =====
    print("2. 文章構成分析中...")
    structures = classify_structure(df)
    lines.append("---")
    lines.append("## 2. 文章構成の型（全投稿分類）")
    lines.append("")

    struct_stats = []
    for struct, items in structures.items():
        avg_likes = sum(i["likes"] for i in items) / len(items)
        struct_stats.append((struct, items, avg_likes))
    struct_stats.sort(key=lambda x: len(x[1]), reverse=True)

    lines.append("| 構成パターン | 件数 | 割合 | 平均いいね | 最高いいね |")
    lines.append("|:---|---:|---:|---:|---:|")
    for struct, items, avg_likes in struct_stats:
        max_likes = max(i["likes"] for i in items)
        pct = len(items) / len(df) * 100
        lines.append(f"| {struct} | {len(items)} | {pct:.1f}% | {avg_likes:.0f} | {max_likes} |")
    lines.append("")

    # 各パターンの代表例
    lines.append("### 各パターンの代表例（いいね数TOP）")
    lines.append("")
    for struct, items, avg_likes in struct_stats:
        best = max(items, key=lambda x: x["likes"])
        lines.append(f"- **{struct}**: 「{best['first_line']}...」（{best['likes']}いいね）")
    lines.append("")

    # ===== 3. CTAフレーズ一覧 =====
    print("3. CTAフレーズ抽出中...")
    cta_data = extract_cta_phrases(df)
    lines.append("---")
    lines.append("## 3. CTA（行動喚起）フレーズ一覧")
    lines.append("")

    cta_stats = [(cat, items) for cat, items in cta_data.items()]
    cta_stats.sort(key=lambda x: len(x[1]), reverse=True)

    for cat, items in cta_stats:
        avg_likes = sum(i["likes"] for i in items) / len(items) if items else 0
        lines.append(f"### {cat}（出現{len(items)}回 / 平均いいね: {avg_likes:.0f}）")
        lines.append("")
        # ユニークなフレーズを表示
        seen = set()
        unique_items = []
        for item in sorted(items, key=lambda x: x["likes"], reverse=True):
            phrase_key = item["phrase"][:20]
            if phrase_key not in seen:
                seen.add(phrase_key)
                unique_items.append(item)
        for item in unique_items[:8]:
            lines.append(f"- 「{item['phrase']}」（{item['likes']}いいね）")
        lines.append("")

    # CTAなしの投稿数
    posts_with_cta = set()
    for cat, items in cta_data.items():
        for item in items:
            posts_with_cta.add(item["likes"])  # いいね数で識別（簡易）

    lines.append(f"**CTAを含む投稿率**: 概算{min(len(posts_with_cta), len(df))}/{len(df)}件")
    lines.append("")

    # ===== 4. 頻出キーワードTOP20 =====
    print("4. 頻出キーワード集計中...")
    word_top, phrase_top = extract_frequent_keywords(df, top_n=20)
    lines.append("---")
    lines.append("## 4. 頻出キーワード・フレーズ TOP20")
    lines.append("")

    lines.append("### 単語レベル TOP20")
    lines.append("")
    lines.append("| 順位 | キーワード | 出現回数 |")
    lines.append("|---:|:---|---:|")
    for i, (word, count) in enumerate(word_top, 1):
        lines.append(f"| {i} | {word} | {count} |")
    lines.append("")

    lines.append("### バズ文脈フレーズ")
    lines.append("")
    if phrase_top:
        lines.append("| フレーズ | 出現回数 |")
        lines.append("|:---|---:|")
        for phrase, count in phrase_top:
            lines.append(f"| {phrase} | {count} |")
    else:
        lines.append("（該当フレーズなし）")
    lines.append("")

    # ===== 5. いいねTOP5の構造分解 =====
    print("5. TOP5投稿の構造分解中...")
    top_posts = decompose_top_posts(df, top_n=5)
    lines.append("---")
    lines.append("## 5. いいね数 TOP5 投稿の構造分解")
    lines.append("")

    for post in top_posts:
        lines.append(f"### 第{post['rank']}位: {post['likes']}いいね / {post['rts']}RT / {post['replies']}リプ")
        lines.append(f"**ユーザー**: @{post['user']}")
        if post['url']:
            lines.append(f"**URL**: {post['url']}")
        lines.append("")

        lines.append("#### 【冒頭（フック）】")
        lines.append(f"> {post['opening']}")
        lines.append("")

        lines.append("#### 【本文】")
        lines.append("```")
        lines.append(post['body'])
        lines.append("```")
        lines.append("")

        lines.append("#### 【CTA（行動喚起）】")
        lines.append(f"> {post['cta']}")
        lines.append("")

        if post['urls']:
            lines.append("#### 【URL】")
            for u in post['urls']:
                lines.append(f"- {u}")
            lines.append("")

        lines.append("#### 【全文】")
        lines.append("<details><summary>クリックで展開</summary>")
        lines.append("")
        lines.append("```")
        lines.append(post['full_text'])
        lines.append("```")
        lines.append("</details>")
        lines.append("")
        lines.append("---")
        lines.append("")

    # まとめ
    lines.append("## まとめ：バズるテキストの法則")
    lines.append("")

    # 冒頭パターンの勝者
    best_opening = cat_stats[0] if cat_stats else None
    if best_opening:
        lines.append(f"1. **最強の冒頭パターン**: 「{best_opening[0]}」（平均{best_opening[2]:.0f}いいね）")

    # 構成の勝者
    best_struct_items = [(s, items, avg) for s, items, avg in struct_stats if len(items) >= 3]
    if best_struct_items:
        best_struct_items.sort(key=lambda x: x[2], reverse=True)
        lines.append(f"2. **最強の構成パターン**: 「{best_struct_items[0][0]}」（平均{best_struct_items[0][2]:.0f}いいね / {len(best_struct_items[0][1])}件）")

    # CTA
    if cta_stats:
        best_cta = max(cta_stats, key=lambda x: sum(i["likes"] for i in x[1]) / len(x[1]) if x[1] else 0)
        avg = sum(i["likes"] for i in best_cta[1]) / len(best_cta[1]) if best_cta[1] else 0
        lines.append(f"3. **最も効果的なCTA**: 「{best_cta[0]}」（平均{avg:.0f}いいね）")

    # キーワード
    if word_top:
        top3_words = [w[0] for w in word_top[:3]]
        lines.append(f"4. **頻出キーワードTOP3**: {', '.join(top3_words)}")

    lines.append("")

    # ファイル出力
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nレポート出力完了: {output_path}")
    return output_path


if __name__ == "__main__":
    df = load_and_filter("output/buzz_posts_20260215.xlsx")
    if df is not None:
        generate_report(df, "output/buzz_text_analysis_20260217.md")
