from ._cmake import CMakeBuilder


class Nghttp2Builder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
        static_flag = "-DBUILD_STATIC_LIBS=OFF" if self.tc.shared_deps else "-DBUILD_STATIC_LIBS=ON"
        return [
            "-DENABLE_LIB_ONLY=ON",
            static_flag,
            f"-DZLIB_ROOT={self.tc.dep_prefix('zlib')}",
        ]
