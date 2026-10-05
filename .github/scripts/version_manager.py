import argparse
import datetime
import glob
import json
import os
import re
import subprocess


def find_manifest():
    matches = glob.glob("custom_components/*/manifest.json")
    return matches[0] if matches else None


MANIFEST_FILE = find_manifest()


def get_current_version(manifest_path=None):
    if manifest_path is None:
        manifest_path = MANIFEST_FILE
    try:
        tags = (
            subprocess.check_output(["git", "tag"], stderr=subprocess.DEVNULL)
            .decode()
            .splitlines()
        )
        v_tags = []
        for tag in tags:
            tag = tag.strip()
            match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:(b)(\d+)|(-dev)(\d+))?$", tag)
            if match:
                y, m, p, bp, bn, dp, dn = match.groups()
                v_tags.append(
                    {
                        "tag": tag,
                        "key": (
                            int(y),
                            int(m),
                            int(p),
                            (1 if bp else (0 if dp else 2)),
                            (int(bn) if bp else (int(dn) if dp else 0)),
                        ),
                    }
                )
        if v_tags:
            return sorted(v_tags, key=lambda x: x["key"], reverse=True)[0]["tag"]
    except Exception:
        pass
    if manifest_path and os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f).get("version", "1.0.0")
    return "1.0.0"


def write_version(v, manifest_path=None):
    if manifest_path is None:
        manifest_path = MANIFEST_FILE
    if manifest_path and os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        data["version"] = v
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")


def parse_semver(v):
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:(b|-dev|-nightly)(\d+))?$", v)
    if not match:
        return 1, 0, 0, None, 0
    maj, min_, pat, pre_type, pre_num = match.groups()
    return (
        int(maj),
        int(min_),
        int(pat),
        pre_type,
        int(pre_num) if pre_num else 0,
    )


def bump(
    current_version,
    release_type="patch",
    bump_level="patch",
    version_override=None,
):
    if version_override and version_override.strip():
        return version_override.strip().lstrip("v")

    maj, min_, pat, pre_type, pre_num = parse_semver(current_version)

    if release_type == "stable":
        if pre_type is not None:
            return f"{maj}.{min_}.{pat}"
        if bump_level == "major":
            return f"{maj + 1}.0.0"
        if bump_level == "minor":
            return f"{maj}.{min_ + 1}.0"
        return f"{maj}.{min_}.{pat + 1}"

    if release_type == "beta":
        if pre_type == "b":
            return f"{maj}.{min_}.{pat}b{pre_num + 1}"
        if pre_type is not None:
            return f"{maj}.{min_}.{pat}b1"
        if bump_level == "major":
            return f"{maj + 1}.0.0b1"
        if bump_level == "minor":
            return f"{maj}.{min_ + 1}.0b1"
        return f"{maj}.{min_}.{pat + 1}b1"

    if release_type == "nightly":
        today = datetime.datetime.now().strftime("%Y%m%d")
        return f"{maj}.{min_}.{pat}-nightly{today}"

    if release_type == "dev":
        if pre_type == "-dev":
            return f"{maj}.{min_}.{pat}-dev{pre_num + 1}"
        return f"{maj}.{min_}.{pat + 1}-dev0"

    return current_version


def main():
    parser = argparse.ArgumentParser(description="Manage project versions")
    subparsers = parser.add_subparsers(dest="command")

    get_parser = subparsers.add_parser("get", help="Get current version")
    get_parser.add_argument("--manifest", help="Path to manifest.json")

    bump_parser = subparsers.add_parser("bump", help="Bump version")
    bump_parser.add_argument(
        "--type",
        choices=["stable", "beta", "nightly", "dev"],
        default="patch",
        help="Release type",
    )
    bump_parser.add_argument(
        "--level",
        choices=["major", "minor", "patch"],
        default="patch",
        help="Bump level",
    )
    bump_parser.add_argument("--override", help="Explicit version override")
    bump_parser.add_argument("--manifest", help="Path to manifest.json")
    bump_parser.add_argument(
        "--no-write", action="store_true", help="Do not write to manifest"
    )

    args = parser.parse_args()

    manifest_path = args.manifest or find_manifest()

    if args.command == "get":
        print(get_current_version(manifest_path))
    elif args.command == "bump":
        curr = get_current_version(manifest_path)
        new_v = bump(
            curr,
            release_type=args.type,
            bump_level=args.level,
            version_override=args.override,
        )
        if not args.no_write:
            write_version(new_v, manifest_path)
        print(new_v)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
