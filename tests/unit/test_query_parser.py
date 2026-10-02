"""Unit tests for QueryParser class."""


import pytest

from src.core.query_parser import QueryParser


class TestQueryParser:
    """Test suite for QueryParser class."""

    @pytest.fixture
    def qp(self):
        """Create a fresh QueryParser instance for each test."""
        return QueryParser()

    @pytest.fixture
    def sample_plan_leaf(self):
        """Sample leaf node plan."""
        return {
            "Node Type": "Seq Scan",
            "Relation Name": "users",
            "Alias": "u",
            "Filter": "u.age > 18",
            "Total Cost": 10.5,
            "Plan Rows": 100,
            "Plan Width": 50,
        }

    @pytest.fixture
    def sample_plan_join(self):
        """Sample join plan with children."""
        return {
            "Node Type": "Hash Join",
            "Hash Cond": "u.id = p.user_id",
            "Total Cost": 25.0,
            "Plan Rows": 200,
            "Plan Width": 100,
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "users",
                    "Alias": "u",
                    "Total Cost": 5.0,
                    "Plan Rows": 50,
                    "Plan Width": 40,
                },
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "posts",
                    "Alias": "p",
                    "Filter": "p.published = true",
                    "Total Cost": 8.0,
                    "Plan Rows": 100,
                    "Plan Width": 60,
                },
            ],
        }

    def test_init(self, qp):
        """Test QueryParser initialization."""
        assert qp.s_num == 0
        assert len(qp.m_cost) == 0
        assert len(qp.node_list) == 0
        assert qp.U_max == 0.0

    def test_natural_sort_key(self, qp):
        """Test natural sorting of filenames."""
        files = ["query_1.json", "query_10.json", "query_2.json"]
        sorted_files = sorted(files, key=qp.natural_sort_key)
        assert sorted_files == ["query_1.json", "query_2.json", "query_10.json"]

    def test_convert_node_leaf(self, qp, sample_plan_leaf):
        """Test converting a leaf node."""
        subquery_list = []
        deep_list = []
        order_list = []

        result, new_order = qp.convert_node(
            sample_plan_leaf, subquery_list, deep_list, order_list, order=0, depth=1, frequency=1
        )

        assert result["type"] == "leaf"
        assert result["operator"] == "Seq Scan"
        assert result["table"] == "users"
        assert result["alias"] == "u"
        assert result["filter"] == "u.age > 18"
        assert result["cost"] == 10.5
        assert result["size"] == 100 * 50  # Plan Rows * Plan Width
        assert result["width"] == 50
        assert len(deep_list) == 1
        assert deep_list[0] == 1

    def test_convert_node_leaf_no_filter(self, qp):
        """Test converting a leaf node without filter."""
        plan = {
            "Node Type": "Seq Scan",
            "Relation Name": "users",
            "Alias": "u",
            "Total Cost": 10.0,
            "Plan Rows": 100,
            "Plan Width": 50,
        }

        subquery_list = []
        deep_list = []
        order_list = []

        result, _ = qp.convert_node(
            plan, subquery_list, deep_list, order_list, order=0, frequency=1
        )

        assert result["filter"] == ""
        assert result["cost"] == 0.0  # Cost should be zero without filter

    def test_convert_node_join(self, qp, sample_plan_join):
        """Test converting a join node with children."""
        subquery_list = []
        deep_list = []
        order_list = []

        result, new_order = qp.convert_node(
            sample_plan_join, subquery_list, deep_list, order_list, order=0, frequency=1
        )

        assert result["type"] == "non_leaf"
        assert result["operator"] == "Hash Join"
        assert result["filter"] == "u.id = p.user_id"
        assert len(result["children"]) == 2
        assert result["children"][0]["type"] == "leaf"
        assert result["children"][1]["type"] == "leaf"

    def test_convert_node_frequency(self, qp, sample_plan_leaf):
        """Test that frequency multiplies cost."""
        subquery_list = []
        deep_list = []
        order_list = []

        result, _ = qp.convert_node(
            sample_plan_leaf, subquery_list, deep_list, order_list, order=0, frequency=5
        )

        # Cost should be multiplied by frequency
        assert result["cost"] == 10.5 * 5

    def test_convert_node_zero_width(self, qp):
        """Test that zero width is converted to 1."""
        plan = {
            "Node Type": "Seq Scan",
            "Relation Name": "users",
            "Alias": "u",
            "Filter": "u.id = 1",
            "Total Cost": 5.0,
            "Plan Rows": 10,
            "Plan Width": 0,  # Zero width
        }

        subquery_list = []
        result, _ = qp.convert_node(plan, subquery_list, [], [], 0, frequency=1)

        assert result["width"] == 1

    def test_convert_json(self, qp):
        """Test converting JSON query plan."""
        json_data = [
            {
                "Plan": {
                    "Node Type": "Seq Scan",
                    "Relation Name": "users",
                    "Alias": "u",
                    "Filter": "u.age > 18",
                    "Total Cost": 10.0,
                    "Plan Rows": 100,
                    "Plan Width": 50,
                }
            }
        ]

        subquery_list, deep_list, order_list = qp.convert_json(json_data, freq=1)

        assert len(subquery_list) == 1
        assert subquery_list[0]["type"] == "leaf"
        assert len(deep_list) > 0
        assert len(order_list) > 0

    def test_make_reverse_dict(self, qp):
        """Test creating reverse dictionary from positions."""
        positions = {"leaf_1": [[0, 0], [1, 2]], "leaf_2": [[0, 1]]}

        reverse = qp.make_reverse_dict(positions)

        assert reverse[(0, 0)] == "leaf_1"
        assert reverse[(1, 2)] == "leaf_1"
        assert reverse[(0, 1)] == "leaf_2"

    def test_make_reverse_dict2(self, qp):
        """Test creating reverse dictionary."""
        d = {("leaf_1", "leaf_2"): "non_leaf_1", ("leaf_3", "leaf_4"): "non_leaf_2"}

        reverse = qp.make_reverse_dict2(d)

        assert reverse["non_leaf_1"] == ("leaf_1", "leaf_2")
        assert reverse["non_leaf_2"] == ("leaf_3", "leaf_4")

    def test_search_leaf_node(self, qp):
        """Test finding leaf tables in a subtree."""
        # Create a tree structure
        qp.qm.process_leaf_node("Seq Scan", "users", "u", "", [-1, -1], 5.0, 5.0, 100, 50)
        qp.qm.process_leaf_node("Seq Scan", "posts", "p", "", [-1, -1], 7.0, 7.0, 200, 60)
        qp.qm.process_non_leaf_node(["leaf_1", "leaf_2"], [-1, -1], 15.0, 300, 110)

        # Search from non-leaf node
        tables = qp.search_leaf_node("non_leaf_1")

        assert set(tables) == {"users", "posts"}

    def test_search_leaf_node_direct_leaf(self, qp):
        """Test searching from a leaf node itself."""
        qp.qm.process_leaf_node("Seq Scan", "users", "u", "", [-1, -1], 5.0, 5.0, 100, 50)

        tables = qp.search_leaf_node("leaf_1")

        assert tables == ["users"]

    def test_check_m_cost(self, qp):
        """Test maintenance cost calculation."""
        # Create some nodes
        qp.qm.process_leaf_node("Seq Scan", "users", "u", "", [-1, -1], 10.0, 10.0, 100, 50)
        qp.qm.process_leaf_node("Seq Scan", "posts", "p", "", [-1, -1], 15.0, 15.0, 200, 60)

        m_cost = [0.0, 0.0]
        table_list = ["users", "posts"]
        update_table = [["users"], ["posts"]]
        record_list = [1000, 2000]
        search_cost = [5.0, 6.0]
        insert_cost = 0.01
        table_width = [100, 120]
        insert_times = 10

        result = qp.check_m_cost(
            m_cost,
            table_list,
            update_table,
            record_list,
            search_cost,
            insert_cost,
            table_width,
            insert_times,
        )

        # Should have non-zero maintenance costs
        assert result[0] > 0.0
        assert result[1] > 0.0

    def test_set_inclusive_dependency(self, qp):
        """Test building inclusive dependency matrix."""
        # Create a simple tree
        qp.qm.process_leaf_node("Seq Scan", "users", "u", "", [-1, -1], 5.0, 5.0, 100, 50)
        qp.qm.process_leaf_node("Seq Scan", "posts", "p", "", [-1, -1], 7.0, 7.0, 200, 60)
        qp.qm.process_non_leaf_node(["leaf_1", "leaf_2"], [-1, -1], 15.0, 300, 110)

        qp.node_list = ["leaf_1", "leaf_2", "non_leaf_1"]
        qp.subqlist = {"non_leaf_1": ("leaf_1", "leaf_2")}

        X = qp.set_inclusive_dependency(None, 0)

        # Check matrix dimensions
        assert len(X) == 3
        assert len(X[0]) == 3

        # non_leaf_1 should depend on its children
        assert X[2][0] == 1  # non_leaf_1 -> leaf_1
        assert X[2][1] == 1  # non_leaf_1 -> leaf_2

    @pytest.fixture
    def sample_bitmap_heap_scan(self):
        """Sample Bitmap Heap Scan plan with Bitmap Index Scan child."""
        return {
            "Node Type": "Bitmap Heap Scan",
            "Relation Name": "person_info",
            "Alias": "pi",
            "Recheck Cond": "(info_type_id = it.id)",
            "Filter": "(note IS NOT NULL)",
            "Total Cost": 150.5,
            "Plan Rows": 500,
            "Plan Width": 80,
            "Plans": [
                {
                    "Node Type": "Bitmap Index Scan",
                    "Index Name": "info_type_id_person_info",
                    "Index Cond": "(info_type_id = it.id)",
                    "Total Cost": 10.0,
                    "Plan Rows": 500,
                    "Plan Width": 0,
                }
            ],
        }

    def test_convert_bitmap_heap_scan(self, qp, sample_bitmap_heap_scan):
        """Test converting a Bitmap Heap Scan node (should be treated as leaf)."""
        subquery_list = []
        deep_list = []
        order_list = []

        result, new_order = qp.convert_node(
            sample_bitmap_heap_scan, subquery_list, deep_list, order_list, order=0, depth=1, frequency=1
        )

        # Bitmap Heap Scan should be treated as a leaf node
        assert result["type"] == "leaf"
        assert result["operator"] == "Bitmap Heap Scan"
        assert result["table"] == "person_info"
        assert result["alias"] == "pi"
        # Filter should only include Filter, not Recheck Cond or Index Cond
        # (Index/Recheck conditions are typically join conditions handled by parent)
        assert result["filter"] == "(note IS NOT NULL)"
        assert "(info_type_id = it.id)" not in result["filter"]  # Join condition excluded
        assert result["cost"] == 150.5
        assert result["size"] == 500 * 80  # Plan Rows * Plan Width
        assert result["width"] == 80
        # Index columns should be extracted from condition (for reference)
        assert "info_type_id" in result["index_columns"]
        # Only one leaf node should be created (not two for Bitmap Index Scan)
        assert len(subquery_list) == 1
        assert len(deep_list) == 1

    @pytest.fixture
    def sample_bitmap_and_scan(self):
        """Sample Bitmap Heap Scan with BitmapAnd child (multiple index conditions)."""
        return {
            "Node Type": "Bitmap Heap Scan",
            "Relation Name": "orders",
            "Alias": "o",
            "Recheck Cond": "((customer_id = c.id) AND (product_id = p.id))",
            "Total Cost": 200.0,
            "Plan Rows": 100,
            "Plan Width": 60,
            "Plans": [
                {
                    "Node Type": "BitmapAnd",
                    "Plans": [
                        {
                            "Node Type": "Bitmap Index Scan",
                            "Index Name": "idx_customer_id",
                            "Index Cond": "(customer_id = c.id)",
                            "Total Cost": 5.0,
                            "Plan Rows": 200,
                            "Plan Width": 0,
                        },
                        {
                            "Node Type": "Bitmap Index Scan",
                            "Index Name": "idx_product_id",
                            "Index Cond": "(product_id = p.id)",
                            "Total Cost": 5.0,
                            "Plan Rows": 150,
                            "Plan Width": 0,
                        },
                    ],
                }
            ],
        }

    def test_convert_bitmap_and_scan(self, qp, sample_bitmap_and_scan):
        """Test converting a Bitmap Heap Scan with BitmapAnd child."""
        subquery_list = []
        deep_list = []
        order_list = []

        result, new_order = qp.convert_node(
            sample_bitmap_and_scan, subquery_list, deep_list, order_list, order=0, depth=1, frequency=1
        )

        # Should still be a single leaf node
        assert result["type"] == "leaf"
        assert result["operator"] == "Bitmap Heap Scan"
        assert result["table"] == "orders"
        assert result["alias"] == "o"
        # Filter should be empty (no Filter field in fixture, only join conditions)
        # Join conditions (Index Cond) are NOT included in leaf filter
        assert result["filter"] == ""
        assert "(customer_id = c.id)" not in result["filter"]
        assert "(product_id = p.id)" not in result["filter"]
        # Index columns should include both (for reference)
        assert "customer_id" in result["index_columns"]
        assert "product_id" in result["index_columns"]
        # Only one leaf node should be created
        assert len(subquery_list) == 1
