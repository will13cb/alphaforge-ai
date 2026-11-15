"""(G) dh.risk.controls and the architecture rules of dh.risk (no forbidden import, no cycle)."""
import ast
from pathlib import Path

from dh.risk import controls as ct

RISK = Path(__file__).resolve().parents[1] / "src" / "dh" / "risk"
ALLOWED = {"dh.metrics", "dh.quant_toolkit", "dh.data", "dh.kyc", "dh.agents.rules"}


class TestMethod:
    def test_current_rules_are_circular_and_duplicated(self):
        """Documents A7 (passes today)."""
        codes = [(i.code, i.evidence["control"]) for i in ct.audit(ct.CURRENT)]
        assert ("G-circular", "G7") in codes and ("G-circular", "D2") in codes
        assert ("G-duplicate", "G17") in codes

    def test_target_registry_is_clean(self):
        assert ct.audit(ct.TARGET) == []
        assert ct.count_independent(ct.TARGET) == len([c for c in ct.TARGET if c.kind is not ct.Kind.CONSTRUCTION])

    def test_guardian_matches_the_registry(self):
        """R8 implemented: G7 is the simulated loss rule (= D2), G17 merged into it, G18 checks the stamps."""
        from dh.agents import guardian
        assert "G17" not in guardian.RULES and "G18" in guardian.RULES and "simulated" in guardian.RULES["G7"]


class TestTechnical:
    def test_risk_imports_only_allowed_modules(self):
        """dh.risk never imports the Portfolio, Guardian, checks or LLM agents (they will import it): no cycle."""
        bad = []
        for f in RISK.glob("*.py"):
            for node in ast.walk(ast.parse(f.read_text())):
                if isinstance(node, ast.ImportFrom) and node.level:
                    if node.level == 1:      # inside dh.risk
                        continue
                    full = ["dh." + node.module] if node.module else ["dh." + a.name for a in node.names]
                    bad += [(f.name, m) for m in full if node.level != 2 or m not in ALLOWED]
                elif isinstance(node, (ast.Import, ast.ImportFrom)) and not getattr(node, "level", 0):
                    names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
                    bad += [(f.name, n) for n in names if n and n.startswith("dh.") and n not in ALLOWED]
        assert bad == []

    def test_contracts_has_no_project_import(self):
        tree = ast.parse((RISK / "contracts.py").read_text())
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level]
