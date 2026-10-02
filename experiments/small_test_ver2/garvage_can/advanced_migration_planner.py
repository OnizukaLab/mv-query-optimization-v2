import json
import pickle
from pathlib import Path
from typing import Dict, Any
import sys

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# from src.core.query_parser import QueryParser
from experiments.small_test_ver2.frequency_weighted_parser import FrequencyWeightedParser
from config.settings import Settings

from experiments.small_test_ver2.mv_sql_generator import MVSQLGenerator


class Migration_Plan:

    def __init__(
            self,
            settings: Settings | None = None,
            parser_file: str | None = None,
            summary_file: str | None = None
    ): 
        self.settings = settings
        self.parser_file = Path(parser_file) if parser_file else None
        self.summary_file = Path(summary_file) if summary_file else None

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
        output_dir = Path("experiments/small_test_ver2/time_dependent_output")
        
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
        # setで重複を排除してソート済みリストで返す
        return sorted(set(all_children))

    def generate_mv_sql_with_existing(self, node_id: str, existing_mvs: list[str], time_id: str) -> str | None:
        """既存のMVを利用して新しいMVのSQLを作成（generate_mv_sql_with_rewriterを使用）"""
        if self.mv_sql_generator is None:
            print(f"  エラー: MVSQLGeneratorが初期化されていません")
            return None
        
        return self.mv_sql_generator.generate_mv_sql_with_rewriter(
            node_id, 
            existing_mvs, 
            time_id
        )

    def _generate_sql_file(self, timestep_key: str, drop_sqls: dict, create_sqls: dict):
        """マイグレーションSQLファイルを生成"""
        sql_file = Path(f"experiments/small_test_ver2/time_dependent_output/{timestep_key.replace(' -> ', '_to_')}.sql")
        
        with open(sql_file, 'w', encoding='utf-8') as f:
            f.write(f"-- {timestep_key} のマイグレーション SQL\n")
            f.write("-- =====================================================\n\n")
        
            # CREATE SQL
            if create_sqls:
                f.write("-- CREATE MATERIALIZED VIEW\n")
                for node_id in sorted(create_sqls.keys()):
                    f.write(f"{create_sqls[node_id]}\n\n")

             # DROP SQL
            if drop_sqls:
                f.write("-- DROP MATERIALIZED VIEW\n")
                for mv_id in sorted(drop_sqls.keys()):
                    f.write(f"{drop_sqls[mv_id]}\n")
                f.write("\n")
            
        
        print(f"SQLファイルを生成しました: {sql_file}")

    def _filter_outermost_nodes(self, candidate_nodes: list[str]) -> list[str]:
        """包含関係にあるノードの中で、最も外側（親）のノードのみを返す
        
        Args:
            candidate_nodes: 候補ノードのリスト
            
        Returns:
            最も外側のノードのみを含むリスト
            
        例:
            候補: ["leaf_15", "non_leaf_25", "non_leaf_26"]
            non_leaf_26 の子孫: ["leaf_14", "non_leaf_25"]
            non_leaf_25 の子孫: ["leaf_15"]
            
            結果: ["non_leaf_26"]
            理由: leaf_15 と non_leaf_25 は non_leaf_26 に含まれるため除外
        """
        if not self.qp or not hasattr(self.qp, 'qm'):
            return candidate_nodes
        
        # 各候補ノードの子孫ノードを取得
        descendants_map = {}
        for node in candidate_nodes:
            descendants_map[node] = set(self.get_all_child_nodes(node))
        
        # 他のノードに含まれていないノード（最も外側）のみを抽出
        outermost_nodes = []
        
        for node in candidate_nodes:
            is_contained = False
            
            # このノードが他のノードの子孫に含まれているかチェック
            for other_node in candidate_nodes:
                if node != other_node and node in descendants_map[other_node]:
                    is_contained = True
                    break
            
            # 他のノードに含まれていない場合のみ追加
            if not is_contained:
                outermost_nodes.append(node)
        
        return sorted(outermost_nodes)

    def get_migration_plan(
            self,
            target_mv: str,
            mv_set
            ):

        migration_data = {} # マイグレーションプランを保存
        
        #前の時刻と同じMVがあるか探す
        
            before_mvs = set(self.mvs[i])
            after_mvs = set(self.mvs[i+1])
            common_mvs = sorted(before_mvs.intersection(after_mvs))
            print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] 共通MV: {common_mvs}")

            # 共通なMVをなくす
            unique_after_mvs = sorted([mv for mv in after_mvs if mv not in common_mvs])

            # leaf_node だけ取り出す
            if unique_after_mvs is None:
                return           
            leaf_nodes = sorted([mv for mv in unique_after_mvs if mv.startswith("leaf_")])
            print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] ユニークなleaf_node: {leaf_nodes}")

            # leaf_nodeの生成SQLを作成、辞書に保存
            mv_sqls = {}

            for leaf in leaf_nodes:
                # leaf_nodesは新規生成なので、既存MVは使用しない（空リスト）
                mv_sql = self.generate_mv_sql_with_existing(leaf, [], self.time_ids[i+1])
                if mv_sql:
                    print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {leaf} の生成SQL: {mv_sql}")
                    mv_sqls[leaf] = mv_sql
                else:
                    print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {leaf} のSQL生成失敗")

            # non_leaf_nodeを取り出す
            non_leaf_nodes = sorted([mv for mv in unique_after_mvs if mv.startswith("non_leaf_")])

            # 利用できるMVのあるnon_leaf_nodeを格納
            non_leaf_nodes_with_mv = {}
            # 各non_leaf_nodeの全ての子ノードを格納
            all_children_dict = {}
            for node in non_leaf_nodes:
                all_children_dict[node] = self.get_all_child_nodes(node)
                print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node}の全ての子ノード: {all_children_dict[node]}")
                # 各non_leaf_nodeについて、その子ノードの中にbefore_mvsに含まれているものがあるかを確認
                common_children = sorted(before_mvs.intersection(set(all_children_dict[node])))

                # ★ 包含関係にあるノードの中で最も外側のノードのみを選択 ★
                if common_children:
                    filtered_children = self._filter_outermost_nodes(common_children)
                    print(f"  [DEBUG] 元の候補: {common_children}")
                    print(f"  [DEBUG] フィルタ後: {filtered_children}")
                    
                    if filtered_children:
                        print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node}は{filtered_children}を利用する")
                        non_leaf_nodes_with_mv[node] = filtered_children
                        
                        # 新しい MV の SQL を生成
                        mv_sql_non = self.generate_mv_sql_with_existing(node, filtered_children, self.time_ids[i+1])
                        if mv_sql_non:
                            print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} の生成SQL作成")
                            mv_sqls[node] = mv_sql_non
                        else:
                            print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} のSQL生成失敗")
                    else:
                        # フィルタ後に候補がなくなった場合は新規生成 このパターンはなさそうだけど、、
                        print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node}はフィルタ後に候補なし、新規生成")
                        mv_sql_non_new = self.generate_mv_sql_with_existing(node, [], self.time_ids[i+1])
                        if mv_sql_non_new:
                            print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} の新規生成SQL作成")
                            mv_sqls[node] = mv_sql_non_new
                        else:
                            print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} のSQL生成失敗")
                else:
                    print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node}は新規に配置が必要")
                    # 新規の場合も SQL 生成可能（existing_mvs を空で）
                    mv_sql_non_new = self.generate_mv_sql_with_existing(node, [], self.time_ids[i+1])
                    if mv_sql_non_new:
                        print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} の新規生成SQL作成")
                        mv_sqls[node] = mv_sql_non_new
                    else:
                        print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} のSQL生成失敗")
            
            # DROP SQL を生成（before_mvs の中で after_mvs に含まれないもの）
            """DROPは一旦考えない
            mvs_to_drop = sorted([mv for mv in before_mvs if mv not in after_mvs])
            drop_sqls = {}
            for mv in mvs_to_drop:
                drop_sqls[mv] = f"DROP MATERIALIZED VIEW IF EXISTS {mv};"  # mv_プレフィックスなし
            
            print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] DROP対象のMV: {mvs_to_drop}")
            """
            # 空で定義しておく
            drop_sqls = {}
            
            # 辞書形式で保存
            migration_data[f"{self.time_ids[i]} -> {self.time_ids[i+1]}"] = {
                "common_mvs": common_mvs,
                "generate_leaf_nodes": leaf_nodes,
                "generate_non_leaf_nodes_0": non_leaf_nodes,
                "generate_non_leaf_nodes_with_mv": non_leaf_nodes_with_mv,
                "migration_plans_sql": mv_sqls,
                #"drop_mvs": mvs_to_drop,
                #"drop_sqls": drop_sqls
            }
        # JSONファイルに保存
        output_file = Path("experiments/small_test_ver2/time_dependent_output/migration_plan.json")
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

    # ファイルパスの設定(必要に応じて変更)
    parser_file = "experiments/small_test_ver2/time_dependent_output/qp_morning.pkl"  # pickle ファイル(子ノード情報用)
    summary_file = "experiments/small_test_ver2/time_dependent_output/normal_summary.json"  # JSON ファイル
    
    # Migration_Plan のインスタンス作成
    plan = Migration_Plan(
        parser_file=parser_file, 
        summary_file=summary_file
    )

    if plan.summary:
        plan.get_migration_plan()
    else:
        print("サマリーファイルの読み込み失敗")