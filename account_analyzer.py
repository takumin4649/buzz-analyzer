"""特定のXアカウントの投稿を取得して、アカウントごとの傾向を分析するスクリプト"""

import os
import sys
import time
import re
from datetime import datetime, timedelta
from collections import Counter
from statistics import mean, median

import requests
from dotenv import load_dotenv
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# .envファイルから環境変数を読み込む
load_dotenv()

# 対象アカウントリスト
TARGET_ACCOUNTS = [
    "1banana2546",
    "Naoki_GPT",
    "ethann_AI",
    "maind200",
    "gyarados__AI",
    "ComagerTon79278",
    "mamiya_afi",
    "takkun_life_ea",
    "ai_nepro",
]


def fetch_user_tweets(username, api_key, count=100):
    """指定されたユーザーの投稿を取得"""
    url = "https://api.twitterapi.io/twitter/user/tweets"
    headers = {"X-API-Key": api_key}
    params = {
        "username": username,
        "count": count,
    }

    print(f"  @{username} の投稿を取得中...")

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.ConnectionError:
        print(f"エラー: APIサーバーに接続できません（@{username}）")
        return []
    except requests.exceptions.Timeout:
        print(f"エラー: APIリクエストがタイムアウトしました（@{username}）")
        return []
    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            print(f"エラー: APIキーが無効です（@{username}）")
        elif response.status_code == 429:
            print(f"エラー: APIのレート制限に達しました（@{username}）")
        else:
            print(f"エラー: APIリクエストに失敗しました（@{username}）: HTTP {response.status_code}")
        return []
    except Exception as e:
        print(f"エラー: 予期しないエラーが発生しました（@{username}）: {e}")
        return []

    tweets = data.get("tweets", [])
    print(f"    → {len(tweets)}件取得")
    return tweets


def classify_opening_pattern(text):
    """冒頭パターンを分類"""
    # 改行や空白を除去して最初の文を取得
    first_line = text.strip().split("\n")[0].strip()

    # 数字提示パターン（冒頭に数字がある）
    if re.match(r"^\d+[.、。:：\s]", first_line):
        return "数字提示"

    # 疑問形パターン（？で終わる、または疑問詞で始まる）
    if "？" in first_line or "?" in first_line or re.match(r"^(何|どう|いつ|どこ|誰|なぜ|どの)", first_line):
        return "疑問形"

    # 断定形パターン（です、だ、である、ですで終わる）
    if re.search(r"(です|だ|である|ます|ました|でした)[\s。]*$", first_line):
        return "断定形"

    # 共感パターン（わかる、あるある、そう、ほんと、まじ など）
    if re.search(r"(わかる|あるある|そう|ほんと|まじ|やば|すご|えぐ)", first_line, re.IGNORECASE):
        return "共感"

    return "その他"


def detect_cta(text):
    """CTA（Call To Action）の有無を検出"""
    cta_patterns = [
        r"(やって|試して|使って|見て|読んで|チェック|クリック|登録|フォロー|リプ|RT|シェア)",
        r"(ください|してね|しよう|しましょう|おすすめ)",
        r"(こちら|リンク|プロフ|固定|bio)",
    ]

    for pattern in cta_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def count_line_breaks(text):
    """改行数をカウント"""
    return text.count("\n")


def analyze_posting_time(tweets):
    """投稿時間帯の傾向を分析"""
    hours = []
    for tweet in tweets:
        created_at = tweet.get("createdAt", "")
        if created_at:
            try:
                # ISO 8601形式の日時をパース
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                # 日本時間に変換（+9時間）
                dt_jst = dt + timedelta(hours=9)
                hours.append(dt_jst.hour)
            except Exception:
                continue

    if not hours:
        return {}

    # 時間帯を分類
    morning = sum(1 for h in hours if 6 <= h < 12)  # 6-11時
    afternoon = sum(1 for h in hours if 12 <= h < 18)  # 12-17時
    evening = sum(1 for h in hours if 18 <= h < 24)  # 18-23時
    night = sum(1 for h in hours if 0 <= h < 6)  # 0-5時

    total = len(hours)
    return {
        "朝（6-11時）": f"{morning}件 ({morning/total*100:.1f}%)",
        "昼（12-17時）": f"{afternoon}件 ({afternoon/total*100:.1f}%)",
        "夕方・夜（18-23時）": f"{evening}件 ({evening/total*100:.1f}%)",
        "深夜（0-5時）": f"{night}件 ({night/total*100:.1f}%)",
    }


