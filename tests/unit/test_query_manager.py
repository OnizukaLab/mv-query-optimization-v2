"""Unit tests for QueryManager class."""

import pytest

from src.core.query_manager import QueryManager


class TestQueryManager:
    """Test suite for QueryManager class."""

    @pytest.fixture
    def qm(self):
        """Create a fresh QueryManager instance for each test."""
        return QueryManager()

    def test_init(self, qm):
        """Test QueryManager initialization."""
        assert len(qm.leaf_nodes_map) == 0
        assert len(qm.non_leaf_nodes_map) == 0
        assert qm.leaf_id_counter == 0
        assert qm.non_leaf_id_counter == 0

    def test_generate_unique_id_leaf(self, qm):
        """Test leaf node ID generation."""
        id1 = qm._generate_unique_id("leaf")
        id2 = qm._generate_unique_id("leaf")
        assert id1 == "leaf_1"
        assert id2 == "leaf_2"
        assert qm.leaf_id_counter == 2

    def test_generate_unique_id_non_leaf(self, qm):
        """Test non-leaf node ID generation."""
        id1 = qm._generate_unique_id("non_leaf")
        id2 = qm._generate_unique_id("non_leaf")
        assert id1 == "non_leaf_1"
        assert id2 == "non_leaf_2"
        assert qm.non_leaf_id_counter == 2

    def test_generate_unique_id_invalid_prefix(self, qm):
        """Test that invalid prefix raises ValueError."""
        with pytest.raises(ValueError, match="Invalid prefix"):
            qm._generate_unique_id("invalid")

    def test_process_leaf_node_new(self, qm):
        """Test processing a new leaf node."""
        node_id = qm.process_leaf_node(
            operator_name="Seq Scan",
            table_name="users",
            alias="u",
            filter_condition="u.age > 18",
            position=[0, 0],
            total_cost=10.5,
            original_cost=10.5,
            size=1000,
            width=100,
        )

        assert node_id == "leaf_1"
        assert qm.leaf_nodes_map[("Seq Scan", "users", "u", "u.age > 18")] == "leaf_1"
        assert qm.subquery_costs["leaf_1"] == 10.5
        assert qm.subquery_sizes["leaf_1"] == 1000
        assert qm.subquery_widths["leaf_1"] == 100
        assert qm.relation_tables["leaf_1"] == "users"
        assert qm.subquery_positions["leaf_1"] == [[0, 0]]

    def test_process_leaf_node_duplicate(self, qm):
        """Test processing a duplicate leaf node returns same ID."""
        # First call
        node_id1 = qm.process_leaf_node(
            "Seq Scan", "users", "u", "u.age > 18", [0, 0], 10.5, 10.5, 1000, 100
        )

        # Second call with same properties
        node_id2 = qm.process_leaf_node(
            "Seq Scan", "users", "u", "u.age > 18", [1, 0], 10.5, 10.5, 1000, 100
        )

        assert node_id1 == node_id2
        assert qm.leaf_id_counter == 1  # Only one ID created
        assert len(qm.subquery_positions["leaf_1"]) == 2  # Two positions

    def test_process_leaf_node_cost_minimum(self, qm):
        """Test that minimum cost is kept for duplicate nodes."""
        # First call with higher cost
        qm.process_leaf_node("Seq Scan", "users", "u", "u.age > 18", [0, 0], 20.0, 20.0, 1000, 100)

        # Second call with lower cost
        qm.process_leaf_node("Seq Scan", "users", "u", "u.age > 18", [1, 0], 10.0, 10.0, 1000, 100)

        assert qm.subquery_costs["leaf_1"] == 10.0  # Lower cost kept

    def test_process_leaf_node_invalid_position(self, qm):
        """Test that invalid position is not added."""
        node_id = qm.process_leaf_node(
            "Seq Scan", "users", "u", "u.age > 18", [-1, -1], 10.5, 10.5, 1000, 100
        )

        assert node_id not in qm.subquery_positions

    def test_process_non_leaf_node_new(self, qm):
        """Test processing a new non-leaf node."""
        # Create child nodes first
        child1 = qm.process_leaf_node("Seq Scan", "users", "u", "", [0, 0], 5.0, 5.0, 500, 50)
        child2 = qm.process_leaf_node("Seq Scan", "posts", "p", "", [0, 1], 7.0, 7.0, 700, 70)

        # Process non-leaf node
        node_id = qm.process_non_leaf_node(
            child_node_ids=[child1, child2],
            position=[0, 2],
            total_cost=15.0,
            size=200,
            width=120,
            filter_condition="u.id = p.user_id",
        )

        assert node_id == "non_leaf_1"
        assert qm.subquery_costs["non_leaf_1"] == 15.0
        assert qm.subquery_sizes["non_leaf_1"] == 200
        assert qm.subquery_widths["non_leaf_1"] == 120
        assert qm.non_leaf_nodes_filter["non_leaf_1"] == "u.id = p.user_id"
        assert qm.subquery_positions["non_leaf_1"] == [[0, 2]]

    def test_process_non_leaf_node_order_independent(self, qm):
        """Test that child order doesn't affect node deduplication."""
        child1 = qm.process_leaf_node("Seq Scan", "users", "u", "", [-1, -1], 5.0, 5.0, 500, 50)
        child2 = qm.process_leaf_node("Seq Scan", "posts", "p", "", [-1, -1], 7.0, 7.0, 700, 70)

        # Process with children in different order
        node_id1 = qm.process_non_leaf_node([child1, child2], [-1, -1], 15.0, 200, 120)
        node_id2 = qm.process_non_leaf_node([child2, child1], [-1, -1], 15.0, 200, 120)

        assert node_id1 == node_id2  # Same node due to sorted key
        assert qm.non_leaf_id_counter == 1  # Only one node created

    def test_depth_first_search_leaf(self, qm):
        """Test DFS on a leaf node."""
        node = {
            "type": "leaf",
            "operator": "Seq Scan",
            "table": "users",
            "alias": "u",
            "filter": "u.age > 18",
            "cost": 10.0,
            "size": 1000,
            "width": 100,
        }

        node_id = qm.depth_first_search(node, [0, 0])

        assert node_id == "leaf_1"
        assert qm.subquery_costs["leaf_1"] == 10.0

    def test_depth_first_search_non_leaf(self, qm):
        """Test DFS on a non-leaf node with children."""
        node = {
            "type": "non_leaf",
            "operator": "Hash Join",
            "filter": "u.id = p.user_id",
            "cost": 20.0,
            "size": 500,
            "width": 150,
            "children": [
                {
                    "type": "leaf",
                    "operator": "Seq Scan",
                    "table": "users",
                    "alias": "u",
                    "filter": "",
                    "cost": 5.0,
                    "size": 200,
                    "width": 50,
                },
                {
                    "type": "leaf",
                    "operator": "Index Scan",
                    "table": "posts",
                    "alias": "p",
                    "filter": "p.published = true",
                    "cost": 8.0,
                    "size": 300,
                    "width": 100,
                },
            ],
        }

        node_id = qm.depth_first_search(node, [0, 0])

        assert node_id == "non_leaf_1"
        assert qm.leaf_id_counter == 2  # Two leaf children
        assert qm.non_leaf_id_counter == 1  # One non-leaf node

    def test_depth_first_search_invalid_type(self, qm):
        """Test DFS with invalid node type raises ValueError."""
        node = {"type": "invalid", "cost": 10.0}

        with pytest.raises(ValueError, match="Invalid node type"):
            qm.depth_first_search(node, [0, 0])

    def test_get_node_info_leaf(self, qm):
        """Test getting info for a leaf node."""
        qm.process_leaf_node("Seq Scan", "users", "u", "u.age > 18", [0, 0], 10.0, 10.0, 1000, 100)

        info = qm.get_node_info("leaf_1")

        assert info is not None
        assert info["type"] == "leaf"
        assert info["table"] == "users"
        assert info["filter"] == "u.age > 18"
        assert info["cost"] == 10.0
        assert info["size"] == 1000
        assert info["width"] == 100

    def test_get_node_info_non_leaf(self, qm):
        """Test getting info for a non-leaf node."""
        child1 = qm.process_leaf_node("Seq Scan", "users", "u", "", [-1, -1], 5.0, 5.0, 500, 50)
        child2 = qm.process_leaf_node("Seq Scan", "posts", "p", "", [-1, -1], 7.0, 7.0, 700, 70)
        qm.process_non_leaf_node([child1, child2], [0, 0], 15.0, 200, 120, "u.id = p.user_id")

        info = qm.get_node_info("non_leaf_1")

        assert info is not None
        assert info["type"] == "non_leaf"
        assert set(info["children"]) == {child1, child2}
        assert info["filter"] == "u.id = p.user_id"
        assert info["cost"] == 15.0

    def test_get_node_info_not_found(self, qm):
        """Test getting info for non-existent node."""
        info = qm.get_node_info("nonexistent_1")
        assert info is None

    def test_reset(self, qm):
        """Test resetting the QueryManager."""
        # Add some nodes
        qm.process_leaf_node("Seq Scan", "users", "u", "", [0, 0], 10.0, 10.0, 1000, 100)
        qm.process_non_leaf_node(["leaf_1"], [0, 1], 20.0, 500, 50)

        # Reset
        qm.reset()

        # Check everything is cleared
        assert len(qm.leaf_nodes_map) == 0
        assert len(qm.non_leaf_nodes_map) == 0
        assert qm.leaf_id_counter == 0
        assert qm.non_leaf_id_counter == 0
        assert len(qm.subquery_positions) == 0
        assert len(qm.subquery_costs) == 0
        assert len(qm.subquery_sizes) == 0
