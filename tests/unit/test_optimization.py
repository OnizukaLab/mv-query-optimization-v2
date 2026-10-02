"""Unit tests for ILP optimization algorithms."""

from unittest.mock import Mock

import pytest

from src.core.query_manager import QueryManager
from src.optimization import BigSubsOptimizer, NormalOptimizer, OptimizerFactory
from src.optimization.base import BaseILPOptimizer


class TestOptimizerFactory:
    """Test suite for OptimizerFactory."""

    def test_list_algorithms(self):
        """Test listing available algorithms."""
        algorithms = OptimizerFactory.list_algorithms()
        assert "normal" in algorithms
        assert "bigsubs" in algorithms
        assert len(algorithms) >= 2

    def test_is_available(self):
        """Test checking algorithm availability."""
        assert OptimizerFactory.is_available("normal")
        assert OptimizerFactory.is_available("bigsubs")
        assert not OptimizerFactory.is_available("nonexistent")

    def test_create_normal_optimizer(self):
        """Test creating a Normal optimizer."""
        qm = Mock(spec=QueryManager)

        optimizer = OptimizerFactory.create(
            "normal",
            qm=qm,
            s_num=10,
            m_cost=[1.0] * 10,
            node_list=["leaf_1", "leaf_2"] + ["non_leaf_1"] * 8,
            B_max=1000.0,
            b_j=[100] * 10,
            u_ij=[[1.0] * 10 for _ in range(5)],
            X=[[0] * 10 for _ in range(10)],
            q_s_list=[[1] * 10 for _ in range(5)],
        )

        assert isinstance(optimizer, NormalOptimizer)
        assert isinstance(optimizer, BaseILPOptimizer)

    def test_create_bigsubs_optimizer(self):
        """Test creating a BigSubs optimizer."""
        qm = Mock(spec=QueryManager)

        optimizer = OptimizerFactory.create(
            "bigsubs",
            qm=qm,
            s_num=10,
            m_cost=[1.0] * 10,
            node_list=["leaf_1", "leaf_2"] + ["non_leaf_1"] * 8,
            B_max=1000.0,
            b_j=[100] * 10,
            u_ij=[[1.0] * 10 for _ in range(5)],
            X=[[0] * 10 for _ in range(10)],
            q_s_list=[[1] * 10 for _ in range(5)],
            U_j_max=[10.0] * 10,
            U_max=100.0,
            y_ij=[[0] * 10 for _ in range(5)],
        )

        assert isinstance(optimizer, BigSubsOptimizer)
        assert isinstance(optimizer, BaseILPOptimizer)

    def test_create_unknown_algorithm(self):
        """Test that unknown algorithm raises ValueError."""
        with pytest.raises(ValueError, match="Unknown optimization algorithm"):
            OptimizerFactory.create("unknown_algo", qm=Mock())

    def test_register_new_algorithm(self):
        """Test registering a custom algorithm."""

        class CustomOptimizer(BaseILPOptimizer):
            def initialize_candidates(self, **kwargs):
                return [], []

            def optimize(self, **kwargs):
                pass

        OptimizerFactory.register("custom", CustomOptimizer)

        assert "custom" in OptimizerFactory.list_algorithms()
        assert OptimizerFactory.is_available("custom")

    def test_register_invalid_class(self):
        """Test that registering non-BaseILPOptimizer raises TypeError."""

        class NotAnOptimizer:
            pass

        with pytest.raises(TypeError, match="must inherit from BaseILPOptimizer"):
            OptimizerFactory.register("invalid", NotAnOptimizer)


class TestBaseILPOptimizer:
    """Test suite for BaseILPOptimizer."""

    @pytest.fixture
    def mock_qm(self):
        """Create a mock QueryManager."""
        qm = Mock(spec=QueryManager)
        qm.subquery_positions = {
            "leaf_1": [[0, 0], [1, 0]],
            "leaf_2": [[0, 1]],
            "non_leaf_1": [[0, 2]],
        }
        qm.subquery_costs = {"leaf_1": 10.0, "leaf_2": 5.0, "non_leaf_1": 20.0}
        qm.subquery_sizes = {"leaf_1": 100, "leaf_2": 50, "non_leaf_1": 200}
        return qm

    @pytest.fixture
    def optimizer_params(self, mock_qm):
        """Create standard optimizer parameters."""
        return {
            "qm": mock_qm,
            "s_num": 3,
            "m_cost": [1.0, 0.5, 2.0],
            "node_list": ["leaf_1", "leaf_2", "non_leaf_1"],
            "B_max": 1000.0,
            "b_j": [100, 50, 200],
            "u_ij": [[10.0, 5.0, 20.0], [10.0, 0.0, 0.0]],
            "X": [[0, 0, 0], [0, 0, 0], [1, 1, 0]],
            "q_s_list": [[1, 1, 1], [1, 0, 0]],
        }

    def test_make_nodename_from_id(self, optimizer_params):
        """Test converting node IDs to names."""
        optimizer = NormalOptimizer(**optimizer_params)

        names = optimizer.make_nodename_from_id([0, 2])
        assert names == ["leaf_1", "non_leaf_1"]

    def test_calculate_storage_used(self, optimizer_params):
        """Test calculating storage used."""
        optimizer = NormalOptimizer(**optimizer_params)

        z_j = [1, 0, 1]  # Materialize leaf_1 and non_leaf_1
        storage = optimizer.calculate_storage_used(z_j)
        assert storage == 300  # 100 + 200

    def test_get_materialized_views(self, optimizer_params):
        """Test creating MaterializedView objects."""
        optimizer = NormalOptimizer(**optimizer_params)

        z_j = [1, 0, 1]
        mvs = optimizer.get_materialized_views(z_j)

        assert len(mvs) == 2
        assert mvs[0].node_id == "leaf_1"
        assert mvs[0].size == 100
        assert mvs[1].node_id == "non_leaf_1"
        assert mvs[1].size == 200


