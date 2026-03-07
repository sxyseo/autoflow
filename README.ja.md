# Autoflow

<div align="center">

**自律型ソフトウェア配信コントロールプレーン**

OpenAIの「Harness Engineering」哲学とAI駆動開発ワークフローに触発されて

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**[English](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Español](README.es.md)**

</div>

---

## 目次

- [概要](#概要)
- [哲学](#哲学)
- [主要な概念](#主要な概念)
- [アーキテクチャ](#アーキテクチャ)
- [機能](#機能)
- [クイックスタート](#クイックスタート)
- [設定](#設定)
- [使用方法](#使用方法)
- [高度なトピック](#高度なトピック)
- [ベストプラクティス](#ベストプラクティス)
- [トラブルシューティング](#トラブルシューティング)
- [貢献](#貢献)
- [ライセンス](#ライセンス)

## 概要

**Autoflow**は、自律型ソフトウェア配信のための軽量コントロールプレーンです。AIエージェントが仕様作成、タスク分解、実装、レビュー、保守の周りで反復可能なループを実行し、具体的なコーディング作業を様々なAIエージェントバックエンドに委任できるようにします。

### Autoflowの独自性

従来の開発ツールとは異なり、Autoflowは**AI駆動開発**のために最初から構築されています：

- **状態を真実のソースとする**：すべての仕様、タスク、実行、決断が明示的に追跡されます
- **決定論的プロンプト**：再利用可能なスキルとテンプレートが一貫したエージェント動作を保証します
- **交換可能なバックエンド**：様々なAIエージェントを互換性を持って使用できます
- **バックグラウンド実行**：エージェントは`tmux`を介して自律的に実行され、ワークフローをブロックしません
- **自動化ゲート**：レビュー、テスト、マージチェックが不正なコミットを防ぎます
- **完全復旧**：すべての実行がログ記録され、透明性とデバッグのために再開可能です

### 目標：信頼できるAI自律性

最初の目標は**完全な自律性ではなく**、**信頼できるハーネス**です：

- 人間は目標、境界、受入基準を定義します
- AIはこれらの制約内で自律的に動作します
- すべての変更はテスト、レビュー、原子コミットされます
- 失敗した反復は人間の介入ではなく自動修正をトリガーします

## 哲学

### Harness Engineering

Autoflowは[OpenAIのHarness Engineering](https://openai.com/index/harness-engineering/)哲学に触発されています：**強力なエージェントは強力なハーネスから生まれます**。

ハーネスは以下を提供します：
- **評価**：成功と失敗の明確な指標
- **オーケストレーション**：調整されたマルチエージェントワークフロー
- **チェックポイント**：回復可能な状態とロールバック機能
- **契約**：ツール使用のための明確に定義されたインターフェース

### AI自己完結ループ

Autoflowは自律的な開発サイクルを実現します：

```
従来のAIコーディング：
人間が問題発見 → 人間がプロンプト作成 → AIがコード作成 → 人間が検証 → (繰り返し)

Autoflowワークフロー：
AIが問題発見 → AIが修正 → AIがテスト → AIがコミット → (1-2分ごとにループ)
```

**主要な洞察**：
1. **自動化テストは前提条件**：すべてのコミットはテストに合格する必要があります
2. **AI自己完結ループ**：AIが自律的に発見、修正、テスト、コミットを行います
3. **細粒度のコミット**：小さな変更（数行）が安全で高速な反復を可能にします
4. **実行ではなくルールの人間関与**：人間が境界を設定；AIが実行を処理します

### 仕様駆動開発

Autoflowは仕様駆動開発の原則を適用します：

- **仕様**は意図、制約、受入基準を定義します
- **タスク**は依存関係とステータスを持つ作業単位を定義します
- **スキル**は各ロールの再利用可能なワークフローを定義します
- **実行**は完全なコンテキストを持つ具体的な実行を保存します
- **エージェント**は論理ロールを具体的なAIバックエンドにマッピングします

## 主要な概念

### 状態階層

```
.autoflow/
├── specs/           # 製品の意図と制約
│   └── <slug>/
│       ├── SPEC.md              # 要件と制約
│       ├── TASKS.json           # タスクグラフとステータス
│       ├── QA_FIX_REQUEST.md    # レビュー所見（markdown）
│       ├── QA_FIX_REQUEST.json  # レビュー所見（構造化）
│       └── events.jsonl         # イベントログ
├── tasks/           # タスク定義とステータス
├── runs/            # 実行ごとのプロンプト、ログ、出力
│   └── <timestamp>-<role>-<spec>-<task>/
│       ├── prompt.md            # エージェントに送信された完全なプロンプト
│       ├── summary.md           # エージェントの要約
│       ├── run.sh               # 実行スクリプト
│       └── metadata.json        # 実行メタデータ
├── memory/          # スコープ付きメモリキャプチャ
│   ├── global.md                # 仕様間の教訓
│   └── specs/
│       └── <slug>.md            # 仕様ごとのコンテキスト
├── worktrees/       # 仕様ごとのgitワークツリー
└── logs/            # 実行ログ
```

### タスクステータスワークフロー

```
todo → in_progress → in_review → done
                   ↓           ↑
              needs_changes    |
                   ↓           |
                blocked ←─────┘
                   ↓
                  todo
```

**有効なステータス**：
- `todo`：開始準備完了
- `in_progress`：現在実行中
- `in_review`：レビュー待ち
- `done`：完了および承認済み
- `needs_changes`：レビューで問題が発見
- `blocked`：依存関係を待機中

### 実行結果

**有効な結果**：
- `success`：タスクが正常に完了
- `needs_changes`：完了 but 修正が必要
- `blocked`：依存関係のため継続不可
- `failed`：実行失敗

### スキルとロール

Autoflowは**スキル**を再利用可能なワークフローとして定義します：

| スキル | ロール | 説明 |
|-------|--------|-------------|
| `spec-writer` | プランナー | 意図を構造化された仕様に変換 |
| `task-graph-manager` | アーキテクト | 実行グラフの導出と改良 |
| `implementation-runner` | 実装者 | 境界付き範囲のコーディングスライスを実行 |
| `reviewer` | 品質保証 | レビュー、回帰、マージチェックを実行 |
| `maintainer` | オペレーター | 問題トリアージ、依存関係アップグレード、クリーンアップ |

各スキルには以下が含まれます：
- **ワークフロー説明**：ステップバイステッププロセス
- **ロールフレーミング**：一貫したエージェントペルソナのためのテンプレート
- **ルールと制約**：エージェントができることとできないこと
- **出力形式**：期待されるアーティファクトと引き継ぎ

### エージェントプロトコル

Autoflowは複数のエージェントプロトコルをサポートします：

#### CLIプロトコル (codex, claude)

```json
{
  "protocol": "cli",
  "command": "claude",
  "args": ["--full-auto"],
  "model_profile": "implementation",
  "memory_scopes": ["global", "spec"],
  "resume": {
    "mode": "subcommand",
    "subcommand": "resume",
    "args": ["--last"]
  }
}
```

#### ACPプロトコル (acp-agent)

```json
{
  "protocol": "acp",
  "transport": {
    "type": "stdio",
    "command": "my-agent",
    "args": []
  },
  "prompt_mode": "argv"
}
```

## アーキテクチャ

### 4層システム

```
┌─────────────────────────────────────────────────────────────┐
│                  レイヤー4：ガバナンス                        │
│              レビューゲート、CI/CD、ブランチポリシー          │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                  レイヤー3：実行                             │
│           仕様、ロール、エージェント、プロンプト、ワークスペース│
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                  レイヤー2：ロール（スキル）                  │
│    Spec-Writer、Task-Graph-Manager、Implementation-Runner、  │
│              Reviewer、Maintainer、Iteration-Manager         │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                  レイヤー1：コントロールプレーン              │
│              状態、設定、メモリ、発見                         │
└─────────────────────────────────────────────────────────────┘
```

## 機能

### 1. 明示的な状態管理

開発プロセスのすべての側面が明示的に追跡されます：

- **仕様**：意図、要件、制約、受入基準
- **タスク**：依存関係、ステータス、割り当てを持つ作業単位
- **実行**：プロンプト、出力、メタデータを含む完全な実行履歴
- **メモリ**：仕様や実行間のスコープ付き学習キャプチャ
- **イベント**：監査と復旧のための仕様ごとのイベントログ

### 2. 決定論的プロンプトアセンブリ

Autoflowは以下を通じて一貫したエージェント動作を保証します：

- **スキル定義**：明確なステップを持つ再利用可能なワークフロー
- **ロールテンプレート**：一貫したエージェントペルソナのためのロールフレーミング
- **コンテキスト注入**：関連する状態、メモリ、所見の自動包含
- **プロンプトバージョニング**：再現性のために各実行に完全なプロンプトを保存

### 3. 交換可能なエージェントバックエンド

統一プロトコルを通じて複数のAIバックエンドをサポート：

- **CLIプロトコル**：コマンドラインエージェント用
- **ACPプロトコル**：Agent Communication Protocolエージェント用
- **ネイティブ継続**：エージェント固有の再開メカニズム
- **動的フォールバック**：失敗時の自動エージェント選択

### 4. バックグラウンド実行

`tmux`を介した自律操作：

- **ノンブロッキング**：実行がバックグラウンドで実行され、ワークフローを中断しません
- **アタッチ可能**：実行をリアルタイムで監視または後でログを確認
- **再開可能**：中断された実行のネイティブ継続サポート
- **リソース管理**：エージェントと仕様ごとの同時実行制限

### 5. レビューとマージゲート

自動化された品質チェックが不正なコミットを防止：

- **構造化された所見**：位置、重大度、修正を含む機械可読QAアーティファクト
- **ハッシュベースの承認**：実装ハッシュは承認されたレビューと一致する必要があります
- **ゲート強制**：システムは計画変更後の実装をブロックします
- **タスク駆動の再試行**：構造化された所見が修正プロンプトに注入されます

### 6. メモリと学習

実行間で蓄積された知恵：

- **グローバルメモリ**：仕様間の教訓とパターン
- **仕様メモリ**：仕様ごとのコンテキストと履歴
- **ストラテジメモリ**：繰り返されるブロッカーのプレイブック
- **自動キャプチャ**：成功した実行から抽出されたメモリ
- **プロンプト注入**：エージェント設定に基づいて自動的に含まれるコンテキスト

### 7. ワークツリー分離

安全な並列開発：

- **仕様ごとのワークツリー**：分離されたgitワーキングツリー
- **クリーンなメインリポジトリ**：メインブランチは元の状態を維持
- **原子マージ**：承認後のみ変更をマージ
- **簡単なロールバック**：失敗時にワークツリーを revert

### 8. 継続的反復

スケジュールされた自律開発：

- **ティックベースのループ**：チェック、コミット、ディスパッチ、プッシュ
- **自動コミット**：プレフィックス付きメッセージによる記述的コミット
- **検証**：コミット前テストとチェック
- **進行状況追跡**：自動タスクステータス進行

## クイックスタート

### 前提条件

- Python 3.10以降
- Git
- tmux
- AIエージェントバックエンド (Claude Code、Codex、またはカスタム)

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/your-org/autoflow.git
cd autoflow

# （オプション）仮想環境を作成
python3 -m venv .venv
source .venv/bin/activate

# 依存関係をインストール
pip install -r requirements.txt
```

### 初期化

```bash
# 1. ローカル状態ディレクトリを設定
python3 scripts/autoflow.py init

# 2. システム設定を初期化
python3 scripts/autoflow.py init-system-config

# 3. エージェント設定をコピーしてカスタマイズ
cp config/agents.example.json .autoflow/agents.json

# 4. AIバックエンドを追加するためにエージェント設定を編集
# エージェントを設定するには.autoflow/agents.jsonを編集

# 5. ローカル/ACPエージェントを発見して同期
python3 scripts/autoflow.py sync-agents
```

### 最初の仕様を作成

```bash
python3 scripts/autoflow.py new-spec \
  --slug my-first-project \
  --title "私の最初のAIプロジェクト" \
  --summary "素晴らしいAI駆動アプリケーションを構築"
```

### タスクグラフを生成

```bash
# AIが仕様をタスクに分解させる
python3 scripts/autoflow.py init-tasks --spec my-first-project

# ワークフロー状態を表示
python3 scripts/autoflow.py workflow-state --spec my-first-project
```

### 自律開発を開始

```bash
# 継続的反復を有効化
python3 scripts/continuous_iteration.py \
  --spec my-first-project \
  --config config/continuous-iteration.example.json \
  --commit-if-dirty \
  --dispatch \
  --push
```

これだけです！Autoflowは以下を行います：
1. 完了した作業をチェック
2. 記述的なメッセージで変更をコミット
3. 検証テストを実行
4. 次の準備完了タスクをディスパッチ
5. バックグラウンドでエージェントを起動
6. 2-5分ごとに繰り返し

## 設定

### エージェント設定 (`.autoflow/agents.json`)

```json
{
  "agents": {
    "claude-impl": {
      "name": "Claude実装エージェント",
      "protocol": "cli",
      "command": "claude",
      "args": ["--full-auto"],
      "model_profile": "implementation",
      "tool_profile": "default",
      "memory_scopes": ["global", "spec"],
      "roles": ["implementation-runner", "maintainer"],
      "max_concurrent": 3,
      "resume": {
        "mode": "subcommand",
        "subcommand": "resume",
        "args": ["--last"]
      }
    },
    "codex-spec": {
      "name": "Codex仕様エージェント",
      "protocol": "cli",
      "command": "codex",
      "args": ["--full-auto"],
      "model_profile": "spec",
      "tool_profile": "spec-tools",
      "memory_scopes": ["global"],
      "roles": ["spec-writer", "task-graph-manager"],
      "max_concurrent": 2
    }
  }
}
```

### システム設定 (`.autoflow/system.json`)

```json
{
  "memory": {
    "enabled": true,
    "scopes": ["global", "spec", "strategy"],
    "auto_capture": true,
    "global_memory_path": ".autoflow/memory/global.md",
    "spec_memory_dir": ".autoflow/memory/specs",
    "strategy_memory_dir": ".autoflow/memory/strategy"
  },
  "model_profiles": {
    "spec": {
      "model": "claude-sonnet-4-6",
      "temperature": 0.7,
      "max_tokens": 8192
    },
    "implementation": {
      "model": "claude-sonnet-4-6",
      "temperature": 0.3,
      "max_tokens": 16384
    },
    "review": {
      "model": "claude-opus-4-6",
      "temperature": 0.2,
      "max_tokens": 16384
    }
  },
  "tool_profiles": {
    "default": {
      "allowed_tools": ["read", "write", "edit", "bash", "search"],
      "denied_tools": []
    },
    "spec-tools": {
      "allowed_tools": ["read", "write", "edit", "search"],
      "denied_tools": ["bash"]
    }
  },
  "acp_registry": {
    "enabled": true,
    "discovery_paths": [
      "/usr/local/bin/acp-agents/*",
      "~/.local/share/acp-agents/*"
    ]
  }
}
```

## 使用方法

### 基本コマンド

#### 仕様管理

```bash
# 新しい仕様を作成
python3 scripts/autoflow.py new-spec \
  --slug <spec-slug> \
  --title "<title>" \
  --summary "<summary>"

# 既存の仕様を更新
python3 scripts/autoflow.py update-spec --slug <spec-slug>

# 仕様詳細を表示
python3 scripts/autoflow.py show-spec --slug <spec-slug>
```

#### タスク管理

```bash
# 仕様のタスクを初期化
python3 scripts/autoflow.py init-tasks --spec <spec-slug>

# ワークフロー状態を表示
python3 scripts/autoflow.py workflow-state --spec <spec-slug>

# タスクステータスを更新
python3 scripts/autoflow.py update-task \
  --spec <spec-slug> \
  --task <task-id> \
  --status <status>

# タスク履歴を表示
python3 scripts/autoflow.py task-history \
  --spec <spec-slug> \
  --task <task-id>
```

#### 実行管理

```bash
# 新しい実行を作成
python3 scripts/autoflow.py new-run \
  --spec <spec-slug> \
  --role <role> \
  --agent <agent-name> \
  --task <task-id>

# tmuxで実行を起動
scripts/tmux-start.sh .autoflow/runs/<run-id>/run.sh

# 実行中のセッションにアタッチ
tmux attach -t autoflow-run-<timestamp>

# 実行を完了
python3 scripts/autoflow.py complete-run \
  --run <run-id> \
  --result <success|needs_changes|blocked|failed> \
  --summary "<summary>"
```

## ベストプラクティス

### 1. 強力な基盤から始める

- 包括的なテストカバレッジに事前投資
- すべてのタスクに明確な受入基準を定義
- 自律操作の前にCI/CDゲートを設定

### 2. 明確な境界を定義する

- AIが自律的にできることとできないことを指定
- リソース制限を設定（時間、メモリ、API呼び出し）
- 人間の介入のためのエスカレーショントリガーを定義

### 3. 信頼 but 検証

- AIを境界内で自律的に動作させる
- 常時ではなく定期的に出力を監視
- 境界違反時のみ介入

### 4. 急速な反復を受け入れる

- 小さく集中した変更 > 大きなPR
- 高速なフィードバックループ > 完璧な計画
- 自動回復 > 手動デバッグ

### 5. 学習と適応

- AIの決定を毎週レビュー
- パターンに基づいて境界を更新
- 学んだ教訓をメモリに統合

## トラブルシューティング

### エージェント実行が停滞またはハングする

```bash
# アクティブなtmuxセッションをチェック
tmux ls

# デバッグのために特定のセッションにアタッチ
tmux attach -t autoflow-run-<timestamp>

# 停滞したセッションを強制終了
tmux kill-session -t autoflow-run-<timestamp>
```

### タスクが失敗し続ける

```bash
# パターンのためにタスク履歴を調べる
python3 scripts/autoflow.py task-history --spec <spec> --task <task-id>

# 修正リクエストが存在するかチェック
python3 scripts/autoflow.py show-fix-request --spec <spec>

# タスクの最近の実行を表示
ls -lt .autoflow/runs/ | grep <task-id>

# ブロックされたタスクを手動で進める
python3 scripts/autoflow.py update-task \
  --spec <spec> \
  --task <task-id> \
  --status todo
```

## 貢献

貢献を歓迎します！ガイドラインについては[CONTRIBUTING.md](CONTRIBUTING.md)をご覧ください。

## ライセンス

MITライセンス - 詳細は[LICENSE](LICENSE)ファイルを参照してください

---

<div align="center">

**[⬆ トップに戻る](#autoflow)**

Autoflowコミュニティが❤️で作成

</div>
