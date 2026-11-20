# Android protocol-3 compatibility build

This branch maintains a narrow patch to published
`com.github:copilot-sdk-java:1.0.32` as `1.0.32-aca.1`.
It does not migrate packages or adopt protocol-4 session payloads.

The published client's private `verifyProtocolVersion` method runs for every
transport; its public options expose no protocol-check override. The patch
accepts server protocol versions **3 or newer**, rejects missing/older versions,
and writes one INFO compatibility notice per newer-server handshake.
`SdkProtocolVersion.LATEST` stays **3**. The original `connect` and fallback
`ping` requests do **not** send a `protocolVersion` field; neither request is
changed. Capability negotiation and protocol-3 session shapes stay unchanged.

## Rebuild

Requirements: Python 3, Git, and JDK 17 (`JAVA_HOME`). No Maven installation,
reflection, Gradle cache edits or upstream package migration is required.
From a project directory:

```powershell
python .\android-compat\1.0.32\rebuild.py --output-dir .\target\patched-sdk
```

All downloads are public Maven Central inputs pinned by SHA-256 in `inputs.json`.
The script extracts only the original `CopilotClient.java`, applies
`protocol-3.patch`, and recompiles that class and its nested classes against the
unchanged upstream artifact. All other class files, including
`SdkProtocolVersion.class`, are byte-for-byte unchanged. Archive entry order,
timestamps and permissions are normalized, and output checksums are emitted.
Generated files stay beneath the caller's `target` directory.

The original repository has become a documentation-site mirror; using the
published sources JAR avoids accidentally building its migrated main branch.
The source and artifact hashes identify the exact upstream baseline independently
of mutable branches. Preserve this module and its license with redistributions.

Android Coding Agent checks the resulting JAR and POM into its local Maven
repository and pins the same version in both `app` and `learning-core`.
The application repository contains focused real TCP handshake tests for current,
newer, missing and older server versions, including legacy `ping` fallback.
