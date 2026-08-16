from ..utils import conditional_args
from ._cmake import CMakeBuilder


class CurlBuilder(CMakeBuilder):
    features = {"idn2": ["libidn2"]}
    default_deps: list[str] = ["zlib", "openssl", "brotli", "cares", "zstd", "nghttp2"]

    def cmake_args(self) -> list[str]:
        tc = self.tc
        return conditional_args({
            "-DCURL_USE_GTEST=OFF": True,
            "-DBUILD_CURL_EXE=OFF": True,
            "-DCURL_USE_OPENSSL=ON": True,
            f"-DOPENSSL_ROOT_DIR={tc.dep_prefix('openssl')}": True,
            f"-DZLIB_ROOT={tc.dep_prefix('zlib')}": True,
            "-DCURL_USE_LIBPSL=OFF": True,
            "-DCURL_USE_LIBSSH2=OFF": True,
            "-DCURL_DISABLE_LDAP=ON": True,
            "-DUSE_NGHTTP2=ON": True,
            f"-DNGHTTP2_ROOT_DIR={tc.dep_prefix('nghttp2')}": True,
            "-DCURL_BROTLI=ON": True,
            "-DCURL_ZSTD=ON": True,
            "-DCURL_USE_CARES=ON": True,
            f"-DCARES_ROOT_DIR={tc.dep_prefix('cares')}": True,
            "-DUSE_LIBIDN2=ON": "idn2" in self.lib.features,
            f"-DIDN2_ROOT_DIR={tc.dep_prefix('libidn2')}": "idn2" in self.lib.features,
        })
