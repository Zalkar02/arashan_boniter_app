"""Формирует manifest.json для релиза.

python tools/make_manifest.py --version 1.3.0 --min-version 1.0.0 --base-url https://... \
    --notes "Текст" --windows dist/Setup.exe --linux dist/App.AppImage > dist/manifest.json
"""
import argparse
import hashlib
import json
import os


def describe(path, base_url):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    name = os.path.basename(path)
    return {"url": f"{base_url}/{name}", "sha256": digest.hexdigest(), "size": os.path.getsize(path)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--min-version", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument("--windows")
    parser.add_argument("--linux")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    platforms = {}
    if args.windows:
        platforms["windows"] = describe(args.windows, base_url)
    if args.linux:
        platforms["linux"] = describe(args.linux, base_url)
    manifest = {
        "version": args.version,
        "min_supported_version": args.min_version,
        "notes": args.notes,
        "platforms": platforms,
    }
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
