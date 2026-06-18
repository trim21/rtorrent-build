from ._cmake import CMakeBuilder


class Nghttp2Builder(CMakeBuilder):
    def cmake_args(self) -> list[str]:
        return [
            "-DENABLE_LIB_ONLY=ON",
            "-DBUILD_STATIC_LIBS=ON",
            f"-DZLIB_ROOT={self.tc.dep_prefix('zlib')}",
        ]
