# morphe-patches skill

Use when authoring, editing, or debugging patches in this project.

## Project facts
- Library: morphe-patcher 1.7.0
- Target app: `com.valvesoftware.steamlinkvr` 2.0.22 (Steam Link)
- Kotlin source root: `patches/src/main/kotlin/app/template/patches/steamlink/`
- Resources root: `patches/src/main/resources/steamlink/`

## Patch type selection

| Need | Use |
|------|-----|
| Copy/replace raw APK file (lib, assets, .so) | `rawResourcePatch {}` |
| Edit AndroidManifest.xml or other XML | `resourcePatch {}` |
| Merge a DEX extension into the app | `bytecodePatch {}` + `extendWith(...)` |

## Patch structure template

```kotlin
@Suppress("unused")
val myPatch = bytecodePatch(          // or rawResourcePatch / resourcePatch
    name = "Human readable name",
    description = "What it does.",
    default = true,
) {
    compatibleWith(COMPATIBILITY_STEAM_LINK)   // always required
    dependsOn(someOtherPatch)                  // if ordering matters

    extendWith("extensions/extension.mpe")     // bytecodePatch only, when needed

    execute {
        // patch logic here
        // rawResourcePatch: get("lib/arm64-v8a/libfoo.so").writeBytes(...)
        // bytecodePatch:    (no fingerprint injection — see FORBIDDEN below)
    }

    finalize {
        // runs after APK rebuild; use for XML/manifest edits via document(...)
    }
}
```

## Extension DEX (smali)

- Sources: `patches/src/main/resources/steamlink/androidxr/smali/`
- Built by `assembleExtension` Gradle task
- Output: `build/generated/extension-resources/extensions/extension.mpe`
- Delete cached `.mpe` before rebuilding: `Remove-Item patches/build/generated/extension-resources/extensions/extension.mpe`
- **Smali API level: `-a 33`** — never use 35 or higher

### Why not `-a 35`?
API 35 makes smali emit DEX format 040/041 (multi-DEX container). morphe-patcher 1.7.0's
bundled dexlib2 cannot parse container-format headers and crashes:
```
Caused by: com.android.tools.smali.dexlib2.util.DexUtil$InvalidFile: Unexpected container offset in header
```
API 33 → DEX 039, no container, fully compatible.

## FORBIDDEN patterns

### Fingerprint-based bytecode injection
Do **not** define `Fingerprint` objects or call `addInstructions(index, "smali string")`.
The InlineSmaliCompiler in morphe-patcher 1.7.0 crashes with:
```
Caused by: java.util.NoSuchElementException: Collection is empty.
    at app.morphe.patcher.util.smali.InlineSmaliCompiler$Companion.compile
```
steamlinkvr does not need runtime bytecode injection — use manifest/resource/binary patches instead.

## Constants
```kotlin
// shared/Constants.kt
val COMPATIBILITY_STEAM_LINK = Compatibility(
    name = "Steam Link",
    packageName = "com.valvesoftware.steamlinkvr",
    apkFileType = ApkFileType.APK,
    targets = listOf(AppTarget(version = "2.0.22"), AppTarget(version = null, isExperimental = true))
)
```

## Helpers available
- `loadResource(name: String): ByteArray` — loads from `/steamlink/androidxr/` classpath resources
- `BinaryPatchHelper.findUniqueAndReplace(bytes, search, replace)` — AArch64 .so patching
- `BinaryPatchHelper.vaddrToFileOffset(...)` — virtual address → file offset in ELF

## Build commands
```powershell
.\gradlew.bat build              # full build
.\gradlew.bat assembleExtension  # rebuild extension DEX only
.\gradlew.bat generatePatchesList # regenerate patches-list.json
```
