from ._cmake import CMakeBuilder


class QtToolsBuilder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
        return [
            "-DCMAKE_DISABLE_FIND_PACKAGE_Clang=ON",
            "-DFEATURE_assistant=OFF",
            "-DFEATURE_designer=OFF",
            "-DFEATURE_kmap2qmap=OFF",
            "-DFEATURE_pixeltool=OFF",
            "-DFEATURE_qdbus=OFF",
            "-DFEATURE_qev=OFF",
            "-DFEATURE_qmlls=OFF",
            "-DFEATURE_qtattributionsscanner=OFF",
            "-DFEATURE_qtdiag=OFF",
            "-DFEATURE_qtplugininfo=OFF",
        ]