def calculate_posting_frequency(tweets):
    """投稿頻度を計算（1日あたり何件）"""
    if not tweets:
        return 0

    dates = []
    for tweet in tweets:
        created_at = tweet.get("createdAt", "")
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                dates.append(dt.date())
            except Exception:
                continue

    if not dates:
        return 0

    # 最古と最新の日付の差を計算
    min_date = min(dates)
    max_date = max(dates)
    days = (max_date - min_date).days + 1

    return len(tweets) / days if days > 0 else 0


def analyze_account(username, tweets):
    """アカウントごとの分析を実行"""
    if not tweets:
        return None

    # エンゲージメント指標を計算
    likes = [tweet.get("likeCount", 0) for tweet in tweets]
    retweets = [tweet.get("retweetCount", 0) for tweet in tweets]
    replies = [tweet.get("replyCount", 0) for tweet in tweets]

    # 各投稿にエンゲージメントスコアを付与（いいね + リポスト*2 + リプライ*3）
    for tweet in tweets:
        tweet["engagement_score"] = (
            tweet.get("likeCount", 0) +
            tweet.get("retweetCount", 0) * 2 +
            tweet.get("replyCount", 0) * 3
        )

    # バズった投稿TOP3とバズらなかった投稿TOP3
    sorted_tweets = sorted(tweets, key=lambda x: x["engagement_score"], reverse=True)
    top3 = sorted_tweets[:3]
    bottom3 = sorted_tweets[-3:]

    # 冒頭パターン分類
    opening_patterns = [classify_opening_pattern(tweet.get("text", "")) for tweet in tweets]
    pattern_counter = Counter(opening_patterns)

    # CTA使用率
    cta_count = sum(1 for tweet in tweets if detect_cta(tweet.get("text", "")))
    cta_rate = cta_count / len(tweets) * 100 if tweets else 0

    # 改行数の傾向
    line_breaks = [count_line_breaks(tweet.get("text", "")) for tweet in tweets]

    # 投稿頻度
    posting_freq = calculate_posting_frequency(tweets)

    # 投稿時間帯の傾向
    time_distribution = analyze_posting_time(tweets)

    return {
        "username": username,
        "total_tweets": len(tweets),
        "avg_likes": mean(likes) if likes else 0,
        "median_likes": median(likes) if likes else 0,
        "avg_retweets": mean(retweets) if retweets else 0,
        "median_retweets": median(retweets) if retweets else 0,
        "avg_replies": mean(replies) if replies else 0,
        "top3_tweets": top3,
        "bottom3_tweets": bottom3,
        "opening_patterns": dict(pattern_counter),
        "cta_rate": cta_rate,
        "avg_line_breaks": mean(line_breaks) if line_breaks else 0,
        "median_line_breaks": median(line_breaks) if line_breaks else 0,
        "posting_frequency": posting_freq,
        "time_distribution": time_distribution,
    }


def format_tweet_for_markdown(tweet, rank):
    """投稿をMarkdown形式でフォーマット"""
    text = tweet.get("text", "").replace("\n", " ")[:100]  # 最初の100文字
    likes = tweet.get("likeCount", 0)
    retweets = tweet.get("retweetCount", 0)
    replies = tweet.get("replyCount", 0)
    score = tweet.get("engagement_score", 0)

    username = tweet.get("author", {}).get("userName", "")
    tweet_id = tweet.get("id", "")
    url = f"https://x.com/{username}/status/{tweet_id}" if username and tweet_id else ""

    return f"{rank}. **{text}...** \n   いいね: {likes} | RT: {retweets} | リプ: {replies} | スコア: {score}\n   [{url}]({url})\n"


