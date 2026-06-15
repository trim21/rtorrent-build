from ._cmake import CMakeBuilder


class ZstdBuilder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
        flags = [
            "-DZSTD_BUILD_PROGRAMS=OFF",
            "-DZSTD_BUILD_TESTS=OFF",
            "-DZSTD_BUILD_CONTRIB=OFF",
        ]
        if self.tc.shared_deps:
            flags.append("-DZSTD_BUILD_SHARED=ON")
            flags.append("-DZSTD_BUILD_STATIC=OFF")
        else:
            flags.append("-DZSTD_BUILD_SHARED=OFF")
        return flags

    def build(self) -> None:
        self.src_dir = self.src_dir / "build" / "cmake"
        super().build()
