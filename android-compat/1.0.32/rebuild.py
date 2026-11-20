#!/usr/bin/env python3
"""Rebuild the protocol-3 compatibility artifact from checksum-pinned Maven inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

VERSION = "1.0.32-aca.1"
SOURCE = "com/github/copilot/CopilotClient.java"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--work-dir", type=Path, default=Path("target") / "sdk-protocol-build")
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    work = args.work_dir.resolve()
    cache = (args.cache_dir or work / "inputs").resolve()
    cache.mkdir(parents=True, exist_ok=True)
    inputs = json.loads((here / "inputs.json").read_text(encoding="utf-8"))
    for item in inputs:
        path = cache / item["file"]
        if not path.exists():
            with urllib.request.urlopen("https://repo1.maven.org/maven2/" + item["path"], timeout=60) as response:
                path.write_bytes(response.read())
        if sha256(path) != item["sha256"]:
            raise RuntimeError("Input checksum mismatch: " + item["file"])

    source_dir = work / "src"
    classes = work / "classes"
    for directory in (source_dir, classes):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)
    source = source_dir / SOURCE
    source.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(cache / "copilot-sdk-java-1.0.32-sources.jar") as archive:
        source.write_bytes(archive.read(SOURCE))
    patch = (here / "protocol-3.patch").read_text(encoding="utf-8").encode("utf-8")
    subprocess.run(["git", "apply", "--unsafe-paths", "--directory", str(source_dir), "-"],
                   input=patch, check=True)
    java_home = os.environ.get("JAVA_HOME")
    javac = str(Path(java_home) / "bin" / ("javac.exe" if os.name == "nt" else "javac")) if java_home else "javac"
    classpath = os.pathsep.join(str(cache / item["file"]) for item in inputs
                               if item["file"].endswith(".jar") and not item["file"].endswith("-sources.jar"))
    subprocess.run([javac, "--release", "17", "-encoding", "UTF-8", "-g", "-parameters", "-proc:none",
                    "-cp", classpath, "-d", str(classes), str(source)], check=True)

    with zipfile.ZipFile(cache / "copilot-sdk-java-1.0.32.jar") as archive:
        entries = {item.filename: archive.read(item) for item in archive.infolist()}
    if any(name.upper().endswith((".RSA", ".DSA", ".SF")) for name in entries):
        raise RuntimeError("Unexpected signed upstream artifact")
    changed = {path.relative_to(classes).as_posix(): path.read_bytes() for path in classes.rglob("*.class")}
    if not changed or any(not name.startswith("com/github/copilot/CopilotClient") for name in changed):
        raise RuntimeError("Unexpected compiler output")
    original_enum = entries["com/github/copilot/SdkProtocolVersion.class"]
    entries.update(changed)
    if entries["com/github/copilot/SdkProtocolVersion.class"] != original_enum:
        raise RuntimeError("SDK-reported protocol version was changed")
    pom = (cache / "copilot-sdk-java-1.0.32.pom").read_text(encoding="utf-8")
    if pom.count("<version>1.0.32</version>") != 1:
        raise RuntimeError("Unexpected upstream POM")
    pom = pom.replace("<version>1.0.32</version>", "<version>" + VERSION + "</version>")
    entries["META-INF/maven/com.github/copilot-sdk-java/pom.xml"] = pom.encode("utf-8")
    properties = "META-INF/maven/com.github/copilot-sdk-java/pom.properties"
    if properties in entries:
        entries[properties] = entries[properties].replace(b"version=1.0.32", ("version=" + VERSION).encode())
    entries["META-INF/LICENSE.android-compat"] = (here / "LICENSE").read_text(encoding="utf-8").encode("utf-8")
    entries["META-INF/ANDROID-COMPAT.txt"] = (
        "Protocol-3 compatibility patch for com.github:copilot-sdk-java:1.0.32\n"
        "Accept server protocol >= 3 without changing SdkProtocolVersion or request payloads.\n"
        "Source patch SHA-256: " + hashlib.sha256(patch).hexdigest() + "\n"
    ).encode()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    jar = output / ("copilot-sdk-java-" + VERSION + ".jar")
    def order(name):
        return (0 if name == "META-INF/" else 1 if name == "META-INF/MANIFEST.MF" else 2, name)
    with zipfile.ZipFile(jar, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries, key=order):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o40755 if name.endswith("/") else 0o100644) << 16
            archive.writestr(info, entries[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    pom_path = output / ("copilot-sdk-java-" + VERSION + ".pom")
    pom_path.write_bytes(pom.encode("utf-8"))
    for path in (jar, pom_path):
        digest = sha256(path)
        path.with_suffix(path.suffix + ".sha256").write_text(digest + "\n", encoding="ascii")
        print(path.name + " SHA-256 " + digest)


if __name__ == "__main__":
    main()
