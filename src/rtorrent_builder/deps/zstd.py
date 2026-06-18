from ._cmake import CMakeBuilder


class ZstdBuilder(CMakeBuilder):
    def cmake_args(self) -> list[str]:
        return [
            "-DZSTD_BUILD_PROGRAMS=OFF",
            "-DZSTD_BUILD_TESTS=OFF",
            "-DZSTD_BUILD_CONTRIB=OFF",
            "-DZSTD_BUILD_SHARED=OFF",
        ]

    def build(self) -> None:
        self.src_dir = self.src_dir / "build" / "cmake"
        super().build()
