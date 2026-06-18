from ..utils import replace_in_file
from ._cmake import CMakeBuilder


class BrotliBuilder(CMakeBuilder):
    default_deps: list[str] = []

    def cmake_args(self) -> list[str]:
        return [
            "-DBROTLI_BUILD_TOOLS=OFF",
            "-DBROTLI_DISABLE_TESTS=ON",
        ]

    _REQUIRES_PRIVATE = "Requires.private: libbrotlicommon"

    def build(self) -> None:
        super().build()
        for pc in ["libbrotlidec.pc", "libbrotlienc.pc"]:
            pc_path = self.tc.install_prefix / "lib" / "pkgconfig" / pc
            if pc_path.exists():
                replace_in_file(pc_path, self._REQUIRES_PRIVATE, "Requires: libbrotlicommon")
                print(f"  Patched {pc}: Requires.private -> Requires")
