import argparse
import pathlib
import typing
import json
from watchfiles import watch


class CacheDir:
    def __init__(self, name: str) -> None:
        self.name = name
        # CacheDir | str
        self.sub: list[typing.Any] = []

    def __repr__(self) -> str:
        return str(self.__dict__)


def as_cache_dir(dct: dict[str, typing.Any]) -> CacheDir:
    cache_dir = CacheDir("")
    if "name" in dct:
        cache_dir.name = dct["name"]
    else:
        raise ValueError("miss name")
    if "sub" in dct:
        for sub in dct["sub"]:
            if isinstance(sub, str):
                cache_dir.sub.append(sub)
            elif isinstance(sub, dict):
                cache_dir.sub.append(as_cache_dir(sub))
            else:
                raise TypeError("CacheDir sub type not CacheDir | str")
    else:
        raise ValueError("miss sub")
    return cache_dir


def as_cache_dirs(dcts: list[dict[str, typing.Any]]) -> list[CacheDir]:
    cache_dirs: list[CacheDir] = []
    for dct in dcts:
        cache_dirs.append(as_cache_dir(dct))
    return cache_dirs


class Config:
    def __init__(self, dct: dict[str, typing.Any]) -> None:
        if "path_maps" in dct:
            self.path_maps: list[dict[str, str]] = dct["path_maps"]
        else:
            raise ValueError("miss path_maps")
        if "include" in dct:
            self.include: list[str] = dct["include"]
        else:
            raise ValueError("miss include")
        if "cache" in dct:
            self.cache: bool = dct["cache"]
        else:
            raise ValueError("miss cache")


def cache_dir_to_strs(cache_dir: CacheDir, parent: pathlib.Path) -> list[str]:
    strs: list[str] = []
    for item in cache_dir.sub:
        if isinstance(item, str):
            strs.append(str(parent.joinpath(item)))
        elif isinstance(item, CacheDir):
            strs.extend(cache_dir_to_strs(item, parent.joinpath(item.name)))
        else:
            raise TypeError("CacheDir sub type not CacheDir | str")
    return strs


def cache_dirs_to_strs(cache_dirs: list[CacheDir]) -> list[str]:
    strs: list[str] = []
    for cache_dir in cache_dirs:
        strs.extend(cache_dir_to_strs(cache_dir, pathlib.Path(cache_dir.name)))
    return strs


def cache_dir_insert_path(cache_dir: CacheDir, path: list[str]) -> None:
    if path.__len__() == 1:
        file_name = path.pop(0)
        if file_name in cache_dir.sub:
            raise ValueError("cached file {fileName} duplicate link")
        else:
            cache_dir.sub.append(file_name)
    elif path.__len__() > 1:
        dir_name = path.pop(0)
        next_cache_dir: CacheDir | None = None
        for cache_dir_sub in cache_dir.sub:
            if isinstance(cache_dir_sub, CacheDir) and dir_name == cache_dir_sub.name:
                next_cache_dir = cache_dir_sub
        if not next_cache_dir:
            next_cache_dir = CacheDir(dir_name)
            cache_dir.sub.append(next_cache_dir)
        cache_dir_insert_path(next_cache_dir, path)
    else:
        raise ValueError("path len < 1")


def cache_dirs_insert_path(
    cache_dirs: list[CacheDir], path: pathlib.Path, src_dir: pathlib.Path
) -> None:
    root_cache_dir: CacheDir | None = None
    for cache_dir in cache_dirs:
        if str(src_dir.resolve()) == cache_dir.name:
            root_cache_dir = cache_dir
    if not root_cache_dir:
        root_cache_dir = CacheDir(str(src_dir.resolve()))
        cache_dirs.append(root_cache_dir)
    cache_dir_insert_path(
        root_cache_dir, str(str(path.relative_to(src_dir))).split("/")
    )


def hit_cache(file: pathlib.Path, caches: list[str]) -> bool:
    return str(file.resolve()) in caches


def allow_suffiex(file_name: str, suffixes: list[str]) -> bool:
    for suffix in suffixes:
        if file_name.endswith(suffix):
            return True
    return False


def link_directory(
    config: Config,
    caches: list[str],
    src_dir: pathlib.Path,
    dst_dir: pathlib.Path,
    sub: bool = True,
) -> list[pathlib.Path]:
    if not src_dir.exists():
        raise FileNotFoundError(src_dir)
    if not src_dir.is_dir():
        raise NotADirectoryError(src_dir)

    if sub:
        dst_dir = dst_dir.joinpath(src_dir.name)
    if not dst_dir.exists():
        dst_dir.mkdir(parents=True)

    new_link_files: list[pathlib.Path] = []
    for src_sub in src_dir.iterdir():
        if src_sub.is_file():
            if allow_suffiex(src_sub.name, config.include) and (
                not config.cache or (config.cache and not hit_cache(src_sub, caches))
            ):
                dst_path = dst_dir.joinpath(src_sub.name)
                if dst_path.exists():
                    dst_path.unlink()
                dst_path.symlink_to(src_sub)
                new_link_files.append(src_sub)
                print(f"+ link {str(src_sub)}")
            else:
                print(f". miss {str(src_sub)}")
        else:
            new_link_files.extend(link_directory(config, caches, src_sub, dst_dir))
    return new_link_files


def link(config_str: str, cache_str: str | None) -> None:
    config_path: pathlib.Path = pathlib.Path(config_str)
    if not config_path.exists():
        raise FileNotFoundError(str(config_path))

    config: Config
    with config_path.open() as f:
        config = Config(json.loads(f.read()))

    cache_dirs: list[CacheDir] = []
    cache_path: pathlib.Path
    if config.cache:
        if not cache_str:
            raise ValueError("miss cache")
        cache_path = pathlib.Path(cache_str)
        if not cache_path.exists():
            raise FileNotFoundError(str(cache_path))
        with cache_path.open() as f:
            cache_dirs = as_cache_dirs(json.loads(f.read()))

    caches = cache_dirs_to_strs(cache_dirs)
    for path_map in config.path_maps:
        src_path = pathlib.Path(path_map["src"])
        dst_dir = pathlib.Path(path_map["dst"])
        print(f"\nlink {str(src_path)} > {str(dst_dir)}")
        new_link_files = link_directory(
            config,
            caches,
            src_path,
            dst_dir,
            False,
        )
        for new_link_path in new_link_files:
            cache_dirs_insert_path(cache_dirs, new_link_path, src_path)

    if config.cache:
        with cache_path.open("w") as f:
            f.write(json.dumps(cache_dirs, default=vars, sort_keys=True, indent=4))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bt/Pt symbolic link tool")
    parser.add_argument("config", help="config json file")
    parser.add_argument("cache", help="cache json file")
    parser.add_argument("flag", help="watch file")
    args = parser.parse_args()

    config_str: str = args.config
    cache_str: str | None = args.cache
    flag_str: str | None = args.flag

    if flag_str:
        for changes in watch(flag_str):
            link(config_str, cache_str)

    link(config_str, cache_str)
