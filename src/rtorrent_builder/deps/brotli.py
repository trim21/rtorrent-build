from ._cmake import CMakeBuilder


class BrotliBuilder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
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
                content = pc_path.read_text()
                assert self._REQUIRES_PRIVATE in content, (
                    f"{pc}: expected '{self._REQUIRES_PRIVATE}'"
                )
                pc_path.write_text(
                    content.replace(self._REQUIRES_PRIVATE, "Requires: libbrotlicommon")
                )
                print(f"  Patched {pc}: Requires.private -> Requires")
