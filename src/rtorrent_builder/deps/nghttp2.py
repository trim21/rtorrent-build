from ._cmake import CMakeBuilder


class Nghttp2Builder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
        return [
            "-DBUILD_SHARED_LIBS=OFF",
            "-DENABLE_LIB_ONLY=ON",
            "-DBUILD_TESTING=OFF",
        ]
