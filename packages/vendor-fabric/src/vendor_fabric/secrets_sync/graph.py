"""Dependency graph handling for SecretSync targets."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from vendor_fabric.secrets_sync.models import SecretSyncConfig


class NodeType(StrEnum):
    """Dependency graph node type."""

    SOURCE = "source"
    TARGET = "target"


@dataclass(slots=True)
class Node:
    """Dependency graph node."""

    name: str
    type: NodeType
    level: int = 0
    deps: list[str] = field(default_factory=list)
    depended_by: list[str] = field(default_factory=list)


class Graph:
    """Target dependency graph."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}

    @classmethod
    def from_config(cls, config: SecretSyncConfig) -> Graph:
        """Build a graph from a pipeline config."""
        graph = cls()
        for name in config.sources:
            graph.nodes[name] = Node(name=name, type=NodeType.SOURCE)
        for name in config.targets:
            graph.nodes[name] = Node(name=name, type=NodeType.TARGET)
        for name, target in config.targets.items():
            node = graph.nodes[name]
            for imported in target.imports:
                dep = graph.nodes.get(imported)
                if dep is None:
                    msg = f'target "{name}" imports unknown source/target "{imported}"'
                    raise ValueError(msg)
                node.deps.append(imported)
                dep.depended_by.append(name)
        graph.calculate_levels()
        return graph

    def calculate_levels(self) -> None:
        """Calculate dependency levels and reject cycles."""
        visited: set[str] = set()
        in_stack: set[str] = set()

        def level(name: str) -> int:
            node = self.nodes.get(name)
            if node is None:
                msg = f'node "{name}" not found'
                raise ValueError(msg)
            if name in in_stack:
                msg = f'circular dependency detected involving "{name}"'
                raise ValueError(msg)
            if name in visited:
                return node.level
            in_stack.add(name)
            if node.type is NodeType.SOURCE:
                node.level = 0
            else:
                node.level = max((level(dep) for dep in node.deps), default=-1) + 1
            in_stack.remove(name)
            visited.add(name)
            return node.level

        for name in list(self.nodes):
            level(name)

    def topological_order(self) -> list[str]:
        """Return targets in dependency order."""
        targets = [name for name, node in self.nodes.items() if node.type is NodeType.TARGET]
        return sorted(targets, key=lambda name: (self.nodes[name].level, name))

    def include_dependencies(self, targets: list[str]) -> list[str]:
        """Expand target names to include target dependencies."""
        included: set[str] = set()

        def add(name: str) -> None:
            if name in included:
                return
            included.add(name)
            node = self.nodes.get(name)
            if node is None:
                return
            for dep in node.deps:
                dep_node = self.nodes.get(dep)
                if dep_node and dep_node.type is NodeType.TARGET:
                    add(dep)

        for target in targets:
            add(target)
        return sorted(included, key=lambda name: (self.nodes[name].level, name))

    def group_by_level(self) -> list[list[str]]:
        """Group target names by dependency level."""
        max_level = max((node.level for node in self.nodes.values() if node.type is NodeType.TARGET), default=0)
        levels: list[list[str]] = [[] for _ in range(max_level + 1)]
        for name, node in self.nodes.items():
            if node.type is NodeType.TARGET:
                levels[node.level].append(name)
        return [sorted(level) for level in levels]

    def render(self) -> str:
        """Render a human-readable dependency graph."""
        lines = ["Dependency Graph:"]
        for index, level in enumerate(self.group_by_level()):
            lines.append(f"  Level {index}: {level}")
        lines.append("")
        lines.append("Inheritance:")
        for name in self.topological_order():
            target_deps = [
                dep for dep in self.nodes[name].deps if dep in self.nodes and self.nodes[dep].type is NodeType.TARGET
            ]
            if target_deps:
                lines.append(f"  {name} <- {target_deps}")
        return "\n".join(lines)
