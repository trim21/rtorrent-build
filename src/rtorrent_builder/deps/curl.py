from ._cmake import CMakeBuilder


class CurlBuilder(CMakeBuilder):
    def cmake_args(self) -> list[str]:
        tc = self.tc
        return [
            "-DCURL_USE_GTEST=OFF",
            "-DBUILD_CURL_EXE=OFF",
            "-DCURL_USE_OPENSSL=ON",
            f"-DOPENSSL_ROOT_DIR={tc.dep_prefix('openssl')}",
            f"-DZLIB_ROOT={tc.dep_prefix('zlib')}",
            "-DCURL_USE_LIBPSL=OFF",
            "-DCURL_USE_LIBSSH2=OFF",
            "-DUSE_LIBIDN2=ON",
            f"-DIDN2_ROOT_DIR={tc.dep_prefix('libidn2')}",
            "-DCURL_DISABLE_LDAP=ON",
            "-DUSE_NGHTTP2=ON",
            f"-DNGHTTP2_ROOT_DIR={tc.dep_prefix('nghttp2')}",
            "-DCURL_BROTLI=ON",
            "-DCURL_ZSTD=ON",
            "-DCURL_USE_CARES=ON",
            f"-DCARES_ROOT_DIR={tc.dep_prefix('cares')}",
        ]
