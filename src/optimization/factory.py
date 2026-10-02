"""Factory for creating ILP optimizer instances.

This module provides a factory pattern for creating different ILP
optimization algorithm instances based on algorithm name.
"""


from .base import BaseILPOptimizer
from .bigsubs import BigSubsOptimizer
from .frequency import FrequencyOptimizer
from .normal import NormalOptimizer
from .utility import UtilityOptimizer
from .utility_capacity import UtilityCapacityOptimizer


class OptimizerFactory:
    """Factory for creating optimizer instances.

    This class implements the Factory pattern to create different
    ILP optimization algorithm instances based on a string identifier.

    Supported algorithms:
    - 'normal': Basic ILP optimization
    - 'bigsubs': BigSubs with randomized search
    - 'utility_capacity': Utility-Capacity ratio based greedy
    - 'utility': Utility-based greedy
    - 'frequency': Frequency-based greedy
    """

    _optimizers: dict[str, type[BaseILPOptimizer]] = {
        "normal": NormalOptimizer,
        "bigsubs": BigSubsOptimizer,
        "utility_capacity": UtilityCapacityOptimizer,
        "utility": UtilityOptimizer,
        "frequency": FrequencyOptimizer,
    }

    @classmethod
    def create(cls, algorithm: str, **kwargs) -> BaseILPOptimizer:
        """Create an optimizer instance for the specified algorithm.

        Args:
            algorithm: Name of the optimization algorithm
                      ('normal', 'bigsubs', etc.)
            **kwargs: Arguments to pass to the optimizer constructor
                     Required args depend on the specific optimizer

        Returns:
            Instance of the requested optimizer

        Raises:
            ValueError: If algorithm name is not recognized

        Example:
            >>> optimizer = OptimizerFactory.create(
            ...     'normal',
            ...     qm=query_manager,
            ...     s_num=100,
            ...     m_cost=costs,
            ...     node_list=nodes,
            ...     B_max=50000000,
            ...     b_j=sizes,
            ...     u_ij=utilities,
            ...     X=dependencies,
            ...     q_s_list=query_subquery_map
            ... )
            >>> result = optimizer.optimize()
        """
        if algorithm not in cls._optimizers:
            available = ", ".join(cls._optimizers.keys())
            raise ValueError(
                f"Unknown optimization algorithm: '{algorithm}'. "
                f"Available algorithms: {available}"
            )

        optimizer_class = cls._optimizers[algorithm]
        return optimizer_class(**kwargs)

    @classmethod
    def register(cls, name: str, optimizer_class: type[BaseILPOptimizer]) -> None:
        """Register a new optimizer algorithm.

        This allows external code to add custom optimization algorithms
        to the factory.

        Args:
            name: Name to register the algorithm under
            optimizer_class: Class implementing BaseILPOptimizer

        Raises:
            TypeError: If optimizer_class doesn't inherit from BaseILPOptimizer

        Example:
            >>> class MyOptimizer(BaseILPOptimizer):
            ...     # implementation
            ...     pass
            >>> OptimizerFactory.register('my_algorithm', MyOptimizer)
        """
        if not issubclass(optimizer_class, BaseILPOptimizer):
            raise TypeError(f"{optimizer_class.__name__} must inherit from BaseILPOptimizer")

        cls._optimizers[name] = optimizer_class

    @classmethod
    def list_algorithms(cls) -> list:
        """List all available algorithm names.

        Returns:
            List of registered algorithm names
        """
        return list(cls._optimizers.keys())

    @classmethod
    def is_available(cls, algorithm: str) -> bool:
        """Check if an algorithm is available.

        Args:
            algorithm: Name of the algorithm to check

        Returns:
            True if algorithm is registered, False otherwise
        """
        return algorithm in cls._optimizers