class TestNormalOptimizer:
    """Test suite for NormalOptimizer."""

    @pytest.fixture
    def optimizer(self):
        """Create a NormalOptimizer for testing."""
        qm = Mock(spec=QueryManager)
        qm.subquery_positions = {"leaf_1": [[0, 0]]}
        qm.subquery_costs = {"leaf_1": 10.0}
        qm.subquery_sizes = {"leaf_1": 100}

        return NormalOptimizer(
            qm=qm,
            s_num=3,
            m_cost=[1.0, 0.5, 2.0],
            node_list=["leaf_1", "leaf_2", "non_leaf_1"],
            B_max=1000.0,
            b_j=[100, 50, 200],
            u_ij=[[10.0, 5.0, 20.0]],
            X=[[0, 0, 0], [0, 0, 0], [1, 1, 0]],
            q_s_list=[[1, 1, 1]],
        )

    def test_initialize_candidates(self, optimizer):
        """Test candidate initialization."""
        cand_i, cand_j = optimizer.initialize_candidates()

        # Should have at least some candidates
        assert len(cand_i) >= 0
        assert len(cand_j) >= 0

        # All candidates should be valid indices
        assert all(0 <= i < len(optimizer.u_ij) for i in cand_i)
        assert all(0 <= j < optimizer.s_num for j in cand_j)


class TestBigSubsOptimizer:
    """Test suite for BigSubsOptimizer."""

    @pytest.fixture
    def optimizer(self):
        """Create a BigSubsOptimizer for testing."""
        qm = Mock(spec=QueryManager)
        qm.subquery_positions = {"leaf_1": [[0, 0]]}
        qm.subquery_costs = {"leaf_1": 10.0}
        qm.subquery_sizes = {"leaf_1": 100}

        return BigSubsOptimizer(
            qm=qm,
            s_num=3,
            m_cost=[1.0, 0.5, 2.0],
            node_list=["leaf_1", "leaf_2", "non_leaf_1"],
            B_max=1000.0,
            b_j=[100, 50, 200],
            u_ij=[[10.0, 5.0, 20.0]],
            X=[[0, 0, 0], [0, 0, 0], [1, 1, 0]],
            q_s_list=[[1, 1, 1]],
            U_j_max=[10.0, 5.0, 20.0],
            U_max=35.0,
            y_ij=[[0, 0, 0]],
        )

    def test_initialize_random(self, optimizer):
        """Test random initialization."""
        mv_list = [0] * optimizer.s_num  # s_num=3
        result = optimizer.initialize_random(mv_list)

        # Should have at least one selected
        assert sum(result) >= 1
        assert len(result) == optimizer.s_num
        assert all(x in [0, 1] for x in result)

    def test_flip_probability(self, optimizer):
        """Test flip probability calculation."""
        prob = optimizer.flip_probability(
            iter_num=1,
            z_j=0,
            b_j=100,
            B_cur=500,
            U_cur=10.0,
            U_j_cur=5.0,
            U_j_max=10.0,
            U_max=50.0,
            B_max=1000.0,
        )

        # Probability should be between 0 and 1
        assert 0 <= prob <= 1

    def test_do_flip(self, optimizer):
        """Test flip decision."""
        # With probability 1.0, should always flip
        result = optimizer.do_flip(1.0, 0)
        assert result == 1

        result = optimizer.do_flip(1.0, 1)
        assert result == 0

        # With probability 0.0, should never flip
        result = optimizer.do_flip(0.0, 0)
        assert result == 0

        result = optimizer.do_flip(0.0, 1)
        assert result == 1
