"""TOP10投稿を抽出するスクリプト"""

import pandas as pd
import json

def extract_top_posts():
    # 自分の投稿を読み込み
    self_df = pd.read_csv("output/TwExport_20260217_191942.csv", encoding='utf-8')
    self_df = self_df.rename(columns={
        'テキスト': '本文',
        'いいね数': 'いいね数',
        'imp': 'インプレッション数',
        '投稿日時': '投稿日時',
        'リプライ数': 'リプライ数',
        'RT数': 'リポスト数',
        'URL': 'URL'
    })

    # バズ投稿を読み込み
    buzz_df = pd.read_excel("output/buzz_posts_20260215.xlsx")

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

    # 自分のインプレッションTOP10
    self_top10 = self_df.nlargest(10, 'インプレッション数')

    # バズ投稿のいいね数TOP10
    buzz_top10 = buzz_df.nlargest(10, 'いいね数')

    # JSON形式で保存（分析用）
    self_data = []
    for idx, row in self_top10.iterrows():
        self_data.append({
            'rank': len(self_data) + 1,
            'text': str(row['本文']),
            'impressions': int(row['インプレッション数']),
            'likes': int(row['いいね数']),
            'retweets': int(row['リポスト数']),
            'replies': int(row['リプライ数']),
            'date': str(row['投稿日時']),
            'url': str(row.get('URL', ''))
        })

    buzz_data = []
    for idx, row in buzz_top10.iterrows():
        buzz_data.append({
            'rank': len(buzz_data) + 1,
            'text': str(row['本文']),
            'likes': int(row['いいね数']),
            'retweets': int(row.get('リポスト数', 0)),
            'replies': int(row.get('リプライ数', 0)),
            'username': str(row['ユーザー名']),
            'url': str(row.get('ポストURL', ''))
        })

    # JSON保存
    with open('output/top10_posts.json', 'w', encoding='utf-8') as f:
        json.dump({
            'self': self_data,
            'buzz': buzz_data
        }, f, ensure_ascii=False, indent=2)

    print("=== 自分のインプレッションTOP10 ===")
    for post in self_data:
        print(f"\n{post['rank']}位: {post['impressions']}インプ / {post['likes']}いいね")
        print(f"「{post['text'][:80]}...」")

    print("\n\n=== バズ投稿のいいね数TOP10 ===")
    for post in buzz_data:
        print(f"\n{post['rank']}位: {post['likes']}いいね (@{post['username']})")
        print(f"「{post['text'][:80]}...」")

    return self_data, buzz_data

if __name__ == "__main__":
    extract_top_posts()
