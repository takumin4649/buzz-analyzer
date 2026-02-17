"""文章スタイル詳細分析の実行スクリプト

使い方：
1. 自分の投稿とバズ投稿のTOP10を比較
   python run_writing_analysis.py

2. カスタムデータで分析
   このスクリプトを参考に、任意のデータで分析可能
"""

import pandas as pd
import json
from writing_analysis import WritingAnalyzer, generate_detailed_report, generate_comparison_report


def load_top_posts_from_csv_and_excel(self_csv, buzz_xlsx, top_n=10):
    """CSVとExcelからTOP投稿を抽出"""

    # 自分の投稿を読み込み
    self_df = pd.read_csv(self_csv, encoding='utf-8')
    self_df = self_df.rename(columns={
        'テキスト': '本文',
        'いいね数': 'いいね数',
        'imp': 'インプレッション数',
        '投稿日時': '投稿日時',
        'リプライ数': 'リプライ数',
        'RT数': 'リポスト数'
    })

    # バズ投稿を読み込み
    buzz_df = pd.read_excel(buzz_xlsx)

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

    buzz_df = buzz_df[~buzz_df["本文"].apply(should_exclude)].copy()
    buzz_df = buzz_df.sort_values("いいね数", ascending=False)
    buzz_df = buzz_df.drop_duplicates(subset=["ユーザー名"], keep="first")

    # TOP N抽出
    self_top = self_df.nlargest(top_n, 'インプレッション数')
    buzz_top = buzz_df.nlargest(top_n, 'いいね数')

    # フォーマット変換
    self_posts = []
    for idx, row in self_top.iterrows():
        self_posts.append({
            'text': str(row['本文']),
            'metrics': {
                'インプレッション数': int(row['インプレッション数']),
                'いいね数': int(row['いいね数']),
                'リポスト数': int(row.get('リポスト数', 0)),
                'リプライ数': int(row.get('リプライ数', 0))
            },
            'title': f"{int(row['インプレッション数']):,}インプ / {int(row['いいね数'])}いいね"
        })

    buzz_posts = []
    for idx, row in buzz_top.iterrows():
        buzz_posts.append({
            'text': str(row['本文']),
            'metrics': {
                'いいね数': int(row['いいね数']),
                'リポスト数': int(row.get('リポスト数', 0)),
                'リプライ数': int(row.get('リプライ数', 0))
            },
            'title': f"{int(row['いいね数'])}いいね (@{row['ユーザー名']})"
        })

    return self_posts, buzz_posts


def main():
    """メイン処理"""
    print("=== 文章スタイル詳細分析を開始 ===\n")

    # データ読み込み
    print("1. データ読み込み中...")
    self_csv = "output/TwExport_20260217_191942.csv"
    buzz_xlsx = "output/buzz_posts_20260215.xlsx"

    self_posts, buzz_posts = load_top_posts_from_csv_and_excel(self_csv, buzz_xlsx, top_n=10)
    print(f"   自分の投稿TOP10: {len(self_posts)}件")
    print(f"   バズ投稿TOP10: {len(buzz_posts)}件\n")

    # 個別の詳細レポート生成
    print("2. 自分の投稿の詳細分析レポートを生成中...")
    self_report = generate_detailed_report(
        self_posts,
        "output/writing_analysis_self_top10.md",
        "自分のインプレッションTOP10 詳細分析"
    )
    print(f"   → {self_report}\n")

    print("3. バズ投稿の詳細分析レポートを生成中...")
    buzz_report = generate_detailed_report(
        buzz_posts,
        "output/writing_analysis_buzz_top10.md",
        "バズ投稿いいね数TOP10 詳細分析"
    )
    print(f"   → {buzz_report}\n")

    # 比較レポート生成
    print("4. 文章スタイル比較レポートを生成中...")
    comparison_report = generate_comparison_report(
        self_posts,
        buzz_posts,
        "自分の投稿TOP10",
        "バズ投稿TOP10",
        "output/writing_style_comparison_auto.md"
    )
    print(f"   → {comparison_report}\n")

    # 統計サマリー表示
    print("=== 分析完了 ===")
    print("\n生成されたレポート:")
    print(f"1. {self_report}")
    print(f"2. {buzz_report}")
    print(f"3. {comparison_report}")

    # クイック統計
    analyzer = WritingAnalyzer()

    print("\n【クイック統計】")

    # 自分の投稿の傾向
    self_openings = [analyzer.analyze_opening(p['text'])['pattern'] for p in self_posts]
    print(f"\n自分の冒頭パターンTOP3:")
    for pattern, count in pd.Series(self_openings).value_counts().head(3).items():
        print(f"  - {pattern}: {count}件")

    # バズ投稿の傾向
    buzz_openings = [analyzer.analyze_opening(p['text'])['pattern'] for p in buzz_posts]
    print(f"\nバズ投稿の冒頭パターンTOP3:")
    for pattern, count in pd.Series(buzz_openings).value_counts().head(3).items():
        print(f"  - {pattern}: {count}件")

    # 平均文字数
    self_avg_chars = sum(len(p['text']) for p in self_posts) / len(self_posts)
    buzz_avg_chars = sum(len(p['text']) for p in buzz_posts) / len(buzz_posts)
    print(f"\n平均文字数:")
    print(f"  - 自分: {self_avg_chars:.0f}文字")
    print(f"  - バズ: {buzz_avg_chars:.0f}文字")


if __name__ == "__main__":
    main()
