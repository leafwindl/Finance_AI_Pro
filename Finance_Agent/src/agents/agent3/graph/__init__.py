"""Agent 3 graph package.

Do not import ``workflow`` eagerly here: node modules import ``graph.state``,
and eager workflow loading creates a circular import through those nodes.
"""


def build_graph(*args, **kwargs):
    from .workflow import build_graph as _build_graph

    return _build_graph(*args, **kwargs)


__all__ = ["build_graph"]

__all__ = ["build_graph"]
