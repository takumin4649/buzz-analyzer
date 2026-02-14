"""buzz_analyzer.pyのモックテスト"""

import csv
import json
import os
import sys
from datetime import datetime
from unittest.mock import Mock, patch

# Windowsコンソールのエンコーディング対応
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# ダミーレスポンスデータ
MOCK_RESPONSE_SUCCESS = {
    "tweets": [
        {
            "id": "1234567890",
            "text": "最新のAI技術について解説します！ChatGPTやStable Diffusionの進化がすごい。 #AI #機械学習",
            "likeCount": 1500,
            "retweetCount": 300,
            "replyCount": 50,
            "createdAt": "2026-02-14T10:30:00.000Z",
            "author": {
                "userName": "ai_expert_jp",
                "followersCount": 50000
            }
        },
        {
            "id": "0987654321",
            "text": "AI画像生成ツールで作ったイラストです🎨\nプロンプトエンジニアリングのコツも紹介 #生成AI #イラスト",
            "likeCount": 2300,
            "retweetCount": 520,
            "replyCount": 80,
            "createdAt": "2026-02-13T15:45:00.000Z",
            "author": {
                "userName": "creative_ai",
                "followersCount": 120000
            }
        },
        {
            "id": "1122334455",
            "text": "企業向けAIソリューションの導入事例を紹介。業務効率が3倍になった実績あり。",
            "likeCount": 850,
            "retweetCount": 180,
            "replyCount": 25,
            "createdAt": "2026-02-12T09:20:00.000Z",
            "author": {
                "userName": "business_ai",
                "followersCount": 35000
            }
        }
    ]
}

MOCK_RESPONSE_EMPTY = {
    "tweets": []
}


def test_successful_fetch():
    """正常にデータを取得してCSVが作成されるケース"""
    print("\n【テスト1】正常なデータ取得")
    print("-" * 50)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_RESPONSE_SUCCESS

    with patch.dict(os.environ, {"TWITTER_API_KEY": "test-api-key"}):
        with patch("requests.get", return_value=mock_response):
            # buzz_analyzer.pyのfetch_buzz_posts関数を実行
            import buzz_analyzer
            buzz_analyzer.fetch_buzz_posts()

    # CSVファイルが作成されたか確認
    today = datetime.now().strftime("%Y%m%d")
    filename = f"buzz_posts_{today}.csv"

    if os.path.exists(filename):
        print(f"✓ CSVファイル作成成功: {filename}")

        # CSVの内容を確認
        with open(filename, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

            print(f"✓ 取得件数: {len(rows)}件")
            print("\n【CSV内容サンプル】")
            for i, row in enumerate(rows, 1):
                print(f"\n--- ポスト{i} ---")
                print(f"本文: {row['本文'][:50]}...")
                print(f"いいね数: {row['いいね数']}")
                print(f"リポスト数: {row['リポスト数']}")
                print(f"リプライ数: {row['リプライ数']}")
                print(f"投稿日時: {row['投稿日時']}")
                print(f"ユーザー名: {row['ユーザー名']}")
                print(f"フォロワー数: {row['フォロワー数']}")
                print(f"ポストURL: {row['ポストURL']}")

        # 文字化けチェック
        with open(filename, "r", encoding="utf-8-sig") as f:
            content = f.read()
            if "最新のAI技術" in content and "🎨" in content:
                print("\n✓ 日本語と絵文字が正しく保存されています（文字化けなし）")
            else:
                print("\n✗ 文字化けの可能性があります")

        # クリーンアップ
        os.remove(filename)
        print(f"\n✓ テストファイル削除完了")
    else:
        print(f"✗ CSVファイルが作成されませんでした")


def test_no_api_key():
    """APIキーが設定されていないケース"""
    print("\n【テスト2】APIキー未設定エラー")
    print("-" * 50)

    # 環境変数をクリア
    env_backup = os.environ.get("TWITTER_API_KEY")
    if "TWITTER_API_KEY" in os.environ:
        del os.environ["TWITTER_API_KEY"]

    exit_called = False
    original_exit = sys.exit

    def mock_exit(code=0):
        nonlocal exit_called
        exit_called = True
        raise SystemExit(code)

    sys.exit = mock_exit

    try:
        import buzz_analyzer
        import importlib
        importlib.reload(buzz_analyzer)
        buzz_analyzer.fetch_buzz_posts()
    except SystemExit:
        pass

    sys.exit = original_exit

    # 環境変数を復元
    if env_backup is not None:
        os.environ["TWITTER_API_KEY"] = env_backup

    if exit_called:
        print("✓ APIキー未設定時に適切にエラー終了しました")
    else:
        print("✗ エラーハンドリングが機能していません")


def test_http_401_error():
    """APIキーが無効なケース（401エラー）"""
    print("\n【テスト3】APIキー無効エラー（401）")
    print("-" * 50)

    import requests

    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("401 Unauthorized")

    exit_called = False
    original_exit = sys.exit

    def mock_exit(code=0):
        nonlocal exit_called
        exit_called = True
        raise SystemExit(code)

    sys.exit = mock_exit

    with patch.dict(os.environ, {"TWITTER_API_KEY": "invalid-key"}):
        with patch("requests.get", return_value=mock_response):
            try:
                import buzz_analyzer
                import importlib
                importlib.reload(buzz_analyzer)
                buzz_analyzer.fetch_buzz_posts()
            except SystemExit:
                pass

    sys.exit = original_exit

    if exit_called:
        print("✓ 401エラー時に適切にエラー終了しました")
    else:
        print("✗ エラーハンドリングが機能していません")


def test_empty_response():
    """該当ポストが見つからないケース"""
    print("\n【テスト4】該当ポストなし")
    print("-" * 50)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_RESPONSE_EMPTY
    mock_response.raise_for_status.return_value = None

    exit_code = None
    original_exit = sys.exit

    def mock_exit(code=0):
        nonlocal exit_code
        exit_code = code
        raise SystemExit(code)

    sys.exit = mock_exit

    with patch.dict(os.environ, {"TWITTER_API_KEY": "test-api-key"}):
        with patch("requests.get", return_value=mock_response):
            try:
                import buzz_analyzer
                import importlib
                importlib.reload(buzz_analyzer)
                buzz_analyzer.fetch_buzz_posts()
            except SystemExit:
                pass

    sys.exit = original_exit

    if exit_code == 0:
        print("✓ 該当ポストなしの場合に適切に終了しました")
    else:
        print(f"✗ エラーハンドリングが機能していません（終了コード: {exit_code}）")


if __name__ == "__main__":
    print("=" * 50)
    print("buzz_analyzer.py モックテスト開始")
    print("=" * 50)

    try:
        test_successful_fetch()
        test_no_api_key()
        test_http_401_error()
        test_empty_response()

        print("\n" + "=" * 50)
        print("全テスト完了")
        print("=" * 50)
    except Exception as e:
        print(f"\n✗ テスト実行中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
