# バズ投稿分析プロジェクト

## ファイル構成
- buzz_analyzer.py: データ収集
- analyze_posts.py: 35関数の分析エンジン
- text_analysis.py: テキスト詳細分析
- writing_analysis.py: ライティング構造分析
- algorithm_analysis.py: Xアルゴリズム分析（Grok/Phoenix重みベース）
- x_algorithm_guide.md: Xアルゴリズム完全ガイド（2026年2月版）
- run_writing_analysis.py: 分析実行スクリプト
- generate_posts.py: 投稿テンプレート生成
- visualize.py: チャート生成（現在不使用）
- dashboard.py: Streamlit（現在不使用）

## 分析データ
- output/buzz_posts_20260215.xlsx: バズ投稿76件
- output/TwExport_20260217_191942.csv: @Mr_boten自分の投稿

## 完了済みレポート
- self_comparison_20260217.md: 自分vsバズ投稿比較
- strategy_rethink_20260217.md: 拓巳型バズ戦略
- writing_style_comparison_auto.md: ライティング比較
- reproduction_guide_20260217.md: 再現性ガイド
- generated_posts_20260217.md: 投稿テンプレート5パターン

## 拓巳のバズ方程式
- 等身大の告白×具体的体験×18-21時投稿
- CTAなしでも伸びる、秘匿感フレーズが効果的
- 「ド素人」「正直」系の自己開示が最大の武器

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
1. 実践：戦略に基づいた投稿作成・投稿
2. 1-2週間後にツイポスで再エクスポート→効果検証
3. 競合アカウント5件のデータ取得・横断比較

## Git
- スマホ版はmasterにpush不可(403)、claude/ブランチにpush→PRでマージ
- PCではmasterに直接push可能

## 【自動ルール】
タスク完了時は毎回自動で以下を実行すること：
git add . && git commit -m "変更内容の要約" && git push