def generate_markdown_report(all_analyses, output_path):
    """Markdown形式のレポートを生成"""
    today = datetime.now().strftime("%Y年%m月%d日")

    md_content = f"""# Xアカウント分析レポート

**生成日時**: {today}

---

## 📊 全アカウント横断比較

### エンゲージメント率ランキング（平均いいね数順）

"""

    # 平均いいね数でソート
    sorted_analyses = sorted(all_analyses, key=lambda x: x["avg_likes"], reverse=True)

    for i, analysis in enumerate(sorted_analyses, 1):
        username = analysis["username"]
        avg_likes = analysis["avg_likes"]
        avg_retweets = analysis["avg_retweets"]
        posting_freq = analysis["posting_frequency"]

        md_content += f"{i}. **@{username}**\n"
        md_content += f"   - 平均いいね: {avg_likes:.1f}\n"
        md_content += f"   - 平均RT: {avg_retweets:.1f}\n"
        md_content += f"   - 投稿頻度: {posting_freq:.2f}件/日\n\n"

    # 共通パターン分析
    md_content += "\n### 共通してバズっているパターン\n\n"

    # 全アカウントのTOP3投稿から共通パターンを抽出
    all_top_patterns = []
    for analysis in all_analyses:
        for tweet in analysis["top3_tweets"]:
            pattern = classify_opening_pattern(tweet.get("text", ""))
            all_top_patterns.append(pattern)

    top_pattern_counter = Counter(all_top_patterns)
    for pattern, count in top_pattern_counter.most_common():
        md_content += f"- **{pattern}**: {count}件\n"

    md_content += "\n---\n\n"

    # 各アカウントの詳細分析
    for analysis in all_analyses:
        username = analysis["username"]

        md_content += f"## 👤 @{username}\n\n"

        # 基本統計
        md_content += "### 📈 基本統計\n\n"
        md_content += f"- **投稿数**: {analysis['total_tweets']}件\n"
        md_content += f"- **平均いいね数**: {analysis['avg_likes']:.1f} （中央値: {analysis['median_likes']:.0f}）\n"
        md_content += f"- **平均RT数**: {analysis['avg_retweets']:.1f} （中央値: {analysis['median_retweets']:.0f}）\n"
        md_content += f"- **平均リプライ数**: {analysis['avg_replies']:.1f}\n"
        md_content += f"- **投稿頻度**: {analysis['posting_frequency']:.2f}件/日\n\n"

        # 投稿時間帯
        md_content += "### ⏰ 投稿時間帯の傾向\n\n"
        for time_slot, value in analysis["time_distribution"].items():
            md_content += f"- {time_slot}: {value}\n"
        md_content += "\n"

        # バズった投稿TOP3
        md_content += "### 🔥 最もバズった投稿 TOP3\n\n"
        for i, tweet in enumerate(analysis["top3_tweets"], 1):
            md_content += format_tweet_for_markdown(tweet, i)
        md_content += "\n"

        # バズらなかった投稿TOP3
        md_content += "### 📉 最もバズらなかった投稿 TOP3\n\n"
        for i, tweet in enumerate(analysis["bottom3_tweets"], 1):
            md_content += format_tweet_for_markdown(tweet, i)
        md_content += "\n"

        # 冒頭パターン分析
        md_content += "### 🎯 冒頭パターン分析\n\n"
        total_patterns = sum(analysis["opening_patterns"].values())
        for pattern, count in sorted(analysis["opening_patterns"].items(), key=lambda x: x[1], reverse=True):
            percentage = count / total_patterns * 100 if total_patterns > 0 else 0
            md_content += f"- **{pattern}**: {count}件 ({percentage:.1f}%)\n"
        md_content += "\n"

        # CTA使用率
        md_content += f"### 📢 CTA使用率: {analysis['cta_rate']:.1f}%\n\n"

        # 改行数の傾向
        md_content += f"### 📝 改行数の傾向\n\n"
        md_content += f"- **平均改行数**: {analysis['avg_line_breaks']:.1f}\n"
        md_content += f"- **中央値**: {analysis['median_line_breaks']:.0f}\n\n"

        # 勝ちパターン
        md_content += "### 💡 このアカウントの勝ちパターン\n\n"

        # TOP3投稿の共通点を分析
        top3_patterns = [classify_opening_pattern(tweet.get("text", "")) for tweet in analysis["top3_tweets"]]
        top3_pattern_counter = Counter(top3_patterns)
        most_common_pattern = top3_pattern_counter.most_common(1)[0][0] if top3_pattern_counter else "不明"

        top3_has_cta = sum(1 for tweet in analysis["top3_tweets"] if detect_cta(tweet.get("text", "")))

        md_content += f"- **効果的な冒頭パターン**: {most_common_pattern}\n"
        md_content += f"- **TOP3でのCTA使用**: {top3_has_cta}/3件\n"

        # 平均より高いエンゲージメント要因
        avg_engagement = mean([t["engagement_score"] for t in analysis["top3_tweets"]])
        md_content += f"- **TOP3平均エンゲージメントスコア**: {avg_engagement:.0f}\n"

        md_content += "\n---\n\n"

    # ファイルに保存
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"Markdownレポート保存完了: {output_path}")


