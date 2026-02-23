#!/bin/bash
set -euo pipefail

# Claude Code on the web のみ実行
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# ============================================================
# 依存パッケージのインストール
# ============================================================
echo "バズ分析ツールの環境をセットアップ中..."
pip install -q -r "${CLAUDE_PROJECT_DIR}/requirements.txt"
echo "依存パッケージ インストール完了"

# ============================================================
# プロジェクトのステータス表示（起動時のボス）
# ============================================================
python3 - << 'PYEOF'
import sqlite3
import os
from datetime import datetime

db_path = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", "."), "data/buzz_database.db")

print("")
print("=" * 55)
print("  バズ投稿分析プロジェクト - セッション開始")
print("=" * 55)

# DBの状態
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    latest = conn.execute("SELECT MAX(date) FROM posts").fetchone()[0]
    accounts = conn.execute("SELECT COUNT(DISTINCT account) FROM posts").fetchone()[0]
    conn.close()
    print(f"  DB: {total:,}件 / {accounts}アカウント")
    if latest:
        print(f"  最新データ: {str(latest)[:10]}")
else:
    print("  DB: 未作成（import_csv.pyでインポートしてください）")

# 今日の投稿タイミング
now = datetime.now()
hour = now.hour
if 18 <= hour <= 21:
    timing = "今がベストタイム！ (18-21時)"
elif hour < 18:
    remaining = 18 - hour
    timing = f"あと{remaining}時間でベストタイム (18時〜)"
else:
    timing = "今日のベストタイムは過ぎました (明日18-21時)"
print(f"  投稿タイミング: {timing}")

print("")
print("  使えるコマンド:")
print("  python cli_post_builder.py        → ポスト作成・改善")
print("  python competitor_analysis.py     → 競合分析")
print("  python reader_psychology.py       → 読者心理レポート")
print("  streamlit run app.py              → ダッシュボード(PC)")
print("")
print("  拓巳のバズ方程式:")
print("  等身大の告白 × 具体的体験 × 18-21時 × リプ必ず返信")
print("=" * 55)
print("")
PYEOF
