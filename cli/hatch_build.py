"""Bundle the shared operating model from a checkout or an extracted sdist."""

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        root = Path(self.root)
        for source, destination in (
            ("skills/the-loop", "skills/the-loop"),
            ("skills/writing", "skills/writing"),
            ("commands", "commands"),
            ("hooks", "hooks"),
        ):
            checkout = root.parent / source
            target = f"the_loop/resources/{destination}"
            if checkout.is_dir():
                build_data.setdefault("force_include", {})[str(checkout)] = target
            elif not (root / target).is_dir():
                raise FileNotFoundError(
                    f"the-loop's required Codex resource is missing: {source}"
                )
