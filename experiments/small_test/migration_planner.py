import json
import pickle
from pathlib import Path
from typing import Dict, Any
import sys

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# from src.core.query_parser import QueryParser
from experiments.small_test.frequency_weighted_parser import FrequencyWeightedParser
from config.settings import Settings

from experiments.small_test.mv_sql_generator import MVSQLGenerator


class Migration_Plan:

    def __init__(
            self,
            settings: Settings | None = None,
            parser_file: str | None = None,
            summary_file: str | None = None,
            generation_mode: str = "enhanced"  # "enhanced", "rewriter", "subtree" から選択
    ): 
        self.settings = settings
        self.parser_file = Path(parser_file) if parser_file else None
        self.summary_file = Path(summary_file) if summary_file else None
        self.generation_mode = generation_mode  # MV生成方式の選択

        #読み込んだデータを保持する属性
        self.qp: FrequencyWeightedParser | None = None
        self.qp_dict: Dict[str, FrequencyWeightedParser] = {}  # 各時刻のQueryParserを保存
        self.summary: Dict[str, Any] | None = None
        # 各時刻のMVを保存
        self.mvs: list | None = None
        self.time_ids: list | None = None
        # MV SQL Generator
        self.mv_sql_generator: MVSQLGenerator | None = None
        
        # 本来各タイムステップごとのpickleファイルがあるが、ここで使う子ノードの情報は共通なため1つだけ読み込む
        if self.parser_file and self.parser_file.exists():
            self.load_pickle()
        if self.summary_file and self.summary_file.exists():
            self.load_summary()
            # summaryから各時刻のQueryParserを読み込む
            if self.summary:
                self.load_all_parsers()
                # MV SQL Generatorを初期化
                if self.qp_dict:
                    self.mv_sql_generator = MVSQLGenerator(self.qp_dict)

    def load_pickle(self) -> None:

        try:
            with open(self.parser_file, 'rb') as f:
                self.qp = pickle.load(f)
            print(f"pickle ファイルを読み込みました: {self.parser_file}")
        except Exception as e:
            print(f"pickle ファイルの読み込みに失敗しました: {e}")
            self.qp = None

    def load_summary(self) -> None:
        try:
            with open(self.summary_file, 'r', encoding='utf-8') as f:
                self.summary = json.load(f)
            print(f"JSONファイルを読み込みました: {self.summary_file}")
        except Exception as e:
            print(f"JSONファイルの読み込みに失敗しました: {e}")
            self.summary = None
    
    def load_all_parsers(self) -> None:
        """summaryから全ての時刻のQueryParserを読み込む"""
        if not self.summary:
            return
        
        time_ids = self.get_time_id(self.summary)
        output_dir = Path("experiments/small_test/time_dependent_output")
        
        for time_id in time_ids:
            parser_file = output_dir / f"qp_{time_id}.pkl"
            if parser_file.exists():
                try:
                    with open(parser_file, 'rb') as f:
                        qp = pickle.load(f)
                    self.qp_dict[time_id] = qp
                    print(f"  {time_id} のQueryParserを読み込みました: {parser_file}")
                except Exception as e:
                    print(f"  {time_id} のQueryParserの読み込みに失敗: {e}")
            else:
                print(f"  警告: {parser_file} が見つかりません")
    
    # ファイルから時刻を取得
    def get_time_id(self, data: list):
        time_ids =[]
        for item in data:
            time_ids.append(item.get("time_id"))
        return time_ids
    
    # 特定の時刻のMVを取得
    def get_selected_mvs(self, data: list, time_id: str):
        selected_mvs = []
        for item in data:
            if item.get("time_id") == time_id:
                selected_mvs = item.get("selected_mvs", [])
        return selected_mvs
    
    # 全ての子孫ノードを取得する(stackを使った深さ優先探索)
    def get_all_child_nodes(self, node_id: str) -> list[str]:

        if not self.qp or not hasattr(self.qp, 'qm'):
            return []
        
        all_children = []
        stack = [node_id]

        while stack:
            current = stack.pop()
            if current in self.qp.qm.non_leaf_nodes_info:
                children = self.qp.qm.non_leaf_nodes_info[current].children
                all_children.extend(children)
                stack.extend(children)
        # setで重複を排除して返す
        return list(set(all_children))

    def generate_mv_sql_with_existing(self, node_id: str, existing_mvs: list[str], time_id: str) -> str | None:
        """既存のMVを利用して新しいMVのSQLを作成（mv_sql_generatorに委譲）"""
        if self.mv_sql_generator is None:
            print(f"  エラー: MVSQLGeneratorが初期化されていません")
            return None
        
        # generation_modeに基づいて使用するメソッドを切り替え
        if self.generation_mode == "rewriter":
            # ☆結局うまくつかえていない、フラットになるからかな？
            print(f"  [INFO] クエリ書き換え機能（Rewriter）を使用してSQL生成")
            return self.mv_sql_generator.generate_mv_sql_with_rewriter(
                node_id, 
                existing_mvs, 
                time_id
            )
        elif self.generation_mode == "subtree":
        # 辺にネストが多くなりrewiteが機能していない
            print(f"  [INFO] サブツリー復元機能（SubtreeRestorer）を使用してSQL生成")
            return self.mv_sql_generator.generate_mv_sql_with_subtree_restore(
                node_id,
                existing_mvs,
                time_id,
                preserve_join_structure=True  # デフォルトでJOIN構造を保持
            )
        else:  # "enhanced" or default
        # ふらっと展開ではあるがまし、non_leafを再活用するパターンで上手くいかなそう、、
            print(f"  [INFO] EnhancedMVGeneratorを使用してSQL生成")
            return self.mv_sql_generator.generate_mv_sql_with_existing(
                node_id, 
                existing_mvs, 
                time_id
            )

    def _generate_sql_file(self, timestep_key: str, drop_sqls: dict, create_sqls: dict):
        """マイグレーションSQLファイルを生成"""
        sql_file = Path(f"experiments/small_test/time_dependent_output/{timestep_key.replace(' -> ', '_to_')}.sql")
        
        with open(sql_file, 'w', encoding='utf-8') as f:
            f.write(f"-- {timestep_key} のマイグレーション SQL\n")
            f.write("-- =====================================================\n\n")
        
            # CREATE SQL
            if create_sqls:
                f.write("-- CREATE MATERIALIZED VIEW\n")
                for create_sql in create_sqls.values():
                    f.write(f"{create_sql}\n\n")

             # DROP SQL
            if drop_sqls:
                f.write("-- DROP MATERIALIZED VIEW\n")
                for drop_sql in drop_sqls.values():
                    f.write(f"{drop_sql}\n")
                f.write("\n")
            
        
        print(f"SQLファイルを生成しました: {sql_file}")


    def get_migration_plan(self):

        migration_data = {} # マイグレーションプランを保存

        # 各時刻のMVを格納
        for time_id in self.get_time_id(self.summary):
            if self.time_ids is None:
                self.time_ids = []
            if self.mvs is None:
                self.mvs = []
            self.time_ids.append(time_id)
            self.mvs.append(self.get_selected_mvs(self.summary, time_id))
        
        #前の時刻と同じMVがあるか探す
        for i in range(len(self.time_ids)-1):
            before_mvs = set(self.mvs[i])
            after_mvs = set(self.mvs[i+1])
            common_mvs = list(before_mvs.intersection(after_mvs))
            print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] 共通MV: {common_mvs}")

            # 共通なMVをなくす
            unique_after_mvs = [mv for mv in after_mvs if mv not in common_mvs]

            # leaf_node だけ取り出す
            if unique_after_mvs is None:
                return           
            leaf_nodes = [mv for mv in unique_after_mvs if mv.startswith("leaf_")]
            print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] ユニークなleaf_node: {leaf_nodes}")

            # leaf_nodeの生成SQLを作成、辞書に保存
            mv_sqls = {}

            for leaf in leaf_nodes:
                mv_sql = self.generate_mv_sql_with_existing(leaf, list(before_mvs), self.time_ids[i+1])
                if mv_sql:
                    print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {leaf} の生成SQL: {mv_sql}")
                    mv_sqls[leaf] = mv_sql
                else:
                    print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {leaf} のSQL生成失敗")

            # non_leaf_nodeを取り出す
            non_leaf_nodes = [mv for mv in unique_after_mvs if mv.startswith("non_leaf_")]

            # 利用できるMVのあるnon_leaf_nodeを格納
            non_leaf_nodes_with_mv = {}
            # 各non_leaf_nodeの全ての子ノードを格納
            all_children_dict = {}
            for node in non_leaf_nodes:
                all_children_dict[node] = self.get_all_child_nodes(node)
                print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node}の全ての子ノード: {all_children_dict[node]}")
                # 各non_leaf_nodeについて、その子ノードの中にbefore_mvsに含まれているものがあるかを確認
                common_children = list(before_mvs.intersection(set(all_children_dict[node])))
                if common_children:
                    print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node}は{common_children}を利用する")
                    non_leaf_nodes_with_mv[node] = common_children
                    # 新しい MV の SQL を生成　このパターン未確認
                    mv_sql_non = self.generate_mv_sql_with_existing(node, common_children, self.time_ids[i+1])
                    if mv_sql_non:
                        print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} の生成SQL作成")
                        mv_sqls[node] = mv_sql_non # SQLを保存
                    else:
                        print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} のSQL生成失敗")
                else:
                    print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node}は新規に配置が必要")
                    # 新規の場合も SQL 生成可能（existing_mvs を空で）
                    mv_sql_non_new = self.generate_mv_sql_with_existing(node, [], self.time_ids[i+1])
                    if mv_sql_non_new:
                        print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} の新規生成SQL作成")
                        mv_sqls[node] = mv_sql_non_new # SQLを保存
                    else:
                        print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} のSQL生成失敗")

            # DROP SQL を生成（before_mvs の中で after_mvs に含まれないもの）　これは実行のタイミングが分からない
            mvs_to_drop = [mv for mv in before_mvs if mv not in after_mvs]
            drop_sqls = {}
            for mv in mvs_to_drop:
                drop_sqls[mv] = f"DROP MATERIALIZED VIEW IF EXISTS {mv};"  # mv_プレフィックスなし
            
            print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] DROP対象のMV: {mvs_to_drop}")
            
            # 辞書形式で保存
            migration_data[f"{self.time_ids[i]} -> {self.time_ids[i+1]}"] = {
                "common_mvs": common_mvs,
                "generate_leaf_nodes": leaf_nodes,
                "generate_non_leaf_nodes_0": non_leaf_nodes,
                "generate_non_leaf_nodes_with_mv": non_leaf_nodes_with_mv,
                "migration_plans_sql": mv_sqls,
                "drop_mvs": mvs_to_drop,
                "drop_sqls": drop_sqls
            }
        # JSONファイルに保存
        output_file = Path("experiments/small_test/time_dependent_output/migration_plan.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(migration_data, f, indent=2, ensure_ascii=False)
        print(f"マイグレーションプランを{output_file}に保存しました")

            # SQL ファイルを生成
        self._generate_sql_file(f"{self.time_ids[i]} -> {self.time_ids[i+1]}", drop_sqls, mv_sqls)

"""
todo :
他のパターンも試す->もっとクエリ増やしてもいいかも
jsonで書き出す=>完了
コストの計算もいれたい->EXPLAIN
SQL生成クエリの書き換えと同じ方法でしてみる
MVではなくTABLEにするうかも？ このままでは1パターン
"""

            


                

if __name__ == "__main__":

    # ファイルパスの設定（必要に応じて変更）
    parser_file = "experiments/small_test/time_dependent_output/qp_morning.pkl"  # pickle ファイル（子ノード情報用）
    summary_file = "experiments/small_test/time_dependent_output/normal_summary.json"  # JSON ファイル
    
    # コマンドライン引数でMV生成方式を制御
    import sys
    generation_mode = "enhanced"  # デフォルト
    
    if '--rewriter' in sys.argv:
        generation_mode = "rewriter"
    elif '--subtree' in sys.argv:
        generation_mode = "subtree"
    
    # 選択された方式を表示
    mode_names = {
        "enhanced": "EnhancedMVGenerator（フラット展開方式）",
        "rewriter": "QueryRewriter（クエリ書き換え方式）",
        "subtree": "SubtreeRestorer（サブツリー復元方式 + カラム推論）"
    }
    
    print("=" * 60)
    print(f"MV生成方式: {mode_names.get(generation_mode, generation_mode)}")
    print("=" * 60)
    print(f"使用方法:")
    print(f"  python migration_planner.py          # EnhancedMVGenerator")
    print(f"  python migration_planner.py --rewriter   # QueryRewriter")
    print(f"  python migration_planner.py --subtree    # SubtreeRestorer")
    print("=" * 60)
    
    # Migration_Plan のインスタンス作成
    plan = Migration_Plan(
        parser_file=parser_file, 
        summary_file=summary_file,
        generation_mode=generation_mode
    )

    if plan.summary:
        plan.get_migration_plan()
    else:
        print("サマリーファイルの読み込み失敗")