def save_to_excel(all_tweets_by_account, output_path):
    """全投稿データをExcelに保存（アカウントごとにシート分け）"""
    wb = Workbook()

    # デフォルトシートを削除
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])

    for username, tweets in all_tweets_by_account.items():
        # シート名（最大31文字制限）
        sheet_name = f"@{username}"[:31]
        ws = wb.create_sheet(title=sheet_name)

        # ヘッダー
        headers = ["本文", "いいね数", "RT数", "リプライ数", "投稿日時", "投稿URL", "冒頭パターン", "CTA有無", "改行数"]
        ws.append(headers)

        # ヘッダー行のスタイル設定
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # データ行を追加
        for tweet in tweets:
            text = tweet.get("text", "")
            tweet_id = tweet.get("id", "")
            post_url = f"https://x.com/{username}/status/{tweet_id}" if tweet_id else ""

            ws.append([
                text,
                tweet.get("likeCount", 0),
                tweet.get("retweetCount", 0),
                tweet.get("replyCount", 0),
                tweet.get("createdAt", ""),
                post_url,
                classify_opening_pattern(text),
                "あり" if detect_cta(text) else "なし",
                count_line_breaks(text),
            ])

        # 本文列（A列）の折り返し設定
        for row in range(2, len(tweets) + 2):
            cell = ws.cell(row=row, column=1)
            cell.alignment = Alignment(wrap_text=True, vertical="top")

        # 列幅の調整
        column_widths = {
            1: 60,  # 本文
            2: 12,  # いいね数
            3: 12,  # RT数
            4: 12,  # リプライ数
            5: 25,  # 投稿日時
            6: 50,  # 投稿URL
            7: 15,  # 冒頭パターン
            8: 12,  # CTA有無
            9: 10,  # 改行数
        }

        for col_num, width in column_widths.items():
            ws.column_dimensions[get_column_letter(col_num)].width = width

        # オートフィルター設定
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(tweets) + 1}"

    # 保存
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    wb.save(output_path)
    print(f"Excel保存完了: {output_path}")


def main():
    """メイン処理"""
    # APIキー取得
    api_key = os.environ.get("TWITTER_API_KEY")
    if not api_key:
        print("エラー: 環境変数 TWITTER_API_KEY が設定されていません。")
        print("設定例: export TWITTER_API_KEY='your-api-key'")
        sys.exit(1)

    print("=" * 60)
    print("Xアカウント分析スクリプト")
    print("=" * 60)
    print(f"対象アカウント数: {len(TARGET_ACCOUNTS)}個")
    print()

    # 各アカウントの投稿を取得
    all_tweets_by_account = {}
    all_analyses = []

    for i, username in enumerate(TARGET_ACCOUNTS):
        print(f"[{i+1}/{len(TARGET_ACCOUNTS)}] @{username} を処理中...")

        tweets = fetch_user_tweets(username, api_key, count=100)

        if tweets:
            all_tweets_by_account[username] = tweets

            # アカウント分析を実行
            analysis = analyze_account(username, tweets)
            if analysis:
                all_analyses.append(analysis)

        # レート制限対策：最後のアカウント以外は待機
        if i < len(TARGET_ACCOUNTS) - 1:
            print("    レート制限対策で3秒待機中...")
            time.sleep(3)

        print()

    if not all_analyses:
        print("分析可能なデータが取得できませんでした。")
        sys.exit(0)

    print(f"分析完了: {len(all_analyses)}アカウント")
    print()

    # 出力ファイルパス
    today = datetime.now().strftime("%Y%m%d")
    output_dir = "output"
    md_path = os.path.join(output_dir, f"account_analysis_{today}.md")
    excel_path = os.path.join(output_dir, f"account_posts_{today}.xlsx")

    # Markdownレポート生成
    print("Markdownレポートを生成中...")
    generate_markdown_report(all_analyses, md_path)

    # Excel保存
    print("Excelファイルを生成中...")
    save_to_excel(all_tweets_by_account, excel_path)

    print()
    print("=" * 60)
    print("すべての処理が完了しました！")
    print("=" * 60)


if __name__ == "__main__":
    main()
