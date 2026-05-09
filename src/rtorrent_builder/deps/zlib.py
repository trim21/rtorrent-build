from ._cmake import CMakeBuilder


class ZlibBuilder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
        return ["-DZLIB_COMPAT=ON"]
