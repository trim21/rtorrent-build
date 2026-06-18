from ._cmake import CMakeBuilder


class ZlibBuilder(CMakeBuilder):
    default_deps: list[str] = []

    def cmake_args(self) -> list[str]:
        return ["-DZLIB_COMPAT=ON"]
