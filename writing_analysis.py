"""投稿の文章スタイル詳細分解・分析モジュール

各投稿について以下を自動分析：
- 冒頭（最初の1文）の役割
- 展開部の構造
- 感情の動き
- 締め方のパターン
- 文章のリズム
- なぜ伸びたか（推定）
"""

import os
import re
from typing import Dict, List, Tuple
import pandas as pd


class WritingAnalyzer:
    """投稿文章の詳細分析クラス"""

    def __init__(self):
        # 冒頭パターンの分類
        self.opening_patterns = {
            "疑問形": r"^.{0,50}[\?？]",
            "感嘆形": r"^[！!]{1,}|^.{0,30}[！!]{2,}",
            "呼びかけ形": r"^(あなた|君|皆|みんな|お前|貴方)",
            "仮定法": r"^(もし|もしも|仮に|〜だったら|〜なら)",
            "否定形": r"^(〜ない|まだ|やめ|するな|ダメ)",
            "数字強調": r"^\d+[選つ個件万円%人]",
            "秘匿情報": r"^(知らない|知らなかった|実は|本当は|正直|ぶっちゃけ|ガチで|マジで)",
            "自己開示": r"^(僕|私|俺|自分|ワイ|うち)は?"
        }

        # 感情トリガーのパターン
        self.emotion_patterns = {
            "驚き": ["ヤバい", "やばい", "すごい", "凄い", "エグい", "えぐい", "びっくり", "ビックリ", "マジで", "ガチで"],
            "共感": ["わかる", "そう", "あるある", "同じ", "僕も", "私も", "俺も"],
            "不安": ["怖い", "不安", "心配", "大丈夫", "どうしよう"],
            "期待": ["ワクワク", "楽しみ", "期待", "待ち遠しい"],
            "喜び": ["嬉しい", "やった", "最高", "良かった", "ありがとう"],
            "怒り": ["ムカつく", "腹立つ", "イライラ", "許せない", "最悪"],
            "困惑": ["意味わからん", "わからん", "なんで", "どうして", "え？"],
            "決意": ["やる", "やってやる", "絶対", "必ず", "頑張る"]
        }

        # 締めのパターン
        self.closing_patterns = {
            "行動喚起": r"(フォロー|いいね|リプ|RT|保存|拡散|シェア|チェック|見て|試して|やって).*[！!。\.]*$",
            "疑問投げかけ": r"[\?？]$",
            "余韻・省略": r"[\.．…]{2,}$",
            "絵文字締め": r"[🔥💪👍✨🎉🙏👇⬇↓]$",
            "決意表明": r"(やる|行く|進む|挑む|続ける|目指す|頑張る)[！!。\.]*$",
            "期待煽り": r"(楽しみ|期待|これから|今後|次|続き)[！!。\.]*$"
        }

    def analyze_opening(self, text: str) -> Dict[str, str]:
        """冒頭（最初の1文）を分析"""
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if not lines:
            return {"first_sentence": "", "pattern": "不明", "role": "不明"}

        first_line = lines[0]

        # パターン判定
        pattern = "その他"
        for name, regex in self.opening_patterns.items():
            if re.search(regex, first_line):
                pattern = name
                break

        # 役割を推定
        role_map = {
            "疑問形": "疑問を投げかけて読者の思考を引き出す",
            "感嘆形": "強い感情で注意を引く",
            "呼びかけ形": "読者に直接語りかけて引き込む",
            "仮定法": "想像させて自分事にさせる",
            "否定形": "常識を否定して興味を引く",
            "数字強調": "具体性で信頼を得る",
            "秘匿情報": "秘密の共有で好奇心を刺激",
            "自己開示": "親近感を作り共感を得る",
            "その他": "自然な語り口で入りやすくする"
        }

        return {
            "first_sentence": first_line,
            "pattern": pattern,
            "role": role_map.get(pattern, "読者の注意を引く")
        }

    def analyze_structure(self, text: str) -> Dict[str, any]:
        """文章の展開構造を分析"""
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        sentences = re.split(r'[。\.！!？?]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        # 基本統計
        stats = {
            "total_chars": len(text),
            "line_count": len(lines),
            "sentence_count": len(sentences),
            "avg_sentence_length": len(text) / max(len(sentences), 1)
        }

        # 構成要素の検出
        has_list = bool(re.search(r'^[・\-▶▸✅☑✓◆■●①②③④⑤⑥⑦⑧⑨⑩\d+[\.\)）]]', text, re.MULTILINE))
        has_url = bool(re.search(r'https?://', text))
        has_quote = bool(re.search(r'「.*?」', text))
        has_numbers = len(re.findall(r'\d+', text))

        # 展開パターンの判定
        if has_list:
            structure_type = "リスト型（箇条書きで整理）"
        elif len(sentences) <= 3:
            structure_type = "短文完結型（インパクト重視）"
        elif has_quote:
            structure_type = "引用型（会話や引用で臨場感）"
        else:
            structure_type = "説明型（論理的に展開）"

        return {
            "stats": stats,
            "has_list": has_list,
            "has_url": has_url,
            "has_quote": has_quote,
            "number_count": has_numbers,
            "structure_type": structure_type
        }

    def analyze_emotions(self, text: str) -> List[Tuple[str, List[str]]]:
        """感情の動きを分析"""
        # 文を3つのブロックに分割（導入・展開・締め）
        sentences = re.split(r'[。\.！!？?]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) == 0:
            return []

        # 各ブロックの感情を検出
        blocks = []
        if len(sentences) <= 3:
            blocks = [("全体", text)]
        else:
            third = len(sentences) // 3
            blocks = [
                ("導入", '。'.join(sentences[:third])),
                ("展開", '。'.join(sentences[third:third*2])),
                ("締め", '。'.join(sentences[third*2:]))
            ]

        emotion_flow = []
        for block_name, block_text in blocks:
            detected_emotions = []
            for emotion, keywords in self.emotion_patterns.items():
                if any(kw in block_text for kw in keywords):
                    detected_emotions.append(emotion)

            if detected_emotions:
                emotion_flow.append((block_name, detected_emotions))

        return emotion_flow

    def analyze_closing(self, text: str) -> Dict[str, str]:
        """締め方を分析"""
        # 最後の1-2文を取得
        sentences = re.split(r'[。\.！!？?]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return {"last_sentence": "", "pattern": "不明", "effect": "不明"}

        last_sentence = sentences[-1]

        # パターン判定
        pattern = "その他"
        for name, regex in self.closing_patterns.items():
            if re.search(regex, text[-50:]):  # 最後50文字で判定
                pattern = name
                break

        # 効果を推定
        effect_map = {
            "行動喚起": "読者に具体的な行動を促す",
            "疑問投げかけ": "考えさせて議論を誘発する",
            "余韻・省略": "想像の余地を残して余韻を作る",
            "絵文字締め": "感情を視覚化して印象づける",
            "決意表明": "決意を示して読者を鼓舞する",
            "期待煽り": "次への期待を高めてエンゲージメントを維持",
            "その他": "自然に締めて余韻を残す"
        }

        return {
            "last_sentence": last_sentence,
            "pattern": pattern,
            "effect": effect_map.get(pattern, "読者の印象に残す")
        }

    def analyze_rhythm(self, text: str) -> Dict[str, any]:
        """文章のリズムを分析"""
        sentences = re.split(r'[。\.！!？?]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return {"rhythm": "不明", "variation": 0, "punctuation_style": "不明"}

        # 文の長さのバラつき
        lengths = [len(s) for s in sentences]
        avg_length = sum(lengths) / len(lengths)
        variation = sum(abs(l - avg_length) for l in lengths) / len(lengths)

        # リズムの評価
        if variation < 10:
            rhythm = "単調（文の長さが均一）"
        elif variation < 30:
            rhythm = "バランス型（適度な長短の変化）"
        else:
            rhythm = "メリハリ型（文の長短が大きく変化）"

        # 句読点スタイル
        exclamation_count = text.count('！') + text.count('!')
        question_count = text.count('？') + text.count('?')
        ellipsis_count = text.count('…') + text.count('..')

        if exclamation_count >= 3:
            punctuation = "感嘆型（！の多用で興奮を表現）"
        elif question_count >= 2:
            punctuation = "疑問型（？で対話を誘発）"
        elif ellipsis_count >= 2:
            punctuation = "余韻型（…で間を作る）"
        else:
            punctuation = "標準型（バランスの取れた句読点）"

        # 口語表現の検出
        casual_markers = ['〜だよね', '〜だわ', '〜かな', '〜んだけど', '〜って', 'w', 'www']
        casual_count = sum(text.count(m) for m in casual_markers)

        return {
            "rhythm": rhythm,
            "variation": round(variation, 1),
            "punctuation_style": punctuation,
            "casual_degree": "高" if casual_count >= 3 else "中" if casual_count >= 1 else "低",
            "avg_sentence_length": round(avg_length, 1)
        }

    def estimate_success_factor(self, text: str, metrics: Dict[str, int]) -> str:
        """なぜ伸びたかを推定（1文で）"""
        # 各要素をスコアリング
        factors = []

        opening = self.analyze_opening(text)
        if opening['pattern'] in ['疑問形', '秘匿情報', '数字強調']:
            factors.append(f"冒頭の{opening['pattern']}で注意を引いた")

        structure = self.analyze_structure(text)
        if structure['has_list']:
            factors.append("リスト形式で情報を整理した")
        if structure['has_url']:
            factors.append("URLで詳細情報へ誘導した")
        if structure['number_count'] >= 3:
            factors.append("具体的な数字で信頼性を高めた")

        emotions = self.analyze_emotions(text)
        if len(emotions) >= 2:
            factors.append("感情の変化で読者を引き込んだ")

        closing = self.analyze_closing(text)
        if closing['pattern'] == '行動喚起':
            factors.append("CTAで拡散を促した")

        # メトリクスから判断
        if 'likes' in metrics and metrics['likes'] > 500:
            if structure['stats']['total_chars'] < 100:
                factors.append("短文でインパクトを最大化した")

        # 総合判断
        if factors:
            return "、".join(factors[:2]) + "ため"
        else:
            return "読者の共感または役立つ情報を提供したため"

    def analyze_post(self, text: str, metrics: Dict[str, int] = None) -> Dict[str, any]:
        """1つの投稿を完全分析"""
        if metrics is None:
            metrics = {}

        opening = self.analyze_opening(text)
        structure = self.analyze_structure(text)
        emotions = self.analyze_emotions(text)
        closing = self.analyze_closing(text)
        rhythm = self.analyze_rhythm(text)
        success_factor = self.estimate_success_factor(text, metrics)

        return {
            "text": text,
            "metrics": metrics,
            "opening": opening,
            "structure": structure,
            "emotions": emotions,
            "closing": closing,
            "rhythm": rhythm,
            "success_factor": success_factor
        }

    def compare_writing_styles(self, posts_a: List[Dict], posts_b: List[Dict],
                               label_a: str = "グループA", label_b: str = "グループB") -> Dict[str, any]:
        """2つの投稿グループの文章スタイルを比較"""

        def aggregate_analyses(posts):
            """複数投稿の分析結果を集計"""
            opening_patterns = []
            structure_types = []
            closing_patterns = []
            rhythm_types = []
            total_chars = []
            casual_degrees = []

            for post in posts:
                analysis = self.analyze_post(post['text'], post.get('metrics', {}))
                opening_patterns.append(analysis['opening']['pattern'])
                structure_types.append(analysis['structure']['structure_type'])
                closing_patterns.append(analysis['closing']['pattern'])
                rhythm_types.append(analysis['rhythm']['rhythm'])
                total_chars.append(analysis['structure']['stats']['total_chars'])
                casual_degrees.append(analysis['rhythm']['casual_degree'])

            return {
                "opening_distribution": pd.Series(opening_patterns).value_counts(normalize=True) * 100,
                "structure_distribution": pd.Series(structure_types).value_counts(normalize=True) * 100,
                "closing_distribution": pd.Series(closing_patterns).value_counts(normalize=True) * 100,
                "rhythm_distribution": pd.Series(rhythm_types).value_counts(normalize=True) * 100,
                "avg_chars": sum(total_chars) / len(total_chars) if total_chars else 0,
                "casual_high_rate": casual_degrees.count('高') / len(casual_degrees) * 100 if casual_degrees else 0
            }

        stats_a = aggregate_analyses(posts_a)
        stats_b = aggregate_analyses(posts_b)

        return {
            label_a: stats_a,
            label_b: stats_b
        }


def generate_detailed_report(posts: List[Dict], output_path: str, title: str = "投稿文章詳細分析レポート"):
    """投稿リストから詳細な文章分解レポートを生成"""
    analyzer = WritingAnalyzer()
    lines = []

    lines.append(f"# {title}")
    lines.append(f"\n**分析日**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**分析対象**: {len(posts)}件の投稿")
    lines.append("")

    for i, post in enumerate(posts, 1):
        analysis = analyzer.analyze_post(post['text'], post.get('metrics', {}))

        lines.append(f"---")
        lines.append(f"## {i}位: {post.get('title', f'投稿{i}')}")
        lines.append("")

        # メトリクス表示
        if analysis['metrics']:
            lines.append("**📊 データ**:")
            for key, value in analysis['metrics'].items():
                lines.append(f"- {key}: {value:,}")
            lines.append("")

        # 全文
        lines.append("**全文**:")
        lines.append(f"> {analysis['text']}")
        lines.append("")

        # 冒頭分析
        lines.append(f"**冒頭の役割** ({analysis['opening']['pattern']})")
        lines.append(f"- 最初の1文: 「{analysis['opening']['first_sentence']}」")
        lines.append(f"- 役割: {analysis['opening']['role']}")
        lines.append("")

        # 展開部
        lines.append(f"**展開部** ({analysis['structure']['structure_type']})")
        lines.append(f"- 文字数: {analysis['structure']['stats']['total_chars']}文字")
        lines.append(f"- 文の数: {analysis['structure']['stats']['sentence_count']}文")
        features = []
        if analysis['structure']['has_list']:
            features.append("リスト形式")
        if analysis['structure']['has_url']:
            features.append("URL含む")
        if analysis['structure']['has_quote']:
            features.append("引用あり")
        if analysis['structure']['number_count'] >= 3:
            features.append(f"数字{analysis['structure']['number_count']}個")
        if features:
            lines.append(f"- 特徴: {', '.join(features)}")
        lines.append("")

        # 感情の動き
        lines.append("**感情の動き**:")
        if analysis['emotions']:
            emotion_strs = [f"{block}: {', '.join(emotions)}" for block, emotions in analysis['emotions']]
            lines.append(f"- {' → '.join(emotion_strs)}")
        else:
            lines.append("- 感情の変化: 検出されず（事実ベースの投稿）")
        lines.append("")

        # 締め方
        lines.append(f"**締め方** ({analysis['closing']['pattern']})")
        lines.append(f"- 最後の1文: 「{analysis['closing']['last_sentence']}」")
        lines.append(f"- 効果: {analysis['closing']['effect']}")
        lines.append("")

        # リズム
        lines.append(f"**文章のリズム**:")
        lines.append(f"- タイプ: {analysis['rhythm']['rhythm']}")
        lines.append(f"- 平均文長: {analysis['rhythm']['avg_sentence_length']:.0f}文字")
        lines.append(f"- 句読点: {analysis['rhythm']['punctuation_style']}")
        lines.append(f"- 口語度: {analysis['rhythm']['casual_degree']}")
        lines.append("")

        # なぜ伸びたか
        lines.append(f"**📌 この投稿がなぜ伸びたか**:")
        lines.append(f"- {analysis['success_factor']}")
        lines.append("")

    # ファイル出力
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"レポート生成完了: {output_path}")
    return output_path


def generate_comparison_report(posts_a: List[Dict], posts_b: List[Dict],
                               label_a: str, label_b: str, output_path: str):
    """2グループの文章スタイル比較レポートを生成"""
    analyzer = WritingAnalyzer()

    # 個別の詳細分析
    lines = []
    lines.append(f"# {label_a} vs {label_b} 文章スタイル比較レポート")
    lines.append(f"\n**分析日**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**{label_a}**: {len(posts_a)}件")
    lines.append(f"**{label_b}**: {len(posts_b)}件")
    lines.append("")

    # グループAの詳細
    lines.append(f"---")
    lines.append(f"## 第1部：{label_a} 詳細分解")
    lines.append("")

    for i, post in enumerate(posts_a, 1):
        analysis = analyzer.analyze_post(post['text'], post.get('metrics', {}))
        lines.append(f"### {i}位: {post.get('title', f'投稿{i}')}")
        lines.append("")
        lines.append(f"**全文**: {analysis['text'][:100]}...")
        lines.append("")
        lines.append(f"- **冒頭**: {analysis['opening']['role']}")
        lines.append(f"- **展開**: {analysis['structure']['structure_type']}")
        if analysis['emotions']:
            emotion_flow = ' → '.join([', '.join(ems) for _, ems in analysis['emotions']])
            lines.append(f"- **感情**: {emotion_flow}")
        lines.append(f"- **締め**: {analysis['closing']['effect']}")
        lines.append(f"- **リズム**: {analysis['rhythm']['rhythm']}")
        lines.append(f"- **なぜ伸びたか**: {analysis['success_factor']}")
        lines.append("")

    # グループBの詳細
    lines.append(f"---")
    lines.append(f"## 第2部：{label_b} 詳細分解")
    lines.append("")

    for i, post in enumerate(posts_b, 1):
        analysis = analyzer.analyze_post(post['text'], post.get('metrics', {}))
        lines.append(f"### {i}位: {post.get('title', f'投稿{i}')}")
        lines.append("")
        lines.append(f"**全文**: {analysis['text'][:100]}...")
        lines.append("")
        lines.append(f"- **冒頭**: {analysis['opening']['role']}")
        lines.append(f"- **展開**: {analysis['structure']['structure_type']}")
        if analysis['emotions']:
            emotion_flow = ' → '.join([', '.join(ems) for _, ems in analysis['emotions']])
            lines.append(f"- **感情**: {emotion_flow}")
        lines.append(f"- **締め**: {analysis['closing']['effect']}")
        lines.append(f"- **リズム**: {analysis['rhythm']['rhythm']}")
        lines.append(f"- **なぜ伸びたか**: {analysis['success_factor']}")
        lines.append("")

    # 比較統計
    comparison = analyzer.compare_writing_styles(posts_a, posts_b, label_a, label_b)

    lines.append(f"---")
    lines.append(f"## 第3部：文章スタイルの決定的な違い")
    lines.append("")

    # 冒頭パターン比較
    lines.append("### 1. 冒頭パターンの違い")
    lines.append("")
    lines.append(f"| パターン | {label_a} | {label_b} |")
    lines.append("|:---|---:|---:|")
    all_patterns = set(comparison[label_a]['opening_distribution'].index) | set(comparison[label_b]['opening_distribution'].index)
    for pattern in sorted(all_patterns):
        pct_a = comparison[label_a]['opening_distribution'].get(pattern, 0)
        pct_b = comparison[label_b]['opening_distribution'].get(pattern, 0)
        lines.append(f"| {pattern} | {pct_a:.1f}% | {pct_b:.1f}% |")
    lines.append("")

    # 文章構成比較
    lines.append("### 2. 文章構成の違い")
    lines.append("")
    lines.append(f"| 構成タイプ | {label_a} | {label_b} |")
    lines.append("|:---|---:|---:|")
    all_structures = set(comparison[label_a]['structure_distribution'].index) | set(comparison[label_b]['structure_distribution'].index)
    for struct in sorted(all_structures):
        pct_a = comparison[label_a]['structure_distribution'].get(struct, 0)
        pct_b = comparison[label_b]['structure_distribution'].get(struct, 0)
        lines.append(f"| {struct} | {pct_a:.1f}% | {pct_b:.1f}% |")
    lines.append("")

    # 平均文字数
    lines.append("### 3. 文字数の違い")
    lines.append("")
    lines.append(f"- **{label_a}**: 平均 {comparison[label_a]['avg_chars']:.0f}文字")
    lines.append(f"- **{label_b}**: 平均 {comparison[label_b]['avg_chars']:.0f}文字")
    lines.append("")

    # 口語度
    lines.append("### 4. 口語表現の使用度")
    lines.append("")
    lines.append(f"- **{label_a}**: 口語度「高」の割合 {comparison[label_a]['casual_high_rate']:.1f}%")
    lines.append(f"- **{label_b}**: 口語度「高」の割合 {comparison[label_b]['casual_high_rate']:.1f}%")
    lines.append("")

    # まとめ
    lines.append("### 📌 決定的な違いのまとめ")
    lines.append("")

    # 自動で違いを検出
    differences = []

    # 冒頭パターンの最大の差
    opening_diffs = {}
    for pattern in all_patterns:
        pct_a = comparison[label_a]['opening_distribution'].get(pattern, 0)
        pct_b = comparison[label_b]['opening_distribution'].get(pattern, 0)
        opening_diffs[pattern] = abs(pct_a - pct_b)
    top_opening_diff = max(opening_diffs.items(), key=lambda x: x[1])
    if top_opening_diff[1] > 15:
        differences.append(f"冒頭パターンは「{top_opening_diff[0]}」の使用率が大きく異なる（差: {top_opening_diff[1]:.1f}%）")

    # 文字数の差
    char_diff = abs(comparison[label_a]['avg_chars'] - comparison[label_b]['avg_chars'])
    if char_diff > 30:
        longer = label_a if comparison[label_a]['avg_chars'] > comparison[label_b]['avg_chars'] else label_b
        differences.append(f"文字数は{longer}の方が平均{char_diff:.0f}文字長い")

    # 口語度の差
    casual_diff = abs(comparison[label_a]['casual_high_rate'] - comparison[label_b]['casual_high_rate'])
    if casual_diff > 20:
        more_casual = label_a if comparison[label_a]['casual_high_rate'] > comparison[label_b]['casual_high_rate'] else label_b
        differences.append(f"口語表現は{more_casual}の方が多く使われている（差: {casual_diff:.1f}%）")

    for i, diff in enumerate(differences, 1):
        lines.append(f"{i}. {diff}")

    if not differences:
        lines.append("両グループの文章スタイルは比較的似ている")

    lines.append("")

    # ファイル出力
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"比較レポート生成完了: {output_path}")
    return output_path


if __name__ == "__main__":
    # テスト用のサンプル投稿
    sample_posts = [
        {
            "text": "全くわからないド素人だけど、Claude Code始めてみた。いま調べながら触ってる段階なんだけど、これちょっとやばいかもしれない。無料で使えるやつでもある程度は自動化できてたけど、こっちの方がもう1段階えぐそうなんだよな。まだ何もわかってない。でも「わからないなりに触る」がいちばん早い気がしてきた。ここから自動化、どんどん進めていくわ。",
            "metrics": {"impressions": 160105, "likes": 981},
            "title": "160,105インプ / 981いいね"
        }
    ]

    analyzer = WritingAnalyzer()
    for post in sample_posts:
        analysis = analyzer.analyze_post(post['text'], post['metrics'])
        print(f"冒頭: {analysis['opening']}")
        print(f"構成: {analysis['structure']['structure_type']}")
        print(f"感情: {analysis['emotions']}")
        print(f"締め: {analysis['closing']}")
        print(f"リズム: {analysis['rhythm']}")
        print(f"成功要因: {analysis['success_factor']}")
