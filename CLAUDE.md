# バズ投稿分析プロジェクト

## ファイル構成

### 分析エンジン
- analyze_posts.py: 35関数の分析エンジン（冒頭パターン、カテゴリ、感情、CTA等）
- buzz_score_v2.py: バズ予測スコアv2（データ駆動重み最適化）
- algorithm_analysis.py: Xアルゴリズム分析（Grok/Phoenix重みベース）
- text_analysis.py: テキスト詳細分析
- writing_analysis.py: ライティング構造分析
- reader_psychology.py: 読者心理分析（なぜバズったか言語化）

### ポスト作成ツール
- cli_post_builder.py: CLIポストビルダー（スマホ対応・メニュー式）
  - `python cli_post_builder.py` → メニュー表示
  - `python cli_post_builder.py build` → 新規ポスト作成
  - `python cli_post_builder.py improve` → 過去投稿を改善
  - `python cli_post_builder.py score "テキスト"` → スコア診断
  - `python cli_post_builder.py psych "テキスト"` → 読者心理分析
  - `python cli_post_builder.py compare` → 2つのポスト比較
- generate_posts.py: 投稿テンプレート生成（バッチ版）
- competitor_analysis.py: 競合アカウント分析

### ダッシュボード
- app.py: Streamlitダッシュボード（8タブ）
  - tab8「投稿作成」に対話型ポストビルダー搭載
  - `streamlit run app.py` で起動（PC必要）
- import_csv.py: CSVインポート
- buzz_score_v2.py: スコア計算

### データ収集
- buzz_analyzer.py: データ収集

### その他
- x_algorithm_guide.md: Xアルゴリズム完全ガイド（2026年2月版）
- run_writing_analysis.py / run_advanced_analysis.py: 分析実行スクリプト
- visualize.py: チャート生成（現在不使用）
- dashboard.py: 旧Streamlit（現在不使用、app.pyに移行済み）

## 分析データ
- data/buzz_database.db: SQLiteデータベース（6240件）
- output/buzz_posts_20260215.xlsx: バズ投稿76件（元データ）
- output/TwExport_20260217_191942.csv: @Mr_boten自分の投稿（要再インポート）

## 完了済みレポート
- self_comparison_20260217.md: 自分vsバズ投稿比較
- strategy_rethink_20260217.md: 拓巳型バズ戦略
- writing_style_comparison_auto.md: ライティング比較
- reproduction_guide_20260217.md: 再現性ガイド
- generated_posts_20260217.md: 投稿テンプレート5パターン
- x_algorithm_analysis_20260221.md: Xアルゴリズム分析レポート
- reader_psychology_20260221.md: 読者心理分析レポート（6240件）

## 拓巳のバズ方程式
- 等身大の告白×具体的体験×18-21時投稿
- CTAなしでも伸びる、秘匿感フレーズが効果的
- 「ド素人」「正直」系の自己開示が最大の武器

## 読者心理の法則（reader_psychology.pyで分析済み）
- いいね: 共感（あるある）> 自己開示への応援 > 感嘆・尊敬
- RT: 有益情報の拡散 > 権威の借用 > 自己表現
- リプ: 意見表明 > 体験共有 > ツッコミ欲
- ブクマ: ノウハウ備忘録 > データ参照
- フォロー: 人物への興味 > 継続的価値 > 専門性

## Xアルゴリズム重み（公式値）
- リプへの返信（著者）: 75.0（150倍）← 最重要
- リプライ: 13.5（27倍）
- プロフクリック: 12.0（24倍）
- 会話クリック: 11.0（22倍）
- ブックマーク: 10.0（20倍）
- RT: 1.0（2倍）
- いいね: 0.5（1倍）← ほぼ無意味
- ネガティブ: -74.0（-148倍）
- 通報: -369.0（-738倍）
- Grok導入: トーン分析、外部リンク-50%、テキスト>動画+30%、スレッド3倍

## 次のタスク
1. 実践：CLIビルダーで投稿作成→Xに投稿→リプに必ず返信
2. 自分の投稿データを再インポート（ツイポスでエクスポート→DBにインポート）
3. 1-2週間後にツイポスで再エクスポート→効果検証（戦略適用前vs後）
4. 競合アカウント5件のデータ取得・横断比較（competitor_analysis.py）

## Git
- スマホ版はmasterにpush不可(403)、claude/ブランチにpush→PRでマージ
- PCではmasterに直接push可能

## 【自動ルール】
タスク完了時は毎回自動で以下を実行すること：
git add . && git commit -m "変更内容の要約" && git push
